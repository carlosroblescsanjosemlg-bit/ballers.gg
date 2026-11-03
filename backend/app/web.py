"""Servidor de producción: Angular público y API con su autorización habitual."""
from pathlib import Path

from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

from .main import app as api

FRONTEND_DIR = Path(__file__).resolve().parents[2] / 'frontend' / 'dist' / 'arena' / 'browser'
frontend = Starlette(routes=[Mount('/', app=StaticFiles(directory=FRONTEND_DIR, html=True))])


async def application(scope, receive, send):
    path = scope.get('path', '')
    if (scope['type'] != 'http' or path == '/api' or path.startswith('/api/')
            or path in ('/docs', '/docs/oauth2-redirect', '/redoc', '/openapi.json')):
        await api(scope, receive, send)
    else:
        await frontend(scope, receive, send)
