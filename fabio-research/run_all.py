"""One-command reproducible Fabio MTX research pipeline.

Usage:
    PYTHONPATH=src python run_all.py /path/to/MTX_2025.parquet reports

Raw rows are never sorted. All event and execution references use the physical
source sequence index (`seq`).
"""
from __future__ import annotations
import csv, json, sys
from dataclasses import asdict, fields
from pathlib import Path
import numpy as np

from fabio_research.market import MTXDataset
from fabio_research.events import AuctionEvent, build_events_for_day
from fabio_research.analyze import analyze, markdown
from fabio_research.execution import generate_candidates, summarize_grid
from fabio_research.response_confirmation import build_response_grid
from fabio_research.validation import phase_summary


def main():
    src=Path(sys.argv[1]);out=Path(sys.argv[2]) if len(sys.argv)>2 else Path('reports');out.mkdir(parents=True,exist_ok=True)
    events_path=out/'auction_events.csv';ds=MTXDataset(src);prev_high=prev_low=None;n_days=n_ticks=n_events=0
    with events_path.open('w',newline='',encoding='utf-8') as fh:
        w=csv.DictWriter(fh,fieldnames=[f.name for f in fields(AuctionEvent)]);w.writeheader()
        for day in ds.iter_front_month_day_sessions():
            evs=build_events_for_day(day,prev_high,prev_low,cooldown_seconds=660)
            for e in evs:w.writerow(asdict(e))
            n_days+=1;n_ticks+=len(day.price);n_events+=len(evs);prev_high=float(np.max(day.price));prev_low=float(np.min(day.price))
    (out/'phase1_events_summary.json').write_text(json.dumps({'days':n_days,'front_month_day_ticks':n_ticks,'events':n_events,'window_minutes':30,'value_area_pct':.70,'observation_seconds':60,'outcome_horizon_seconds':600,'cooldown_seconds':660,'ordering':'physical source row order; no sorting'},indent=2),encoding='utf-8')

    a=analyze(events_path,out);(out/'phase1_to_6_analysis.md').write_text(markdown(a),encoding='utf-8')
    cand=generate_candidates(events_path,src);cand.to_csv(out/'execution_candidates.csv',index=False)
    grid,selected=summarize_grid(cand);grid.to_csv(out/'phase7_execution_grid.csv',index=False);(out/'phase7_execution_selected.json').write_text(json.dumps(selected,indent=2),encoding='utf-8')
    build_response_grid(out/'execution_candidates.csv',src,out)
    phase_summary(events_path,out/'execution_candidates.csv',out/'phase7_execution_grid.csv',out/'phase7_execution_selected.json',out/'phase1_to_6_analysis.json',out)
    print(f'complete: days={n_days}, ticks={n_ticks:,}, auction_events={n_events:,}')
    print('Run `PYTHONPATH=src pytest -q tests` and the execution regression checker before accepting changes.')


if __name__=='__main__':main()
