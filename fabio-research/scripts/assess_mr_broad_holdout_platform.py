from pathlib import Path
import numpy as np,pandas as pd
R=Path('/mnt/data/fabio-research/reports/v3');C=Path('/mnt/data/fabio_day_cache');D={}
def day(d):
 d=str(d)
 if d not in D:D[d]=np.load(C/f'{d}.npz',allow_pickle=True)
 return D[d]
def sim(setups,buf,tmult,horizon):
 rr=[];dates=[]
 for q in setups.itertuples(index=False):
  z=day(q.trading_date);seq=z['seq'];tt=z['datetime_us'];p=z['price'].astype(float);td=int(q.trade_direction);i=int(np.searchsorted(seq,int(q.entry_seq)))
  if i>=len(seq) or int(seq[i])!=int(q.entry_seq):continue
  entry=float(p[i]);risk=td*(entry-(float(q.lvn_price)-td*buf))
  if risk<1:continue
  dist=max(1.,float(np.ceil(risk*tmult-1e-12)));end=min(len(p),int(np.searchsorted(tt,int(tt[i])+horizon*1_000_000,side='right')));prog=td*(p[i:end]-entry);jt=np.flatnonzero(prog>=dist);js=np.flatnonzero(-prog>=risk);jt=int(jt[0]) if len(jt) else 10**18;js=int(js[0]) if len(js) else 10**18;last=len(prog)-1
  if jt<=last and jt<js:r=dist/risk
  elif js<=last and js<jt:r=float(prog[js]/risk)
  else:r=float(prog[last]/risk)
  rr.append(r);dates.append(str(q.trading_date))
 return np.array(rr,float),np.array(dates)
def metrics(rr,dates,cost,buf):
 net=rr-cost/buf;pos=net[net>0].sum();neg=-net[net<0].sum();mo=pd.DataFrame({'d':dates,'r':net}).assign(m=lambda x:x.d.str[:7]).groupby('m').r.mean()
 return dict(n=len(net),mean_r=net.mean(),win_rate=(net>0).mean(),pf=pos/neg if neg else np.inf,month_min=mo.min(),positive_month_frac=(mo>0).mean())
rows=[]
for split,f in [('discovery','v3_discovery_replay_mr_broad_setups.csv'),('holdout','holdout_mr_broad_setups.csv')]:
 s=pd.read_csv(R/f)
 for b in [4,5,6,7,8]:
  for t in [.5,.625,.75,.875,1.0]:
   for h in [180,240,300,420,600]:
    rr,dt=sim(s,b,t,h)
    for cost in [0,.5,1.0]:
     m=metrics(rr,dt,cost,b);m.update(split=split,stop_buffer=b,target_r=t,horizon_sec=h,cost_points=cost);rows.append(m)
out=pd.DataFrame(rows);out.to_csv(R/'mr_broad_platform_holdout_assessment.csv',index=False)
for split in ['discovery','holdout']:
 z=out[(out['split']==split)&(out.cost_points==.5)]
 print('\n',split,'cost .5: profitable', (z.mean_r>0).mean(),'min',z.mean_r.min(),'median',z.mean_r.median(),'max',z.mean_r.max(),'positive-month-all', (z.month_min>0).mean())
 center=z[(z.stop_buffer==6)&(z.target_r==.75)&(z.horizon_sec==300)]
 print('center',center.to_string(index=False))
 print('worst 10\n',z.nsmallest(10,'mean_r')[['stop_buffer','target_r','horizon_sec','mean_r','month_min','pf']].to_string(index=False))
