from __future__ import annotations

from pathlib import Path
import json
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.metrics import mean_squared_error

SPLIT = pd.Timestamp('2025-09-01')


def pf(r):
    x=np.asarray(r,dtype=float);w=x[x>0].sum();l=-x[x<0].sum();return float(w/l) if l>0 else float('inf')


def stats(g,rcol='r'):
    if len(g)==0:return {'n':0,'mean_r':None,'win_rate':None,'profit_factor':None,'sum_r':0.0}
    x=g[rcol].astype(float);return {'n':int(len(g)),'mean_r':float(x.mean()),'win_rate':float((x>0).mean()),'profit_factor':pf(x),'sum_r':float(x.sum())}


def cost_stress(g,costs=(0,.5,1,2,3)):
    out=[]
    for c in costs:
        x=g.copy();x['r_net']=x.r-c/x.risk_points.clip(lower=.25);s=stats(x,'r_net');s['roundtrip_cost_points']=float(c);out.append(s)
    return out


def max_drawdown_r(r):
    eq=np.cumsum(np.asarray(r,float));peak=np.maximum.accumulate(np.r_[0.0,eq]);dd=peak[1:]-eq;return float(dd.max()) if len(dd) else 0.0


def compounded_equity(r,risk_fraction=.0025):
    eq=peak=1.0;mdd=0.0
    for rr in np.asarray(r,float):
        eq*=max(1e-9,1.0+risk_fraction*rr);peak=max(peak,eq);mdd=max(mdd,(peak-eq)/peak)
    return float(eq-1.0),float(mdd)


def apply_daily_policy(g,cost_points,daily_stop,max_trades):
    x=g.copy();x['r_net']=x.r-cost_points/x.risk_points.clip(lower=.25)
    x=x.sort_values(['trading_date','entry_time_us','event_seq'],kind='stable')
    keep=[]
    for _,d in x.groupby('trading_date',sort=False):
        cum=0.0;n=0
        for idx,row in d.iterrows():
            if max_trades is not None and n>=max_trades:break
            if daily_stop is not None and cum<=-abs(daily_stop):break
            keep.append(idx);cum+=float(row.r_net);n+=1
    return x.loc[keep]


def risk_grid(train,test):
    rows=[]
    for cost in [0,.5,1.0]:
        for ds in [None,2.0,3.0]:
            for mt in [None,3,5]:
                tr=apply_daily_policy(train,cost,ds,mt);te=apply_daily_policy(test,cost,ds,mt);st=stats(tr,'r_net');se=stats(te,'r_net');gr,mdd=compounded_equity(te.r_net.to_numpy(),.0025) if len(te) else (0,0)
                rows.append({'cost_points':cost,'daily_stop_r':ds if ds is not None else np.nan,'max_trades_day':mt if mt is not None else np.nan,'n_train':st['n'],'mean_r_train':st['mean_r'],'pf_train':st['profit_factor'],'n_test':se['n'],'mean_r_test':se['mean_r'],'pf_test':se['profit_factor'],'sum_r_test':se['sum_r'],'max_dd_r_test':max_drawdown_r(te.r_net.to_numpy()) if len(te) else 0,'equity_return_025pct_test':gr,'equity_mdd_025pct_test':mdd})
    df=pd.DataFrame(rows);z=df[df.cost_points==.5].sort_values(['mean_r_train','n_train'],ascending=[False,False]);sel=z.iloc[0].to_dict() if len(z) else {};return df,sel


def walk_forward(cand,family='continuation_retest'):
    c=cand[cand.family==family].copy();c['trading_date']=pd.to_datetime(c.trading_date);windows=[('2025-07-01','2025-09-01'),('2025-09-01','2025-11-01'),('2025-11-01','2026-01-01')];rows=[]
    for start,end in windows:
        st=pd.Timestamp(start);en=pd.Timestamp(end);tr=c[c.trading_date<st];te=c[(c.trading_date>=st)&(c.trading_date<en)]
        agg=tr.groupby('params').agg(n=('r','size'),mean_r=('r','mean')).reset_index();agg=agg[agg.n>=80].sort_values(['mean_r','n'],ascending=[False,False])
        if len(agg)==0:continue
        par=agg.iloc[0].params;a=tr[tr.params==par];b=te[te.params==par]
        for cost in [0,.5,1.0]:
            ar=a.r-cost/a.risk_points;br=b.r-cost/b.risk_points
            rows.append({'test_start':start,'test_end':end,'selected_params':par,'cost_points':cost,'n_train':len(a),'mean_r_train':float(ar.mean()) if len(a) else np.nan,'n_test':len(b),'mean_r_test':float(br.mean()) if len(b) else np.nan,'pf_test':pf(br) if len(b) else np.nan})
    return pd.DataFrame(rows)


