"""Numeric JSON inference, no pickle/joblib/eval or object reconstruction."""
import numpy as np

FORMAT = "numeric-pipeline-json-v1"


def encode(pipeline, algorithm):
    pre, clf = pipeline.named_steps["preprocess"], pipeline.named_steps["classifier"]
    scaler = pre.named_transformers_["numeric"]
    encoder = pre.named_transformers_["categorical"]
    result = {"format": FORMAT,"algorithm":algorithm,"classes":clf.classes_.tolist(),
        "mean":scaler.mean_.tolist(),"scale":scaler.scale_.tolist(),
        "categories":encoder.categories_[0].tolist(),"feature_names":pre.get_feature_names_out().tolist()}
    if algorithm == "logistic":
        result.update(coef=clf.coef_.tolist(),intercept=clf.intercept_.tolist())
    elif algorithm == "forest":
        result["importance"] = clf.feature_importances_.tolist()
        result["trees"] = [{"left":e.tree_.children_left.tolist(),"right":e.tree_.children_right.tolist(),
            "feature":e.tree_.feature.tolist(),"threshold":e.tree_.threshold.tolist(),
            "values":e.tree_.value[:,0,:].tolist()} for e in clf.estimators_]
    else:
        raise ValueError("Unsupported algorithm")
    return result


def probabilities(artifact, rows):
    if artifact.get("format") != FORMAT or artifact.get("algorithm") not in ("logistic","forest"):
        raise ValueError("Unsupported artifact format")
    numeric = np.asarray([r[:5] for r in rows],dtype=float)
    z=(numeric-np.asarray(artifact["mean"]))/np.asarray(artifact["scale"])
    category=np.asarray([[float(r[5]==c) for c in artifact["categories"]] for r in rows])
    x=np.column_stack((z,category))
    if not np.isfinite(x).all():
        raise ValueError("Nonfinite model input")
    if artifact["algorithm"]=="logistic":
        scores=x@np.asarray(artifact["coef"]).T+np.asarray(artifact["intercept"])
        scores-=scores.max(axis=1,keepdims=True)
        p=np.exp(scores);p/=p.sum(axis=1,keepdims=True)
    else:
        # sklearn trees evaluate float32 transformed inputs.
        x=x.astype(np.float32)
        p=np.zeros((len(rows),len(artifact["classes"])))
        for tree in artifact["trees"]:
            for i,row in enumerate(x):
                node=0
                for _ in range(len(tree["left"])+1):
                    if tree["left"][node]==-1:
                        v=np.asarray(tree["values"][node],dtype=float)
                        p[i]+=v/v.sum()
                        break
                    # numpy 2 scalar promotion could round a Python threshold to float32.
                    node=tree["left"][node] if float(row[tree["feature"][node]])<=tree["threshold"][node] else tree["right"][node]
                else:
                    raise ValueError("Invalid tree")
        p/=len(artifact["trees"])
    if not np.isfinite(p).all() or not np.allclose(p.sum(axis=1),1):
        raise ValueError("Invalid model probabilities")
    return p
