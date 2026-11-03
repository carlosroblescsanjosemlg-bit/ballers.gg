import pruebas
import unittest
from collections import Counter
from uuid import uuid4
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.main import app
from app import cuadros, sesiones
from bd.conexion import engine, get_session
from bd.modelos import Tournament, TournamentEntry, TournamentMatch, TournamentRound, TournamentStage, TournamentSlot


class TestDraws(unittest.TestCase):
    def test_single_elimination_all_sizes(self):
        for count in range(2,129):
            plan=cuadros.generate('single_elimination',list(range(1,count+1)))
            matches=plan['stages'][0]['rounds'][0]['matches']
            self.assertEqual(sorted(s['participant_id'] for m in matches for s in m['slots'] if s),list(range(1,count+1)))
            self.assertTrue(all(any(m['slots']) for m in matches))
            self.assertEqual(sum(not slot for m in matches for slot in m['slots']),cuadros.next_power(count)-count)

    def test_double_elimination_paths_all_sizes(self):
        # Simular resultados en pruebas valida el grafo; la aplicación no registra aún marcadores.
        for count in range(2,129):
            for choose_second in (False,True):
                plan=cuadros.generate('double_elimination',list(range(1,count+1)))
                results={}; losses=Counter(); played=0
                for stage in plan['stages']:
                    for round_data in stage['rounds']:
                        for match in round_data['matches']:
                            players=[]
                            for slot in match['slots']:
                                if 'participant_id' in slot: players.append(slot['participant_id'])
                                elif 'source_match' in slot: players.append(results[slot['source_match']][0 if slot['outcome']=='winner' else 1])
                                else: players.append(None)
                            real=[p for p in players if p is not None]
                            if len(real)==2:
                                self.assertNotEqual(*real)
                                winner=real[int(choose_second)]; loser=real[not choose_second]
                                losses[loser]+=1; played+=1
                                if stage['kind']=='upper': self.assertEqual(losses[loser],1)
                                if stage['kind']=='lower': self.assertEqual(losses[loser],2)
                            else: winner=real[0] if real else None; loser=None
                            results[match['key']]=(winner,loser)
                self.assertEqual(played,2*count-2)
                upper_final=plan['stages'][0]['rounds'][-1]['matches'][0]['key']
                lower=plan['stages'][1]
                if count>2:
                    self.assertEqual(lower['rounds'][-1]['matches'][0]['slots'][1],cuadros.source(upper_final,'loser'))

    def test_group_members_schedule_and_qualifiers_all_sizes(self):
        for count in range(2,129):
            plan=cuadros.generate('groups_knockout',list(range(1,count+1)))
            sizes=[len(g['participant_ids']) for g in plan['groups']]
            self.assertTrue(all(2<=size<=4 for size in sizes)); self.assertLessEqual(max(sizes)-min(sizes),1)
            self.assertEqual(sorted(p for g in plan['groups'] for p in g['participant_ids']),list(range(1,count+1)))
            for group,stage in zip(plan['groups'],plan['stages']):
                pairs=[]
                for round_data in stage['rounds']:
                    round_ids=[]
                    for match in round_data['matches']:
                        pair=sorted(s['participant_id'] for s in match['slots']); pairs.append(tuple(pair)); round_ids+=pair
                    self.assertEqual(len(round_ids),len(set(round_ids)))
                size=len(group['participant_ids'])
                self.assertEqual(len(pairs),size*(size-1)//2); self.assertEqual(len(pairs),len(set(pairs)))
            matches=plan['stages'][-1]['rounds'][0]['matches']
            qualifiers=[(s['source_group'],s['rank']) for m in matches for s in m['slots'] if s]
            self.assertEqual(len(qualifiers),2*len(sizes)); self.assertEqual(len(qualifiers),len(set(qualifiers)))
            if len(sizes)>1:
                for match in matches:
                    if all(match['slots']): self.assertNotEqual(match['slots'][0]['source_group'],match['slots'][1]['source_group'])


class TestTournaments(unittest.TestCase):
    def setUp(self):
        self.connection=engine.connect(); self.addCleanup(self.connection.close)
        transaction=self.connection.begin(); self.addCleanup(transaction.rollback)
        def provide():
            with Session(bind=self.connection,expire_on_commit=False,join_transaction_mode='create_savepoint') as db: yield db
        app.dependency_overrides[get_session]=provide; self.addCleanup(app.dependency_overrides.clear)
        sesiones.attempts.clear(); self.addCleanup(sesiones.guests.clear)
        self.client=self.new_client()
        self.register(self.client)

    def new_client(self):
        client=TestClient(app); self.addCleanup(client.close)
        client.get('/api/auth/session'); client.headers['X-XSRF-TOKEN']=client.cookies.get('XSRF-TOKEN')
        return client

    def register(self,client):
        response=client.post('/api/auth/register',json={'username':'QA_'+uuid4().hex[:12],'password':'TestPassword_123'})
        self.assertEqual(response.status_code,201,response.text)

    def players(self,count,active=True,client=None):
        client=client or self.client
        result=[]
        for _ in range(count):
            response=client.post('/api/participants',data={'nick':'QA_'+uuid4().hex[:10],'is_active':str(active).lower()})
            self.assertEqual(response.status_code,201,response.text); result.append(response.json()['id'])
        return result

    def payload(self,ids,format_name='single_elimination'):
        return {'name':'Copa de prueba','format':format_name,'participant_count':len(ids),
                'participant_ids':ids,'request_key':str(uuid4())}

    def test_save_consult_and_idempotent_draw(self):
        payload=self.payload(self.players(5))
        first=self.client.post('/api/tournaments',json=payload)
        self.assertEqual(first.status_code,201,first.text); value=first.json()
        self.assertEqual(value['participant_count'],5)
        self.assertEqual(self.client.get('/api/tournaments/'+str(value['id'])).json(),value)
        self.assertEqual(self.client.post('/api/tournaments',json=payload).json(),value)
        self.assertEqual(self.client.get('/api/tournaments').json()['total'],1)
        first_round=value['stages'][0]['rounds'][0]['matches']
        self.assertEqual(sum(m['state']=='bye' for m in first_round),3)
        self.assertEqual(sum(m['state']=='scheduled' for m in first_round),1)
        payload['name']='Distinto'
        self.assertEqual(self.client.post('/api/tournaments',json=payload).status_code,409)

    def test_active_owned_unique_and_limits(self):
        ids=self.players(3); inactive=self.players(1,False)[0]
        self.assertNotIn(inactive,[p['id'] for p in self.client.get('/api/tournaments/eligible').json()])
        other=self.new_client(); self.register(other); foreign=self.players(1,client=other)[0]
        for bad in ([True,ids[1]],[str(ids[0]),ids[1]],[ids[0],ids[0]],[ids[0],inactive],[ids[0],foreign],[ids[0],2147483647]):
            self.assertEqual(self.client.post('/api/tournaments',json=self.payload(bad)).status_code,422)
        payload=self.payload(ids); payload['participant_count']=1
        self.assertEqual(self.client.post('/api/tournaments',json=payload).status_code,422)
        payload=self.payload(ids); payload['participant_count']=2
        self.assertEqual(self.client.post('/api/tournaments',json=payload).status_code,422)
        payload=self.payload(ids); payload['participant_count']=4
        self.assertEqual(self.client.post('/api/tournaments',json=payload).status_code,422)
        self.assertEqual(self.client.get('/api/tournaments').json()['total'],0)

    def test_formats_groups_and_double_final(self):
        ids=self.players(9)
        for format_name in ('double_elimination','groups_knockout'):
            response=self.client.post('/api/tournaments',json=self.payload(ids,format_name))
            self.assertEqual(response.status_code,201,response.text)
            value=response.json()
            if format_name=='double_elimination':
                self.assertEqual([s['kind'] for s in value['stages']],['upper','lower','final'])
                self.assertEqual(len(value['stages'][-1]['rounds'][0]['matches']),1)
            else:
                self.assertEqual([len(s['participants']) for s in value['stages'] if s['kind']=='group'],[3,3,3])
                self.assertEqual(value['group_qualifiers'],2)
            with patch('app.torneos.cuadros.generate',side_effect=AssertionError('No volver a sortear')):
                self.assertEqual(self.client.get('/api/tournaments/'+str(value['id'])).json(),value)

    def test_access_control_and_no_results_endpoint(self):
        value=self.client.post('/api/tournaments',json=self.payload(self.players(2))).json()
        other=self.new_client(); self.register(other)
        self.assertEqual(other.get('/api/tournaments').json()['total'],0)
        self.assertEqual(other.get('/api/tournaments/'+str(value['id'])).status_code,404)
        anon=self.new_client()
        self.assertEqual(anon.get('/api/tournaments').status_code,401)
        self.assertEqual(anon.get('/api/tournaments/eligible').status_code,401)
        self.assertEqual(anon.post('/api/tournaments',json=self.payload([1,2])).status_code,401)

    def test_deactivation_after_draw_keeps_history(self):
        ids=self.players(2)
        value=self.client.post('/api/tournaments',json=self.payload(ids)).json()
        self.client.patch(f'/api/participants/{ids[0]}/state',json={'is_active':False,'version':1})
        detail=self.client.get('/api/tournaments/'+str(value['id'])).json()
        self.assertEqual(set(p['participant_id'] for p in detail['participants']),set(ids))
        self.assertFalse(next(p for p in detail['participants'] if p['participant_id']==ids[0])['is_active'])

    def test_guest_tournaments_are_ephemeral_and_private(self):
        guest=self.new_client(); guest.post('/api/auth/guest')
        ids=self.players(5,client=guest)
        with Session(self.connection) as db: before=db.scalar(select(func.count(Tournament.id)))
        for format_name in ('single_elimination','double_elimination','groups_knockout'):
            payload=self.payload(ids,format_name); first=guest.post('/api/tournaments',json=payload)
            self.assertEqual(first.status_code,201,first.text)
            self.assertEqual(guest.get('/api/tournaments/'+str(first.json()['id'])).json(),first.json())
            self.assertEqual(guest.post('/api/tournaments',json=payload).json(),first.json())
        with Session(self.connection) as db: self.assertEqual(db.scalar(select(func.count(Tournament.id))),before)
        other=self.new_client(); other.post('/api/auth/guest')
        self.assertEqual(other.get('/api/tournaments').json()['total'],0)
        self.assertEqual(other.get('/api/tournaments/1').status_code,404)
        guest.post('/api/auth/logout'); guest.post('/api/auth/guest')
        self.assertEqual(guest.get('/api/tournaments').json()['total'],0)

    def test_failure_rolls_back_everything(self):
        payload=self.payload(self.players(4))
        original=__import__('app.torneos',fromlist=['save_plan']).save_plan
        def fail(session,tournament_id,plan):
            original(session,tournament_id,plan)
            raise RuntimeError('Fallo de prueba antes del commit')
        with patch('app.torneos.save_plan',side_effect=fail):
            with self.assertRaises(RuntimeError): self.client.post('/api/tournaments',json=payload)
        self.assertEqual(self.client.get('/api/tournaments').json()['total'],0)


class TestTournamentPersistence(unittest.TestCase):
    def test_committed_tournament_survives_independent_engine(self):
        from sqlalchemy import create_engine, delete
        from bd.modelos import User, Participant
        username='Persist_'+uuid4().hex[:12]
        ids=[]; tournament_id=None
        independent=__import__('sqlalchemy').create_engine(engine.url,pool_pre_ping=True,hide_parameters=True)
        with Session(independent) as db:
            user=User(username=username,password_hash='unused-fixture-hash'); db.add(user);db.flush();user_id=user.id
            for index in range(6):
                player=Participant(owner_id=user_id,nick='Persist_'+uuid4().hex[:10],is_active=True)
                db.add(player);db.flush();ids.append(player.id)
            db.commit()
        from app.sesiones import require_access
        app.dependency_overrides[require_access]=lambda:{'mode':'account','user_id':user_id,'username':username}
        try:
            with TestClient(app) as client:
                response=client.post('/api/tournaments',json={'name':'Persistencia de torneo','format':'double_elimination',
                    'participant_count':len(ids),'participant_ids':ids})
                self.assertEqual(response.status_code,201,response.text)
                first=response.json();tournament_id=first['id']
            with Session(independent) as db:
                self.assertEqual(db.scalar(select(func.count(TournamentEntry.id)).where(TournamentEntry.tournament_id==tournament_id)),6)
                match_ids=db.scalars(select(TournamentMatch.id).join(TournamentRound).join(TournamentStage)
                    .where(TournamentStage.tournament_id==tournament_id)).all()
                self.assertGreater(len(match_ids),6)
                self.assertEqual(db.scalar(select(func.count()).select_from(TournamentSlot).where(TournamentSlot.match_id.in_(match_ids))),len(match_ids)*2)
            def independent_session():
                with Session(independent,expire_on_commit=False) as db:yield db
            app.dependency_overrides[get_session]=independent_session
            with TestClient(app) as restarted:
                self.assertEqual(restarted.get('/api/tournaments/'+str(tournament_id)).json(),first)
        finally:
            app.dependency_overrides.clear()
            with Session(independent) as db:
                if tournament_id is not None:
                    match_ids=db.scalars(select(TournamentMatch.id).join(TournamentRound).join(TournamentStage)
                        .where(TournamentStage.tournament_id==tournament_id)).all()
                    db.execute(delete(TournamentSlot).where(TournamentSlot.match_id.in_(match_ids)))
                    db.execute(delete(Tournament).where(Tournament.id==tournament_id,Tournament.owner_id==user_id))
                db.execute(delete(Participant).where(Participant.id.in_(ids),Participant.owner_id==user_id))
                db.execute(delete(User).where(User.id==user_id,User.username==username));db.commit()
            independent.dispose()
