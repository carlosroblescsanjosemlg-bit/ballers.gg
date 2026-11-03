"""Crea o actualiza las tablas: desde backend, python -m bd.preparar."""
from sqlalchemy import inspect, text

from .conexion import engine
from .comprobar import verify_schema

SQL = [
    """
    CREATE TABLE IF NOT EXISTS participants (
        id INTEGER NOT NULL AUTO_INCREMENT,
        nick VARCHAR(24) COLLATE utf8mb4_unicode_ci NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT 1,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        version INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY (id),
        CONSTRAINT uq_participants_nick UNIQUE (nick),
        CONSTRAINT ck_participants_nick_length CHECK (CHAR_LENGTH(nick) BETWEEN 2 AND 24),
        CONSTRAINT ck_participants_is_active CHECK (is_active IN (0, 1)),
        CONSTRAINT ck_participants_version CHECK (version >= 1),
        INDEX ix_participants_is_active (is_active)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS participant_logos (
        participant_id INTEGER NOT NULL,
        content MEDIUMBLOB NOT NULL,
        PRIMARY KEY (participant_id),
        CONSTRAINT fk_logos_participant FOREIGN KEY (participant_id)
            REFERENCES participants (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]



SQL_ACCESS = [
    """CREATE TABLE IF NOT EXISTS users (
        id INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(24) COLLATE utf8mb4_unicode_ci NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_users_username UNIQUE (username)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS user_sessions (
        token_hash VARCHAR(64) NOT NULL PRIMARY KEY,
        user_id INTEGER NOT NULL,
        expires_at DATETIME NOT NULL,
        CONSTRAINT fk_sessions_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        INDEX ix_user_sessions_user_id (user_id),
        INDEX ix_user_sessions_expires_at (expires_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    'ALTER TABLE participants ADD COLUMN IF NOT EXISTS owner_id INTEGER NULL',
    'ALTER TABLE participants ADD INDEX IF NOT EXISTS ix_participants_owner_id (owner_id)',
    'ALTER TABLE participants ADD UNIQUE INDEX IF NOT EXISTS uq_participants_owner_nick (owner_id, nick)',
    'ALTER TABLE participants DROP INDEX IF EXISTS uq_participants_nick',
]

SQL_TOURNAMENTS = [
    """CREATE TABLE IF NOT EXISTS tournaments (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	owner_id INTEGER NOT NULL, 
	name VARCHAR(80) NOT NULL, 
	format VARCHAR(24) NOT NULL, 
	min_participants INTEGER NOT NULL, 
	max_participants INTEGER NOT NULL, 
	request_key VARCHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_tournament_limits CHECK (min_participants >= 2 AND max_participants >= min_participants AND max_participants <= 128), 
	CONSTRAINT ck_tournament_format CHECK (format IN ('single_elimination','double_elimination','groups_knockout')), 
	CONSTRAINT uq_tournament_request UNIQUE (owner_id, request_key), 
	FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE RESTRICT
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci""",
    """CREATE INDEX IF NOT EXISTS ix_tournaments_owner_id ON tournaments (owner_id)""",
    """CREATE TABLE IF NOT EXISTS tournament_entries (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tournament_id INTEGER NOT NULL, 
	participant_id INTEGER NOT NULL, 
	draw_position INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_tournament_participant UNIQUE (tournament_id, participant_id), 
	CONSTRAINT uq_tournament_seed UNIQUE (tournament_id, draw_position), 
	CONSTRAINT ck_entry_position CHECK (draw_position >= 1), 
	FOREIGN KEY(tournament_id) REFERENCES tournaments (id) ON DELETE CASCADE, 
	FOREIGN KEY(participant_id) REFERENCES participants (id) ON DELETE RESTRICT
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci""",
    """CREATE INDEX IF NOT EXISTS ix_tournament_entries_participant_id ON tournament_entries (participant_id)""",
    """CREATE INDEX IF NOT EXISTS ix_tournament_entries_tournament_id ON tournament_entries (tournament_id)""",
    """CREATE TABLE IF NOT EXISTS tournament_stages (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tournament_id INTEGER NOT NULL, 
	kind VARCHAR(16) NOT NULL, 
	name VARCHAR(60) NOT NULL, 
	position INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_tournament_stage_position UNIQUE (tournament_id, position), 
	CONSTRAINT ck_stage_kind CHECK (kind IN ('knockout','upper','lower','final','group')), 
	FOREIGN KEY(tournament_id) REFERENCES tournaments (id) ON DELETE CASCADE
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci""",
    """CREATE INDEX IF NOT EXISTS ix_tournament_stages_tournament_id ON tournament_stages (tournament_id)""",
    """CREATE TABLE IF NOT EXISTS tournament_group_members (
	stage_id INTEGER NOT NULL, 
	entry_id INTEGER NOT NULL, 
	PRIMARY KEY (stage_id, entry_id), 
	CONSTRAINT uq_group_member_entry UNIQUE (entry_id), 
	FOREIGN KEY(stage_id) REFERENCES tournament_stages (id) ON DELETE CASCADE, 
	FOREIGN KEY(entry_id) REFERENCES tournament_entries (id) ON DELETE CASCADE
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS tournament_rounds (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	stage_id INTEGER NOT NULL, 
	number INTEGER NOT NULL, 
	name VARCHAR(60) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_stage_round UNIQUE (stage_id, number), 
	CONSTRAINT ck_round_number CHECK (number >= 1), 
	FOREIGN KEY(stage_id) REFERENCES tournament_stages (id) ON DELETE CASCADE
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci""",
    """CREATE INDEX IF NOT EXISTS ix_tournament_rounds_stage_id ON tournament_rounds (stage_id)""",
    """CREATE TABLE IF NOT EXISTS tournament_matches (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	round_id INTEGER NOT NULL, 
	position INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_round_match UNIQUE (round_id, position), 
	CONSTRAINT ck_match_position CHECK (position >= 1), 
	FOREIGN KEY(round_id) REFERENCES tournament_rounds (id) ON DELETE CASCADE
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci""",
    """CREATE INDEX IF NOT EXISTS ix_tournament_matches_round_id ON tournament_matches (round_id)""",
    """CREATE TABLE IF NOT EXISTS tournament_slots (
	match_id INTEGER NOT NULL, 
	slot_number INTEGER NOT NULL, 
	entry_id INTEGER, 
	source_match_id INTEGER, 
	source_outcome VARCHAR(6), 
	source_group_id INTEGER, 
	group_rank INTEGER, 
	PRIMARY KEY (match_id, slot_number), 
	CONSTRAINT ck_slot_number CHECK (slot_number IN (1,2)), 
	CONSTRAINT ck_slot_source CHECK ((entry_id IS NOT NULL AND source_match_id IS NULL AND source_outcome IS NULL AND source_group_id IS NULL AND group_rank IS NULL) OR (entry_id IS NULL AND source_match_id IS NOT NULL AND source_outcome IS NOT NULL AND source_outcome IN ('winner','loser') AND source_group_id IS NULL AND group_rank IS NULL) OR (entry_id IS NULL AND source_match_id IS NULL AND source_outcome IS NULL AND source_group_id IS NOT NULL AND group_rank IS NOT NULL AND group_rank IN (1,2)) OR (entry_id IS NULL AND source_match_id IS NULL AND source_outcome IS NULL AND source_group_id IS NULL AND group_rank IS NULL)), 
	FOREIGN KEY(match_id) REFERENCES tournament_matches (id) ON DELETE CASCADE, 
	FOREIGN KEY(entry_id) REFERENCES tournament_entries (id) ON DELETE RESTRICT, 
	FOREIGN KEY(source_match_id) REFERENCES tournament_matches (id) ON DELETE RESTRICT, 
	FOREIGN KEY(source_group_id) REFERENCES tournament_stages (id) ON DELETE RESTRICT
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci""",
    """CREATE INDEX IF NOT EXISTS ix_tournament_slots_entry_id ON tournament_slots (entry_id)""",
    """CREATE INDEX IF NOT EXISTS ix_tournament_slots_source_group_id ON tournament_slots (source_group_id)""",
    """CREATE INDEX IF NOT EXISTS ix_tournament_slots_source_match_id ON tournament_slots (source_match_id)""",
]

SQL_RESULTS = [
    """ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1""",
    """ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS finished_at DATETIME NULL""",
    """CREATE TABLE IF NOT EXISTS match_results (
	match_id INTEGER NOT NULL, 
	home_score INTEGER NOT NULL, 
	away_score INTEGER NOT NULL, 
	winner_entry_id INTEGER, 
	recorded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (match_id), 
	CONSTRAINT ck_result_scores CHECK (home_score BETWEEN 0 AND 99 AND away_score BETWEEN 0 AND 99), 
	FOREIGN KEY(match_id) REFERENCES tournament_matches (id) ON DELETE CASCADE, 
	FOREIGN KEY(winner_entry_id) REFERENCES tournament_entries (id) ON DELETE RESTRICT
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci""",
    """CREATE INDEX IF NOT EXISTS ix_match_results_winner_entry_id ON match_results (winner_entry_id)""",
    """CREATE TABLE IF NOT EXISTS group_draws (
	stage_id INTEGER NOT NULL, 
	entry_id INTEGER NOT NULL, 
	draw_order INTEGER NOT NULL, 
	PRIMARY KEY (stage_id, entry_id), 
	CONSTRAINT uq_group_draw_order UNIQUE (stage_id, draw_order), 
	CONSTRAINT ck_group_draw_order CHECK (draw_order >= 1), 
	FOREIGN KEY(stage_id) REFERENCES tournament_stages (id) ON DELETE CASCADE, 
	FOREIGN KEY(entry_id) REFERENCES tournament_entries (id) ON DELETE CASCADE
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci""",
]

SQL_LEAGUES = [
    """ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS pair_mode VARCHAR(12) NOT NULL DEFAULT 'individual'""",
    """ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS league_rounds INTEGER NOT NULL DEFAULT 1""",
    """ALTER TABLE tournaments DROP CONSTRAINT IF EXISTS ck_tournament_format""",
    """ALTER TABLE tournaments ADD CONSTRAINT ck_tournament_format CHECK (format IN ('single_elimination','double_elimination','groups_knockout','league'))""",
    """ALTER TABLE tournament_stages DROP CONSTRAINT IF EXISTS ck_stage_kind""",
    """ALTER TABLE tournament_stages ADD CONSTRAINT ck_stage_kind CHECK (kind IN ('knockout','upper','lower','final','group','league'))""",
    """CREATE TABLE IF NOT EXISTS tournament_partners (
	entry_id INTEGER NOT NULL, 
	participant_id INTEGER NOT NULL, 
	PRIMARY KEY (entry_id), 
	FOREIGN KEY(entry_id) REFERENCES tournament_entries (id) ON DELETE CASCADE, 
	FOREIGN KEY(participant_id) REFERENCES participants (id) ON DELETE RESTRICT
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci""",
    """CREATE INDEX IF NOT EXISTS ix_tournament_partners_participant_id ON tournament_partners (participant_id)""",
]

# Añadir las nuevas versiones SQL aquí cuando se amplíe el programa.
UPDATES = [(1, 'Participantes y logos', SQL), (2, 'Cuentas y jugadores privados', SQL_ACCESS),
           (3, 'Propietario obligatorio', ['ALTER TABLE participants MODIFY COLUMN owner_id INTEGER NOT NULL']),
           (4, 'Torneos, grupos y cuadros', SQL_TOURNAMENTS),
           (5, 'Marcadores y desempates de grupos', SQL_RESULTS),
           (6, 'Ligas y parejas de torneo', SQL_LEAGUES)]


def prepare_database():
    with engine.begin() as connection:
        connection.exec_driver_sql('''
            CREATE TABLE IF NOT EXISTS schema_updates (
                version INTEGER NOT NULL PRIMARY KEY,
                description VARCHAR(100) NOT NULL,
                applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        ''')
        applied = connection.execute(text('SELECT version FROM schema_updates')).scalars().all()
        if any(version > UPDATES[-1][0] for version in applied):
            raise RuntimeError('La base de datos pertenece a una versión posterior del programa.')
        for version, description, statements in UPDATES:
            if version in applied:
                continue
            if version == 3:
                unowned = connection.execute(text('SELECT COUNT(*) FROM participants WHERE owner_id IS NULL')).scalar_one()
                if unowned:
                    raise RuntimeError('Hay jugadores antiguos sin propietario. Asignarlos a una cuenta o retirarlos con autorización antes de continuar.')
            for statement in statements:
                connection.exec_driver_sql(statement)
            if version == 2:
                keys = inspect(connection).get_foreign_keys('participants')
                if not any(key['constrained_columns'] == ['owner_id'] for key in keys):
                    connection.exec_driver_sql('ALTER TABLE participants ADD CONSTRAINT fk_participants_owner FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE RESTRICT')
            connection.execute(
                text('INSERT INTO schema_updates (version, description) VALUES (:version, :description)'),
                {'version': version, 'description': description},
            )
            print('Cambio aplicado:', version, description)
        verify_schema(connection)
        print('Base de datos preparada. Los participantes y sus logos se conservan.')


if __name__ == '__main__':
    try:
        prepare_database()
    except Exception as error:
        if isinstance(error, RuntimeError):
            print(str(error))
        else:
            print('No se pudo preparar MariaDB. Revisa la conexión y los permisos de backend/.env.')
        raise SystemExit(1)
