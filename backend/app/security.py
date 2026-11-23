import os
from datetime import datetime, timedelta, timezone
import jwt
from argon2 import PasswordHasher
from argon2.low_level import Type
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from .database import Session
from .models import User
from .web_session import COOKIE, browser_request

JWT_SECRET = os.environ.get("JWT_SECRET", "")
if len(JWT_SECRET.encode()) < 32:
    raise RuntimeError("JWT_SECRET debe tener al menos 32 bytes y ser aleatorio")
password_hasher = PasswordHasher(type=Type.ID)
# También se verifica un hash para usuarios inexistentes.
DUMMY_HASH = password_hasher.hash("unused-dummy-password")
bearer = HTTPBearer(auto_error=False)

def issue_token(user):
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": user.id, "iat": now, "exp": now + timedelta(minutes=15), "iss": "smartir-net", "aud": "smartir-api"}, JWT_SECRET, algorithm="HS256")

def current_user(request: Request, credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    unauthorized = HTTPException(401, "Sesión inválida o expirada", headers={"WWW-Authenticate": "Bearer"})
    if request.headers.get('authorization') and credentials is None:
        raise unauthorized
    token = credentials.credentials if credentials else request.cookies.get(COOKIE)
    if not token:
        raise unauthorized
    if credentials is None:
        browser_request(request, mutation=request.method not in ('GET','HEAD','OPTIONS'))
    if len(token)>4096:
        raise unauthorized
    try:
        payload = decode_token(token)
        if not isinstance(payload['sub'],str) or not 1<=len(payload['sub'])<=36:
            raise unauthorized
    except jwt.InvalidTokenError:
        raise unauthorized
    with Session() as db:
        user = db.get(User, payload["sub"])
        if user is None or not user.active:
            raise unauthorized
        if user.eve_only and (user.role != 'analista' or (request.method, request.scope['path']) not in {
                ('POST', '/api/events/import/eve'), ('GET', '/api/auth/me')}):
            raise HTTPException(403, 'Cuenta de servicio restringida a importación EVE')
        return user


def decode_token(token):
    return jwt.decode(token, JWT_SECRET, algorithms=['HS256'], audience='smartir-api', issuer='smartir-net',
        options={'require':['sub','exp','iat','iss','aud']})

def require_roles(*roles):
    def check(user: User = Depends(current_user)):
        if user.role not in roles:
            raise HTTPException(403, "Permisos insuficientes")
        return user
    return check

writers = require_roles("administrador", "analista")
administrators = require_roles("administrador")
