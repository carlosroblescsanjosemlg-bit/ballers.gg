import unittest
from unittest.mock import patch
from uuid import uuid4
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from pruebas import test_tournaments as helpers
from app import cuadros, resultados
from bd.conexion import engine
from bd.modelos import Tournament, MatchResult, GroupDraw


def all_games(view):
    return [m for s in view['stages'] for r in s['rounds'] for m in r['matches']]


class TestResults(unittest.TestCase):
    setUp=helpers.TestTournaments.setUp
    new_client=helpers.TestTournaments.new_client
    register=helpers.TestTournaments.register
    players=helpers.TestTournaments.players
    payload=helpers.TestTournaments.payload

    def create(self, count=4, kind='single_elimination'):
        response=self.client.post('/api/tournaments',json=self.payload(self.players(count),kind))
        self.assertEqual(response.status_code,201,response.text)
        return response.json()

    def score(self, view, game, a=2, b=1, winner=None, status=200):
        payload={'version':view['version'],'home_score':a,'away_score':b,'winner_participant_id':winner}
        response=self.client.post(f'/api/tournaments/{view["id"]}/matches/{game["id"]}/result',json=payload)
        self.assertEqual(response.status_code,status,response.text)
        return response.json()

    def finish(self, view, group_draw=False):
        count=0
        while not view['finished_at']:
            game=next((m for m in all_games(view) if m['state']=='scheduled'),None)
            self.assertIsNotNone(game,'Cuadro bloqueado sin campeón')
            group=next(s for s in view['stages'] if any(m['id']==game['id'] for r in s['rounds'] for m in r['matches']))['kind']=='group'
            view=self.score(view,game,0 if group and group_draw else 2,0 if group and group_draw else 1)
            count+=1; self.assertLess(count,100)
        return view,count

    def test_all_formats_advance_close_and_reload(self):
        for kind,expected in [('single_elimination',4),('double_elimination',8),('groups_knockout',5)]:
            view,count=self.finish(self.create(5,kind),group_draw=True)
            self.assertEqual(count,expected if kind!='groups_knockout' else 7)
            self.assertEqual(view['status'],'finished'); self.assertIsNotNone(view['champion'])
            self.assertEqual(self.client.get(f'/api/tournaments/{view["id"]}').json(),view)
            old=next(m for m in all_games(view) if m['result'])
            self.score(view,old,status=409)
            self.assertEqual(self.client.get(f'/api/tournaments/{view["id"]}').json(),view)

    def test_stale_future_duplicate_wrong_winner_and_penalties(self):
        view=self.create(); first=next(m for m in all_games(view) if m['state']=='scheduled')
        future=next(m for m in all_games(view) if m['state']=='waiting')
        self.score(view,future,status=409)
        self.score(view,first,1,1,status=422)
        self.score(view,first,3,0,winner=first['slots'][1]['participant_id'],status=422)
        current=self.score(view,first,1,1,winner=first['slots'][1]['participant_id'])
        self.assertEqual(current['version'],view['version']+1)
        self.score(view,next(m for m in all_games(current) if m['state']=='scheduled'),status=409)
        self.score(current,first,status=409)
        self.assertEqual(self.client.get(f'/api/tournaments/{view["id"]}').json(),current)
        for invalid in (-1,100,True,'2',1.5):
            game=next(m for m in all_games(current) if m['state']=='scheduled')
            response=self.client.post(f'/api/tournaments/{view["id"]}/matches/{game["id"]}/result',json={'version':current['version'],'home_score':invalid,'away_score':0})
            self.assertEqual(response.status_code,422)

    def test_group_goal_difference_then_persisted_lottery(self):
        view=self.create(3,'groups_knockout')
        # Todos empatan a cero: mismos puntos y goal average, sorteo obligatorio.
        while not view['stages'][0]['ready']:
            game=next(m for r in view['stages'][0]['rounds'] for m in r['matches'] if m['state']=='scheduled')
            view=self.score(view,game,0,0)
        stage=view['stages'][0]
        self.assertTrue(stage['draw_used']); self.assertTrue(all(r['points']==2 and r['goal_difference']==0 for r in stage['standings']))
        with patch('app.resultados.secrets.SystemRandom',side_effect=AssertionError('Una lectura no sortea')):
            self.assertEqual(self.client.get(f'/api/tournaments/{view["id"]}').json(),view)
        self.assertEqual(len([m for m in all_games(view) if m['state']=='scheduled']),1)
        people={1:{'nick':'Uno'},2:{'nick':'Dos'},3:{'nick':'Tres'}}
        games=[{'key':'a','slots':[{'participant_id':1},{'participant_id':2}]},
               {'key':'b','slots':[{'participant_id':2},{'participant_id':3}]},
               {'key':'c','slots':[{'participant_id':3},{'participant_id':1}]}]
        scores={'a':{'home_score':4,'away_score':0},'b':{'home_score':1,'away_score':0},'c':{'home_score':1,'away_score':0}}
        table=resultados.standings([1,2,3],games,scores,[],people)
        self.assertTrue(table['ready']); self.assertEqual([r['participant_id'] for r in table['standings']],[1,3,2]); self.assertFalse(table['draw_used'])

    def test_ownership_csrf_and_rollback(self):
        view=self.create(2); game=all_games(view)[0]
        other=self.new_client(); self.register(other)
        path=f'/api/tournaments/{view["id"]}/matches/{game["id"]}/result'
        payload={'version':1,'home_score':2,'away_score':0}
        self.assertEqual(other.post(path,json=payload).status_code,404)
        token=self.client.headers.pop('X-XSRF-TOKEN')
        self.assertEqual(self.client.post(path,json=payload).status_code,403)
        self.client.headers['X-XSRF-TOKEN']=token
        with patch('app.resultados.new_draws',side_effect=RuntimeError('Fallo simulado')):
            with self.assertRaises(RuntimeError): self.client.post(path,json=payload)
        self.assertEqual(self.client.get(f'/api/tournaments/{view["id"]}').json(),view)
        self.score(view,game)

    def test_guest_results_are_temporary(self):
        self.client=self.new_client(); self.assertEqual(self.client.post('/api/auth/guest').status_code,200)
        created=self.create(3,'double_elimination')
        self.assertIsNone(self.client.get('/api/tournaments').json()['items'][0]['finished_at'])
        view,count=self.finish(created)
        self.assertIsNotNone(self.client.get('/api/tournaments').json()['items'][0]['finished_at'])
        self.assertEqual(count,4)
        self.assertEqual(self.client.get(f'/api/tournaments/{view["id"]}').json(),view)
        self.client.post('/api/auth/logout'); self.client.post('/api/auth/guest')
        self.assertEqual(self.client.get(f'/api/tournaments/{view["id"]}').status_code,404)


