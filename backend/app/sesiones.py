"""Cuentas y sesiones. Las contraseñas nunca se guardan en texto plano."""
import hashlib
import hmac
import os
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from bd.conexion import get_session
from bd.modelos import User, UserSession

COOKIE = 'ballers_session'
CSRF_COOKIE = 'XSRF-TOKEN'
ITERATIONS = 600_000
GUEST_SECONDS = 2 * 60 * 60
guests = {}
guest_lock = threading.RLock()
attempts = {}
rate_lock = threading.Lock()


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def hash_password(password):
    salt = secrets.token_hex(16)
    result = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), ITERATIONS)
    return f'pbkdf2_sha256${ITERATIONS}${salt}${result.hex()}'


def verify_password(password, stored):
    try:
        algorithm, count, salt, expected = stored.split('$')
        if algorithm != 'pbkdf2_sha256':
            return False
        result = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(count))
        return hmac.compare_digest(result.hex(), expected)
    except (ValueError, TypeError):
        return False


DUMMY_PASSWORD = hash_password(secrets.token_urlsafe(20))


def check_rate(request, category):
    address = request.client.host if request.client else 'local'
    key = (address, category)
    now = time.monotonic()
    with rate_lock:
        for old_key in list(attempts):
            attempts[old_key] = [stamp for stamp in attempts[old_key] if now - stamp < 60]
            if not attempts[old_key]:
                del attempts[old_key]
        stamps = attempts.setdefault(key, [])
        if len(stamps) >= 15 or len(attempts) > 1000:
            raise HTTPException(429, 'Demasiados intentos. Espera un minuto y vuelve a intentarlo.')
        stamps.append(now)


def check_csrf(request):
    if request.method in ('GET', 'HEAD', 'OPTIONS'):
        return
    cookie = request.cookies.get(CSRF_COOKIE, '')
    header = request.headers.get('X-XSRF-TOKEN', '')
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise HTTPException(403, 'La sesión de acceso ha cambiado. Recarga la página y vuelve a intentarlo.')


def secure_cookie(request):
    return request.url.scheme == 'https' or os.environ.get('SESSION_COOKIE_SECURE') == '1'


def set_csrf(response, request):
    token = request.cookies.get(CSRF_COOKIE) or secrets.token_urlsafe(32)
    response.set_cookie(CSRF_COOKIE, token, httponly=False, samesite='strict', secure=secure_cookie(request), path='/')


def set_session_cookie(response, request, token):
    response.set_cookie(COOKIE, token, httponly=True, samesite='strict', secure=secure_cookie(request), path='/')


def get_identity(request, session):
    token = request.cookies.get(COOKIE, '')
    if not token or len(token) > 100:
        return None
    key = token_hash(token)
    now = time.monotonic()
    with guest_lock:
        for old_key in list(guests):
            if guests[old_key]['expires'] <= now:
                del guests[old_key]
        if key in guests:
            return {'mode': 'guest', 'username': 'Invitado', 'user_id': None, 'guest_key': key}
    row = session.scalar(select(UserSession).where(UserSession.token_hash == key, UserSession.expires_at > utc_now()))
    if row is None:
        return None
    user = session.get(User, row.user_id)
    if user is None:
        return None
    return {'mode': 'account', 'username': user.username, 'user_id': user.id}


def public_identity(identity):
    if identity is None:
        return {'authenticated': False, 'mode': None, 'username': None}
    return {'authenticated': True, 'mode': identity['mode'], 'username': identity['username']}


def require_access(request: Request, session=Depends(get_session)):
    # Esta dependencia global protege también las futuras rutas /api.
    check_csrf(request)
    public = {'/api/health', '/api/auth/session', '/api/auth/login', '/api/auth/register',
              '/api/auth/guest', '/api/auth/logout'}
    if request.url.path in public:
        return None
    identity = get_identity(request, session)
    if identity is None:
        raise HTTPException(401, 'Inicia sesión o entra como invitado para continuar.')
    return identity


def end_session(request, response, session):
    token = request.cookies.get(COOKIE, '')
    if token:
        key = token_hash(token)
        with guest_lock:
            was_guest = guests.pop(key, None) is not None
        if not was_guest:
            session.execute(delete(UserSession).where(UserSession.token_hash == key))
            session.commit()
    response.delete_cookie(COOKIE, path='/', httponly=True, samesite='strict', secure=secure_cookie(request))


def account_session(user, request, response, session):
    end_session(request, response, session)
    token = secrets.token_urlsafe(32)
    session.execute(delete(UserSession).where(UserSession.expires_at <= utc_now()))
    session.add(UserSession(token_hash=token_hash(token), user_id=user.id, expires_at=utc_now() + timedelta(hours=24)))
    session.commit()
    set_session_cookie(response, request, token)
    return public_identity({'mode': 'account', 'username': user.username})


def register(payload, request, response, session):
    check_rate(request, 'register')
    username = payload.username.strip()
    if not re.fullmatch(r'[A-Za-z0-9_.-]{3,24}', username):
        raise HTTPException(422, 'El usuario debe tener de 3 a 24 letras, números, puntos, guiones o guiones bajos.')
    password = hash_password(payload.password)
    try:
        user = User(username=username, password_hash=password)
        session.add(user)
        session.flush()
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, 'Ese nombre de usuario ya está en uso.')
    return account_session(user, request, response, session)


def login(payload, request, response, session):
    check_rate(request, 'login')
    user = session.scalar(select(User).where(User.username == payload.username.strip()))
    valid = verify_password(payload.password, user.password_hash if user else DUMMY_PASSWORD)
    if user is None or not valid:
        raise HTTPException(401, 'Usuario o contraseña incorrectos.')
    return account_session(user, request, response, session)


def start_guest(request, response, session):
    check_rate(request, 'guest')
    end_session(request, response, session)
    token = secrets.token_urlsafe(32)
    key = token_hash(token)
    with guest_lock:
        now = time.monotonic()
        for old_key in list(guests):
            if guests[old_key]['expires'] <= now:
                del guests[old_key]
        if len(guests) >= 50:
            raise HTTPException(503, 'Hay demasiadas sesiones temporales. Vuelve a intentarlo más tarde.')
        guests[key] = {'expires': now + GUEST_SECONDS, 'participants': {}, 'next_id': 1}
    set_session_cookie(response, request, token)
    return public_identity({'mode': 'guest', 'username': 'Invitado'})


def guest_data(identity):
    data = guests.get(identity['guest_key'])
    if data is None:
        raise HTTPException(401, 'La sesión de invitado ha terminado. Vuelve a entrar.')
    return data
