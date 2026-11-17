"""Signed browser sessions; the existing API token remains the signing secret."""
import base64
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import urlsplit

from fastapi import HTTPException
from fastapi.responses import JSONResponse

COOKIE_NAME = 'dnb26_admin_session'
SESSION_SECONDS = 365 * 24 * 60 * 60


def bearer_authorized(request):
    token = request.app.state.runtime.settings.api_token
    supplied = request.headers.get('authorization', '')
    return bool(token) and hmac.compare_digest(supplied.encode(), ('Bearer ' + token).encode())


def cookie_session(request):
    token = request.app.state.runtime.settings.api_token
    value = request.cookies.get(COOKIE_NAME, '')
    if not token or not value or len(value) > 2048:
        return None
    try:
        payload, signature = value.split('.')
        expected = hmac.new(token.encode(), ('browser-session-v1:' + payload).encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        session = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
        if session['expires'] <= time.time():
            return None
        return session
    except (ValueError, KeyError, TypeError, UnicodeError):
        return None


def cookie_authorized(request):
    session = cookie_session(request)
    if not session:
        return False
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        return request.headers.get('origin') == session['origin']
    return True


def create_session(request):
    if not bearer_authorized(request):
        raise HTTPException(401, '管理员令牌无效')
    origin = request.headers.get('origin', '')
    try:
        parsed = urlsplit(origin)
        valid = parsed.scheme in ('http', 'https') and bool(parsed.hostname) and not (
            parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment)
    except ValueError:
        valid = False
    if not valid:
        raise HTTPException(400, '持久管理员会话需要有效的网页源地址')
    session = {'origin': origin, 'expires': int(time.time()) + SESSION_SECONDS, 'nonce': secrets.token_hex(16)}
    payload = base64.urlsafe_b64encode(json.dumps(session, separators=(',', ':')).encode()).decode().rstrip('=')
    token = request.app.state.runtime.settings.api_token
    signature = hmac.new(token.encode(), ('browser-session-v1:' + payload).encode(), hashlib.sha256).hexdigest()
    response = JSONResponse({'write_access': True, 'persistent_admin': True, 'expires_at': session['expires']})
    response.set_cookie(COOKIE_NAME, payload + '.' + signature, max_age=SESSION_SECONDS,
                        httponly=True, secure=parsed.scheme == 'https', samesite='strict', path='/api')
    response.headers['Cache-Control'] = 'no-store'
    return response


def delete_session(request):
    if cookie_session(request) and not cookie_authorized(request):
        raise HTTPException(403, '请从已授权网页退出管理员权限')
    response = JSONResponse({'persistent_admin': False})
    response.delete_cookie(COOKIE_NAME, path='/api', httponly=True, samesite='strict')
    response.headers['Cache-Control'] = 'no-store'
    return response
