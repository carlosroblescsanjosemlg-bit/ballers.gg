"""Consultas a MariaDB. Las reglas y los mensajes pertenecen a app/participantes.py."""
from sqlalchemy import func, select

from .modelos import Participant


def get_participant(session, participant_id, owner_id):
    return session.scalar(select(Participant).where(Participant.id == participant_id, Participant.owner_id == owner_id))


def apply_filters(query, nick, status):
    if nick:
        # autoescape hace que % y _ se busquen como texto, no como comodines SQL.
        query = query.where(Participant.nick.contains(nick, autoescape=True))
    if status == 'active':
        query = query.where(Participant.is_active.is_(True))
    elif status == 'inactive':
        query = query.where(Participant.is_active.is_(False))
    return query


def list_participants(session, nick, status, page, page_size, owner_id):
    query = apply_filters(select(Participant).where(Participant.owner_id == owner_id), nick, status)
    query = query.order_by(Participant.id.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    participants = session.scalars(query).all()

    count_query = select(func.count(Participant.id)).where(Participant.owner_id == owner_id)
    filtered_count = apply_filters(count_query, nick, status)
    total = session.scalar(filtered_count)

    # El resumen incluye toda la comunidad, aunque el listado esté filtrado.
    all_count = session.scalar(count_query)
    active_query = count_query.where(Participant.is_active.is_(True))
    active_count = session.scalar(active_query)
    summary = {
        'total': all_count,
        'active': active_count,
        'inactive': all_count - active_count,
    }
    return participants, total, summary