class TestResultGraph(unittest.TestCase):
    def test_result_resolution_all_sizes_and_formats(self):
        for kind in ('single_elimination','double_elimination','groups_knockout'):
            for count in range(2,33):
                plan=cuadros.generate(kind,list(range(1,count+1)))
                people=[{'participant_id':i,'entry_id':i,'nick':str(i)} for i in range(1,count+1)]
                meta={'format':kind}; results={}; draws={}
                while True:
                    view=resultados.present(meta,people,plan,results,draws)
                    if view['champion']: break
                    game=next((m for m in all_games(view) if m['state']=='scheduled'),None)
                    self.assertIsNotNone(game,(kind,count))
                    self.assertNotEqual(game['slots'][0]['participant_id'],game['slots'][1]['participant_id'])
                    results[game['id']]={'home_score':2,'away_score':1,'winner_participant_id':game['slots'][0]['participant_id']}
                    updated=resultados.present(meta,people,plan,results,draws)
                    draws.update(resultados.new_draws(updated))
                    self.assertLess(len(results),count*5)
                if kind=='single_elimination': self.assertEqual(len(results),count-1)
                if kind=='double_elimination': self.assertEqual(len(results),2*count-2)

class TestResultPersistence(unittest.TestCase):
    def test_scores_draw_and_champion_survive_new_engine(self):
        from sqlalchemy import create_engine
        from bd.modelos import User, Participant, TournamentMatch, TournamentRound, TournamentStage, TournamentSlot
        from app import torneos
        from app.datos import TournamentCreate, ResultCreate
        username='Result_'+uuid4().hex[:12]; ids=[]; tid=None
        with Session(engine,expire_on_commit=False) as db:
            user=User(username=username,password_hash='unused-fixture-hash');db.add(user);db.flush();uid=user.id
            for _ in range(3):
                player=Participant(owner_id=uid,nick='Result_'+uuid4().hex[:10],is_active=True)
                db.add(player);db.flush();ids.append(player.id)
            db.commit()
        identity={'mode':'account','user_id':uid,'username':username}
        try:
            with Session(engine,expire_on_commit=False) as db:
                view=torneos.create(db,TournamentCreate(name='Persistencia de resultados',format='groups_knockout',
                    participant_count=len(ids),participant_ids=ids),identity); tid=view['id']
                from concurrent.futures import ThreadPoolExecutor
                from threading import Barrier
                from fastapi import HTTPException
                gate=Barrier(2); first=next(m for m in all_games(view) if m['state']=='scheduled')
                def concurrent_result():
                    with Session(engine,expire_on_commit=False) as other:
                        # Reproducir una lectura anterior al bloqueo (como autenticación).
                        other.scalar(select(Tournament).where(Tournament.id==tid))
                        gate.wait(timeout=10)
                        try:
                            resultados.record(other,tid,first['id'],ResultCreate(version=1,home_score=0,away_score=0),identity)
                            return 200
                        except HTTPException as error: return error.status_code
                with ThreadPoolExecutor(max_workers=2) as workers:
                    futures=[workers.submit(concurrent_result) for _ in range(2)]
                    self.assertEqual(sorted(f.result(timeout=30) for f in futures),[200,409])
                db.expire_all(); db.commit()
                view=torneos.detail(db,tid,identity)
                while not view['finished_at']:
                    stage,game=next((s,m) for s in view['stages'] for r in s['rounds'] for m in r['matches'] if m['state']=='scheduled')
                    group=stage['kind']=='group'
                    view=resultados.record(db,tid,game['id'],ResultCreate(version=view['version'],home_score=0 if group else 3,away_score=0),identity)
            independent=create_engine(engine.url,pool_pre_ping=True,hide_parameters=True)
            try:
                with Session(independent) as restarted:
                    saved=torneos.detail(restarted,tid,identity)
                    self.assertEqual(saved,view)
                    self.assertTrue(saved['stages'][0]['draw_used'])
                    self.assertEqual(saved['completed_matches'],4)
                    self.assertIsNotNone(saved['champion']);self.assertEqual(saved['status'],'finished')
            finally: independent.dispose()
        finally:
            with Session(engine) as db:
                if tid is not None:
                    mids=db.scalars(select(TournamentMatch.id).join(TournamentRound).join(TournamentStage).where(TournamentStage.tournament_id==tid)).all()
                    db.execute(delete(MatchResult).where(MatchResult.match_id.in_(mids)))
                    db.execute(delete(TournamentSlot).where(TournamentSlot.match_id.in_(mids)))
                    db.execute(delete(Tournament).where(Tournament.id==tid,Tournament.owner_id==uid))
                db.execute(delete(Participant).where(Participant.id.in_(ids),Participant.owner_id==uid))
                db.execute(delete(User).where(User.id==uid,User.username==username));db.commit()
