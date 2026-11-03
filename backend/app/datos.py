"""Describe los datos que recibe y devuelve la API a Angular."""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class ParticipantResponse(BaseModel):
    id: int
    nick: str
    is_active: bool
    has_logo: bool
    created_at: datetime
    updated_at: datetime
    version: int


class Summary(BaseModel):
    total: int
    active: int
    inactive: int


class ParticipantPage(BaseModel):
    items: list[ParticipantResponse]
    total: int
    page: int
    page_size: int
    summary: Summary


class StateUpdate(BaseModel):
    is_active: bool
    version: int = Field(ge=1)


StatusFilter = Literal['all', 'active', 'inactive']


def participant_to_dict(participant):
    """Convierte un modelo de la base de datos en un diccionario para Angular."""
    return {
        'id': participant.id,
        'nick': participant.nick,
        'is_active': participant.is_active,
        'has_logo': participant.logo is not None,
        'created_at': participant.created_at,
        'updated_at': participant.updated_at,
        'version': participant.version,
    }


class RegisterData(BaseModel):
    username: str = Field(min_length=3, max_length=24)
    password: str = Field(min_length=10, max_length=128)


class LoginData(BaseModel):
    username: str = Field(min_length=1, max_length=24)
    password: str = Field(min_length=1, max_length=128)


from uuid import UUID, uuid4


class TournamentCreate(BaseModel):
    name: str = Field(min_length=3,max_length=80)
    format: Literal['single_elimination','double_elimination','groups_knockout','league']
    pair_mode: Literal['individual','manual','random'] = 'individual'
    league_rounds: int = Field(default=1,ge=1,le=2,strict=True)
    pairs: list[tuple[Annotated[int,Field(strict=True,ge=1)],Annotated[int,Field(strict=True,ge=1)]]] = Field(default_factory=list,max_length=64)
    participant_count: int = Field(ge=2,le=128,strict=True)
    participant_ids: list[Annotated[int, Field(strict=True,ge=1)]] = Field(min_length=2,max_length=128)
    request_key: UUID = Field(default_factory=uuid4)


class ResultCreate(BaseModel):
    version: int = Field(ge=1,strict=True)
    home_score: int = Field(ge=0,le=99,strict=True)
    away_score: int = Field(ge=0,le=99,strict=True)
    winner_participant_id: int | None = Field(default=None,ge=1,strict=True)
