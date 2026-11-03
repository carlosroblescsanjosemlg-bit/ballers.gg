import pruebas  # Permite importar app y bd al ejecutar desde la raíz.
"""Pruebas de participantes con unittest y MariaDB real."""
import unittest
from bd.conexion import get_session
from io import BytesIO
from uuid import uuid4
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from bd.conexion import engine
from app.main import app
from bd.modelos import Participant, User
from app.sesiones import require_access

def nick():
    return 'Test_' + uuid4().hex[:12]

def logo_bytes():
    output = BytesIO()
    Image.new('RGB', (48, 48), 'green').save(output, 'PNG')
    return output.getvalue()

def create(client, value=None, active=True, logo=None):
    return client.post('/api/participants', data={'nick': value or nick(), 'is_active': str(active).lower()}, files={'logo': ('logo.png', logo, 'image/png')} if logo is not None else None)

class TestParticipants(unittest.TestCase):

    def setUp(self):
        self.connection = engine.connect()
        self.addCleanup(self.connection.close)
        self.transaction = self.connection.begin()
        self.addCleanup(self.transaction.rollback)
        app.dependency_overrides[get_session] = self.provide_session
        self.addCleanup(app.dependency_overrides.clear)
        with Session(bind=self.connection, join_transaction_mode='create_savepoint') as session:
            user = User(username=nick(), password_hash='unused-test-hash')
            session.add(user); session.flush()
            identity = {'mode':'account','user_id':user.id,'username':user.username}
            session.commit()
        app.dependency_overrides[require_access] = lambda: identity
        self.client = TestClient(app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def provide_session(self):
        with Session(bind=self.connection, expire_on_commit=False, join_transaction_mode='create_savepoint') as session:
            yield session

    def test_create_read_edit_and_state(self):
        client = self.client
        value = nick()
        response = create(client, '  ' + value + '  ')
        self.assertEqual(response.status_code, 201)
        participant = response.json()
        self.assertTrue(participant['nick'] == value and participant['is_active'] is True)
        self.assertEqual(client.get(f"/api/participants/{participant['id']}").json(), participant)
        edited = client.put(f"/api/participants/{participant['id']}", data={'nick': value + 'x', 'is_active': 'false', 'version': participant['version']})
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.json()['nick'], value + 'x')
        self.assertIs(edited.json()['is_active'], False)
        active = client.patch(f"/api/participants/{participant['id']}/state", json={'is_active': True, 'version': edited.json()['version']})
        self.assertTrue(active.status_code == 200 and active.json()['is_active'] is True)

    def test_unique_nick_in_mariadb_collation(self):
        client = self.client
        value = nick()
        self.assertEqual(create(client, value).status_code, 201)
        self.assertEqual(create(client, value.upper()).status_code, 409)
        accented = value.replace('Test', 'Tést')
        self.assertEqual(create(client, accented).status_code, 409)
        second = create(client).json()
        response = client.put(f"/api/participants/{second['id']}", data={'nick': value, 'is_active': 'false', 'version': second['version']})
        self.assertEqual(response.status_code, 409)
        self.assertIs(client.get(f"/api/participants/{second['id']}").json()['is_active'], True)

    def test_invalid_nick_case_1(self):
        client = self.client
        value = ' '
        self.assertEqual(create(client, value).status_code, 422)

    def test_invalid_nick_case_2(self):
        client = self.client
        value = 'a'
        self.assertEqual(create(client, value).status_code, 422)

    def test_invalid_nick_case_3(self):
        client = self.client
        value = 'x' * 25
        self.assertEqual(create(client, value).status_code, 422)

    def test_invalid_nick_case_4(self):
        client = self.client
        value = 'bad\x00nick'
        self.assertEqual(create(client, value).status_code, 422)

    def test_stale_edit_is_rejected(self):
        client = self.client
        participant = create(client).json()
        path = f"/api/participants/{participant['id']}"
        self.assertEqual(client.patch(path + '/state', json={'is_active': False, 'version': participant['version']}).status_code, 200)
        self.assertEqual(client.put(path, data={'nick': nick(), 'is_active': 'true', 'version': participant['version']}).status_code, 409)
        self.assertIs(client.get(path).json()['is_active'], False)

    def test_logo_create_replace_keep_remove(self):
        client = self.client
        participant = create(client, logo=logo_bytes()).json()
        path = f"/api/participants/{participant['id']}"
        self.assertIs(participant['has_logo'], True)
        content = client.get(path + '/logo')
        self.assertTrue(content.headers['content-type'] == 'image/png' and content.content.startswith(b'\x89PNG'))
        updated = client.put(path, data={'nick': participant['nick'], 'is_active': 'false', 'version': participant['version']}).json()
        self.assertIs(updated['has_logo'], True)
        replaced = client.put(path, data={'nick': updated['nick'], 'is_active': 'false', 'version': updated['version']}, files={'logo': ('new.png', logo_bytes(), 'image/png')}).json()
        self.assertTrue(replaced['has_logo'] is True and replaced['version'] > updated['version'])
        removed = client.put(path, data={'nick': updated['nick'], 'is_active': 'true', 'version': replaced['version'], 'remove_logo': 'true'})
        self.assertTrue(removed.status_code == 200 and removed.json()['has_logo'] is False)
        self.assertEqual(client.get(path + '/logo').status_code, 404)

    def test_invalid_logo_does_not_create_participant_case_1(self):
        client = self.client
        content = b'not an image'
        value = nick()
        self.assertEqual(create(client, value, logo=content).status_code, 422)
        self.assertEqual(client.get('/api/participants', params={'q': value}).json()['total'], 0)

    def test_invalid_logo_does_not_create_participant_case_2(self):
        client = self.client
        content = b'x' * (2 * 1024 * 1024 + 1)
        value = nick()
        self.assertEqual(create(client, value, logo=content).status_code, 422)
        self.assertEqual(client.get('/api/participants', params={'q': value}).json()['total'], 0)

    def test_invalid_logo_does_not_create_participant_case_3(self):
        client = self.client
        content = b''
        value = nick()
        self.assertEqual(create(client, value, logo=content).status_code, 422)
        self.assertEqual(client.get('/api/participants', params={'q': value}).json()['total'], 0)

    def test_image_dimensions_limit(self):
        client = self.client
        image = BytesIO()
        Image.new('RGB', (4097, 1)).save(image, 'PNG')
        self.assertEqual(create(client, logo=image.getvalue()).status_code, 422)

    def test_filters_search_pagination_and_summary(self):
        client = self.client
        prefix = nick()
        baseline = client.get('/api/participants').json()['summary']
        for index in range(3):
            self.assertEqual(create(client, prefix + str(index), active=index != 2).status_code, 201)
        first = client.get('/api/participants', params={'q': prefix, 'page_size': 2}).json()
        self.assertTrue(first['total'] == 3 and len(first['items']) == 2)
        self.assertEqual(first['summary']['total'], baseline['total'] + 3)
        self.assertEqual(first['summary']['active'], baseline['active'] + 2)
        second = client.get('/api/participants', params={'q': prefix, 'page_size': 2, 'page': 2}).json()
        self.assertEqual(len(second['items']), 1)
        inactive = client.get('/api/participants', params={'q': prefix, 'status': 'inactive'}).json()
        self.assertTrue(inactive['total'] == 1 and inactive['items'][0]['is_active'] is False)

    def test_search_escapes_sql_wildcards(self):
        client = self.client
        value = nick() + '%'
        create(client, value)
        create(client, value[:-1] + 'x')
        result = client.get('/api/participants', params={'q': value}).json()
        self.assertEqual(result['total'], 1)

    def test_not_found_and_bad_pagination(self):
        client = self.client
        self.assertEqual(client.get('/api/participants/2147483647').status_code, 404)
        self.assertEqual(client.get('/api/participants', params={'page': 0}).status_code, 422)
        self.assertEqual(client.get('/api/participants', params={'page_size': 999}).status_code, 422)

    def test_logo_only_edit_detects_stale_version(self):
        client = self.client
        participant = create(client).json()
        path = f"/api/participants/{participant['id']}"
        data = {'nick': participant['nick'], 'is_active': 'true', 'version': participant['version']}
        updated = client.put(path, data=data, files={'logo': ('logo.png', logo_bytes(), 'image/png')})
        self.assertTrue(updated.status_code == 200 and updated.json()['version'] > participant['version'])
        self.assertEqual(client.put(path, data=data).status_code, 409)

    def test_invalid_logo_edit_keeps_existing_data(self):
        client = self.client
        participant = create(client, logo=logo_bytes()).json()
        path = f"/api/participants/{participant['id']}"
        old_logo = client.get(path + '/logo').content
        response = client.put(path, data={'nick': nick(), 'is_active': 'false', 'version': participant['version']}, files={'logo': ('invalid.png', b'not an image', 'image/png')})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(client.get(path).json(), participant)
        self.assertEqual(client.get(path + '/logo').content, old_logo)

