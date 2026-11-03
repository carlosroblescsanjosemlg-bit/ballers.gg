"""Validaciones, sorteo y consulta de torneos. Sin clases intermedias."""
from copy import deepcopy
from collections import defaultdict
import secrets
import unicodedata

from fastapi import HTTPException
from sqlalchemy import select, func, delete
from sqlalchemy.exc import IntegrityError

from bd.modelos import (Participant, Tournament, TournamentEntry, TournamentStage,
                        TournamentGroupMember, TournamentRound, TournamentMatch, TournamentSlot, MatchResult, GroupDraw, TournamentPartner)
from . import cuadros
from .sesiones import guest_data, guest_lock, utc_now


def validate(payload):
    name = unicodedata.normalize('NFKC', payload.name).strip()
    if not 3 <= len(name) <= 80 or any(unicodedata.category(c).startswith('C') for c in name):
        raise HTTPException(422, 'El nombre del torneo debe tener entre 3 y 80 caracteres, sin caracteres de control.')
    ids = payload.participant_ids
    if len(ids) != len(set(ids)):
        raise HTTPException(422, 'No puedes inscribir al mismo jugador más de una vez.')
    if len(ids) != payload.participant_count:
        raise HTTPException(422, f'Selecciona exactamente {payload.participant_count} jugadores para este torneo.')
    if payload.pair_mode!='individual' and (len(ids)<4 or len(ids)%2):
        raise HTTPException(422,'Los torneos en pareja necesitan un número par de jugadores, al menos cuatro.')
    if payload.pair_mode=='manual':
        paired=[pid for pair in payload.pairs for pid in pair]
        if len(paired)!=len(ids) or len(set(paired))!=len(ids) or set(paired)!=set(ids):
            raise HTTPException(422,'Forma parejas de dos sin repetir jugadores y utiliza todos los seleccionados.')
    elif payload.pairs:
        raise HTTPException(422,'Solo las parejas elegidas manualmente admiten una lista de parejas.')
    if payload.format!='league' and payload.league_rounds!=1:
        raise HTTPException(422,'La opción ida y vuelta solo corresponde a las ligas.')
    return name, ids


def eligible(session, identity):
    if identity['mode'] == 'guest':
        with guest_lock:
            return [{'id':p.id,'nick':p.nick} for p in guest_data(identity)['participants'].values() if p.is_active]
    rows = session.execute(select(Participant.id, Participant.nick).where(
        Participant.owner_id == identity['user_id'], Participant.is_active.is_(True)).order_by(Participant.nick)).all()
    return [{'id':row.id, 'nick':row.nick} for row in rows]


def all_ids(view):
    return [pid for person in view['participants'] for pid in person.get('member_ids',[person['participant_id']])]


def same_request(tournament, payload, name, ids, enrolled):
    if (tournament['name']!=name or tournament['format']!=payload.format or set(enrolled)!=set(ids)
            or tournament.get('pair_mode','individual')!=payload.pair_mode
            or tournament.get('league_rounds',1)!=payload.league_rounds):
        raise HTTPException(409,'Este envío ya se utilizó con otros datos. Vuelve a abrir el formulario.')
    if payload.pair_mode=='manual':
        old={tuple(sorted(p['member_ids'])) for p in tournament['participants']}
        if old!={tuple(sorted(pair)) for pair in payload.pairs}:
            raise HTTPException(409,'Este envío ya se utilizó con otras parejas.')


def generate_plan(payload, ids):
    shuffled=list(ids); secrets.SystemRandom().shuffle(shuffled)
    pairs={}
    if payload.pair_mode=='manual':
        pairs={min(pair):max(pair) for pair in payload.pairs}
        shuffled=list(pairs);secrets.SystemRandom().shuffle(shuffled)
    elif payload.pair_mode=='random':
        pairs={shuffled[i]:shuffled[i+1] for i in range(0,len(shuffled),2)}
        shuffled=list(pairs)
    plan=cuadros.generate(payload.format,shuffled,payload.league_rounds)
    plan['pairs']=pairs
    return plan


