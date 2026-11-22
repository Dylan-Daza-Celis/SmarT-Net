"""Supervised experiment only. Fit preprocessing on training folds, never test."""
from collections import Counter
from datetime import datetime, timezone
import sys
import numpy as np
import scipy
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedGroupKFold
from . import evaluation_metrics as metrics
from .experiments import rank_cases, digest
from .risk import parameters
from .ml_artifact import encode, probabilities

VERSION = "supervised-group-holdout-v1"
NUMERIC = ["max_severity","max_asset_criticality","mean_severity","event_count","event_span_seconds"]
FEATURES = NUMERIC + ["event_type"]


def row(case):
    """Whitelist only. No IDs, group, score, priority, rationale or outcome fields."""
    times = [e.event_timestamp for e in case.events]
    return [max(e.severity for e in case.events), max(e.asset_criticality for e in case.events),
            sum(e.severity for e in case.events)/len(case.events), len(case.events),
            (max(times)-min(times)).total_seconds(),case.event_type]


def record_fingerprint(case):
    # Exclude IDs/labels/groups, retain event content and absolute timestamps.
    events=[{"at":e.event_timestamp.astimezone(timezone.utc).isoformat(),"received":e.received_at.astimezone(timezone.utc).isoformat(),
             "severity":e.severity,"asset":e.asset_criticality} for e in case.events]
    return digest({"type":case.event_type,"events":sorted(events,key=lambda e:(e['at'],e['received'],e['severity'],e['asset']))})


def pipeline(algorithm, seed):
    preprocess=ColumnTransformer([("numeric",StandardScaler(),list(range(5))),
                                  ("categorical",OneHotEncoder(handle_unknown="ignore",sparse_output=False),[5])])
    classifier=LogisticRegression(C=1.0,max_iter=2000,solver="lbfgs",class_weight="balanced",random_state=seed) if algorithm=="logistic" else RandomForestClassifier(
        n_estimators=100,max_depth=6,min_samples_leaf=2,class_weight="balanced",random_state=seed,n_jobs=1)
    return Pipeline([("preprocess",preprocess),("classifier",classifier)])


def supports(y):
    return {c:int(sum(y==c)) for c in metrics.CLASSES}


def group_support(y,groups):
    return {c:len(set(groups[y==c])) for c in metrics.CLASSES}


def valid_classes(y):
    return set(y)==set(metrics.CLASSES)


def plan_split(y,groups,seed):
    if len(y)<32 or len(set(groups))<16 or min(group_support(y,groups).values())<4:
        return None,"At least 32 cases, 16 origin groups and 4 groups per class are required"
    train,test=next(StratifiedGroupKFold(n_splits=4,shuffle=True,random_state=seed).split(np.zeros(len(y)),y,groups))
    if not valid_classes(y[train]) or not valid_classes(y[test]):
        return None,"The predeclared group holdout lacks a class; no test-driven split search is performed"
    return (train,test),None


