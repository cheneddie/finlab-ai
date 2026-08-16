from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.tree import DecisionTreeClassifier, export_text
from sklearn.metrics import roc_auc_score, accuracy_score, brier_score_loss, log_loss

FEATURE_GROUPS = {
    "structure": ["direction","ref_width","profile_concentration","poc_shift_15m","value_overlap_15m","market_state_score"],
    "location": ["edge_volume_ratio","prev_day_extreme_distance","boundary_vwap_distance","boundary_poc_distance"],
    "acceptance": ["time_outside_ratio","volume_outside_ratio","reentry_seconds","breakout_velocity_30s","volume_rate_ratio","trade_rate_ratio"],
    "flow_proxy": ["tick_delta_proxy"],
    "response": ["obs_progress","obs_mfe","obs_mae","price_efficiency"],
}


def prep(df):
    x=df.copy();x["trading_date"]=pd.to_datetime(x["trading_date"]);x=x[x["continuation_label"].isin([0,1])].copy()
    x["boundary_vwap_distance"]=x["direction"]*(x["boundary"]-x["ref_vwap"])/x["ref_width"].clip(lower=1)
    x["boundary_poc_distance"]=x["direction"]*(x["boundary"]-x["ref_poc"])/x["ref_width"].clip(lower=1)
    return x


def logistic_pipeline(features):
    return Pipeline([("impute",SimpleImputer(strategy="median")),("scale",StandardScaler()),("model",LogisticRegression(max_iter=500,C=.5,random_state=42))])


def metrics(y,p):
    pred=(p>=.5).astype(int)
    return {"auc":float(roc_auc_score(y,p)),"accuracy":float(accuracy_score(y,pred)),"brier":float(brier_score_loss(y,p)),"log_loss":float(log_loss(y,p)),"n":int(len(y)),"base_rate":float(np.mean(y))}


def binned_rate(df,col,bins):
    tmp=df[[col,"continuation_label"]].dropna().copy();tmp["bin"]=pd.cut(tmp[col],bins=bins,include_lowest=True,duplicates='drop')
    g=tmp.groupby("bin",observed=True)["continuation_label"].agg(["count","mean"])
    return [{"bin":str(i),"n":int(r["count"]),"continuation_rate":float(r["mean"])} for i,r in g.iterrows()]