def create(session, payload, identity):
    name, ids = validate(payload)
    if identity['mode'] == 'guest':
        with guest_lock:
            data = guest_data(identity)
            tournaments = data.setdefault('tournaments', {})
            for old in tournaments.values():
                if old['request_key'] == str(payload.request_key):
                    same_request(guest_detail(data,old), payload, name, ids, all_ids(guest_detail(data,old)))
                    return guest_detail(data, old)
            if len(tournaments) >= 20:
                raise HTTPException(422, 'La sesión invitada admite hasta 20 torneos temporales.')
            if any(pid not in data['participants'] or not data['participants'][pid].is_active for pid in ids):
                raise HTTPException(422, 'Selecciona únicamente jugadores activos de tu plantilla. Recarga la selección.')
            next_id = data.setdefault('next_tournament_id',max(tournaments,default=0)+1)
            value = {'id':next_id, 'name':name, 'format':payload.format,
                     'min_participants':payload.participant_count, 'max_participants':payload.participant_count,
                     'created_at':utc_now(), 'request_key':str(payload.request_key), 'version':1, 'finished_at':None,
                     'pair_mode':payload.pair_mode,'league_rounds':payload.league_rounds,
                     'plan':generate_plan(payload,ids)}
            tournaments[value['id']] = value
            data['next_tournament_id'] = next_id+1
            return guest_detail(data, value)
    old = session.scalar(select(Tournament).where(Tournament.owner_id == identity['user_id'],
                                                  Tournament.request_key == str(payload.request_key)))
    if old:
        result = detail(session, old.id, identity)
        same_request(result, payload, name, ids, all_ids(result))
        return result
    # Bloquear las filas impide que una desactivación simultánea se cuele en el sorteo.
    players = session.scalars(select(Participant).where(Participant.owner_id == identity['user_id'],
                    Participant.id.in_(ids)).order_by(Participant.id).with_for_update()).all()
    if len(players) != len(ids) or any(not p.is_active for p in players):
        session.rollback()
        raise HTTPException(422, 'Selecciona únicamente jugadores activos de tu plantilla. Recarga la selección.')
    plan = generate_plan(payload,ids)
    tournament = Tournament(owner_id=identity['user_id'], name=name, format=payload.format,
                            min_participants=payload.participant_count, max_participants=payload.participant_count,
                            request_key=str(payload.request_key),pair_mode=payload.pair_mode,league_rounds=payload.league_rounds)
    try:
        session.add(tournament); session.flush()
        save_plan(session, tournament.id, plan)
        session.commit()
    except IntegrityError:
        session.rollback()
        old = session.scalar(select(Tournament).where(Tournament.owner_id == identity['user_id'],
                                                      Tournament.request_key == str(payload.request_key)))
        if old:
            result = detail(session, old.id, identity)
            same_request(result, payload, name, ids, all_ids(result))
            return result
        raise HTTPException(409, 'No se pudo guardar el torneo. Recarga tu plantilla antes de intentarlo.')
    return detail(session, tournament.id, identity)


def save_plan(session, tournament_id, plan):
    # Guardar en bloques evita una ida a MariaDB por cada jugador y cada partido.
    entry_rows = [TournamentEntry(tournament_id=tournament_id,participant_id=pid,draw_position=position)
                  for position,pid in enumerate(plan['entry_order'],1)]
    session.add_all(entry_rows); session.flush()
    entries = {row.participant_id:row.id for row in entry_rows}
    for leader,partner in plan.get('pairs',{}).items():
        session.add(TournamentPartner(entry_id=entries[leader],participant_id=partner))
    stage_rows = {s['key']:TournamentStage(tournament_id=tournament_id,kind=s['kind'],name=s['name'],position=s['position'])
                  for s in plan['stages']}
    session.add_all(stage_rows.values()); session.flush()
    stages = {key:row.id for key,row in stage_rows.items()}
    rounds = {}
    for stage in plan['stages']:
        for round_data in stage['rounds']:
            rounds[(stage['key'],round_data['number'])] = TournamentRound(
                stage_id=stages[stage['key']],number=round_data['number'],name=round_data['name'])
    session.add_all(rounds.values()); session.flush()
    matches = {}
    for stage in plan['stages']:
        for round_data in stage['rounds']:
            for match in round_data['matches']:
                matches[match['key']] = TournamentMatch(
                    round_id=rounds[(stage['key'],round_data['number'])].id,position=match['position'])
    session.add_all(matches.values()); session.flush()
    for group in plan['groups']:
        for pid in group['participant_ids']:
            session.add(TournamentGroupMember(stage_id=stages[group['stage_key']],entry_id=entries[pid]))
    for stage in plan['stages']:
        for round_data in stage['rounds']:
            for match in round_data['matches']:
                for number,slot in enumerate(match['slots'],1):
                    session.add(TournamentSlot(match_id=matches[match['key']].id,slot_number=number,
                        entry_id=entries.get(slot.get('participant_id')),
                        source_match_id=matches[slot['source_match']].id if 'source_match' in slot else None,
                        source_outcome=slot.get('outcome'),source_group_id=stages.get(slot.get('source_group')),
                        group_rank=slot.get('rank')))


