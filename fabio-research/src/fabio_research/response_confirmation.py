from __future__ import annotations
from pathlib import Path
import json
import numpy as np
import pandas as pd
from .market import MTXDataset,SECOND_US


def _fast_hit(cmax,cmin,arr,trade_dir,entry,stop,target,risk):
    INF=10**18
    if trade_dir>0:
        it=int(np.searchsorted(cmax,target,'left')) if cmax[-1]>=target else INF
        nm=-cmin;is_=int(np.searchsorted(nm,-stop,'left')) if cmin[-1]<=stop else INF
    else:
        nm=-cmin;it=int(np.searchsorted(nm,-target,'left')) if cmin[-1]<=target else INF
        is_=int(np.searchsorted(cmax,stop,'left')) if cmax[-1]>=stop else INF
    if it<is_:return abs(target-entry)/risk,'target'
    if is_<it:return -1.0,'stop'
    return float(np.clip(trade_dir*(arr[-1]-entry)/risk,-1,abs(target-entry)/risk)),'horizon'


def build_response_grid(candidates_csv,parquet_path,out_dir,split='2025-09-01',min_train=100):
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    c=pd.read_csv(candidates_csv);c=c[c.family=='fade_reentry'].copy();c['_date']=pd.to_datetime(c.trading_date)
    dev=c[c._date<pd.Timestamp(split)]
    top_base=(dev.groupby('params').r.agg(['size','mean']).reset_index().query('size >= @min_train').sort_values(['mean','size'],ascending=[False,False]).head(4).params.tolist())
    c=c[c.params.isin(top_base)].copy();c['trading_date']=c.trading_date.astype(str)
    bydate={d:g for d,g in c.groupby('trading_date',sort=False)};allrows=[]
    delays=['signal','next_tick','next_2ticks','next_1s','next_2s']
    for day in MTXDataset(parquet_path).iter_front_month_day_sessions():
        d=day.trading_date.isoformat()
        if d not in bydate:continue
        t=day.datetime_us;p=day.price.astype(float,copy=False);seq=day.seq;path_cache={}
        for _,r in bydate[d].iterrows():
            i=int(np.searchsorted(seq,int(r.entry_seq),'left'))
            if i>=len(seq) or int(seq[i])!=int(r.entry_seq):continue
            locs={'signal':i,'next_tick':i+1,'next_2ticks':i+2,'next_1s':int(np.searchsorted(t,int(r.entry_time_us)+SECOND_US,'left')),'next_2s':int(np.searchsorted(t,int(r.entry_time_us)+2*SECOND_US,'left'))}
            tg=str(r.params).split('tg=')[-1]
            for mode,j in locs.items():
                if j>=len(p):continue
                entry=float(p[j]);direction=int(r.direction);stop=float(r.stop);risk=direction*(entry-stop)
                if risk<=0:continue
                if tg=='POC':
                    target=float(r.target);planned=direction*(target-entry)/risk
                    if planned<=0:continue
                else:
                    planned=float(tg[:-1]);target=entry+direction*planned*risk
                if j not in path_cache:
                    end=int(np.searchsorted(t,int(t[j])+600*SECOND_US,'right'));arr=p[j:end]
                    if len(arr)==0:continue
                    path_cache[j]=(arr,np.maximum.accumulate(arr),np.minimum.accumulate(arr))
                arr,cmax,cmin=path_cache[j];rr,outcome=_fast_hit(cmax,cmin,arr,direction,entry,stop,target,risk)
                allrows.append({'trading_date':d,'event_seq':int(r.event_seq),'entry_time_us':int(t[j]),'entry_seq':int(seq[j]),'base_params':str(r.params),'delay_mode':mode,'params':str(r.params)+'|delay='+mode,'direction':direction,'entry':entry,'stop':stop,'target':target,'risk_points':risk,'planned_rr':planned,'r':rr,'outcome':outcome,'ref_width':float(r.ref_width)})
    x=pd.DataFrame(allrows);x['trading_date']=pd.to_datetime(x.trading_date);x.to_csv(out/'phase5_response_candidates.csv',index=False)
    st=pd.Timestamp(split);tr=x[x.trading_date<st];te=x[x.trading_date>=st]
    def agg(g):
        w=g.loc[g.r>0,'r'].sum();l=-g.loc[g.r<0,'r'].sum()
        return pd.Series({'n':len(g),'mean_r':g.r.mean(),'win_rate':(g.r>0).mean(),'pf':w/l if l>0 else np.inf,'mean_r_cost_0_5':(g.r-.5/g.risk_points).mean(),'mean_r_cost_1':(g.r-1/g.risk_points).mean()})
    a=tr.groupby('params').apply(agg,include_groups=False).reset_index().add_suffix('_train').rename(columns={'params_train':'params'})
    b=te.groupby('params').apply(agg,include_groups=False).reset_index().add_suffix('_test').rename(columns={'params_test':'params'})
    grid=a.merge(b,on='params',how='left');eligible=grid[grid.n_train>=min_train].sort_values(['mean_r_train','n_train'],ascending=[False,False]);sel=eligible.iloc[0].to_dict() if len(eligible) else {}
    grid.to_csv(out/'phase5_response_confirmation_grid.csv',index=False)
    if sel:x[x.params==sel['params']].copy().to_csv(out/'phase5_response_selected_trades.csv',index=False)
    summary={'selected':sel,'base_params_selected_on_train':top_base,'n_candidates':int(len(x)),'n_parameter_variants':int(grid.shape[0]),'split':split}
    (out/'phase5_response_confirmation.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return grid,summary
