"""Browser transport for existing short-lived JWTs. No refresh token or schema change."""
import os
from fastapi import HTTPException

COOKIE = 'smartir_session'
COOKIE_PATH = '/api'


def browser_request(request, *, mutation=False):
    # Do not trust X-Forwarded-* here. HTTP is permitted only for the local prototype.
    if request.url.scheme != 'https' and request.url.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise HTTPException(403, 'La sesión web requiere HTTPS o loopback')
    origin = request.headers.get('origin')
    allowed = {s.strip() for s in os.environ.get('SMARTIR_WEB_ORIGINS',
        'http://localhost:5173,http://127.0.0.1:5173').split(',') if s.strip()}
    allowed.add(str(request.base_url).rstrip('/'))
    if (origin is not None and origin not in allowed) or (mutation and not origin):
        raise HTTPException(403, 'Origen de sesión no permitido')
    if mutation and request.headers.get('x-smartir-csrf') != '1':
        raise HTTPException(403, 'Falta protección CSRF de sesión web')


def set_session(response, request, token):
    response.set_cookie(COOKIE, token, max_age=900, path=COOKIE_PATH,
        httponly=True, secure=request.url.scheme == 'https', samesite='strict')


def clear_session(response, request):
    response.delete_cookie(COOKIE, path=COOKIE_PATH, httponly=True,
        secure=request.url.scheme == 'https', samesite='strict')