def metadata(tournament):
    return {key:getattr(tournament,key) for key in
            ('id','name','format','created_at','version','finished_at','pair_mode','league_rounds')}


def list_tournaments(session, identity, page, page_size):
    if identity['mode'] == 'guest':
        with guest_lock:
            values = list(reversed(list(guest_data(identity).get('tournaments',{}).values())))
            total = len(values)
            items = [{key:value[key] for key in ('id','name','format','created_at')}
                     | {'participant_count':len(value['plan']['entry_order'])*(2 if value.get('pair_mode','individual')!='individual' else 1),'finished_at':value.get('finished_at'),'version':value.get('version',1),'pair_mode':value.get('pair_mode','individual'),'league_rounds':value.get('league_rounds',1),'competitor_count':len(value['plan']['entry_order'])} for value in values[(page-1)*page_size:page*page_size]]
    else:
        owner = Tournament.owner_id == identity['user_id']
        total = session.scalar(select(func.count(Tournament.id)).where(owner))
        rows = session.scalars(select(Tournament).where(owner).order_by(Tournament.created_at.desc(),Tournament.id.desc())
                                .offset((page-1)*page_size).limit(page_size)).all()
        counts = dict(session.execute(select(TournamentEntry.tournament_id,func.count(TournamentEntry.id))
                      .where(TournamentEntry.tournament_id.in_([t.id for t in rows])).group_by(TournamentEntry.tournament_id)).all()) if rows else {}
        items = [metadata(t) | {'participant_count':counts.get(t.id,0)*(2 if t.pair_mode!='individual' else 1),'competitor_count':counts.get(t.id,0)} for t in rows]
    return {'items':items,'total':total,'page':page,'page_size':page_size}


def detail(session, tournament_id, identity):
    if identity['mode'] == 'guest':
        with guest_lock:
            data = guest_data(identity)
            value = data.get('tournaments',{}).get(tournament_id)
            if value is None:
                raise HTTPException(404, 'Torneo no encontrado.')
            return guest_detail(data, value)
    tournament = session.scalar(select(Tournament).where(Tournament.id == tournament_id,Tournament.owner_id == identity['user_id']))
    if tournament is None:
        raise HTTPException(404, 'Torneo no encontrado.')
    entries = session.execute(select(TournamentEntry, Participant.nick, Participant.is_active)
                   .join(Participant, Participant.id == TournamentEntry.participant_id)
                   .where(TournamentEntry.tournament_id == tournament.id).order_by(TournamentEntry.draw_position)).all()
    people = [{'entry_id':e.id,'participant_id':e.participant_id,'nick':nick,'is_active':active,'draw_position':e.draw_position}
              for e,nick,active in entries]
    partners=session.execute(select(TournamentPartner,Participant.nick,Participant.is_active).join(Participant,
        Participant.id==TournamentPartner.participant_id).where(TournamentPartner.entry_id.in_([p['entry_id'] for p in people]))).all()
    partner_map={row.entry_id:(row.participant_id,nick,active) for row,nick,active in partners}
    for person in people:
        person['member_ids']=[person['participant_id']]
        person['member_names']=[person['nick']]
        if person['entry_id'] in partner_map:
            pid,nick,active=partner_map[person['entry_id']]
            person['member_ids'].append(pid);person['member_names'].append(nick)
            person['nick']+=' & '+nick;person['is_active']=person['is_active'] and active
    entry_map = {p['entry_id']:p['participant_id'] for p in people}
    stages = session.scalars(select(TournamentStage).where(TournamentStage.tournament_id == tournament.id).order_by(TournamentStage.position)).all()
    stage_ids = [s.id for s in stages]
    rounds = session.scalars(select(TournamentRound).where(TournamentRound.stage_id.in_(stage_ids)).order_by(TournamentRound.number)).all()
    matches = session.scalars(select(TournamentMatch).where(TournamentMatch.round_id.in_([r.id for r in rounds])).order_by(TournamentMatch.position)).all()
    slots = session.scalars(select(TournamentSlot).where(TournamentSlot.match_id.in_([m.id for m in matches])).order_by(TournamentSlot.slot_number)).all()
    members = session.execute(select(TournamentGroupMember).where(TournamentGroupMember.stage_id.in_(stage_ids))).scalars().all()
    by_stage=defaultdict(list);by_round=defaultdict(list);by_match=defaultdict(list)
    for row in rounds:by_stage[row.stage_id].append(row)
    for row in matches:by_round[row.round_id].append(row)
    for row in slots:by_match[row.match_id].append(row)
    plan = {'stages':[], 'groups':[]}
    for s in stages:
        stage_data = {'key':str(s.id),'name':s.name,'kind':s.kind,'position':s.position,'rounds':[]}
        plan['stages'].append(stage_data)
        if s.kind in ('group','league'):
            plan['groups'].append({'stage_key':str(s.id),'participant_ids':[entry_map[m.entry_id] for m in members if m.stage_id == s.id]})
        for r in by_stage[s.id]:
            round_data = {'number':r.number,'name':r.name,'matches':[]}; stage_data['rounds'].append(round_data)
            for m in by_round[r.id]:
                match_data = {'key':str(m.id),'position':m.position,'slots':[]}; round_data['matches'].append(match_data)
                for slot in by_match[m.id]:
                    value = {}
                    if slot.entry_id is not None: value = {'participant_id':entry_map[slot.entry_id]}
                    elif slot.source_match_id is not None: value = {'source_match':str(slot.source_match_id),'outcome':slot.source_outcome}
                    elif slot.source_group_id is not None: value = {'source_group':str(slot.source_group_id),'rank':slot.group_rank}
                    match_data['slots'].append(value)
    results = session.scalars(select(MatchResult).where(MatchResult.match_id.in_([m.id for m in matches]))).all()
    draws = session.scalars(select(GroupDraw).where(GroupDraw.stage_id.in_(stage_ids))).all()
    result_map = {str(r.match_id):{'home_score':r.home_score,'away_score':r.away_score,
                  'winner_participant_id':entry_map.get(r.winner_entry_id),'recorded_at':r.recorded_at} for r in results}
    draw_map = {}
    for d in sorted(draws,key=lambda d:d.draw_order):
        draw_map.setdefault(str(d.stage_id),[]).append(entry_map[d.entry_id])
    return present(metadata(tournament), people, plan, result_map, draw_map)


