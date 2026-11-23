"""Cookie transport regressions; isolated fixture database, no stored browser credentials."""
from datetime import datetime, timezone, timedelta
import jwt
import pytest
from sqlalchemy import select
from app import main, security
from app.abuse import AbuseController
from app.models import User
from app.web_session import COOKIE

CSRF={'Origin':'http://localhost','X-SmartIR-CSRF':'1'}


def web_login(c,role='analista',headers=None):
    return c.post('/api/auth/session',json={'username':role,'password':'test-password-123'},headers=CSRF if headers is None else headers)


@pytest.mark.parametrize('role',['administrador','analista','observador'])
def test_cookie_restore_live_identity_and_logout(api,role):
    c,session,_=api
    response=web_login(c,role)
    assert response.status_code==200 and response.json()['user']['role']==role
    assert 'access_token' not in response.json() and 'password' not in response.text
    cookie=response.headers['set-cookie']
    assert 'HttpOnly' in cookie and 'SameSite=strict' in cookie and 'Path=/api' in cookie
    assert 'Max-Age=900' in cookie and 'Domain=' not in cookie and 'Secure' not in cookie
    original=response.json()['expires_at']
    assert c.get('/api/auth/session').json()['expires_at']==original
    assert 'set-cookie' not in c.get('/api/auth/session').headers
    assert c.get('/api/auth/me').json()['role']==role
    assert c.get('/api/stats').status_code==200
    assert c.get('/api/users').status_code==(200 if role=='administrador' else 403)
    assert c.delete('/api/auth/session',headers=CSRF).status_code==204
    assert c.get('/api/auth/session').status_code==401 and c.get('/api/stats').status_code==401


@pytest.mark.parametrize('headers',[{}, {'Origin':'http://localhost'}, {'X-SmartIR-CSRF':'1'},
    {'Origin':'http://localhost.evil.example','X-SmartIR-CSRF':'1'}, {'Origin':'null','X-SmartIR-CSRF':'1'}])
def test_browser_login_requires_origin_and_custom_header(api,headers):
    c,_,_=api
    response=web_login(c,headers=headers)
    assert response.status_code==403 and 'set-cookie' not in response.headers


def test_cookie_csrf_enforced_for_writes_exports_and_logout_bearer_still_works(api,headers,batch):
    c,_,_=api;assert web_login(c).status_code==200
    assert c.post('/api/events/import',json=batch).status_code==403
    assert c.post('/api/analytics/reports',json={}).status_code==403
    assert c.delete('/api/auth/session').status_code==403
    assert c.get('/api/stats',headers={'Origin':'https://evil.example'}).status_code==403
    assert c.post('/api/events/import',json=batch,headers=CSRF).status_code==200
    assert c.post('/api/events/import',json=batch,headers=headers('analista')).status_code==200
    for authorization in ('Bearer invalid','Basic invalid'):
        assert c.get('/api/stats',headers={'Authorization':authorization}).status_code==401


def test_inactive_changed_role_expired_and_tampered_cookie(api):
    c,session,_=api
    assert web_login(c).status_code==200
    with session.begin() as db:
        user=db.scalar(select(User).where(User.username=='analista'));user.role='observador'
    assert c.get('/api/auth/session').json()['user']['role']=='observador'
    assert c.post('/api/analytics/reports',json={},headers=CSRF).status_code==403
    with session.begin() as db:db.scalar(select(User).where(User.username=='analista')).active=False
    assert c.get('/api/auth/session').status_code==401
    c.cookies.clear();assert web_login(c,'administrador').status_code==200
    payload=security.decode_token(c.cookies.get(COOKIE));payload['exp']=datetime.now(timezone.utc)-timedelta(seconds=1)
    c.cookies.clear();c.cookies.set(COOKIE,jwt.encode(payload,security.JWT_SECRET,algorithm='HS256'),path='/api')
    assert c.get('/api/auth/session').status_code==401
    c.cookies.clear();c.cookies.set(COOKIE,'tampered',path='/api')
    assert c.get('/api/stats').status_code==401
    assert c.delete('/api/auth/session',headers=CSRF).status_code==204  # expired cookie may always be cleared


def test_browser_service_account_rejected_without_cookie_and_login_rate_shared(api,monkeypatch):
    c,session,_=api
    with session.begin() as db:db.scalar(select(User).where(User.username=='analista')).eve_only=True
    assert web_login(c).status_code==403 and COOKIE not in c.cookies
    control=AbuseController(login_limit=2);monkeypatch.setattr(main.app.state,'abuse',control)
    assert web_login(c,'administrador').status_code==200
    assert c.post('/api/auth/login',json={'username':'missing','password':'wrong'}).status_code==401
    r=web_login(c,'administrador');assert r.status_code==429 and int(r.headers['Retry-After'])>0


def test_cookie_secure_https_and_remote_http_rejected(api):
    c,_,_=api
    c.base_url='https://localhost'
    r=web_login(c,headers={'Origin':'https://localhost','X-SmartIR-CSRF':'1'})
    assert r.status_code==200 and 'Secure' in r.headers['set-cookie']
    assert c.get('/api/auth/session').status_code==200
    c.cookies.clear();c.base_url='http://api'
    r=web_login(c,headers={'Origin':'http://api','X-SmartIR-CSRF':'1'})
    assert r.status_code==403 and 'set-cookie' not in r.headers


def test_safe_validation_and_original_bearer_contract(api):
    c,_,_=api
    marker='do-not-echo-'+'x'*200
    r=c.post('/api/auth/session',json={'username':'missing','password':marker},headers=CSRF)
    assert r.status_code==422 and marker not in r.text and r.headers['cache-control']=='no-store'
    r=c.post('/api/auth/login',json={'username':'observador','password':'test-password-123'})
    assert r.status_code==200 and r.json()['expires_in']==900 and 'set-cookie' not in r.headers
    assert c.get('/api/stats',headers={'Authorization':'Bearer '+r.json()['access_token']}).status_code==200
