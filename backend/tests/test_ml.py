import json
from copy import deepcopy
from uuid import uuid4
import numpy as np
import pytest
from alembic import command
from pydantic import ValidationError
from sqlalchemy import text
from app.ml_data import laboratory, MLDatasetIn, annotate
from app.ml_engine import row, pipeline, fit_compare, FEATURES, record_fingerprint
from app.ml_artifact import encode, probabilities
from app.evaluation_metrics import CLASSES


@pytest.fixture(scope="module")
def fitted():
    manifest=laboratory()
    refs={str(r.case_id):r.model_dump(mode='json') for r in manifest.dataset.references}
    membership={str(k):str(v) for k,v in manifest.groups.items()}
    cfg,artifacts,result=fit_compare(manifest.dataset.cases,refs,membership,202606,10)
    return manifest,refs,membership,cfg,artifacts,result


def test_lab_reproducibility_and_nonweighted_labels():
    a,b=laboratory(),laboratory()
    assert a.model_dump()==b.model_dump()
    assert a.model_dump()!=laboratory(seed=42).model_dump()
    assert {r.priority for r in a.dataset.references}==set(CLASSES)
    assert len({c.event_type for c in a.dataset.cases})==6
    assert annotate({'essential_outage':True,'regulated_exposure':False,'compromise':False,'malicious':True})=='Crítica'
    assert 'weighted' not in FEATURES and 'priority' not in FEATURES


def test_no_reference_id_group_or_score_in_features(fitted):
    manifest,refs,groups,*_=fitted
    case=manifest.dataset.cases[0]
    before=row(case)
    changed=deepcopy(manifest)
    changed.dataset.references[0].priority='Baja'
    changed.dataset.references[0].rationale='Entirely different reference'
    changed.groups[case.id]=uuid4()
    changed.dataset.cases[0].id=uuid4()
    assert row(changed.dataset.cases[0])==before
    payload=case.model_dump(mode='json');payload['reference_priority']='Crítica'
    from app.evaluation_data import FeatureCase
    with pytest.raises(ValidationError):FeatureCase.model_validate(payload)


def test_group_isolation_cv_and_test_support(fitted):
    manifest,refs,groups,cfg,art,result=fitted
    assert result['status']=='completed'
    split=cfg['partition']
    assert len(cfg['cv_partition'])==3
    assert not set(split['train'])&set(split['test'])
    assert not set(split['train_groups'])&set(split['test_groups'])
    for fold in cfg['cv_partition']:
        assert set(fold['train']+fold['validation']).issubset(split['train'])
        assert not set(fold['train_groups'])&set(fold['validation_groups'])
    assert all(v>0 for v in split['test_support'].values())
    test_keys=set(split['test'])
    assert set(result['logistic']['predictions'])==set(result['forest']['predictions'])==set(result['weighted-v2']['predictions'])==test_keys
    for name in ('logistic','forest','weighted-v2'):
        assert sum(map(sum,result[name]['classification']['matrix']))==len(test_keys)


def test_preprocessing_train_only_and_safe_inference(fitted):
    manifest,refs,groups,cfg,art,result=fitted
    train=[c for c in sorted(manifest.dataset.cases,key=lambda c:str(c.id)) if str(c.id) in cfg['partition']['train']]
    test=[c for c in sorted(manifest.dataset.cases,key=lambda c:str(c.id)) if str(c.id) in cfg['partition']['test']]
    x=np.asarray([row(c) for c in train],dtype=object)
    y=np.asarray([refs[str(c.id)]['priority'] for c in train])
    for name in ('logistic','forest'):
        model=pipeline(name,202606);model.fit(x,y)
        encoded=json.loads(json.dumps(encode(model,name)))
        assert np.allclose(encoded['mean'],x[:,:5].astype(float).mean(axis=0))
        assert np.allclose(probabilities(encoded,[row(c) for c in test]),model.predict_proba(np.asarray([row(c) for c in test],dtype=object)),atol=1e-9)
        unseen=row(test[0]);unseen[5]='unseen-category'
        assert np.isclose(probabilities(encoded,[unseen])[0].sum(),1)
    with pytest.raises(ValueError):probabilities({'format':'pickle'},[row(test[0])])


def test_repeated_training_exact_reproducibility(fitted):
    manifest,refs,groups,cfg,art,result=fitted
    other_cfg,other_art,other_result=fit_compare(list(reversed(manifest.dataset.cases)),refs,groups,202606,10)
    assert cfg==other_cfg and art==other_art and result==other_result


def test_insufficient_missing_and_one_class_data():
    m=laboratory(groups=16)
    refs={str(r.case_id):r.model_dump(mode='json') for r in m.dataset.references}
    groups={str(k):str(v) for k,v in m.groups.items()}
    refs.pop(str(m.dataset.cases[0].id))
    _,art,r=fit_compare(m.dataset.cases,refs,groups,1,2)
    assert not art and r['status']=='No calculable'
    for ref in refs.values():ref['priority']='Baja'
    refs[str(m.dataset.cases[0].id)]={'priority':'Baja'}
    _,art,r=fit_compare(m.dataset.cases,refs,groups,1,2)
    assert not art and 'groups' in r['reason']


@pytest.mark.parametrize('role',['analista','observador'])
def test_permissions_and_old_dataset_block(api,headers,role):
    client,_,_=api
    h=headers(role)
    assert client.get('/api/ml/versions').status_code==401
    for path,payload in [('datasets/laboratory',{}),('datasets/import',{}),('train',{'dataset_id':str(uuid4())})]:
        assert client.post('/api/ml/'+path,json=payload,headers=h).status_code==403
    admin=headers('administrador')
    old=client.post('/api/evaluation/datasets/synthetic',json={'count':6},headers=admin).json()['id']
    assert client.post('/api/ml/train',json={'dataset_id':old},headers=admin).status_code==422


