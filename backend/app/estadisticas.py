"""Estadísticas e historial derivados de marcadores, sin contadores duplicados."""
from fastapi import HTTPException
from sqlalchemy import select, or_
from bd.modelos import Participant, Tournament, TournamentEntry, TournamentPartner
from .sesiones import guest_data, guest_lock
from . import torneos


def players(session,identity):
    if identity['mode']=='guest':
        with guest_lock:
            return [{'id':p.id,'nick':p.nick,'is_active':p.is_active} for p in guest_data(identity)['participants'].values()]
    rows=session.execute(select(Participant.id,Participant.nick,Participant.is_active).where(Participant.owner_id==identity['user_id'])).all()
    return [{'id':r.id,'nick':r.nick,'is_active':r.is_active} for r in rows]


def views(session,identity,participant_id=None):
    if identity['mode']=='guest':
        with guest_lock:
            data=guest_data(identity)
            return [torneos.guest_detail(data,t) for t in data.get('tournaments',{}).values()
                    if participant_id is None or participant_id in t['plan']['entry_order'] or participant_id in t['plan'].get('pairs',{}).values()]
    query=select(Tournament.id).where(Tournament.owner_id==identity['user_id'])
    if participant_id is not None:
        entries=select(TournamentEntry.tournament_id).outerjoin(TournamentPartner,TournamentPartner.entry_id==TournamentEntry.id).where(
            or_(TournamentEntry.participant_id==participant_id,TournamentPartner.participant_id==participant_id))
        query=query.where(Tournament.id.in_(entries))
    return [torneos.detail(session,tid,identity) for tid in session.scalars(query).all()]


def records(view):
    entrants={p['participant_id']:p for p in view['participants']}
    for stage in view['stages']:
        for round_data in stage['rounds']:
            for game in round_data['matches']:
                result=game['result']
                if not result:continue
                for side,slot in enumerate(game['slots']):
                    own=entrants[slot['participant_id']];other=entrants[game['slots'][1-side]['participant_id']]
                    winner=result['winner_participant_id']
                    outcome='draw' if winner is None else 'win' if winner==own['participant_id'] else 'loss'
                    for pid in own.get('member_ids',[own['participant_id']]):
                        yield {'participant_id':pid,'tournament_id':view['id'],'tournament_name':view['name'],
                            'format':view['format'],'pair_mode':view.get('pair_mode','individual'),
                            'match_id':game['id'],'code':game['code'],'stage':stage['name'],'round':round_data['name'],
                            'team':own['nick'],'opponent':other['nick'],'opponent_ids':other.get('member_ids',[other['participant_id']]),
                            'partner':next((name for mid,name in zip(own.get('member_ids',[]),own.get('member_names',[])) if mid!=pid),None),
                            'goals_for':result['home_score' if side==0 else 'away_score'],
                            'goals_against':result['away_score' if side==0 else 'home_score'],
                            'outcome':outcome,'penalties':winner is not None and result['home_score']==result['away_score'],
                            'recorded_at':result['recorded_at']}


def accumulate(roster,competitions):
    values={p['id']:p | dict(played=0,won=0,drawn=0,lost=0,goals_for=0,goals_against=0,
            goal_difference=0,titles=0,tournaments=0,win_rate=0,team_matches=0) for p in roster}
    for view in competitions:
        for pid in torneos.all_ids(view):
            if pid in values:values[pid]['tournaments']+=1
        if view['finished_at'] and view['champion']:
            for pid in view['champion'].get('member_ids',[view['champion']['participant_id']]):
                if pid in values:values[pid]['titles']+=1
        for row in records(view):
            value=values.get(row['participant_id'])
            if value is None:continue
            value['played']+=1;value[{'win':'won','draw':'drawn','loss':'lost'}[row['outcome']]]+=1
            value['goals_for']+=row['goals_for'];value['goals_against']+=row['goals_against']
            value['team_matches']+=int(row['pair_mode']!='individual')
    for value in values.values():
        value['goal_difference']=value['goals_for']-value['goals_against']
        value['win_rate']=round(100*value['won']/value['played'],1) if value['played'] else 0
    return values


def totals(player,competitions):
    return accumulate([player],competitions)[player['id']]


def ranking(session,identity,page,page_size,q=''):
    competitions=views(session,identity)
    roster=[p for p in players(session,identity) if q.casefold() in p['nick'].casefold()]
    rows=list(accumulate(roster,competitions).values())
    rows.sort(key=lambda r:(-r['titles'],-r['won'],-r['goal_difference'],r['nick'].casefold(),r['id']))
    for index,row in enumerate(rows,1):row['position']=index
    return {'items':rows[(page-1)*page_size:page*page_size],'total':len(rows),'page':page,'page_size':page_size,
            'tournaments':len(competitions),'finished_tournaments':sum(bool(t['finished_at']) for t in competitions),
            'matches':sum(t['completed_matches'] for t in competitions)}


def history(session,identity,participant_id,page,page_size):
    player=next((p for p in players(session,identity) if p['id']==participant_id),None)
    if player is None:raise HTTPException(404,'Jugador no encontrado.')
    competitions=views(session,identity,participant_id)
    rows=[r for view in competitions for r in records(view) if r['participant_id']==participant_id]
    rows.sort(key=lambda r:(r['recorded_at'],r['tournament_id'],r['match_id']),reverse=True)
    titles=[{'tournament_id':t['id'],'name':t['name'],'format':t['format'],'pair_mode':t.get('pair_mode','individual')}
            for t in competitions if t['finished_at'] and t['champion'] and participant_id in t['champion'].get('member_ids',[t['champion']['participant_id']])]
    return {'player':totals(player,competitions),'items':rows[(page-1)*page_size:page*page_size],
            'titles':titles,'total':len(rows),'page':page,'page_size':page_size}
