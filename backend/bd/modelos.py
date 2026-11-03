"""Modelos de MariaDB. Cada atributo corresponde a una columna o relación."""
from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.dialects.mysql import MEDIUMBLOB, VARCHAR
from sqlalchemy.orm import deferred, relationship

from .conexion import Base


class Participant(Base):
    __tablename__ = 'participants'
    __table_args__ = (
        CheckConstraint('char_length(nick) BETWEEN 2 AND 24', name='ck_participants_nick_length'),
        CheckConstraint('version >= 1', name='ck_participants_version'),
        UniqueConstraint('owner_id', 'nick', name='uq_participants_owner_nick'),
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4', 'mysql_collate': 'utf8mb4_unicode_ci'},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(Integer, ForeignKey('users.id', ondelete='RESTRICT'), nullable=False, index=True)
    nick = Column(VARCHAR(24, collation='utf8mb4_unicode_ci'), nullable=False)
    is_active = Column(Boolean(create_constraint=True, name='ck_participants_is_active'),
                       nullable=False, default=True, server_default='1', index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at = Column(DateTime, nullable=False, server_default=func.current_timestamp(),
                        onupdate=func.current_timestamp())
    version = Column(Integer, nullable=False, default=1, server_default='1')

    logo = relationship('ParticipantLogo', back_populates='participant', uselist=False,
                        cascade='all, delete-orphan', lazy='selectin')

    # Impide que una edición sobrescriba otra realizada desde una sesión distinta.
    __mapper_args__ = {'version_id_col': version}


class ParticipantLogo(Base):
    __tablename__ = 'participant_logos'
    __table_args__ = {
        'mysql_engine': 'InnoDB',
        'mysql_charset': 'utf8mb4',
        'mysql_collate': 'utf8mb4_unicode_ci',
    }

    participant_id = Column(ForeignKey('participants.id', ondelete='CASCADE'), primary_key=True)
    # Los listados no cargan la imagen: se lee cuando se pide el logo.
    content = deferred(Column(MEDIUMBLOB, nullable=False))
    participant = relationship('Participant', back_populates='logo')


class User(Base):
    __tablename__ = 'users'
    __table_args__ = {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4', 'mysql_collate': 'utf8mb4_unicode_ci'}
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(VARCHAR(24, collation='utf8mb4_unicode_ci'), nullable=False, unique=True)
    password_hash = Column(VARCHAR(255), nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())


class UserSession(Base):
    __tablename__ = 'user_sessions'
    __table_args__ = {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4', 'mysql_collate': 'utf8mb4_unicode_ci'}
    token_hash = Column(VARCHAR(64), primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)


class Tournament(Base):
    __tablename__ = 'tournaments'
    __table_args__ = (
        CheckConstraint('min_participants >= 2 AND max_participants >= min_participants AND max_participants <= 128', name='ck_tournament_limits'),
        CheckConstraint("format IN ('single_elimination','double_elimination','groups_knockout','league')", name='ck_tournament_format'),
        UniqueConstraint('owner_id', 'request_key', name='uq_tournament_request'),
        {'mysql_engine':'InnoDB','mysql_charset':'utf8mb4','mysql_collate':'utf8mb4_unicode_ci'},
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(Integer, ForeignKey('users.id', ondelete='RESTRICT'), nullable=False, index=True)
    name = Column(VARCHAR(80), nullable=False)
    format = Column(VARCHAR(24), nullable=False)
    min_participants = Column(Integer, nullable=False)
    max_participants = Column(Integer, nullable=False)
    request_key = Column(VARCHAR(36), nullable=False)
    pair_mode = Column(VARCHAR(12), nullable=False,default='individual',server_default='individual')
    league_rounds = Column(Integer, nullable=False,default=1,server_default='1')
    version = Column(Integer, nullable=False, default=1, server_default='1')
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())


class TournamentEntry(Base):
    __tablename__ = 'tournament_entries'
    __table_args__ = (
        UniqueConstraint('tournament_id','participant_id',name='uq_tournament_participant'),
        UniqueConstraint('tournament_id','draw_position',name='uq_tournament_seed'),
        CheckConstraint('draw_position >= 1',name='ck_entry_position'),
        {'mysql_engine':'InnoDB','mysql_charset':'utf8mb4','mysql_collate':'utf8mb4_unicode_ci'},
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    tournament_id = Column(Integer, ForeignKey('tournaments.id',ondelete='CASCADE'),nullable=False,index=True)
    participant_id = Column(Integer, ForeignKey('participants.id',ondelete='RESTRICT'),nullable=False,index=True)
    draw_position = Column(Integer,nullable=False)


class TournamentStage(Base):
    __tablename__ = 'tournament_stages'
    __table_args__ = (
        UniqueConstraint('tournament_id','position',name='uq_tournament_stage_position'),
        CheckConstraint("kind IN ('knockout','upper','lower','final','group','league')",name='ck_stage_kind'),
        {'mysql_engine':'InnoDB','mysql_charset':'utf8mb4','mysql_collate':'utf8mb4_unicode_ci'},
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    tournament_id = Column(Integer,ForeignKey('tournaments.id',ondelete='CASCADE'),nullable=False,index=True)
    kind = Column(VARCHAR(16),nullable=False)
    name = Column(VARCHAR(60),nullable=False)
    position = Column(Integer,nullable=False)


class TournamentGroupMember(Base):
    __tablename__ = 'tournament_group_members'
    __table_args__ = (UniqueConstraint('entry_id',name='uq_group_member_entry'),
                      {'mysql_engine':'InnoDB','mysql_charset':'utf8mb4','mysql_collate':'utf8mb4_unicode_ci'})
    stage_id = Column(Integer,ForeignKey('tournament_stages.id',ondelete='CASCADE'),primary_key=True)
    entry_id = Column(Integer,ForeignKey('tournament_entries.id',ondelete='CASCADE'),primary_key=True)


class TournamentRound(Base):
    __tablename__ = 'tournament_rounds'
    __table_args__ = (UniqueConstraint('stage_id','number',name='uq_stage_round'),
                      CheckConstraint('number >= 1',name='ck_round_number'),
                      {'mysql_engine':'InnoDB','mysql_charset':'utf8mb4','mysql_collate':'utf8mb4_unicode_ci'})
    id = Column(Integer,primary_key=True,autoincrement=True)
    stage_id = Column(Integer,ForeignKey('tournament_stages.id',ondelete='CASCADE'),nullable=False,index=True)
    number = Column(Integer,nullable=False)
    name = Column(VARCHAR(60),nullable=False)


class TournamentMatch(Base):
    __tablename__ = 'tournament_matches'
    __table_args__ = (UniqueConstraint('round_id','position',name='uq_round_match'),
                      CheckConstraint('position >= 1',name='ck_match_position'),
                      {'mysql_engine':'InnoDB','mysql_charset':'utf8mb4','mysql_collate':'utf8mb4_unicode_ci'})
    id = Column(Integer,primary_key=True,autoincrement=True)
    round_id = Column(Integer,ForeignKey('tournament_rounds.id',ondelete='CASCADE'),nullable=False,index=True)
    position = Column(Integer,nullable=False)


class TournamentSlot(Base):
    __tablename__ = 'tournament_slots'
    __table_args__ = (
        CheckConstraint('slot_number IN (1,2)',name='ck_slot_number'),
        CheckConstraint("(entry_id IS NOT NULL AND source_match_id IS NULL AND source_outcome IS NULL AND source_group_id IS NULL AND group_rank IS NULL) OR (entry_id IS NULL AND source_match_id IS NOT NULL AND source_outcome IS NOT NULL AND source_outcome IN ('winner','loser') AND source_group_id IS NULL AND group_rank IS NULL) OR (entry_id IS NULL AND source_match_id IS NULL AND source_outcome IS NULL AND source_group_id IS NOT NULL AND group_rank IS NOT NULL AND group_rank IN (1,2)) OR (entry_id IS NULL AND source_match_id IS NULL AND source_outcome IS NULL AND source_group_id IS NULL AND group_rank IS NULL)",name='ck_slot_source'),
        {'mysql_engine':'InnoDB','mysql_charset':'utf8mb4','mysql_collate':'utf8mb4_unicode_ci'},
    )
    match_id = Column(Integer,ForeignKey('tournament_matches.id',ondelete='CASCADE'),primary_key=True)
    slot_number = Column(Integer,primary_key=True)
    entry_id = Column(Integer,ForeignKey('tournament_entries.id',ondelete='RESTRICT'),nullable=True,index=True)
    source_match_id = Column(Integer,ForeignKey('tournament_matches.id',ondelete='RESTRICT'),nullable=True,index=True)
    source_outcome = Column(VARCHAR(6),nullable=True)
    source_group_id = Column(Integer,ForeignKey('tournament_stages.id',ondelete='RESTRICT'),nullable=True,index=True)
    group_rank = Column(Integer,nullable=True)


class MatchResult(Base):
    __tablename__ = 'match_results'
    __table_args__ = (
        CheckConstraint('home_score BETWEEN 0 AND 99 AND away_score BETWEEN 0 AND 99', name='ck_result_scores'),
        {'mysql_engine':'InnoDB','mysql_charset':'utf8mb4','mysql_collate':'utf8mb4_unicode_ci'},
    )
    match_id = Column(Integer, ForeignKey('tournament_matches.id',ondelete='CASCADE'), primary_key=True)
    home_score = Column(Integer,nullable=False)
    away_score = Column(Integer,nullable=False)
    winner_entry_id = Column(Integer,ForeignKey('tournament_entries.id',ondelete='RESTRICT'),nullable=True,index=True)
    recorded_at = Column(DateTime,nullable=False,server_default=func.current_timestamp())


class GroupDraw(Base):
    __tablename__ = 'group_draws'
    __table_args__ = (
        UniqueConstraint('stage_id','draw_order',name='uq_group_draw_order'),
        CheckConstraint('draw_order >= 1',name='ck_group_draw_order'),
        {'mysql_engine':'InnoDB','mysql_charset':'utf8mb4','mysql_collate':'utf8mb4_unicode_ci'},
    )
    stage_id = Column(Integer,ForeignKey('tournament_stages.id',ondelete='CASCADE'),primary_key=True)
    entry_id = Column(Integer,ForeignKey('tournament_entries.id',ondelete='CASCADE'),primary_key=True)
    draw_order = Column(Integer,nullable=False)


class TournamentPartner(Base):
    """Segundo miembro de una inscripción en pareja. El primero está en entries."""
    __tablename__ = 'tournament_partners'
    __table_args__ = {'mysql_engine':'InnoDB','mysql_charset':'utf8mb4','mysql_collate':'utf8mb4_unicode_ci'}
    entry_id = Column(Integer,ForeignKey('tournament_entries.id',ondelete='CASCADE'),primary_key=True)
    participant_id = Column(Integer,ForeignKey('participants.id',ondelete='RESTRICT'),nullable=False,index=True)