class TestPersistence(unittest.TestCase):

    def test_committed_data_survives_new_engine(self):
        """Real commit + independent connection; removes only its own test participant."""
        value = nick()
        participant_id = None
        with Session(engine) as session:
            user = User(username=nick(), password_hash='unused-test-hash')
            session.add(user); session.commit(); user_id = user.id
        app.dependency_overrides[require_access] = lambda: {'mode':'account','user_id':user_id,'username':value}
        independent = create_engine(engine.url, pool_pre_ping=True, hide_parameters=True)
        try:
            with TestClient(app) as client:
                response = create(client, value, active=False, logo=logo_bytes())
                self.assertEqual(response.status_code, 201)
                participant_id = response.json()['id']
            engine.dispose()
            with Session(independent) as session:
                participant = session.get(Participant, participant_id)
                self.assertTrue(participant.nick == value and participant.is_active is False)
                self.assertTrue(participant.logo.content.startswith(b'\x89PNG'))
                with Image.open(BytesIO(participant.logo.content)) as stored:
                    self.assertTrue(stored.size == (48, 48) and stored.getpixel((0, 0))[:3] == (0, 128, 0))
            with TestClient(app) as restarted:
                self.assertIs(restarted.get(f'/api/participants/{participant_id}').json()['has_logo'], True)
        finally:
            if participant_id is not None:
                with Session(independent) as session:
                    participant = session.get(Participant, participant_id)
                    if participant is not None and participant.nick == value:
                        session.delete(participant)
                        session.commit()
            with Session(independent) as session:
                user = session.get(User,user_id)
                if user is not None:
                    session.delete(user); session.commit()
            app.dependency_overrides.clear()
            independent.dispose()
