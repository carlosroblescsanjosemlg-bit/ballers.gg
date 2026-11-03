"""Acceso real con cookies, MariaDB y transacciones que se deshacen."""
import pruebas
import unittest
from uuid import uuid4
from datetime import timedelta
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.main import app
from app import sesiones
from bd.conexion import engine, get_session
from bd.modelos import User, UserSession, Participant

class TestAccess(unittest.TestCase):
    def setUp(self):
        self.connection = engine.connect()
        self.addCleanup(self.connection.close)
        self.transaction = self.connection.begin()
        self.addCleanup(self.transaction.rollback)
        app.dependency_overrides[get_session] = self.provide_session
        self.addCleanup(app.dependency_overrides.clear)
        sesiones.attempts.clear()
        self.addCleanup(sesiones.guests.clear)
        self.a = self.client(); self.b = self.client()

    def provide_session(self):
        with Session(bind=self.connection, expire_on_commit=False, join_transaction_mode='create_savepoint') as session:
            yield session

    def client(self):
        client = TestClient(app)
        self.addCleanup(client.close)
        client.get('/api/auth/session')
        client.headers['X-XSRF-TOKEN'] = client.cookies.get('XSRF-TOKEN')
        return client

    def register(self, client, name=None):
        username = name or 'QA_' + uuid4().hex[:12]
        response = client.post('/api/auth/register', json={'username': username, 'password': 'TestPassword_123'})
        self.assertEqual(response.status_code, 201, response.text)
        return username

    def create(self, client, name='Mi jugador'):
        result = client.post('/api/participants', data={'nick': name})
        self.assertEqual(result.status_code, 201, result.text)
        return result.json()

    def test_anonymous_and_csrf(self):
        self.assertEqual(self.a.get('/api/participants').status_code, 401)
        self.assertEqual(self.a.post('/api/participants', data={'nick': 'Anonimo'}).status_code, 401)
        del self.a.headers['X-XSRF-TOKEN']
        self.assertEqual(self.a.post('/api/auth/guest').status_code, 403)

    def test_accounts_are_private_including_logo_and_writes(self):
        self.register(self.a); player = self.create(self.a)
        self.register(self.b)
        self.assertEqual(self.b.get('/api/participants').json()['total'], 0)
        path = '/api/participants/' + str(player['id'])
        self.assertEqual(self.b.get(path).status_code, 404)
        self.assertEqual(self.b.get(path+'/logo').status_code, 404)
        self.assertEqual(self.b.put(path, data={'nick':'Otro', 'is_active':True,'version':1}).status_code,404)
        self.assertEqual(self.b.patch(path+'/state',json={'is_active':False,'version':1}).status_code,404)
        self.create(self.b)  # Mismo nick permitido para otra cuenta.

    def test_logout_login_and_password_hash(self):
        username = self.register(self.a); player = self.create(self.a)
        raw_token = self.a.cookies.get(sesiones.COOKIE)
        with Session(self.connection) as db:
            user = db.scalar(select(User).where(User.username == username))
            self.assertNotEqual(user.password_hash, 'TestPassword_123')
            self.assertTrue(sesiones.verify_password('TestPassword_123',user.password_hash))
            self.assertIsNotNone(db.get(UserSession,sesiones.token_hash(raw_token)))
            self.assertIsNone(db.get(UserSession,raw_token))
        self.assertEqual(self.a.post('/api/auth/logout').status_code,200)
        self.assertEqual(self.a.get('/api/participants').status_code,401)
        self.b.cookies.set(sesiones.COOKIE, raw_token)
        self.assertEqual(self.b.get('/api/participants').status_code,401)
        self.assertEqual(self.a.post('/api/auth/login',json={'username':username,'password':'incorrecta'}).status_code,401)
        self.assertEqual(self.a.post('/api/auth/login',json={'username':username.upper(),'password':'TestPassword_123'}).status_code,200)
        self.assertEqual(self.a.get('/api/participants').json()['items'][0]['id'],player['id'])

    def test_validation_and_duplicate_account(self):
        username = self.register(self.a)
        self.assertEqual(self.b.post('/api/auth/register',json={'username':username.upper(),'password':'TestPassword_123'}).status_code,409)
        for name,password in [('bad space','TestPassword_123'),('okname','short')]:
            self.assertEqual(self.b.post('/api/auth/register',json={'username':name,'password':password}).status_code,422)

    def test_guests_are_temporary_and_independent(self):
        with Session(self.connection) as db:
            count = db.scalar(select(func.count(Participant.id)))
        self.a.post('/api/auth/guest'); player = self.create(self.a)
        self.b.post('/api/auth/guest')
        self.assertEqual(self.b.get('/api/participants').json()['total'],0)
        self.assertEqual(self.b.get('/api/participants/1').status_code,404)
        updated = self.a.patch('/api/participants/1/state',json={'is_active':False,'version':1})
        self.assertEqual(updated.status_code,200,updated.text)
        self.assertFalse(updated.json()['is_active'])
        self.assertEqual(self.a.post('/api/participants',data={'nick':player['nick'].upper()}).status_code,409)
        with Session(self.connection) as db:
            self.assertEqual(db.scalar(select(func.count(Participant.id))),count)
        self.a.post('/api/auth/logout'); self.a.post('/api/auth/guest')
        self.assertEqual(self.a.get('/api/participants').json()['total'],0)

    def test_expired_sessions(self):
        self.register(self.a)
        with Session(bind=self.connection,join_transaction_mode='create_savepoint') as db:
            row = db.get(UserSession,sesiones.token_hash(self.a.cookies.get(sesiones.COOKIE)))
            row.expires_at = sesiones.utc_now()-timedelta(seconds=1); db.commit()
        self.assertEqual(self.a.get('/api/participants').status_code,401)
        self.b.post('/api/auth/guest')
        sesiones.guests[sesiones.token_hash(self.b.cookies.get(sesiones.COOKIE))]['expires'] = 0
        self.assertEqual(self.b.get('/api/participants').status_code,401)

    def test_login_rate_limit(self):
        for _ in range(15):
            self.assertEqual(self.a.post('/api/auth/login',json={'username':'nobody','password':'incorrecta'}).status_code,401)
        self.assertEqual(self.a.post('/api/auth/login',json={'username':'nobody','password':'incorrecta'}).status_code,429)

    def test_guest_logo_edit_and_conflict(self):
        from io import BytesIO
        from PIL import Image
        output = BytesIO()
        Image.new('RGB',(24,24),'orange').save(output,'PNG')
        self.a.post('/api/auth/guest')
        result = self.a.post('/api/participants',data={'nick':'Logo temporal'},
                             files={'logo':('test.png',output.getvalue(),'image/png')})
        self.assertEqual(result.status_code,201,result.text)
        self.assertTrue(result.json()['has_logo'])
        path = '/api/participants/' + str(result.json()['id'])
        self.assertTrue(self.a.get(path+'/logo').content.startswith(b'\x89PNG'))
        edit = {'nick':'Logo cambiado','is_active':False,'version':1,'remove_logo':True}
        self.assertEqual(self.a.put(path,data=edit).status_code,200)
        self.assertEqual(self.a.get(path+'/logo').status_code,404)
        self.assertEqual(self.a.put(path,data=edit).status_code,409)
        self.assertEqual(self.a.get(path).json()['nick'],'Logo cambiado')