def robustness(selected,events):
    left=selected.copy();left['trading_date']=left.trading_date.astype(str);right=events.copy();right['trading_date']=right.trading_date.astype(str)
    x=left.merge(right,on=['trading_date','event_seq'],how='left',suffixes=('','_event'));x['trading_date']=pd.to_datetime(x.trading_date);x['month']=x.trading_date.dt.to_period('M').astype(str)
    sec=(x.entry_time_us//1_000_000)%86400;x['time_bucket']=pd.cut(sec,[8*3600+45*60,9*3600+30*60,11*3600+30*60,13*3600+45*60],labels=['open_0845_0930','mid_0930_1130','late_1130_1345'],include_lowest=True,right=False)
    train=x[x.trading_date<SPLIT];q=train.ref_width.quantile([1/3,2/3]).to_numpy();x['width_regime']=pd.cut(x.ref_width,[-np.inf,q[0],q[1],np.inf],labels=['narrow','medium','wide']);out={}
    for key in ['month','direction','time_bucket','width_regime']:
        rows=[]
        for val,g in x[x.trading_date>=SPLIT].groupby(key,observed=True):
            s=stats(g);s[key]=str(val);rows.append(s)
        out[key]=rows
    return out


def interaction_model(selected,events):
    ev=events.copy();ev['trading_date']=ev.trading_date.astype(str);left=selected.copy();left['trading_date']=left.trading_date.astype(str);x=left.merge(ev,on=['trading_date','event_seq'],how='left',suffixes=('','_event'));x['trading_date']=pd.to_datetime(x.trading_date)
    feats=['direction','ref_width','profile_concentration','poc_shift_15m','value_overlap_15m','market_state_score','edge_volume_ratio','prev_day_extreme_distance','time_outside','volume_outside']
    tr=x[x.trading_date<SPLIT].copy();te=x[x.trading_date>=SPLIT].copy();model=Pipeline([('impute',SimpleImputer(strategy='median')),('hgb',HistGradientBoostingRegressor(max_iter=80,learning_rate=.04,max_leaf_nodes=7,min_samples_leaf=40,l2_regularization=2.0,random_state=42))]);model.fit(tr[feats],tr.r);ptr=model.predict(tr[feats]);pte=model.predict(te[feats])
    res={'features':feats,'n_train':len(tr),'n_test':len(te),'rmse_train':float(mean_squared_error(tr.r,ptr)**.5),'rmse_test':float(mean_squared_error(te.r,pte)**.5),'corr_train':float(np.corrcoef(ptr,tr.r)[0,1]),'corr_test':float(np.corrcoef(pte,te.r)[0,1])};buckets=[]
    for frac in [.25,.5,1.0]:
        threshold=float(np.quantile(ptr,1-frac)) if frac<1 else -np.inf;a=tr[ptr>=threshold];b=te[pte>=threshold];buckets.append({'top_fraction':frac,'threshold_train':threshold,'train':stats(a),'test':stats(b)})
    res['predicted_quality_buckets']=buckets;return res


def phase_summary(events_path,candidates_path,grid_path,selected_path,analysis_path,out_dir):
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True);events=pd.read_csv(events_path);events['trading_date']=events.trading_date.astype(str);cand=pd.read_csv(candidates_path);cand['trading_date']=cand.trading_date.astype(str);selected=json.load(open(selected_path));analysis=json.load(open(analysis_path));exec_res={};selected_trades={}
    for fam,info in selected.items():
        par=info['params'];g=cand[(cand.family==fam)&(cand.params==par)].copy();g['trading_date']=pd.to_datetime(g.trading_date);tr=g[g.trading_date<SPLIT];te=g[g.trading_date>=SPLIT];exec_res[fam]={'params':par,'train':stats(tr),'test':stats(te),'cost_stress_oos':cost_stress(te)};selected_trades[fam]=g
    cont=selected_trades.get('continuation_retest',pd.DataFrame())
    if len(cont):
        tr=cont[cont.trading_date<SPLIT];te=cont[cont.trading_date>=SPLIT];rg,rsel=risk_grid(tr,te);rg.to_csv(out/'phase8_risk_grid.csv',index=False);rob=robustness(cont,events);inter=interaction_model(cont,events)
    else:rg=pd.DataFrame();rsel={};rob={};inter={}
    wf=walk_forward(cand);wf.to_csv(out/'phase11_walk_forward.csv',index=False)
    result={'split_date':str(SPLIT.date()),'events_total':int(len(events)),'execution':exec_res,'risk_selected_train':rsel,'robustness_oos':rob,'interaction_execution':inter,'walk_forward':wf.to_dict(orient='records'),'phase1_6_key':{'full_logistic_oos':analysis['leave_one_group_out'][0]['test'],'hgb_oos':analysis['hist_gradient_boosting_test'],'drop_acceptance_oos':next(x['test'] for x in analysis['leave_one_group_out'] if x['drop']=='acceptance'),'drop_location_oos':next(x['test'] for x in analysis['leave_one_group_out'] if x['drop']=='location')},'limitations':['side is exactly the tick-direction sign of price changes, not aggressor-side Bid/Ask classification; true Delta/CVD/Footprint edge is not testable from this file.','Timestamp resolution is one second, while physical row order preserves same-second sequencing; queue/MBO/replenishment/iceberg tests are not possible.','Only 2025 MTX is available, so cross-year robustness cannot be established.','No brokerage-specific commission/fee assumption is imposed; execution sensitivity is expressed as round-trip point-equivalent cost.']}
    (out/'phase8_to_12_summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=lambda o:None if pd.isna(o) else o),encoding='utf-8');return result
