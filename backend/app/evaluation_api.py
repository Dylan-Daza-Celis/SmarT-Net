import csv
import io
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy import select
from . import database
from .security import administrators, current_user
from .models import EvaluationDataset, Experiment, User
from .evaluation_data import GenerateIn, ExperimentIn, ExternalDataset, synthetic, GENERATOR_VERSION
from .experiments import save_dataset, run_experiment, snapshot

router = APIRouter(prefix="/api/evaluation", tags=["Experimental evaluation"])


def dataset_info(row, researcher=False):
    # Deliberately no seed, reference hash, label rationale or provenance narrative.
    return {"id": row.id, "name": row.name if researcher else "Dataset " + row.id[:8], "data_kind": row.data_kind,
            "created_at": row.created_at.isoformat(), "feature_hash": row.feature_hash}


def experiment_info(row, researcher):
    config = json.loads(row.configuration)
    safe_config = {k: v for k, v in config.items() if k != "dataset_configuration"}
    result = {"id": row.id, "dataset_id": row.dataset_id, "created_at": row.created_at.isoformat(),
              "configuration": config if researcher else safe_config, "rankings": json.loads(row.rankings)}
    if researcher:
        result["results"] = json.loads(row.results)
    return result


def get_dataset(db, dataset_id):
    row = db.get(EvaluationDataset, dataset_id)
    if row is None:
        raise HTTPException(404, "Dataset not found")
    return row


def get_experiment(db, experiment_id):
    row = db.get(Experiment, experiment_id)
    if row is None:
        raise HTTPException(404, "Experiment not found")
    return row


@router.get("/datasets")
def datasets(user: User = Depends(current_user)):
    with database.Session() as db:
        return [dataset_info(d, user.role == "administrador") for d in db.scalars(select(EvaluationDataset).order_by(EvaluationDataset.created_at.desc(), EvaluationDataset.id)).all()]


@router.post("/datasets/synthetic", status_code=201)
def generate(data: GenerateIn, user: User = Depends(administrators)):
    with database.Session.begin() as db:
        row = save_dataset(db, synthetic(data.seed, data.count), user.id,
                           {"version": GENERATOR_VERSION, "seed": data.seed, "count": data.count})
        return dataset_info(row)


@router.post("/datasets/import", status_code=201)
async def import_dataset(request: Request, user: User = Depends(administrators)):
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 2 * 1024 * 1024:
            raise HTTPException(413, "Dataset exceeds 2 MiB")
        body.extend(chunk)
    try:
        data = ExternalDataset.model_validate_json(bytes(body))
    except ValidationError:
        # Do not echo reference values or the submitted dataset in validation errors.
        raise HTTPException(422, "Invalid dataset: check schema, authorization, IDs and timestamps")
    with database.Session.begin() as db:
        return dataset_info(save_dataset(db, data, user.id))


@router.get("/datasets/{dataset_id}/cases")
def cases(dataset_id: str, user: User = Depends(current_user)):
    with database.Session() as db:
        get_dataset(db, dataset_id)
        features, _ = snapshot(db, dataset_id)
        return [c.model_dump(mode="json") for c in features]


@router.get("/datasets/{dataset_id}/export")
def export_dataset(dataset_id: str, user: User = Depends(administrators)):
    with database.Session() as db:
        row = get_dataset(db, dataset_id)
        features, references = snapshot(db, dataset_id)
        return {"name": row.name, "data_kind": row.data_kind,
                "provenance": json.loads(row.configuration)["provenance"], "authorized": json.loads(row.configuration)["authorization_declared"],
                "cases": [c.model_dump(mode="json") for c in features], "references": list(references.values())}


@router.post("/experiments", status_code=201)
def create_experiment(data: ExperimentIn, user: User = Depends(administrators)):
    with database.Session.begin() as db:
        dataset = get_dataset(db, str(data.dataset_id))
        row = run_experiment(db, dataset, data.budget, user.id)
        return experiment_info(row, True)


@router.get("/experiments")
def experiments(user: User = Depends(current_user)):
    with database.Session() as db:
        return [{"id": r.id, "dataset_id": r.dataset_id, "created_at": r.created_at.isoformat()}
                for r in db.scalars(select(Experiment).order_by(Experiment.created_at.desc(), Experiment.id)).all()]


@router.get("/experiments/{experiment_id}")
def experiment(experiment_id: str, user: User = Depends(current_user)):
    with database.Session() as db:
        return experiment_info(get_experiment(db, experiment_id), user.role == "administrador")


def csv_report(info, features, references):
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(["record", "strategy", "case_id", "metric", "value", "unit", "status", "reason",
                     "reference_priority", "predicted_priority", "score", "rank", "selected", "incident_id", "event_ids",
                     "reference_json", "features_json"])
    writer.writerow(["configuration", "", "", "experiment", json.dumps({
        "id": info["id"], "created_at": info["created_at"], "configuration": info["configuration"]}, ensure_ascii=True)])
    by_key = {str(c.id): c for c in features}
    budget = info["configuration"]["effective_budget"]
    for strategy, order in info["rankings"]["orders"].items():
        for rank, key in enumerate(order, 1):
            p = info["rankings"]["predictions"][key]
            c = by_key[key]
            writer.writerow(["case", strategy, key, "", "", "", "", "", references.get(key, {}).get("priority"),
                             p["priority"], p["score"], rank, rank <= budget, c.incident_id or "", "|".join(str(e.id) for e in c.events),
                             json.dumps(references.get(key, {}), ensure_ascii=True), json.dumps(c.model_dump(mode="json"), ensure_ascii=True)])
    def flatten(value, path="results"):
        if isinstance(value, dict) and "status" in value and "value" in value:
            writer.writerow(["metric", "", "", path, value["value"], value["unit"], value["status"], value["reason"]])
        elif isinstance(value, dict):
            for key, child in value.items():
                flatten(child, path + "." + key)
        elif path.endswith("matrix") and value is not None:
            writer.writerow(["matrix", "", "", path, json.dumps(value), "counts; rows=true, columns=predicted"])
    flatten(info["results"])
    return out.getvalue()


@router.get("/experiments/{experiment_id}/export")
def export_experiment(experiment_id: str, format: str = "json", user: User = Depends(administrators)):
    if format not in ("json", "csv"):
        raise HTTPException(422, "Format must be json or csv")
    with database.Session() as db:
        row = get_experiment(db, experiment_id)
        info = experiment_info(row, True)
        features, references = snapshot(db, row.dataset_id)
        content = csv_report(info, features, references) if format == "csv" else json.dumps({
            "experiment": info, "features": [c.model_dump(mode="json") for c in features], "references": references}, ensure_ascii=True)
        return Response(content, media_type="text/csv" if format == "csv" else "application/json",
                        headers={"Content-Disposition": f'attachment; filename="experiment-{row.id}.{format}"'})
