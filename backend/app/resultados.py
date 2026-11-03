"""Marcadores, clasificación y avance. Las lecturas nunca sortean ni escriben."""
from collections import defaultdict
from copy import deepcopy
import secrets

from fastapi import HTTPException
from sqlalchemy import select
from bd.modelos import Tournament, MatchResult, GroupDraw
from .sesiones import guest_data, guest_lock, utc_now


def standings(member_ids, games, results, draws, people):
    rows = {pid:dict(participant_id=pid,nick=people[pid]['nick'],played=0,won=0,drawn=0,lost=0,
                     goals_for=0,goals_against=0,goal_difference=0,points=0,by_draw=False) for pid in member_ids}
    for game in games:
        result = results.get(game['key'])
        if result is None: continue
        ids = [s['participant_id'] for s in game['slots']]
        scores = [result['home_score'],result['away_score']]
        for index,pid in enumerate(ids):
            row=rows[pid]; own=scores[index]; other=scores[1-index]
            row['played']+=1; row['goals_for']+=own; row['goals_against']+=other
            row['won']+=int(own>other); row['drawn']+=int(own==other); row['lost']+=int(own<other)
            row['points']+=3 if own>other else 1 if own==other else 0
            row['goal_difference']=row['goals_for']-row['goals_against']
    complete=all(g['key'] in results for g in games)
    ties=defaultdict(list)
    for row in rows.values(): ties[(row['points'],row['goal_difference'])].append(row['participant_id'])
    tied=[ids for ids in ties.values() if len(ids)>1] if complete else []
    ready=complete and all(pid in draws for ids in tied for pid in ids)
    for pid in draws:
        if pid in rows: rows[pid]['by_draw']=True
    order={pid:index for index,pid in enumerate(draws)}
    ordered=sorted(rows.values(),key=lambda r:(-r['points'],-r['goal_difference'],order.get(r['participant_id'],999),r['participant_id']))
    for position,row in enumerate(ordered,1): row['position']=position
    return {'standings':ordered,'complete':complete,'ready':ready,'tied':tied,'draw_used':bool(draws)}


def present(tournament, participants, plan, results, draws):
    people={p['participant_id']:p for p in participants}
    matches={}; codes={}; groups={}; names={}
    for stage in plan['stages']:
        names[stage['key']]=stage['name']
        prefix={'upper':'U','lower':'L','final':'F','knockout':'K','group':f'G{stage["position"]}','league':'J'}[stage['kind']]
        for round_data in stage['rounds']:
            for game in round_data['matches']:
                matches[game['key']]=game
                codes[game['key']]=f'{prefix}{round_data["number"]}-{game["position"]}'
        if stage['kind'] in ('group','league'):
            ids=next(g['participant_ids'] for g in plan['groups'] if g['stage_key']==stage['key'])
            games=[g for r in stage['rounds'] for g in r['matches']]
            groups[stage['key']]=standings(ids,games,results,draws.get(stage['key'],[]),people)
    cache={}
    def player(pid):
        return {'kind':'participant','label':people[pid]['nick'],'participant_id':pid}
    def bye(): return {'kind':'bye','label':'Pase libre','participant_id':None}
    def resolve(slot):
        if 'participant_id' in slot: return player(slot['participant_id'])
        if 'source_group' in slot:
            group=groups[slot['source_group']]
            if group['ready']: return player(group['standings'][slot['rank']-1]['participant_id'])
            return {'kind':'qualifier','label':f'{slot["rank"]}.º de {names[slot["source_group"]]}','participant_id':None}
        if 'source_match' in slot:
            key=slot['source_match']; sides=resolve_match(key)
            result=results.get(key)
            if result:
                winner=result['winner_participant_id']
                if slot['outcome']=='winner': return player(winner)
                return next(dict(s) for s in sides if s['participant_id']!=winner)
            byes=[s['kind']=='bye' for s in sides]
            if any(byes):
                if slot['outcome']=='loser' or all(byes): return bye()
                return dict(sides[1] if byes[0] else sides[0])
            return {'kind':'source','label':f'{"Ganador" if slot["outcome"]=="winner" else "Perdedor"} {codes[key]}','participant_id':None}
        return bye()
    def resolve_match(key):
        if key not in cache: cache[key]=[resolve(s) for s in matches[key]['slots']]
        return cache[key]
    stages=[]
    for stage in plan['stages']:
        output={k:stage[k] for k in ('key','kind','name','position')}; output['rounds']=[]
        ids=next((g['participant_ids'] for g in plan['groups'] if g['stage_key']==stage['key']),[])
        output['participants']=[people[pid] for pid in ids]
        if stage['kind'] in ('group','league'): output.update(groups[stage['key']])
        for round_data in stage['rounds']:
            games=[]
            for game in round_data['matches']:
                key=game['key']; sides=resolve_match(key); kinds=[s['kind'] for s in sides]
                result=results.get(key)
                state='completed' if result else 'empty' if kinds.count('bye')==2 else 'bye' if 'bye' in kinds else 'scheduled' if kinds.count('participant')==2 else 'waiting'
                games.append({'id':key,'code':codes[key],'position':game['position'],'state':state,'slots':sides,'result':result})
            output['rounds'].append({'number':round_data['number'],'name':round_data['name'],'matches':games})
        stages.append(output)
    if tournament['format']=='league':
        table=groups[stages[0]['key']]
        champion=people[table['standings'][0]['participant_id']] if table['ready'] else None
    else:
        terminal=next(s for s in reversed(stages) if s['kind'] in ('final','knockout'))['rounds'][-1]['matches'][0]
        champion=people.get(terminal['result']['winner_participant_id']) if terminal['result'] else None
    return tournament | {'version':tournament.get('version',1),'finished_at':tournament.get('finished_at'),
            'status':'finished' if tournament.get('finished_at') else 'in_progress',
            'champion':champion,'competitor_count':len(participants),'participant_count':sum(len(p.get('member_ids',[p['participant_id']])) for p in participants),'participants':participants,'stages':stages,
            'completed_matches':len(results),'group_qualifiers':2 if tournament['format']=='groups_knockout' else None}


