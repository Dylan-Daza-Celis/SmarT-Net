import os
from datetime import datetime, timedelta, timezone
import jwt
from argon2 import PasswordHasher
from argon2.low_level import Type
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from .database import Session
from .models import User

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

def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    unauthorized = HTTPException(401, "Sesión inválida o expirada", headers={"WWW-Authenticate": "Bearer"})
    if credentials is None:
        raise unauthorized
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"], audience="smartir-api", issuer="smartir-net", options={"require": ["sub", "exp", "iat", "iss", "aud"]})
    except jwt.InvalidTokenError:
        raise unauthorized
    with Session() as db:
        user = db.get(User, payload["sub"])
        if user is None or not user.active:
            raise unauthorized
        return user

def require_roles(*roles):
    def check(user: User = Depends(current_user)):
        if user.role not in roles:
            raise HTTPException(403, "Permisos insuficientes")
        return user
    return check

writers = require_roles("administrador", "analista")
administrators = require_roles("administrador")