def guest_detail(data, tournament):
    people = []
    for position, pid in enumerate(tournament['plan']['entry_order'],1):
        player = data['participants'][pid]
        partner=tournament['plan'].get('pairs',{}).get(pid)
        member_ids=[pid]+([partner] if partner else [])
        names=[data['participants'][mid].nick for mid in member_ids]
        people.append({'entry_id':pid,'participant_id':pid,'nick':' & '.join(names),
                       'is_active':all(data['participants'][mid].is_active for mid in member_ids),
                       'member_ids':member_ids,'member_names':names,'draw_position':position})
    return present({key:tournament[key] for key in ('id','name','format','created_at')} | {'version':tournament.get('version',1),'finished_at':tournament.get('finished_at'),'pair_mode':tournament.get('pair_mode','individual'),'league_rounds':tournament.get('league_rounds',1)}, people, deepcopy(tournament['plan']), tournament.get('results',{}), tournament.get('draws',{}))


def present(tournament, participants, plan, results=None, draws=None):
    from .resultados import present
    return present(tournament, participants, plan, results or {}, draws or {})


def remove(session, tournament_id, version, identity):
    """Eliminar solo el torneo propio, conservando su plantilla de jugadores."""
    if identity['mode']=='guest':
        with guest_lock:
            tournaments=guest_data(identity).get('tournaments',{})
            value=tournaments.get(tournament_id)
            if value is None: raise HTTPException(404,'Torneo no encontrado.')
            if value.get('version',1)!=version:
                raise HTTPException(409,'El torneo ha cambiado. Recárgalo antes de eliminarlo.')
            del tournaments[tournament_id]
        return
    # Comparte el bloqueo de resultados para evitar borrar mientras se registra uno.
    session.commit()
    tournament=session.scalar(select(Tournament).where(Tournament.id==tournament_id,
        Tournament.owner_id==identity['user_id']).with_for_update().execution_options(populate_existing=True))
    if tournament is None: raise HTTPException(404,'Torneo no encontrado.')
    try:
        if tournament.version!=version:
            raise HTTPException(409,'El torneo ha cambiado. Recárgalo antes de eliminarlo.')
        match_ids=select(TournamentMatch.id).join(TournamentRound).join(TournamentStage).where(TournamentStage.tournament_id==tournament_id)
        # Retirar referencias RESTRICT antes de eliminar el torneo y sus hijos CASCADE.
        session.execute(delete(MatchResult).where(MatchResult.match_id.in_(match_ids)))
        session.execute(delete(TournamentSlot).where(TournamentSlot.match_id.in_(match_ids)))
        session.execute(delete(Tournament).where(Tournament.id==tournament_id,Tournament.owner_id==identity['user_id']))
        session.commit()
    except Exception:
        session.rollback()
        raise
