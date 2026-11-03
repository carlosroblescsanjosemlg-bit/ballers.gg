import unittest
from collections import Counter
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.orm import Session
from pruebas import test_results as helpers
from app import cuadros, resultados, torneos
from bd.conexion import engine
from bd.modelos import Tournament, TournamentPartner

class TestCalendars(unittest.TestCase):
    def test_league_schedules_odd_even_and_return_legs(self):
        for size in list(range(2,34))+[128]:
            for turns in (1,2):
                plan=cuadros.generate('league',list(range(1,size+1)),turns)
                days=plan['stages'][0]['rounds']; pairs=[]
                for day in days:
                    ids=[]
                    for game in day['matches']:
                        a,b=[s['participant_id'] for s in game['slots']]
                        self.assertNotEqual(a,b);ids.extend([a,b]);pairs.append((a,b))
                    self.assertEqual(len(ids),len(set(ids)))
                self.assertEqual(len(pairs),size*(size-1)//2*turns)
                self.assertEqual(set(Counter(tuple(sorted(p)) for p in pairs).values()),{turns})
                if turns==2:
                    self.assertEqual(set(pairs),set((b,a) for a,b in pairs));self.assertEqual(len(pairs),len(set(pairs)))

class TestExpansion(unittest.TestCase):
    setUp=helpers.TestResults.setUp
    new_client=helpers.TestResults.new_client
    register=helpers.TestResults.register
    players=helpers.TestResults.players
    payload=helpers.TestResults.payload
    score=helpers.TestResults.score
    finish=helpers.TestResults.finish

    def create_extra(self,count,kind='league',mode='individual',turns=1):
        ids=self.players(count);payload=self.payload(ids,kind)
        payload.update(pair_mode=mode,league_rounds=turns)
        if mode=='manual':payload['pairs']=[[ids[i],ids[i+1]] for i in range(0,count,2)]
        response=self.client.post('/api/tournaments',json=payload)
        self.assertEqual(response.status_code,201,response.text)
        return response.json(),payload

    def test_league_two_legs_draws_title_and_reload(self):
        view,payload=self.create_extra(3,turns=2)
        self.assertEqual(len(view['stages'][0]['rounds']),6)
        while not view['finished_at']:
            game=next(m for m in helpers.all_games(view) if m['state']=='scheduled')
            view=self.score(view,game,1,1)
        self.assertEqual(view['completed_matches'],6);self.assertTrue(view['stages'][0]['draw_used'])
        self.assertIsNotNone(view['champion']);self.assertEqual(view['champion']['participant_id'],view['stages'][0]['standings'][0]['participant_id'])
        self.assertEqual(self.client.get(f'/api/tournaments/{view["id"]}').json(),view)
        self.assertEqual(self.client.post('/api/tournaments',json=payload).json(),view)
        self.score(view,helpers.all_games(view)[0],status=409)
        ranking=self.client.get('/api/statistics').json()
        self.assertEqual(ranking['matches'],6);self.assertEqual(sum(r['titles'] for r in ranking['items']),1)
        for row in ranking['items']:
            self.assertEqual(row['played'],4);self.assertEqual(row['drawn'],4);self.assertEqual(row['goals_for'],4)

    def test_pairs_manual_random_all_formats_and_statistics(self):
        for mode,kind in [('manual','single_elimination'),('random','double_elimination'),('manual','groups_knockout'),('random','league')]:
            view,payload=self.create_extra(4,kind,mode)
            self.assertEqual(view['participant_count'],4);self.assertEqual(view['competitor_count'],2)
            self.assertEqual(sorted(torneos.all_ids(view)),sorted(payload['participant_ids']))
            self.assertTrue(all(len(p['member_ids'])==2 for p in view['participants']))
            self.assertEqual(self.client.post('/api/tournaments',json=payload).json(),view)
            self.assertEqual(self.client.get(f'/api/tournaments/{view["id"]}').json(),view)
            view,count=self.finish(view)
            winners=view['champion']['member_ids'];self.assertEqual(len(winners),2)
            profiles=[self.client.get(f'/api/participants/{pid}/history').json() for pid in winners]
            for profile in profiles:
                self.assertEqual(profile['player']['titles'],1);self.assertEqual(profile['player']['team_matches'],profile['player']['played'])
                self.assertTrue(all(row['partner'] for row in profile['items']))
                self.assertEqual(len(profile['titles']),1)
            self.assertEqual(profiles[0]['player']['won'],profiles[1]['player']['won'])
            self.assertEqual(profiles[0]['player']['goals_for'],profiles[1]['player']['goals_for'])
            response=self.client.delete(f'/api/tournaments/{view["id"]}',params={'version':view['version']})
            self.assertEqual(response.status_code,204,response.text)
            for pid in winners:
                history=self.client.get(f'/api/participants/{pid}/history').json()
                self.assertEqual(history['total'],0);self.assertEqual(history['player']['titles'],0)

    def test_pair_validation_inactive_foreign_duplicate_and_idempotency(self):
        ids=self.players(6);payload=self.payload(ids);payload['pair_mode']='manual'
        for pairs in ([],[[ids[0],ids[0]],[ids[2],ids[3]],[ids[4],ids[5]]],[[ids[0],ids[1]],[ids[2],ids[3]]]):
            payload['pairs']=pairs;self.assertEqual(self.client.post('/api/tournaments',json=payload).status_code,422)
        payload['pairs']=[[ids[0],ids[1]],[ids[2],ids[3]],[ids[4],ids[5]]]
        first=self.client.post('/api/tournaments',json=payload);self.assertEqual(first.status_code,201,first.text)
        payload['pairs']=[[ids[0],ids[2]],[ids[1],ids[3]],[ids[4],ids[5]]]
        self.assertEqual(self.client.post('/api/tournaments',json=payload).status_code,409)
        for count in (2,3,5):
            bad=self.payload(ids[:count]);bad['pair_mode']='random'
            self.assertEqual(self.client.post('/api/tournaments',json=bad).status_code,422)
        inactive=self.players(1,False)[0];bad=self.payload(ids[:3]+[inactive]);bad['pair_mode']='random'
        self.assertEqual(self.client.post('/api/tournaments',json=bad).status_code,422)
        other=self.new_client();self.register(other);foreign=self.players(1,client=other)[0]
        bad=self.payload(ids[:3]+[foreign]);bad['pair_mode']='random'
        self.assertEqual(self.client.post('/api/tournaments',json=bad).status_code,422)

    def test_statistics_penalties_byes_pagination_privacy_and_guests(self):
        view,_=self.create_extra(3,'single_elimination')
        game=next(m for m in helpers.all_games(view) if m['state']=='scheduled')
        view=self.score(view,game,0,0,winner=game['slots'][1]['participant_id'])
        winner=game['slots'][1]['participant_id'];profile=self.client.get(f'/api/participants/{winner}/history').json()
        self.assertEqual(profile['player']['won'],1);self.assertEqual(profile['player']['goals_for'],0)
        self.assertTrue(profile['items'][0]['penalties'])
        ranking=self.client.get('/api/statistics').json();self.assertEqual(sum(p['played'] for p in ranking['items']),2)
        one=self.client.get('/api/statistics?page_size=1&page=2').json();self.assertEqual(len(one['items']),1);self.assertEqual(one['total'],3)
        other=self.new_client();self.register(other)
        self.assertEqual(other.get(f'/api/participants/{winner}/history').status_code,404)
        self.assertEqual(other.get('/api/statistics').json()['total'],0)
        anonymous=self.new_client();self.assertEqual(anonymous.get('/api/statistics').status_code,401)
        guest=self.new_client();guest.post('/api/auth/guest');self.client=guest
        value,_=self.create_extra(4,'league','random');value,count=self.finish(value)
        self.assertEqual(guest.get('/api/statistics').json()['matches'],1)
        guest.post('/api/auth/logout');guest.post('/api/auth/guest')
        self.assertEqual(guest.get('/api/statistics').json()['total'],0)

class TestExpansionPersistence(unittest.TestCase):
    def test_pairs_league_and_statistics_survive_independent_engine(self):
        from sqlalchemy import create_engine,delete
        from bd.modelos import User,Participant
        from app.datos import TournamentCreate,ResultCreate
        from app import estadisticas
        username='PairPersist_'+uuid4().hex[:10];ids=[];tid=None
        with Session(engine,expire_on_commit=False) as db:
            user=User(username=username,password_hash='unused-test-fixture');db.add(user);db.flush();uid=user.id
            for _ in range(4):
                player=Participant(owner_id=uid,nick='Pair_'+uuid4().hex[:10],is_active=True)
                db.add(player);db.flush();ids.append(player.id)
            db.commit()
        identity={'mode':'account','user_id':uid,'username':username}
        try:
            with Session(engine,expire_on_commit=False) as db:
                view=torneos.create(db,TournamentCreate(name='Liga persistente de parejas',format='league',pair_mode='random',
                    league_rounds=2,participant_count=4,participant_ids=ids),identity);tid=view['id']
                while not view['finished_at']:
                    game=next(m for m in helpers.all_games(view) if m['state']=='scheduled')
                    view=resultados.record(db,tid,game['id'],ResultCreate(version=view['version'],home_score=1,away_score=1),identity)
                before=estadisticas.ranking(db,identity,1,12)
                profile=estadisticas.history(db,identity,ids[0],1,20)
            independent=create_engine(engine.url,pool_pre_ping=True,hide_parameters=True)
            try:
                with Session(independent) as db:
                    self.assertEqual(torneos.detail(db,tid,identity),view)
                    self.assertEqual(estadisticas.ranking(db,identity,1,12),before)
                    self.assertEqual(estadisticas.history(db,identity,ids[0],1,20),profile)
                    self.assertEqual(sum(r['titles'] for r in before['items']),2)
                    self.assertTrue(view['stages'][0]['draw_used'])
            finally:independent.dispose()
        finally:
            with Session(engine) as db:
                if tid is not None:torneos.remove(db,tid,view['version'],identity)
                db.execute(delete(Participant).where(Participant.id.in_(ids),Participant.owner_id==uid))
                db.execute(delete(User).where(User.id==uid,User.username==username));db.commit()
