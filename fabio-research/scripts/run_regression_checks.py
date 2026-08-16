from pathlib import Path
import json
import numpy as np
import pandas as pd
from fabio_research.market import MTXDataset,SECOND_US
from fabio_research.execution import _first_hit_r

ROOT=Path('reports')
c=pd.read_csv(ROOT/'execution_candidates.csv')
day0=str(c.trading_date.min())
sample=c[c.trading_date.astype(str)==day0].drop_duplicates(['family','params','event_seq']).head(60)
lookup={(int(r.entry_seq),str(r.family),str(r.params)):r for _,r in sample.iterrows()}
checked=0;mismatches=[]
for day in MTXDataset('/mnt/data/MTX_2025.parquet').iter_front_month_day_sessions():
    if day.trading_date.isoformat()!=day0:continue
    seq=day.seq;t=day.datetime_us;p=day.price.astype(float,copy=False);pos={int(x):i for i,x in enumerate(seq)}
    for key,row in lookup.items():
        es=key[0]
        if es not in pos:mismatches.append({'entry_seq':es,'reason':'entry_seq_missing'});continue
        i=pos[es];end=int(np.searchsorted(t,t[i]+600*SECOND_US,side='right'));rr,out,_=_first_hit_r(p[i:end],int(row.direction),float(row.entry),float(row.stop),float(row.target),float(row.risk_points));checked+=1
        if out!=row.outcome or abs(rr-float(row.r))>1e-9:mismatches.append({'entry_seq':es,'expected_outcome':row.outcome,'actual_outcome':out,'expected_r':float(row.r),'actual_r':rr})
    break
report={'day':day0,'checked':checked,'mismatches':mismatches,'passed':checked>0 and not mismatches}
(ROOT/'execution_regression_check.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
if not report['passed']:raise SystemExit(1)
