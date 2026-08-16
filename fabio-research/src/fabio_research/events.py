from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from .market import TickDay, DAY_US, SECOND_US, DAY_START_SEC, DAY_END_SEC
from .profile import ProfileLevels, add_profile, value_area


@dataclass
class AuctionEvent:
    trading_date: str
    event_seq: int
    event_time_us: int
    event_second: int
    direction: int
    boundary: float
    ref_poc: float
    ref_val: float
    ref_vah: float
    ref_vwap: float
    ref_width: float
    profile_volume: float
    edge_volume_ratio: float
    profile_concentration: float
    poc_shift_15m: float
    value_overlap_15m: float
    market_state_score: float
    prev_day_extreme_distance: float
    obs_seconds: int
    time_outside_ratio: float
    volume_outside_ratio: float
    reentry_seconds: float
    obs_progress: float
    obs_mfe: float
    obs_mae: float
    breakout_velocity_30s: float
    volume_rate_ratio: float
    trade_rate_ratio: float
    tick_delta_proxy: float
    price_efficiency: float
    entry_price_30s: float
    entry_price_60s: float
    entry_price_120s: float
    barrier_points: float
    continuation_label: int
    outcome_seconds: float
    mfe_10m: float
    mae_10m: float
    poc_hit_10m: int


def _minute_profiles(day):
    dt=day.datetime_us;minute=((dt%DAY_US)//(60*SECOND_US)).astype(np.int32);profiles={};ranges={}
    if len(dt)==0:return profiles,ranges
    cuts=np.r_[0,np.flatnonzero(np.diff(minute)!=0)+1,len(dt)];vol=day.volume
    for a,b in zip(cuts[:-1],cuts[1:]):
        m=int(minute[a]);pr=day.price[a:b].astype(np.int64,copy=False);vv=vol[a:b]
        up,inv=np.unique(pr,return_inverse=True);sums=np.bincount(inv,weights=vv)
        profiles[m]={int(p):float(v) for p,v in zip(up,sums) if v>0};ranges[m]=(int(a),int(b))
    return profiles,ranges


def _overlap(a,b):
    if a is None or b is None:return np.nan
    inter=max(0.0,min(a.vah,b.vah)-max(a.val,b.val));union=max(a.vah,b.vah)-min(a.val,b.val)
    return float(inter/union) if union>0 else 1.0


def _build_levels_by_minute(day,window_minutes=30,va_pct=.70):
    mprof,_=_minute_profiles(day);start_m=DAY_START_SEC//60;end_m=DAY_END_SEC//60;rolling={};levels={}
    for m in range(start_m,end_m):
        if m-1 in mprof:add_profile(rolling,mprof[m-1],+1)
        if m-window_minutes-1 in mprof:add_profile(rolling,mprof[m-window_minutes-1],-1)
        if m>=start_m+window_minutes:
            lv=value_area(rolling,va_pct)
            if lv is not None:levels[m]=lv
    return levels


def _last_price_at_or_before(t,p,ts,lo=0):
    i=int(np.searchsorted(t,ts,side='right')-1);return float(p[lo] if i<lo else p[i])


def _first_price_at_or_after(t,p,ts,hi=None):
    i=int(np.searchsorted(t,ts,side='left'))
    if hi is not None and i>=hi:return hi-1,float(p[hi-1])
    i=min(i,len(t)-1);return i,float(p[i])


def _second_last_prices(t,p,t0,seconds,initial):
    out=np.empty(seconds,float);out[:]=np.nan
    a=int(np.searchsorted(t,t0,'left'));b=int(np.searchsorted(t,t0+seconds*SECOND_US,'left'))
    if a<b:
        rel=((t[a:b]-t0)//SECOND_US).astype(int)
        for idx,r in zip(range(a,b),rel):
            if 0<=r<seconds:out[r]=p[idx]
    last=initial
    for i in range(seconds):
        if np.isnan(out[i]):out[i]=last
        else:last=out[i]
    return out


def build_events_for_day(day,prev_day_high=None,prev_day_low=None,window_minutes=30,obs_seconds=60,horizon_seconds=600,barrier_fraction=.20,min_barrier_points=10.0,cooldown_seconds=180):
    t=day.datetime_us;p=day.price.astype(float,copy=False);v=day.volume;s=day.side_proxy.astype(float,copy=False);seq=day.seq
    if len(t)<100:return []
    levels=_build_levels_by_minute(day,window_minutes)
    if not levels:return []
    minutes=((t%DAY_US)//(60*SECOND_US)).astype(np.int32);warm_start=DAY_START_SEC//60+window_minutes
    i=int(np.searchsorted(minutes,warm_start,'left'));events=[];next_allowed_us=-1;state_cache={}
    for m,lv in levels.items():
        old=levels.get(m-15)
        if old is None:state_cache[m]=(0.0,np.nan,0.0)
        else:
            shift=(lv.poc-old.poc)/max(1.0,lv.width);ov=_overlap(lv,old);score=abs(shift)+(1.0-ov if np.isfinite(ov) else 0.0)
            state_cache[m]=(float(shift),float(ov),float(score))

    while i<len(t):
        m=int(minutes[i]);lv=levels.get(m)
        if lv is None or i==0:i+=1;continue
        if t[i]<next_allowed_us:i+=1;continue
        prevp=p[i-1];curp=p[i];direction=0;boundary=np.nan
        if prevp<=lv.vah and curp>lv.vah:direction=1;boundary=lv.vah
        elif prevp>=lv.val and curp<lv.val:direction=-1;boundary=lv.val
        if direction==0:i+=1;continue
        t0=int(t[i]);end_needed=t0+(obs_seconds+horizon_seconds)*SECOND_US
        if end_needed>int(t[-1]):break
        obs_end=t0+obs_seconds*SECOND_US;oa=i;ob=int(np.searchsorted(t,obs_end,'left'))
        if ob<=oa:i+=1;continue
        op=p[oa:ob];ovv=v[oa:ob];oss=s[oa:ob];outside=direction*(op-boundary)>0;vtot=float(ovv.sum())
        vov=float(ovv[outside].sum()/vtot) if vtot>0 else np.nan
        sec_prices=_second_last_prices(t,p,t0,obs_seconds,float(curp));tov=float(np.mean(direction*(sec_prices-boundary)>0))
        re=np.flatnonzero(direction*(op-boundary)<=0);resec=float((t[oa+int(re[0])]-t0)/SECOND_US) if re.size else float(obs_seconds+1)
        progress=float(direction*(sec_prices[-1]-boundary)/max(1.0,lv.width));exc=direction*(op-boundary)/max(1.0,lv.width)
        obs_mfe=float(np.max(exc));obs_mae=float(np.min(exc));p30ago=_last_price_at_or_before(t,p,t0-30*SECOND_US)
        velocity=float(direction*(curp-p30ago)/max(1.0,lv.width));ba=int(np.searchsorted(t,t0-300*SECOND_US,'left'))
        bv=float(v[ba:i].sum());baseline_seconds=max(1.0,(t0-int(t[ba]))/SECOND_US) if i>ba else 300.0
        obs_vol_rate=vtot/obs_seconds;base_vol_rate=bv/baseline_seconds if baseline_seconds>0 else np.nan
        vol_rate_ratio=float(obs_vol_rate/base_vol_rate) if base_vol_rate and np.isfinite(base_vol_rate) else np.nan
        obs_trade_rate=(ob-oa)/obs_seconds;base_trade_rate=(i-ba)/baseline_seconds if baseline_seconds>0 else np.nan
        trade_rate_ratio=float(obs_trade_rate/base_trade_rate) if base_trade_rate and np.isfinite(base_trade_rate) else np.nan
        # side is empirically sign(price_t-price_{t-1}), not true bid/ask aggressor delta.
        directional_proxy=float(direction*np.sum(ovv*oss)/vtot) if vtot>0 else np.nan
        path=float(np.sum(np.abs(np.diff(np.r_[curp,op]))));net=float(direction*(op[-1]-curp));efficiency=float(net/path) if path>0 else 0.0
        def entry_after(sec):return _first_price_at_or_after(t,p,t0+sec*SECOND_US)[1]
        e30,e60,e120=entry_after(30),entry_after(60),entry_after(120)
        t1=obs_end;ia=int(np.searchsorted(t,t1,'left'));ib=int(np.searchsorted(t,t1+horizon_seconds*SECOND_US,'right'))
        future_p=p[ia:ib];future_t=t[ia:ib];barrier=max(min_barrier_points,barrier_fraction*lv.width);directed=direction*(future_p-e60)
        hit_s=np.flatnonzero(directed>=barrier);hit_f=np.flatnonzero(directed<=-barrier);hs=int(hit_s[0]) if hit_s.size else 10**18;hf=int(hit_f[0]) if hit_f.size else 10**18
        if hs==10**18 and hf==10**18:label=-1;outcome_seconds=float(horizon_seconds)
        elif hs<hf:label=1;outcome_seconds=float((future_t[hs]-t1)/SECOND_US)
        else:label=0;outcome_seconds=float((future_t[hf]-t1)/SECOND_US)
        mfe=float(np.max(directed)) if future_p.size else np.nan;mae=float(np.min(directed)) if future_p.size else np.nan
        poc_hit=int(np.any(future_p<=lv.poc)) if direction==1 else int(np.any(future_p>=lv.poc))
        shift,voverlap,state_score=state_cache.get(m,(0.0,np.nan,0.0));edge_ratio=lv.edge_high_ratio if direction==1 else lv.edge_low_ratio
        if prev_day_high is None or prev_day_low is None:prev_dist=np.nan
        elif direction==1:prev_dist=float((boundary-prev_day_high)/max(1.0,lv.width))
        else:prev_dist=float((prev_day_low-boundary)/max(1.0,lv.width))
        events.append(AuctionEvent(day.trading_date.isoformat(),int(seq[i]),t0,int((t0%DAY_US)//SECOND_US),direction,float(boundary),lv.poc,lv.val,lv.vah,lv.vwap,lv.width,lv.total_volume,float(edge_ratio),lv.concentration,shift,voverlap,state_score,prev_dist,obs_seconds,tov,vov,resec,progress,obs_mfe,obs_mae,velocity,vol_rate_ratio,trade_rate_ratio,directional_proxy,efficiency,e30,e60,e120,float(barrier),label,outcome_seconds,mfe,mae,poc_hit))
        next_allowed_us=t0+cooldown_seconds*SECOND_US;i=int(np.searchsorted(t,next_allowed_us,'left'))
    return events