def test_api_training_blinding_inference_and_persistence(api,headers):
    client,session,_=api
    admin=headers('administrador')
    did=client.post('/api/ml/datasets/laboratory',json={},headers=admin).json()['id']
    trained=client.post('/api/ml/train',json={'dataset_id':did},headers=admin)
    assert trained.status_code==201
    run=trained.json();assert run['status']=='completed'
    case=client.get(f'/api/evaluation/datasets/{did}/cases',headers=admin).json()[0]
    for role in ('analista','observador'):
        h=headers(role)
        visible=client.get('/api/ml/runs/'+run['id'],headers=h).json()
        assert 'results' not in visible and 'configuration' not in visible
        assert client.get('/api/ml/runs/'+run['id']+'/export',headers=h).status_code==403
        prediction=client.post('/api/ml/runs/'+run['id']+'/predict',json=case,headers=h).json()
        assert prediction['priority'] in CLASSES and prediction['uncalibrated'] is True
        assert sum(prediction['probabilities'].values())==pytest.approx(1)
    exported=client.get('/api/ml/runs/'+run['id']+'/export',headers=admin).json()
    assert exported['artifacts']['forest']['format']=='numeric-pipeline-json-v1'
    assert client.post('/api/ml/runs/'+run['id']+'/predict?algorithm=evil',json=case,headers=admin).status_code==422
    with session() as db:
        assert db.execute(text('SELECT count(*) FROM incidents')).scalar()==0
        assert db.execute(text('SELECT count(*) FROM risk_evaluations')).scalar()==0
    from app.models import MLRun
    with session.begin() as db:
        stored=db.get(MLRun,run['id'])
        payload=json.loads(stored.artifacts)
        payload['logistic']['mean'][0]+=1
        stored.artifacts=json.dumps(payload)
    assert client.post('/api/ml/runs/'+run['id']+'/predict',json=case,headers=admin).status_code==409


def test_duplicate_records_bad_groups_and_insufficient_run(api,headers):
    client,_,_=api
    h=headers('administrador')
    manifest=laboratory(groups=16).model_dump(mode='json')
    # Same event content with different UUIDs is still a duplicate case.
    duplicate=deepcopy(manifest)
    duplicate['dataset']['cases'][1]['events']=deepcopy(duplicate['dataset']['cases'][0]['events'])
    duplicate['dataset']['cases'][1]['event_type']=duplicate['dataset']['cases'][0]['event_type']
    for event in duplicate['dataset']['cases'][1]['events']:event['id']=str(uuid4())
    assert client.post('/api/ml/datasets/import',json=duplicate,headers=h).status_code==422
    bad=deepcopy(manifest);bad['groups'].pop(next(iter(bad['groups'])))
    assert client.post('/api/ml/datasets/import',json=bad,headers=h).status_code==422
    dependent=deepcopy(manifest)
    incident=str(uuid4())
    dependent['dataset']['cases'][0]['incident_id']=incident
    dependent['dataset']['cases'][3]['incident_id']=incident
    assert client.post('/api/ml/datasets/import',json=dependent,headers=h).status_code==422
    invalid_source=deepcopy(manifest);invalid_source['label_source']='weighted-v2'
    assert client.post('/api/ml/datasets/import',json=invalid_source,headers=h).status_code==422
    manifest['dataset']['references']=[]
    did=client.post('/api/ml/datasets/import',json=manifest,headers=h).json()['id']
    assert client.post('/api/ml/datasets/import',json=manifest,headers=h).status_code==409
    run=client.post('/api/ml/train',json={'dataset_id':did},headers=h).json()
    assert run['status']=='insufficient_data' and run['results']['status']=='No calculable'
    case=manifest['dataset']['cases'][0]
    assert client.post('/api/ml/runs/'+run['id']+'/predict',json=case,headers=h).status_code==409


@pytest.mark.parametrize('api',['0005'],indirect=True)
def test_0006_additive_migration_preserves_experiments(api):
    _,session,config=api
    with session.begin() as db:
        uid=db.execute(text('SELECT id FROM users LIMIT 1')).scalar()
        db.execute(text("INSERT INTO evaluation_datasets(id,author_id,name,data_kind,configuration,feature_hash,created_at) VALUES('d',:uid,'old','synthetic','{}','old',CURRENT_TIMESTAMP)"),{'uid':uid})
        db.execute(text("INSERT INTO experiments(id,dataset_id,author_id,configuration,rankings,results,created_at) VALUES('x','d',:uid,'{}','{}','{}',CURRENT_TIMESTAMP)"),{'uid':uid})
        tables=['users','events','incidents','risk_evaluations','event_evidence','evaluation_datasets','evaluation_cases','evaluation_references','evaluation_event_links','experiments','incident_history','response_actions']
        before={t:db.execute(text(f'SELECT * FROM {t}')).mappings().all() for t in tables}
    command.upgrade(config,'head');command.upgrade(config,'head')
    with session() as db:
        assert db.execute(text('SELECT version_num FROM alembic_version')).scalar()=='0009'
        for table in tables:
            rows=db.execute(text(f'SELECT * FROM {table}')).mappings().all()
            assert [{k:r[k] for k in before[table][0]} for r in rows]==before[table] if before[table] else rows==[]
