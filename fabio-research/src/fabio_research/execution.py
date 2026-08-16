from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

from .market import MTXDataset, SECOND_US


def _first_hit_r(path: np.ndarray, trade_dir: int, entry: float, stop: float, target: float, risk: float) -> tuple[float,str,int]:
    if path.size == 0 or risk <= 0:
        return np.nan,"invalid",-1
    pnl = trade_dir * (path - entry)
    stop_dist = abs(stop-entry)
    target_dist = abs(target-entry)
    hs=np.flatnonzero(pnl <= -stop_dist)
    ht=np.flatnonzero(pnl >= target_dist)
    is_=int(hs[0]) if hs.size else 10**18
    it=int(ht[0]) if ht.size else 10**18
    if it < is_:
        return float(target_dist/risk),"target",it
    if is_ < it:
        return -1.0,"stop",is_
    r=float(pnl[-1]/risk)
    r=float(np.clip(r,-1.0,target_dist/risk))
    return r,"horizon",len(path)-1


def _time_outside_ratio(t,p,t0,seconds,direction,boundary,initial):
    out=np.empty(seconds,float);out[:]=np.nan
    a=int(np.searchsorted(t,t0,side='left'));b=int(np.searchsorted(t,t0+seconds*SECOND_US,side='left'))
    if a<b:
        rel=((t[a:b]-t0)//SECOND_US).astype(int)
        for idx,r in zip(range(a,b),rel):
            if 0<=r<seconds: out[r]=p[idx]
    last=initial
    for i in range(seconds):
        if np.isnan(out[i]):out[i]=last
        else:last=out[i]
    return float(np.mean(direction*(out-boundary)>0))


def generate_candidates(events_csv:str|Path, parquet_path:str|Path, row_group_start:int=0, min_date:str|None=None)->pd.DataFrame:
    ev=pd.read_csv(events_csv);ev['trading_date']=ev['trading_date'].astype(str)
    by_date={d:g.copy() for d,g in ev.groupby('trading_date')}
    ds=MTXDataset(parquet_path);rows=[]
    fade_exc_fracs=[0.03,0.07];fade_reentry=[15,30,60];fade_buffers=[1.0,3.0]
    cont_holds=[30,60];cont_thresholds=[0.75,0.90];cont_bands=[0.10];cont_targets=[1.0,2.0]

    for day in ds.iter_front_month_day_sessions(row_group_start=row_group_start):
        d=day.trading_date.isoformat()
        if min_date and d < min_date: continue
        if d not in by_date: continue
        t=day.datetime_us;p=day.price.astype(float,copy=False);v=day.volume;seq=day.seq
        for _,e in by_date[d].iterrows():
            i=int(np.searchsorted(seq,int(e.event_seq),side='left'))
            if i>=len(seq) or int(seq[i])!=int(e.event_seq): continue
            t0=int(t[i]);direction=int(e.direction);boundary=float(e.boundary);poc=float(e.ref_poc);width=max(1.0,float(e.ref_width))
            end=int(np.searchsorted(t,t0+660*SECOND_US,side='right'))
            pp=p[i:end];tt=t[i:end];vv=v[i:end]
            if len(pp)<2:continue
            rel=(tt-t0)/SECOND_US;path_cache={}
            def fast_first_hit(j,trade_dir,entry,stop,target,risk):
                # j is event-relative; convert to absolute day index before reading future prices.
                gi=int(i+j)
                if gi not in path_cache:
                    horizon_end=int(np.searchsorted(t,t[gi]+600*SECOND_US,side='right'))
                    arr=p[gi:horizon_end].astype(float,copy=False)
                    path_cache[gi]=(arr,np.maximum.accumulate(arr),np.minimum.accumulate(arr))
                arr,cmax,cmin=path_cache[gi]
                if arr.size==0 or risk<=0:return np.nan,'invalid',-1
                INF=10**18
                if trade_dir>0:
                    it=int(np.searchsorted(cmax,target,'left')) if cmax[-1]>=target else INF
                    nm=-cmin;is_=int(np.searchsorted(nm,-stop,'left')) if cmin[-1]<=stop else INF
                else:
                    nm=-cmin;it=int(np.searchsorted(nm,-target,'left')) if cmin[-1]<=target else INF
                    is_=int(np.searchsorted(cmax,stop,'left')) if cmax[-1]>=stop else INF
                if it<is_:return float(abs(target-entry)/risk),'target',it
                if is_<it:return -1.0,'stop',is_
                return float(np.clip(trade_dir*(arr[-1]-entry)/risk,-1,abs(target-entry)/risk)),'horizon',len(arr)-1

            outside_move=direction*(pp-boundary)
            for exc_frac in fade_exc_fracs:
                need=max(1.0,exc_frac*width);reached=np.flatnonzero(outside_move>=need)
                if not reached.size:continue
                k0=int(reached[0]);re=np.flatnonzero((np.arange(len(pp))>k0)&(outside_move<=0))
                if not re.size:continue
                j=int(re[0]);resec=float(rel[j])
                for maxsec in fade_reentry:
                    if resec>maxsec:continue
                    entry=float(pp[j]);extreme=float(np.max(outside_move[:j+1]))
                    for buffer in fade_buffers:
                        stop=boundary+direction*(extreme+buffer);risk=float(direction*(stop-entry));reward=float(direction*(entry-poc))
                        if risk<=0 or reward<=0:continue
                        trade_dir=-direction
                        specs=[('1R',entry+trade_dir*risk,1.0),('2R',entry+trade_dir*2*risk,2.0),('POC',poc,reward/risk)]
                        for target_name,target,planned_rr in specs:
                            if planned_rr<=0:continue
                            r,outcome,_=fast_first_hit(j,trade_dir,entry,stop,target,risk)
                            rows.append({'trading_date':d,'event_seq':int(e.event_seq),'family':'fade_reentry','params':f'exc={exc_frac:.2f}|re={maxsec}|buf={buffer:.0f}|tg={target_name}','direction':trade_dir,'entry_time_us':int(tt[j]),'entry_seq':int(seq[i+j]),'entry':entry,'stop':stop,'target':target,'risk_points':risk,'planned_rr':planned_rr,'r':r,'outcome':outcome,'event_direction':direction,'ref_width':width,'reentry_seconds':resec})

            for hold in cont_holds:
                hb=int(np.searchsorted(tt,t0+hold*SECOND_US,'left'))
                if hb<=0 or hb>=len(pp):continue
                hp=pp[:hb];hv=vv[:hb];outmask=direction*(hp-boundary)>0
                volratio=float(hv[outmask].sum()/hv.sum()) if hv.sum()>0 else 0.0
                timeratio=_time_outside_ratio(tt,pp,t0,hold,direction,boundary,float(pp[0]))
                if float(np.max(direction*(hp-boundary))) < max(2.0,0.10*width):continue
                for thr in cont_thresholds:
                    if timeratio<thr or volratio<thr:continue
                    rb=int(np.searchsorted(tt,t0+(hold+120)*SECOND_US,'right'));om=direction*(pp[hb:rb]-boundary)
                    for band_frac in cont_bands:
                        band=max(2.0,band_frac*width);cand=np.flatnonzero((om>0)&(om<=band))
                        if not cand.size:continue
                        j=hb+int(cand[0]);entry=float(pp[j]);inside=max(3.0,0.10*width);stop=boundary-direction*inside;risk=float(direction*(entry-stop))
                        if risk<=0 or risk>0.35*width+5:continue
                        for tr in cont_targets:
                            target=entry+direction*(tr*risk);rr,outcome,_=fast_first_hit(j,direction,entry,stop,target,risk)
                            rows.append({'trading_date':d,'event_seq':int(e.event_seq),'family':'continuation_retest','params':f'hold={hold}|thr={thr:.2f}|band={band_frac:.2f}|tr={tr:.0f}','direction':direction,'entry_time_us':int(tt[j]),'entry_seq':int(seq[i+j]),'entry':entry,'stop':stop,'target':target,'risk_points':risk,'planned_rr':tr,'r':rr,'outcome':outcome,'event_direction':direction,'ref_width':width,'reentry_seconds':np.nan,'time_outside':timeratio,'volume_outside':volratio})
    return pd.DataFrame(rows)


def summarize_grid(cand:pd.DataFrame, split_date='2025-09-01', min_train_trades=80):
    c=cand.copy();c['trading_date']=pd.to_datetime(c.trading_date)
    train=c[c.trading_date<pd.Timestamp(split_date)];test=c[c.trading_date>=pd.Timestamp(split_date)]
    def stat(g):
        if len(g)==0:return pd.Series({'n':0,'mean_r':np.nan,'win_rate':np.nan,'profit_factor':np.nan,'mean_rr':np.nan})
        wins=g.loc[g.r>0,'r'].sum();loss=-g.loc[g.r<0,'r'].sum()
        return pd.Series({'n':len(g),'mean_r':g.r.mean(),'win_rate':(g.r>0).mean(),'profit_factor':wins/loss if loss>0 else np.inf,'mean_rr':g.planned_rr.mean()})
    tr=train.groupby(['family','params']).apply(stat,include_groups=False).reset_index();te=test.groupby(['family','params']).apply(stat,include_groups=False).reset_index()
    grid=tr.merge(te,on=['family','params'],how='left',suffixes=('_train','_test'));selected={}
    for fam,g in grid.groupby('family'):
        eligible=g[g.n_train>=min_train_trades].sort_values(['mean_r_train','n_train'],ascending=[False,False])
        if len(eligible):selected[fam]=eligible.iloc[0].to_dict()
    return grid,selected
