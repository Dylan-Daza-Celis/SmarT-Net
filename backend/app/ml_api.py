"""Experimental ML endpoints; no artifact upload or operational scoring hook."""
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy import select, text
from . import database
from .security import current_user, administrators
from .models import User, MLRun, EvaluationDataset
from .evaluation_api import get_dataset, dataset_info
from .evaluation_data import FeatureCase
from .experiments import save_dataset, snapshot, canonical, digest
from .ml_data import LabIn, TrainIn, MLDatasetIn, laboratory, LAB_VERSION
from .ml_engine import fit_compare, row, record_fingerprint, VERSION, FEATURES
from .ml_artifact import probabilities

router=APIRouter(prefix="/api/ml",tags=["Experimental supervised learning"])


def save_ml_dataset(db,manifest,user_id,generator=None):
    fingerprints=[record_fingerprint(c) for c in manifest.dataset.cases]
    if len(set(fingerprints)) != len(fingerprints):
        raise HTTPException(422,"Duplicate event content across cases, even with different UUIDs")
    if db.bind.dialect.name=="postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(739031506)"))
    elif db.bind.dialect.name=="sqlite":
        db.execute(text("BEGIN IMMEDIATE"))
    manifest_hash=digest(manifest.model_dump(mode="json"))
    feature_hash=digest(sorted([c.model_dump(mode="json") for c in manifest.dataset.cases],key=lambda c:c['id']))
    for previous in db.scalars(select(EvaluationDataset).where(EvaluationDataset.feature_hash==feature_hash)).all():
        if (json.loads(previous.configuration).get('generator') or {}).get('manifest_hash')==manifest_hash:
            raise HTTPException(409,"Identical ML dataset already exists: "+previous.id)
    meta={"ml_protocol":"annotated-groups-v1","generator":generator,
          "manifest_hash":manifest_hash,
          "annotation_policy":manifest.annotation_policy,"label_source":manifest.label_source,
          "groups":{str(k):str(v) for k,v in manifest.groups.items()}}
    dataset=save_dataset(db,manifest.dataset,user_id,meta)
    return dataset


@router.post("/datasets/laboratory",status_code=201)
def generate(data:LabIn,user:User=Depends(administrators)):
    with database.Session.begin() as db:
        return dataset_info(save_ml_dataset(db,laboratory(data.seed,data.groups),user.id,
            {"version":LAB_VERSION,"seed":data.seed,"groups":data.groups}),True)


@router.post("/datasets/import",status_code=201)
async def import_dataset(request:Request,user:User=Depends(administrators)):
    body=bytearray()
    async for chunk in request.stream():
        if len(body)+len(chunk)>2*1024*1024:
            raise HTTPException(413,"Dataset exceeds 2 MiB")
        body.extend(chunk)
    try:
        data=MLDatasetIn.model_validate_json(bytes(body))
    except ValidationError:
        raise HTTPException(422,"Invalid authorized dataset, references, group map or annotation policy")
    with database.Session.begin() as db:
        return dataset_info(save_ml_dataset(db,data,user.id),True)


def get_run(db,run_id):
    run=db.get(MLRun,run_id)
    if run is None:
        raise HTTPException(404,"Model run not found")
    return run


def info(run,researcher=False):
    config=json.loads(run.configuration)
    result={"id":run.id,"dataset_id":run.dataset_id,"created_at":run.created_at.isoformat(),
            "status":run.status,"protocol":config["protocol"],"algorithms":sorted(json.loads(run.artifacts)),"operational":False}
    if researcher:
        result.update(configuration=json.loads(run.configuration),results=json.loads(run.results))
        # Coefficients / importance are only visible to the researcher.
        result["interpretation"]={name:{k:v for k,v in a.items() if k in ("feature_names","classes","coef","intercept","importance")}
                                  for name,a in json.loads(run.artifacts).items()}
    return result


@router.post("/train",status_code=201)
def train(data:TrainIn,user:User=Depends(administrators)):
    with database.Session.begin() as db:
        dataset=get_dataset(db,str(data.dataset_id))
        manifest=json.loads(dataset.configuration).get("generator") or {}
        if manifest.get("ml_protocol")!="annotated-groups-v1":
            raise HTTPException(422,"Explicit independent annotation and groups required; iteration-05 generator is not predictive evidence")
        cases,references=snapshot(db,dataset.id)
        fingerprints=[record_fingerprint(c) for c in cases]
        if len(set(fingerprints))!=len(fingerprints):
            raise HTTPException(422,"Duplicate cases detected")
        config,artifacts,results=fit_compare(cases,references,manifest["groups"],data.seed,data.budget)
        config.update(dataset_id=dataset.id,feature_hash=dataset.feature_hash,data_kind=dataset.data_kind,
                      annotation_manifest=manifest,artifact_hash=digest(artifacts),application_version="0.6.0")
        run=MLRun(dataset_id=dataset.id,author_id=user.id,status="completed" if artifacts else "insufficient_data",
                  configuration=canonical(config),artifacts=canonical(artifacts),results=canonical(results))
        db.add(run);db.flush()
        return info(run,True)


@router.get("/versions")
def versions(user:User=Depends(current_user)):
    with database.Session() as db:
        return [info(r) for r in db.scalars(select(MLRun).order_by(MLRun.created_at.desc(),MLRun.id)).all()]


@router.get("/runs/{run_id}")
def comparison(run_id:str,user:User=Depends(current_user)):
    with database.Session() as db:
        return info(get_run(db,run_id),user.role=="administrador")


@router.post("/runs/{run_id}/predict")
def predict(run_id:str,case:FeatureCase,algorithm:str="logistic",user:User=Depends(current_user)):
    if algorithm not in ("logistic","forest"):
        raise HTTPException(422,"Unknown classifier")
    with database.Session() as db:
        run=get_run(db,run_id)
        if run.status!="completed":
            raise HTTPException(409,"No trained model: insufficient data")
        artifacts=json.loads(run.artifacts)
        config=json.loads(run.configuration)
        if config.get("feature_schema")!="incident-aggregates-v1" or config.get("features")!=FEATURES:
            raise HTTPException(409,"Unsupported frozen feature schema")
        if digest(artifacts)!=config["artifact_hash"]:
            raise HTTPException(409,"Model artifact integrity mismatch")
        artifact=artifacts[algorithm]
        p=probabilities(artifact,[row(case)])[0]
        index=int(p.argmax())
        return {"model_id":run.id,"algorithm":algorithm,"protocol":config["protocol"],"priority":artifact["classes"][index],
                "probabilities":dict(zip(artifact['classes'],map(float,p))),"maximum_probability":float(p[index]),
                "uncalibrated":True,"operational":False,"note":"Not a validated confidence or production prediction"}


@router.get("/runs/{run_id}/export")
def export(run_id:str,user:User=Depends(administrators)):
    with database.Session() as db:
        run=get_run(db,run_id)
        cases,references=snapshot(db,run.dataset_id)
        data={"run":info(run,True),"artifacts":json.loads(run.artifacts),
              "features":[c.model_dump(mode='json') for c in cases],"references":references}
        return Response(canonical(data),media_type="application/json",
                        headers={"Content-Disposition":f'attachment; filename="ml-{run.id}.json"'})