def fit_compare(cases,references,membership,seed,budget):
    cases=sorted(cases,key=lambda c:str(c.id))
    config={"protocol":VERSION,"feature_schema":"incident-aggregates-v1","features":FEATURES,"seed":seed,"test_fraction_target":.25,
            "cv_folds":3,"budget":budget,"sklearn":sklearn.__version__,"numpy":np.__version__,
            "scipy":scipy.__version__,"python":sys.version.split()[0],"metrics_version":metrics.VERSION,
            "probability_policy":"uncalibrated estimates, not validated confidence"}
    if any(references.get(str(c.id),{}).get("priority") is None for c in cases):
        return config,{}, {"status":"No calculable","reason":"Complete independently annotated four-class references are required"}
    y=np.asarray([references[str(c.id)]["priority"] for c in cases])
    groups=np.asarray([membership[str(c.id)] for c in cases])
    split,reason=plan_split(y,groups,seed)
    config.update(support=supports(y),group_support=group_support(y,groups))
    if split is None:
        return config,{}, {"status":"No calculable","reason":reason}
    train,test=split
    x=np.asarray([row(c) for c in cases],dtype=object)
    config["partition"]={"train":[str(cases[i].id) for i in train],"test":[str(cases[i].id) for i in test],
        "train_groups":sorted(set(groups[train])),"test_groups":sorted(set(groups[test])),
        "train_support":supports(y[train]),"test_support":supports(y[test])}
    # CV diagnostics on training only. Fixed hyperparameters; neither CV nor test tune them.
    cv=[]
    if min(group_support(y[train],groups[train]).values())>=3:
        proposed=list(StratifiedGroupKFold(n_splits=3,shuffle=True,random_state=seed+1).split(x[train],y[train],groups[train]))
        if all(valid_classes(y[train][a]) and valid_classes(y[train][b]) for a,b in proposed):
            cv=proposed
    cv_plan=[{"train":[str(cases[train[i]].id) for i in a],"validation":[str(cases[train[i]].id) for i in b],
              "train_groups":sorted(set(groups[train][a])),"validation_groups":sorted(set(groups[train][b]))} for a,b in cv]
    config["cv_partition"]=cv_plan
    test_cases=[cases[i] for i in test]
    test_refs={str(c.id):references[str(c.id)] for c in test_cases}
    counts={str(c.id):len(c.events) for c in test_cases}
    effective=min(budget,len(test))
    models,results={},{}
    for algorithm in ("logistic","forest"):
        diagnostics=[]
        for a,b in cv:
            estimator=pipeline(algorithm,seed)
            estimator.fit(x[train][a],y[train][a])
            p=estimator.predict(x[train][b])
            result=metrics.classification(dict(zip(map(str,b),p)),{str(i):{"priority":y[train][i]} for i in b})
            diagnostics.append(result["macro"]["f1"])
        estimator=pipeline(algorithm,seed)
        estimator.fit(x[train],y[train])
        artifact=encode(estimator,algorithm)
        # Verify the numeric JSON codec against sklearn before persisting anything.
        p=probabilities(artifact,x[test].tolist())
        if not np.allclose(p,estimator.predict_proba(x[test]),rtol=1e-7,atol=1e-9):
            raise ValueError("Safe artifact inference diverged from fitted pipeline")
        predicted={str(c.id):artifact["classes"][int(np.argmax(p[i]))] for i,c in enumerate(test_cases)}
        expected={str(c.id):sum(metrics.CLASSES.index(label)*p[i,j] for j,label in enumerate(artifact["classes"])) for i,c in enumerate(test_cases)}
        order=sorted(predicted,key=lambda k:(-expected[k], min(e.received_at for e in next(c for c in test_cases if str(c.id)==k).events),k))
        results[algorithm]={"classification":metrics.classification(predicted,test_refs),
            "critical_coverage":metrics.attention(order,test_refs,effective,counts),
            "cv": {"folds":diagnostics,"status":"Calculable" if cv else "No calculable",
                   "reason":None if cv else "Insufficient stratified groups/classes in training folds"},
            "predictions":{k:{"priority":predicted[k],"probabilities":dict(zip(artifact["classes"],map(float,p[i]))),
                               "uncalibrated":True} for i,k in enumerate(str(c.id) for c in test_cases)},"order":order}
        config[algorithm+"_parameters"]=estimator.named_steps['classifier'].get_params()
        models[algorithm]=artifact
    weighted=parameters();weighted["algorithm_version"]="weighted-v2"
    config["weighted_parameters"]=weighted
    config["effective_budget"]=effective
    orders,predictions=rank_cases(test_cases,weighted)
    results["weighted-v2"]={"classification":metrics.classification({k:v['priority'] for k,v in predictions.items()},test_refs),
        "critical_coverage":metrics.attention(orders['smartir'],test_refs,effective,counts),"predictions":predictions,"order":orders['smartir']}
    results.update(status="completed",limitations=["Laboratory/synthetic evidence is not real-world efficacy",
        "Single reserved group test; no statistical superiority claim", "Probabilities are uncalibrated", "No production deployment"])
    return config,models,results
