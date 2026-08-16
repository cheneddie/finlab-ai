"""Tiny order-preserving Parquet reader for this MTX dataset.

Supports the source file's flat schema, Snappy compression, DataPageV1,
PLAIN/dictionary values, and RLE/bit-packed dictionary indices. It never sorts.
"""
from __future__ import annotations
import ctypes, ctypes.util, struct
from pathlib import Path
from typing import Iterable
import numpy as np
from thrift.transport import TTransport
from thrift.protocol import TCompactProtocol
from thrift.Thrift import TType

INT64, DOUBLE, BYTE_ARRAY = 2, 5, 6
DATA_PAGE, DICT_PAGE = 0, 2
PLAIN, RLE_DICT = 0, 8
SNAPPY = 1


def _skip(p,t):
    if t==TType.BOOL:p.readBool()
    elif t==TType.BYTE:p.readByte()
    elif t==TType.I16:p.readI16()
    elif t==TType.I32:p.readI32()
    elif t==TType.I64:p.readI64()
    elif t==TType.DOUBLE:p.readDouble()
    elif t==TType.STRING:p.readBinary()
    elif t==TType.STRUCT:
        p.readStructBegin()
        while True:
            _,tt,_=p.readFieldBegin()
            if tt==TType.STOP:break
            _skip(p,tt);p.readFieldEnd()
        p.readStructEnd()
    elif t in (TType.LIST,TType.SET):
        et,n=(p.readListBegin() if t==TType.LIST else p.readSetBegin())
        for _ in range(n):_skip(p,et)
        p.readListEnd() if t==TType.LIST else p.readSetEnd()
    elif t==TType.MAP:
        kt,vt,n=p.readMapBegin()
        for _ in range(n):_skip(p,kt);_skip(p,vt)
        p.readMapEnd()


def _struct(p, handlers):
    out={};p.readStructBegin()
    while True:
        _,t,f=p.readFieldBegin()
        if t==TType.STOP:break
        fn=handlers.get(f)
        if fn: out.update(fn(p,t))
        else:_skip(p,t)
        p.readFieldEnd()
    p.readStructEnd();return out


def _schema_el(p):
    return _struct(p,{1:lambda p,t:{'type':p.readI32()},4:lambda p,t:{'name':p.readBinary().decode()},5:lambda p,t:{'num_children':p.readI32()}})

def _colmeta(p):
    def path(p,t):
        _,n=p.readListBegin();a=[p.readBinary().decode() for _ in range(n)];p.readListEnd();return {'path':a}
    return _struct(p,{1:lambda p,t:{'type':p.readI32()},3:path,4:lambda p,t:{'codec':p.readI32()},5:lambda p,t:{'num_values':p.readI64()},7:lambda p,t:{'total_compressed_size':p.readI64()},9:lambda p,t:{'data_page_offset':p.readI64()},11:lambda p,t:{'dictionary_page_offset':p.readI64()}})

def _chunk(p):
    return _struct(p,{2:lambda p,t:{'file_offset':p.readI64()},3:lambda p,t:{'meta_data':_colmeta(p)}})

def _rowgroup(p):
    def cols(p,t):
        _,n=p.readListBegin();a=[_chunk(p) for _ in range(n)];p.readListEnd();return {'columns':a}
    return _struct(p,{1:cols,3:lambda p,t:{'num_rows':p.readI64()}})

def _metadata(raw):
    p=TCompactProtocol.TCompactProtocol(TTransport.TMemoryBuffer(raw))
    def schema(p,t):
        _,n=p.readListBegin();a=[_schema_el(p) for _ in range(n)];p.readListEnd();return {'schema':a}
    def rgs(p,t):
        _,n=p.readListBegin();a=[_rowgroup(p) for _ in range(n)];p.readListEnd();return {'row_groups':a}
    return _struct(p,{2:schema,3:lambda p,t:{'num_rows':p.readI64()},4:rgs})


def _data_header(p):
    return _struct(p,{1:lambda p,t:{'num_values':p.readI32()},2:lambda p,t:{'encoding':p.readI32()}})

def _dict_header(p):
    return _struct(p,{1:lambda p,t:{'num_values':p.readI32()},2:lambda p,t:{'encoding':p.readI32()}})

def _page_header(fh):
    p=TCompactProtocol.TCompactProtocol(TTransport.TFileObjectTransport(fh))
    return _struct(p,{1:lambda p,t:{'type':p.readI32()},2:lambda p,t:{'uncompressed_page_size':p.readI32()},3:lambda p,t:{'compressed_page_size':p.readI32()},5:lambda p,t:{'data':_data_header(p)},7:lambda p,t:{'dict':_dict_header(p)}})