def validate_result(view, match_id, payload):
    if view['finished_at']: raise HTTPException(409,'Este torneo ha finalizado y no admite más cambios.')
    if payload.version!=view['version']: raise HTTPException(409,'El cuadro ha cambiado. Recarga antes de registrar el resultado.')
    found=next(((s,m) for s in view['stages'] for r in s['rounds'] for m in r['matches'] if m['id']==match_id),None)
    if not found: raise HTTPException(404,'Partido no encontrado en este torneo.')
    stage,game=found
    if game['state']!='scheduled': raise HTTPException(409,'Este partido ya tiene resultado o todavía no tiene dos rivales definidos.')
    ids=[s['participant_id'] for s in game['slots']]
    a,b=payload.home_score,payload.away_score
    if a!=b:
        winner=ids[0 if a>b else 1]
        if payload.winner_participant_id not in (None,winner): raise HTTPException(422,'El ganador no coincide con el marcador.')
    elif stage['kind'] in ('group','league'):
        winner=None
        if payload.winner_participant_id is not None: raise HTTPException(422,'Un empate de grupos no tiene ganador.')
    else:
        winner=payload.winner_participant_id
        if winner not in ids: raise HTTPException(422,'Indica quién ganó por penaltis para resolver el empate eliminatorio.')
    return {'home_score':a,'away_score':b,'winner_participant_id':winner,'recorded_at':utc_now().replace(microsecond=0)}


def new_draws(view):
    """Solo al completar un grupo: desempate aleatorio real y persistido."""
    values={}
    for stage in view['stages']:
        if stage['kind'] not in ('group','league') or not stage['complete'] or stage['ready']: continue
        order=[]
        for tied in stage['tied']:
            tied=list(tied); secrets.SystemRandom().shuffle(tied); order.extend(tied)
        if order: values[stage['key']]=order
    return values


def record(session, tournament_id, match_id, payload, identity):
    from . import torneos
    if identity['mode']=='guest':
        with guest_lock:
            data=guest_data(identity); original=data.get('tournaments',{}).get(tournament_id)
            if original is None: raise HTTPException(404,'Torneo no encontrado.')
            value=deepcopy(original)
            result=validate_result(torneos.guest_detail(data,value),match_id,payload)
            value.setdefault('results',{})[match_id]=result
            view=torneos.guest_detail(data,value)
            value.setdefault('draws',{}).update(new_draws(view))
            view=torneos.guest_detail(data,value)
            value['version']=payload.version+1
            if view['champion']: value['finished_at']=utc_now().replace(microsecond=0)
            data['tournaments'][tournament_id]=value
            return torneos.guest_detail(data,value)
    # Un bloqueo del torneo serializa resultados, clasificación y cierre.
    # Cerrar la lectura de autenticación: el snapshot de MariaDB debe empezar
    # después de obtener el bloqueo, para ver el resultado del envío anterior.
    session.commit()
    tournament=session.scalar(select(Tournament).where(Tournament.id==tournament_id,
        Tournament.owner_id==identity['user_id']).with_for_update().execution_options(populate_existing=True))
    if tournament is None: raise HTTPException(404,'Torneo no encontrado.')
    try:
        view=torneos.detail(session,tournament_id,identity)
        result=validate_result(view,match_id,payload)
        entries={p['participant_id']:p['entry_id'] for p in view['participants']}
        session.add(MatchResult(match_id=int(match_id),home_score=result['home_score'],away_score=result['away_score'],
                                winner_entry_id=entries.get(result['winner_participant_id']),recorded_at=result['recorded_at']))
        session.flush()
        view=torneos.detail(session,tournament_id,identity)
        for key,ids in new_draws(view).items():
            for index,pid in enumerate(ids,1): session.add(GroupDraw(stage_id=int(key),entry_id=entries[pid],draw_order=index))
        session.flush()
        view=torneos.detail(session,tournament_id,identity)
        tournament.version+=1
        if view['champion']: tournament.finished_at=utc_now().replace(microsecond=0)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return torneos.detail(session,tournament_id,identity)