def analyze(events_csv,out_dir,split_date="2025-09-01"):
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True);raw=pd.read_csv(events_csv);df=prep(raw)
    train=df[df.trading_date<pd.Timestamp(split_date)].copy();test=df[df.trading_date>=pd.Timestamp(split_date)].copy()
    ytr=train.continuation_label.astype(int).to_numpy();yte=test.continuation_label.astype(int).to_numpy()
    result={"resolved_events":int(len(df)),"unresolved_events":int((~raw.continuation_label.isin([0,1])).sum()),"train_events":int(len(train)),"test_events":int(len(test)),"split_date":split_date,"train_base_rate":float(ytr.mean()),"test_base_rate":float(yte.mean())}
    result["univariate"]={"time_outside":binned_rate(train,"time_outside_ratio",[-.001,.2,.4,.6,.8,1.001]),"volume_outside":binned_rate(train,"volume_outside_ratio",[-.001,.2,.4,.6,.8,1.001]),"reentry_seconds":binned_rate(train,"reentry_seconds",[-.001,.001,1,5,15,30,61.1]),"obs_progress":binned_rate(train,"obs_progress",[-10,-.25,0,.1,.25,.5,10])}
    tb=pd.cut(train.time_outside_ratio,[-.001,.2,.4,.6,.8,1.001],labels=["0-20","20-40","40-60","60-80","80-100"]);vb=pd.cut(train.volume_outside_ratio,[-.001,.2,.4,.6,.8,1.001],labels=["0-20","20-40","40-60","60-80","80-100"])
    train.assign(tbin=tb,vbin=vb).pivot_table(index="tbin",columns="vbin",values="continuation_label",aggfunc=["mean","count"],observed=True).to_csv(out/"phase2_acceptance_matrix_train.csv")
    cumulative=[];features=[]
    for group in ["structure","location","acceptance","flow_proxy","response"]:
        features+=FEATURE_GROUPS[group];model=logistic_pipeline(features);model.fit(train[features],ytr)
        cumulative.append({"through_group":group,"features":list(features),"train":metrics(ytr,model.predict_proba(train[features])[:,1]),"test":metrics(yte,model.predict_proba(test[features])[:,1])})
    result["ablation_cumulative"]=cumulative
    full_features=sum(FEATURE_GROUPS.values(),[]);leave=[]
    for drop in [None]+list(FEATURE_GROUPS):
        feats=[f for f in full_features if drop is None or f not in FEATURE_GROUPS[drop]];m=logistic_pipeline(feats);m.fit(train[feats],ytr);leave.append({"drop":drop or "none_full","test":metrics(yte,m.predict_proba(test[feats])[:,1])})
    result["leave_one_group_out"]=leave
    imputer=SimpleImputer(strategy="median");Xtr=imputer.fit_transform(train[full_features]);Xte=imputer.transform(test[full_features])
    tree=DecisionTreeClassifier(max_depth=4,min_samples_leaf=120,random_state=42);tree.fit(Xtr,ytr);ptree=tree.predict_proba(Xte)[:,1]
    result["decision_tree_test"]=metrics(yte,ptree);result["decision_tree_rules"]=export_text(tree,feature_names=full_features,decimals=3)
    hgb=HistGradientBoostingClassifier(max_iter=120,learning_rate=.05,max_leaf_nodes=15,min_samples_leaf=80,l2_regularization=1.0,random_state=42);hgb.fit(Xtr,ytr);phgb=hgb.predict_proba(Xte)[:,1]
    result["hist_gradient_boosting_test"]=metrics(yte,phgb)
    full_log=logistic_pipeline(full_features);full_log.fit(train[full_features],ytr);plog=full_log.predict_proba(test[full_features])[:,1]
    pred=test[["trading_date","event_seq","event_time_us","direction","entry_price_60s","barrier_points","continuation_label","ref_width"]].copy();pred["p_logistic"]=plog;pred["p_tree"]=ptree;pred["p_hgb"]=phgb;pred.to_csv(out/"oos_predictions.csv",index=False)
    conf=np.abs(phgb-.5);order=np.argsort(conf)
    for frac in [.2,.4,.6,1.0]:
        k=max(1,int(len(order)*frac));idx=order[-k:];guess=(phgb[idx]>=.5).astype(int);result.setdefault("hgb_confidence",[]).append({"top_fraction":frac,"n":int(k),"accuracy":float(np.mean(guess==yte[idx])),"mean_confidence":float(conf[idx].mean())})
    (out/"phase1_to_6_analysis.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');return result


def markdown(r):
    lines=["# Phase 1–6 — Fabio Auction Edge Analysis","",f"Resolved events: **{r['resolved_events']:,}**; unresolved: **{r['unresolved_events']:,}**.",f"Train/test split: **before {r['split_date']}** vs **{r['split_date']} onward**.",f"Train base continuation rate: **{r['train_base_rate']:.1%}**; OOS base: **{r['test_base_rate']:.1%}**.","","## Incremental ablation (logistic, out-of-sample)","","| Through layer | OOS AUC | Accuracy | Brier |","|---|---:|---:|---:|"]
    for x in r['ablation_cumulative']:
        m=x['test'];lines.append(f"| {x['through_group']} | {m['auc']:.3f} | {m['accuracy']:.1%} | {m['brier']:.3f} |")
    lines += ["","## Leave-one-layer-out (full logistic)","","| Removed | OOS AUC | Accuracy |","|---|---:|---:|"]
    for x in r['leave_one_group_out']:
        m=x['test'];lines.append(f"| {x['drop']} | {m['auc']:.3f} | {m['accuracy']:.1%} |")
    lines += ["",f"Interpretable tree OOS AUC: **{r['decision_tree_test']['auc']:.3f}**.",f"Non-linear interaction model OOS AUC: **{r['hist_gradient_boosting_test']['auc']:.3f}**.","","## Interpretable tree rules","","```",r['decision_tree_rules'],"```","","## Data caveat","","`tick_delta_proxy` is uptick/downtick volume derived from price changes, not aggressor-side Delta. Any improvement from that feature is a price-path proxy result, not proof of Fabio's true CVD/footprint edge."]
    return '\n'.join(lines)
