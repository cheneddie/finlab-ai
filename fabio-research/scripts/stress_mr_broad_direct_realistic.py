from pathlib import Path
import numpy as np,pandas as pd
R=Path('/mnt/data/fabio-research/reports/v3');C=Path('/mnt/data/fabio_day_cache');D={}
def day(d):
 d=str(d)
 if d not in D:D[d]=np.load(C/f'{d}.npz',allow_pickle=True)
 return D[d]
def sim(s,ticks=0,sec=0.,cost=0.,stop_extra=0.):
 rec=[]
 for q in s.itertuples(index=False):
  z=day(q.trading_date);seq=z['seq'];tt=z['datetime_us'];p=z['price'].astype(float);td=int(q.trade_direction);i0=int(np.searchsorted(seq,int(q.entry_seq)))
  if i0>=len(seq) or int(seq[i0])!=int(q.entry_seq):continue
  if sec>0:i=int(np.searchsorted(tt,int(tt[i0])+int(sec*1e6),side='left'))
  else:i=i0+ticks
  if i>=len(p):continue
  entry=float(p[i]);stop=float(q.lvn_price)-td*6.;risk=td*(entry-stop)
  if risk<1:continue
  dist=max(1.,float(np.ceil(risk*.75-1e-12)));end=min(len(p),int(np.searchsorted(tt,int(tt[i])+300_000_000,side='right')));prog=td*(p[i:end]-entry);jt=np.flatnonzero(prog>=dist);js=np.flatnonzero(-prog>=risk);jt=int(jt[0]) if len(jt) else 10**18;js=int(js[0]) if len(js) else 10**18;last=len(prog)-1
  if jt<=last and jt<js:r=dist/risk;out='target';xi=i+jt
  elif js<=last and js<jt:
   xi=i+js;fill=float(p[xi])-td*stop_extra;r=td*(fill-entry)/risk;out='stop'
  else:xi=i+last;r=float(prog[last]/risk);out='time'
  rnet=r-cost/risk
  rec.append(dict(trading_date=str(q.trading_date),entry_seq=int(seq[i]),delay_ticks=i-i0,delay_sec=(int(tt[i])-int(tt[i0]))/1e6,risk_points=risk,r_gross=r,r_net=rnet,outcome=out))
 return pd.DataFrame(rec)
def met(t):
 rr=t.r_net.to_numpy();pos=rr[rr>0].sum();neg=-rr[rr<0].sum();mo=t.assign(month=t.trading_date.str[:7]).groupby('month').r_net.mean();eq=np.cumsum(rr);pk=np.maximum.accumulate(np.r_[0.,eq]);dd=np.r_[0.,eq]-pk
 return dict(n=len(t),ev=rr.mean(),win=(rr>0).mean(),pf=pos/neg if neg else np.inf,maxdd=-dd.min(),monthmin=mo.min(),months=len(mo))
rows=[]
for split,f in [('discovery','v3_discovery_replay_mr_broad_setups.csv'),('holdout','holdout_mr_broad_setups.csv')]:
 s=pd.read_csv(R/f)
 for lab,tk,sc in [('0tick',0,0),('1tick',1,0),('2tick',2,0),('5tick',5,0),('10tick',10,0),('1sec',0,1),('2sec',0,2)]:
  for cost in [0,.5,1]:
   for ss in [0,1,2]:
    t=sim(s,tk,sc,cost,ss);m=met(t);m.update(split=split,delay=lab,cost_points=cost,stop_extra_slip=ss);rows.append(m)
out=pd.DataFrame(rows);out.to_csv(R/'mr_broad_direct_realistic_stress.csv',index=False)
print(out[(out['split']=='holdout')&(out.stop_extra_slip==0)&(out.cost_points.isin([0,.5,1]))][['delay','cost_points','n','ev','win','pf','maxdd','monthmin']].to_string(index=False))
