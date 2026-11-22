"""Bounded analytical reads and immutable sanitized report exports."""
import json
from typing import Annotated, Literal
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select, func, or_, and_
from . import database, lifecycle, analytics
from .analytics import Filters, QueryFilters
from .analytical_reports import csv_bytes, pdf_bytes
from .models import User, Event, Incident, AnalyticsReport, MLRun, EvaluationDataset
from .security import current_user, writers, administrators
from .experiments import canonical, digest
from .abuse import analytics_reader, report_writer, export_reader, research_exporter

router = APIRouter(prefix='/api/analytics', tags=['Analytics and reports'])
MAX_REPORT_ROWS = 2000
MAX_REPORT_BYTES = 5*1024*1024


@router.get('/dashboard')
def dashboard(q: Annotated[QueryFilters, Query()], user: User = Depends(analytics_reader)):
    with database.Session() as db:
        lifecycle.read_snapshot(db)
        # Include first page in the SAME database snapshot as all charts/indicators.
        return {**analytics.dashboard(db, q), 'incidents': analytics.incident_page(db, q, q.offset, q.limit)}


@router.get('/incidents')
def incidents(q: Annotated[QueryFilters, Query()], user: User = Depends(analytics_reader)):
    with database.Session() as db:
        lifecycle.read_snapshot(db)
        return analytics.incident_page(db, q, q.offset, q.limit)


@router.get('/options')
def options(offset: int = Query(0, ge=0, le=100000), limit: int = Query(100, ge=1, le=100), user: User = Depends(current_user)):
    with database.Session() as db:
        lifecycle.read_snapshot(db)
        sources = db.scalars(select(Event.source).distinct().order_by(Event.source).offset(offset).limit(limit+1)).all()
        visible = or_(and_(User.active.is_(True), User.eve_only.is_(False), User.role.in_(['administrador', 'analista'])),
            select(Incident.id).where(Incident.assigned_to_id == User.id).exists())
        users = db.execute(select(User.id, User.username, User.active).where(visible)
            .order_by(User.username).offset(offset).limit(limit+1)).mappings().all()
        return {'sources': sources[:limit], 'assignees': [dict(u) for u in users[:limit]],
                'more_sources': len(sources)>limit, 'more_assignees': len(users)>limit, 'offset': offset, 'limit': limit}


@router.post('/reports', status_code=201)
def create_report(q: Filters, user: User = Depends(report_writer)):
    # Expensive aggregation uses an MVCC read snapshot, without the operational mutation lock.
    with database.Session() as db:
        lifecycle.read_snapshot(db)
        lifecycle.actor(db, user.id)
        cohort, _ = analytics.cohorts(q)
        total = db.scalar(select(func.count()).select_from(cohort))
        if total > MAX_REPORT_ROWS:
            raise HTTPException(413, 'Reporte supera 2000 incidentes; reduzca periodo o filtros. No se trunca.')
        timestamp = lifecycle.now()
        payload = {'id': str(uuid4()), 'generated_at': lifecycle.iso(timestamp),
            'dashboard': analytics.dashboard(db, q),
            'incidents': analytics.incident_page(db, q, 0, MAX_REPORT_ROWS, public=True)['items']}
        body = canonical(payload)
        if len(body.encode()) > MAX_REPORT_BYTES:
            raise HTTPException(413, 'Snapshot supera 5 MiB; reduzca filtros')
    with database.Session.begin() as db:
        # Recheck a role/deactivation change after computation; only the short INSERT is serialized.
        lifecycle.mutation_lock(db); actor = lifecycle.actor(db, user.id)
        report = AnalyticsReport(id=payload['id'], author_id=actor.id, created_at=timestamp, payload=body, content_sha256=digest(payload))
        db.add(report)
        return {'id': report.id, 'created_at': payload['generated_at'], 'content_sha256': report.content_sha256, 'incidents': total}


@router.get('/reports')
def reports(offset: int = Query(0, ge=0, le=100000), limit: int = Query(20, ge=1, le=100), user: User = Depends(current_user)):
    with database.Session() as db:
        lifecycle.read_snapshot(db)
        rows = db.execute(select(AnalyticsReport.id, AnalyticsReport.created_at, AnalyticsReport.content_sha256)
            .order_by(AnalyticsReport.created_at.desc(), AnalyticsReport.id).offset(offset).limit(limit)).mappings()
        return {'items': [{**dict(r), 'created_at': lifecycle.iso(r['created_at'])} for r in rows],
                'total': db.scalar(select(func.count()).select_from(AnalyticsReport)), 'offset': offset, 'limit': limit}


@router.get('/reports/{report_id}')
def export_report(report_id: str, format: Literal['json', 'csv', 'pdf'] = 'json', user: User = Depends(export_reader)):
    with database.Session() as db:
        row = db.get(AnalyticsReport, report_id)
        if row is None: raise HTTPException(404, 'Reporte no encontrado')
        try:
            payload = json.loads(row.payload)
            valid=digest(payload)==row.content_sha256
        except (ValueError,TypeError):valid=False
        if not valid: raise HTTPException(409, 'Integridad del snapshot no verificable')
        if format == 'json': content, mime = canonical({'payload': payload, 'content_sha256': row.content_sha256}), 'application/json'
        elif format == 'csv': content, mime = csv_bytes(payload, row.content_sha256), 'text/csv'
        else: content, mime = pdf_bytes(payload, row.content_sha256), 'application/pdf'
        return Response(content, media_type=mime, headers={'Content-Disposition': f'attachment; filename="smartir-{row.id}.{format}"',
            'X-Content-SHA256': row.content_sha256, 'Cache-Control': 'no-store'})


@router.get('/comparisons')
def comparisons(offset: int = Query(0, ge=0, le=100000), limit: int = Query(10, ge=1, le=20), user: User = Depends(research_exporter)):
    # Independent frozen experimental cohorts: NEVER filter/recalculate their stored metrics using incident attributes.
    with database.Session() as db:
        lifecycle.read_snapshot(db)
        query = select(MLRun.id, MLRun.created_at, MLRun.status, MLRun.configuration, MLRun.results, EvaluationDataset.data_kind
            ).join(EvaluationDataset, EvaluationDataset.id == MLRun.dataset_id).order_by(MLRun.created_at.desc(), MLRun.id).offset(offset).limit(limit)
        rows = []
        missing = {'value': None, 'status': 'No calculable', 'unit': 'ratio', 'reason': 'Sin resultado registrado suficiente'}
        for run in db.execute(query).mappings():
            config, results = json.loads(run['configuration']), json.loads(run['results'])
            models = []
            for name in ('weighted-v2', 'logistic', 'forest'):
                result = results.get(name, {}); classification = result.get('classification', {})
                models.append({'model': name, 'accuracy': classification.get('accuracy', missing),
                    'macro_f1': classification.get('macro', {}).get('f1', missing),
                    'critical_coverage': result.get('critical_coverage', {}).get('critical_coverage', missing),
                    'support': classification.get('total'), 'budget': config.get('effective_budget')})
            rows.append({'id': run['id'], 'created_at': lifecycle.iso(run['created_at']), 'status': run['status'],
                'data_kind': run['data_kind'], 'protocol': config.get('protocol'), 'operational': False, 'models': models})
        return {'items': rows, 'total': db.scalar(select(func.count()).select_from(MLRun)), 'offset': offset, 'limit': limit,
                'scope': 'Cohortes experimentales congeladas independientes; los filtros operativos no se aplican y estos valores no integran sus indicadores/exportaciones.',
                'limitation': 'Simulación offline, no comparación causal ni evidencia de eficacia en redes reales. Sin entrenamiento nuevo.'}
