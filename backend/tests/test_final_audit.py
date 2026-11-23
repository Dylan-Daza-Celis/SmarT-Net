"""Final endpoint inventory and authorization checks, isolated fixture databases only."""
import re
import pytest
from sqlalchemy import select
from app.models import User


def test_all_api_operations_require_identity_before_parsing(api):
    c,_,_=api
    operations=[]
    for path,methods in c.get('/openapi.json').json()['paths'].items():
        if not path.startswith('/api/') or path in ('/api/auth/login','/api/auth/session'):continue
        concrete=re.sub(r'\{[^}]+\}','00000000-0000-0000-0000-000000000000',path)
        for method in methods:
            if method not in ('get','post','patch','delete'):continue
            r=c.request(method,concrete)
            assert r.status_code==401,(method,path,r.status_code)
            assert r.headers['cache-control']=='no-store'
            invalid=c.request(method,concrete,headers={'Authorization':'Bearer invalid'})
            assert invalid.status_code==401,(method,path,invalid.status_code)
            operations.append((method,path))
    assert len(operations)>30


@pytest.mark.parametrize('role',['analista','observador'])
def test_reference_exports_are_not_available_to_operators(api,headers,role):
    c,_,_=api;h=headers(role)
    for path in ('/api/users','/api/analytics/comparisons','/api/ml/runs/missing/export',
                 '/api/evaluation/datasets/missing/export','/api/evaluation/experiments/missing/export'):
        assert c.get(path,headers=h).status_code==403,path


def test_service_account_cannot_query_other_modules_with_valid_jwt(api,headers):
    c,session,_=api
    with session.begin() as db:db.scalar(select(User).where(User.username=='analista')).eve_only=True
    h=headers('analista')
    assert c.get('/api/auth/me',headers=h).status_code==200
    for path in ('/api/incidents','/api/analytics/dashboard','/api/ml/versions','/api/evaluation/datasets','/api/users','/api/operations/metrics'):
        assert c.get(path,headers=h).status_code==403,path


def test_sql_metacharacters_are_literal_filter_data(api,headers,batch):
    c,_,_=api;h=headers('analista')
    assert c.post('/api/events/import',headers=h,json=batch).status_code==200
    before=c.get('/api/stats',headers=h).json()
    r=c.get('/api/analytics/dashboard',headers=h,params={'source':"x'; DROP TABLE events; --"})
    assert r.status_code==200 and r.json()['totals']['events']==0
    assert c.get('/api/stats',headers=h).json()==before
