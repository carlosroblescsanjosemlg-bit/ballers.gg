import unittest
from pathlib import Path
from unittest.mock import patch
from tempfile import TemporaryDirectory
import pruebas
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles
from app.main import app as api
from app import sesiones
from bd.conexion import get_session

@unittest.skipUnless((Path(__file__).resolve().parents[1]/'frontend/dist/arena/browser/index.html').is_file(), 'Compila Angular para comprobar el servidor de producción.')
class TestProductionWeb(unittest.TestCase):
    def setUp(self):
        # Sin acceso a MariaDB: las rutas anónimas no necesitan consultas.
        api.dependency_overrides[get_session]=lambda:None
        self.addCleanup(api.dependency_overrides.clear)
        from app.web import application
        self.client=TestClient(application,base_url='https://ballers.test')
        self.addCleanup(self.client.close)

    def test_angular_public_assets_and_missing_api(self):
        home=self.client.get('/')
        self.assertEqual(home.status_code,200);self.assertIn('<app-root',home.text)
        folder=Path(__file__).resolve().parents[1]/'frontend/dist/arena/browser'
        asset=next(folder.glob('main-*.js')).name
        self.assertEqual(self.client.get('/'+asset).status_code,200)
        self.assertEqual(self.client.get('/api/no-existe').status_code,404)
        self.assertEqual(self.client.get('/backend/.env').status_code,404)
        self.assertEqual(self.client.get('/Main.py').status_code,404)

    def test_private_api_and_https_cookie_csrf(self):
        self.assertEqual(self.client.get('/api/participants').status_code,401)
        response=self.client.get('/api/auth/session')
        self.assertEqual(response.status_code,200)
        self.assertIn('Secure',response.headers['set-cookie'])
        self.assertEqual(response.headers['cache-control'],'no-store')
        self.assertEqual(self.client.post('/api/auth/guest').status_code,403)
        self.client.headers['X-XSRF-TOKEN']=self.client.cookies.get('XSRF-TOKEN')
        response=self.client.post('/api/auth/guest')
        self.assertEqual(response.status_code,200)
        self.assertIn('HttpOnly',response.headers['set-cookie'])
        self.assertIn('Secure',response.headers['set-cookie'])
        self.assertEqual(self.client.get('/api/participants').status_code,200)
        self.client.post('/api/auth/logout')

    def test_missing_static_resource_remains_404(self):
        self.assertEqual(self.client.get('/missing.js').status_code,404)
        self.assertEqual(self.client.post('/index.html').status_code,405)
