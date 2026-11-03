"""Funciones con las validaciones y operaciones de los participantes."""
import unicodedata
import warnings
from datetime import datetime, timezone
from io import BytesIO

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from bd import consultas
from bd.modelos import Participant, ParticipantLogo
from .datos import participant_to_dict
from . import invitados

MAX_LOGO_BYTES = 2 * 1024 * 1024
CONFLICT_MESSAGE = 'El participante cambió en otra sesión. Recarga la lista antes de editarlo.'


def get_participant(session, participant_id, identity):
    if identity['mode'] == 'guest':
        return invitados.get_participant(identity, participant_id)
    participant = consultas.get_participant(session, participant_id, identity['user_id'])
    if participant is None:
        raise HTTPException(404, 'Participante no encontrado.')
    return participant


def list_participants(session, nick, status, page, page_size, identity):
    if identity['mode'] == 'guest':
        return invitados.list_participants(identity, nick, status, page, page_size)
    participants, total, summary = consultas.list_participants(
        session, nick.strip(), status, page, page_size, identity['user_id'],
    )
    items = []
    for participant in participants:
        items.append(participant_to_dict(participant))
    return {'items': items, 'total': total, 'page': page, 'page_size': page_size, 'summary': summary}


def validate_nick(nick):
    nick = unicodedata.normalize('NFKC', nick).strip()
    if len(nick) < 2 or len(nick) > 24:
        raise HTTPException(422, 'El nick debe tener entre 2 y 24 caracteres.')
    for character in nick:
        if unicodedata.category(character).startswith('C'):
            raise HTTPException(422, 'El nick no puede contener caracteres de control.')
    return nick


def validate_logo(content):
    if not content or len(content) > MAX_LOGO_BYTES:
        raise HTTPException(422, 'El logo debe ocupar entre 1 byte y 2 MB.')
    try:
        # Pillow detecta imágenes enormes; tratamos también ese aviso como error.
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                if image.format not in ('PNG', 'JPEG', 'WEBP'):
                    raise ValueError()
                width, height = image.size
                if width > 4096 or height > 4096:
                    raise ValueError()
                image.load()
                image = image.convert('RGBA')
                image.thumbnail((512, 512))
                output = BytesIO()
                image.save(output, format='PNG')
                return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise HTTPException(422, 'El logo debe ser PNG, JPG o WebP válido, de hasta 4096 × 4096 píxeles.')


def check_version(participant, version):
    if participant.version != version:
        raise HTTPException(409, CONFLICT_MESSAGE)


def update_logo(participant, content, remove_logo):
    if content is not None and remove_logo:
        raise HTTPException(422, 'No se puede subir y quitar el logo al mismo tiempo.')
    if content is not None:
        image = validate_logo(content)
        if participant.logo is None:
            participant.logo = ParticipantLogo(content=image)
        else:
            participant.logo.content = image
    elif remove_logo:
        participant.logo = None


def save_changes(session, participant):
    """Guarda todos los cambios juntos; si hay un conflicto, los deshace."""
    participant.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        session.add(participant)
        session.commit()
        session.refresh(participant)
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, 'Ya existe un participante con ese nick. No se distinguen mayúsculas ni acentos.')
    except StaleDataError:
        session.rollback()
        raise HTTPException(409, CONFLICT_MESSAGE)
    return participant_to_dict(participant)


def create_participant(session, nick, is_active, logo=None, identity=None):
    if identity['mode'] == 'guest':
        image = validate_logo(logo) if logo is not None else None
        return invitados.save(identity, validate_nick(nick), is_active, image)
    participant = Participant(owner_id=identity['user_id'])
    participant.nick = validate_nick(nick)
    participant.is_active = is_active
    update_logo(participant, logo, remove_logo=False)
    return save_changes(session, participant)


def edit_participant(session, participant_id, nick, is_active, version, logo=None, remove_logo=False, identity=None):
    if identity['mode'] == 'guest':
        if logo is not None and remove_logo:
            raise HTTPException(422, 'No se puede subir y quitar el logo al mismo tiempo.')
        image = validate_logo(logo) if logo is not None else None
        return invitados.save(identity, validate_nick(nick), is_active, image, remove_logo, participant_id, version)
    participant = get_participant(session, participant_id, identity)
    check_version(participant, version)
    participant.nick = validate_nick(nick)
    participant.is_active = is_active
    update_logo(participant, logo, remove_logo)
    # También cambia la versión si la edición solo modifica el logo.
    participant.version += 1
    return save_changes(session, participant)


def change_state(session, participant_id, is_active, version, identity):
    if identity['mode'] == 'guest':
        return invitados.change_state(identity, participant_id, is_active, version)
    participant = get_participant(session, participant_id, identity)
    check_version(participant, version)
    participant.is_active = is_active
    participant.version += 1
    return save_changes(session, participant)