class _Snappy:
    def __init__(self):
        self.lib=ctypes.CDLL(ctypes.util.find_library('snappy'))
        self.lib.snappy_uncompressed_length.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)]
        self.lib.snappy_uncompress.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.POINTER(ctypes.c_size_t)]
    def decompress(self,b,expected):
        src=ctypes.create_string_buffer(b);n=ctypes.c_size_t()
        if self.lib.snappy_uncompressed_length(src,len(b),ctypes.byref(n)):raise RuntimeError('snappy length error')
        if n.value!=expected:raise RuntimeError('snappy size mismatch')
        dst=ctypes.create_string_buffer(n.value);dn=ctypes.c_size_t(n.value)
        if self.lib.snappy_uncompress(src,len(b),dst,ctypes.byref(dn)):raise RuntimeError('snappy error')
        return dst.raw[:dn.value]
_SNAPPY=_Snappy()


def _varint(b,pos):
    v=s=0
    while True:
        x=b[pos];pos+=1;v|=(x&127)<<s
        if not x&128:return v,pos
        s+=7

def _hybrid(data,bw,n):
    mv=memoryview(data);pos=0;out=[];made=0;bytew=(bw+7)//8
    while made<n:
        h,pos=_varint(mv,pos)
        if h&1:
            groups=h>>1;cnt=groups*8;nb=groups*bw
            if bw:
                a=np.frombuffer(mv[pos:pos+nb],dtype=np.uint8);bits=np.unpackbits(a,bitorder='little')[:cnt*bw]
                vals=bits.reshape(cnt,bw).astype(np.int64)@(1<<np.arange(bw,dtype=np.int64))
            else:vals=np.zeros(cnt,dtype=np.int64)
            pos+=nb
        else:
            cnt=h>>1;val=int.from_bytes(mv[pos:pos+bytew],'little') if bytew else 0;pos+=bytew
            vals=np.full(cnt,val,dtype=np.int64)
        take=min(cnt,n-made);out.append(vals[:take]);made+=take
    return np.concatenate(out) if len(out)>1 else out[0]


def _plain(raw,typ,n):
    if typ==INT64:return np.frombuffer(raw,dtype='<i8',count=n).copy()
    if typ==DOUBLE:return np.frombuffer(raw,dtype='<f8',count=n).copy()
    if typ==BYTE_ARRAY:
        out=np.empty(n,dtype=object);pos=0
        for i in range(n):
            z=struct.unpack_from('<I',raw,pos)[0];pos+=4;out[i]=raw[pos:pos+z].decode('utf-8','replace');pos+=z
        return out
    raise NotImplementedError(typ)


def _data_page(raw,h,dictionary,typ):
    n=h['num_values'];pos=0
    z=struct.unpack_from('<I',raw,pos)[0];pos+=4
    defs=_hybrid(raw[pos:pos+z],1,n);pos+=z
    if np.count_nonzero(defs)!=n:raise NotImplementedError('actual nulls unsupported')
    if h['encoding']==PLAIN:return _plain(raw[pos:],typ,n)
    if h['encoding']!=RLE_DICT or dictionary is None:raise NotImplementedError('encoding')
    bw=raw[pos];idx=_hybrid(raw[pos+1:],bw,n)
    return dictionary[idx]


class NativeParquetFile:
    def __init__(self,path):
        self.path=Path(path)
        with self.path.open('rb') as f:
            f.seek(-8,2);tail=f.read(8);mlen=struct.unpack('<I',tail[:4])[0]
            if tail[4:]!=b'PAR1':raise ValueError('not parquet')
            f.seek(-(8+mlen),2);self.metadata=_metadata(f.read(mlen))
        self.num_rows=int(self.metadata['num_rows']);self.row_groups=self.metadata['row_groups']
        self.columns=[x['name'] for x in self.metadata['schema'][1:]]
    def _info(self,rg,name):
        for c in self.row_groups[rg]['columns']:
            m=c['meta_data']
            if m['path']==[name]:return m
        raise KeyError(name)
    def read_column(self,rg,name):
        m=self._info(rg,name)
        if m['codec']!=SNAPPY:raise NotImplementedError('codec')
        start=m.get('dictionary_page_offset')
        if start is None:raise NotImplementedError('no dictionary offset')
        dictionary=None;parts=[];decoded=0
        with self.path.open('rb') as f:
            f.seek(start)
            while decoded<m['num_values']:
                h=_page_header(f);raw=_SNAPPY.decompress(f.read(h['compressed_page_size']),h['uncompressed_page_size'])
                if h['type']==DICT_PAGE:dictionary=_plain(raw,m['type'],h['dict']['num_values'])
                elif h['type']==DATA_PAGE:
                    a=_data_page(raw,h['data'],dictionary,m['type']);parts.append(a);decoded+=len(a)
                else:raise NotImplementedError('page type')
        out=np.concatenate(parts) if len(parts)>1 else parts[0]
        if len(out)!=m['num_values']:raise RuntimeError('decoded length mismatch')
        return out
    def read_row_group(self,rg,columns:Iterable[str]|None=None):
        names=list(columns or self.columns);out={n:self.read_column(rg,n) for n in names}
        if len({len(v) for v in out.values()})!=1:raise RuntimeError('column length mismatch')
        return out
