import unittest
from unittest.mock import patch
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from pruebas import test_results as helpers
from bd.modelos import Tournament, TournamentStage, TournamentRound, TournamentMatch, TournamentSlot, TournamentEntry, MatchResult, GroupDraw
from app import torneos

class TestTournamentManagement(unittest.TestCase):
    setUp=helpers.TestResults.setUp
    new_client=helpers.TestResults.new_client
    register=helpers.TestResults.register
    players=helpers.TestResults.players
    payload=helpers.TestResults.payload
    create=helpers.TestResults.create
    score=helpers.TestResults.score
    finish=helpers.TestResults.finish

    def remove(self,view,client=None,version=None):
        return (client or self.client).delete(f'/api/tournaments/{view["id"]}',params={'version':version or view['version']})

    def test_exact_count_required_and_validated(self):
        ids=self.players(3)
        for count in (None,True,'3',3.5,1,129,2,4):
            payload=self.payload(ids);payload['participant_count']=count
            self.assertEqual(self.client.post('/api/tournaments',json=payload).status_code,422)
        payload=self.payload(ids);payload.pop('participant_count');payload.update(min_participants=2,max_participants=4)
        self.assertEqual(self.client.post('/api/tournaments',json=payload).status_code,422)
        response=self.client.post('/api/tournaments',json=self.payload(ids))
        self.assertEqual(response.status_code,201,response.text)
        self.assertEqual(response.json()['participant_count'],3)
        self.assertNotIn('min_participants',response.json());self.assertNotIn('max_participants',response.json())

    def test_delete_finished_formats_cleans_children_keeps_players_and_other_tournament(self):
        for kind in ('single_elimination','double_elimination','groups_knockout'):
            created=self.create(3,kind);view,_=self.finish(created,group_draw=True)
            players_before=self.client.get('/api/participants').json()
            # Otro torneo con la misma plantilla debe conservarse.
            ids=[p['participant_id'] for p in view['participants']]
            other=self.client.post('/api/tournaments',json=self.payload(ids)).json()
            with Session(self.connection) as db:
                stages=db.scalars(select(TournamentStage.id).where(TournamentStage.tournament_id==view['id'])).all()
                rounds=db.scalars(select(TournamentRound.id).where(TournamentRound.stage_id.in_(stages))).all()
                matches=db.scalars(select(TournamentMatch.id).where(TournamentMatch.round_id.in_(rounds))).all()
            response=self.remove(view);self.assertEqual(response.status_code,204,response.text)
            self.assertEqual(self.client.get(f'/api/tournaments/{view["id"]}').status_code,404)
            self.assertEqual(self.remove(view).status_code,404)
            self.assertEqual(self.client.get(f'/api/tournaments/{other["id"]}').json(),other)
            self.assertEqual(self.client.get('/api/participants').json(),players_before)
            with Session(self.connection) as db:
                for model,condition in ((TournamentEntry,TournamentEntry.tournament_id==view['id']),
                    (TournamentStage,TournamentStage.id.in_(stages)),(TournamentRound,TournamentRound.id.in_(rounds)),
                    (TournamentMatch,TournamentMatch.id.in_(matches)),(TournamentSlot,TournamentSlot.match_id.in_(matches)),
                    (MatchResult,MatchResult.match_id.in_(matches)),(GroupDraw,GroupDraw.stage_id.in_(stages))):
                    self.assertEqual(db.scalar(select(func.count()).select_from(model).where(condition)),0,model.__name__)

    def test_delete_ownership_csrf_version_and_rollback(self):
        view=self.create(2);other=self.new_client();self.register(other)
        self.assertEqual(self.remove(view,other).status_code,404)
        anon=self.new_client();self.assertEqual(self.remove(view,anon).status_code,401)
        token=self.client.headers.pop('X-XSRF-TOKEN');self.assertEqual(self.remove(view).status_code,403);self.client.headers['X-XSRF-TOKEN']=token
        self.assertEqual(self.remove(view,version=99).status_code,409)
        original=view;view,_=self.finish(view)
        self.assertEqual(self.remove(original).status_code,409)
        original_delete=torneos.delete
        def fail(model):
            if model is TournamentSlot:raise RuntimeError('Fallo simulado después de retirar resultados')
            return original_delete(model)
        with patch('app.torneos.delete',side_effect=fail):
            with self.assertRaises(RuntimeError):self.remove(view)
        self.assertEqual(self.client.get(f'/api/tournaments/{view["id"]}').json(),view)
        self.assertEqual(self.remove(view).status_code,204)

    def test_guest_delete_and_ids_are_not_reused(self):
        self.client=self.new_client();self.client.post('/api/auth/guest')
        view=self.create(3,'double_elimination');ids=[p['participant_id'] for p in view['participants']]
        other=self.new_client();other.post('/api/auth/guest')
        self.assertEqual(self.remove(view,other).status_code,404)
        self.assertEqual(self.remove(view).status_code,204)
        self.assertEqual(self.client.get('/api/tournaments').json()['total'],0)
        self.assertEqual(self.client.get('/api/participants').json()['total'],3)
        new=self.client.post('/api/tournaments',json=self.payload(ids)).json()
        self.assertGreater(new['id'],view['id'])
        self.assertEqual(self.remove(view).status_code,404)
        self.assertEqual(self.client.get(f'/api/tournaments/{new["id"]}').json(),new)
