"""Jugadores temporales en memoria. Este módulo nunca guarda en MariaDB."""
import unicodedata

from fastapi import HTTPException

from bd.modelos import Participant, ParticipantLogo
from .datos import participant_to_dict
from .sesiones import guest_data, guest_lock, utc_now, guests


def key(nick):
    # Misma política visible: sin distinguir mayúsculas ni acentos.
    value = unicodedata.normalize('NFKD', nick).casefold()
    return ''.join(character for character in value if not unicodedata.combining(character))


def get_participant(identity, participant_id):
    participant = guest_data(identity)['participants'].get(participant_id)
    if participant is None:
        raise HTTPException(404, 'Participante no encontrado.')
    return participant


def list_participants(identity, query, status, page, page_size):
    with guest_lock:
        all_items = list(guest_data(identity)['participants'].values())
        active = sum(1 for participant in all_items if participant.is_active)
        items = []
        for participant in reversed(all_items):
            if key(query.strip()) not in key(participant.nick):
                continue
            if status != 'all' and participant.is_active != (status == 'active'):
                continue
            items.append(participant)
        start = (page - 1) * page_size
        return {'items': [participant_to_dict(p) for p in items[start:start + page_size]],
                'total': len(items), 'page': page, 'page_size': page_size,
                'summary': {'total': len(all_items), 'active': active, 'inactive': len(all_items) - active}}


def save(identity, nick, is_active, image, remove_logo=False, participant_id=None, version=None):
    with guest_lock:
        data = guest_data(identity)
        if image is not None:
            image_bytes = sum(len(p.logo.content) for guest in guests.values()
                              for p in guest['participants'].values() if p.logo is not None)
            previous = data['participants'].get(participant_id)
            if previous is not None and previous.logo is not None:
                image_bytes -= len(previous.logo.content)
            if image_bytes + len(image) > 32 * 1024 * 1024:
                raise HTTPException(503, 'El espacio temporal para logos está lleno. Prueba sin logo o crea una cuenta.')
        for participant in data['participants'].values():
            if participant.id != participant_id and key(participant.nick) == key(nick):
                raise HTTPException(409, 'Ya existe un participante con ese nick. No se distinguen mayúsculas ni acentos.')
        if participant_id is None:
            if len(data['participants']) >= 32:
                raise HTTPException(422, 'La sesión de invitado admite hasta 32 jugadores. Crea una cuenta para guardar tu comunidad.')
            participant = Participant(id=data['next_id'], created_at=utc_now(), version=1)
            data['next_id'] += 1
        else:
            participant = get_participant(identity, participant_id)
            if participant.version != version:
                raise HTTPException(409, 'El participante cambió en otra sesión. Recarga la lista antes de editarlo.')
            participant.version += 1
        participant.nick = nick
        participant.is_active = is_active
        participant.updated_at = utc_now()
        if image is not None:
            participant.logo = ParticipantLogo(content=image)
        elif remove_logo:
            participant.logo = None
        data['participants'][participant.id] = participant
        return participant_to_dict(participant)


def change_state(identity, participant_id, is_active, version):
    with guest_lock:
        participant = get_participant(identity, participant_id)
        return save(identity, participant.nick, is_active, None, participant_id=participant_id, version=version)
