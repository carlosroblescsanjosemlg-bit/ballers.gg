"""Comprueba la conexión y las tablas de Ballers.gg sin modificar datos."""
from sqlalchemy import DateTime, Integer, String, inspect
from sqlalchemy.dialects.mysql import MEDIUMBLOB

from .conexion import engine


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def verify_schema(connection):
    inspector = inspect(connection)
    tables = inspector.get_table_names()
    require('participants' in tables and 'participant_logos' in tables and 'users' in tables and 'user_sessions' in tables,
            'Faltan tablas. Ejecuta: python -m bd.preparar')

    participants = {column['name']: column for column in inspector.get_columns('participants')}
    logos = {column['name']: column for column in inspector.get_columns('participant_logos')}
    require(set(participants) == {'id', 'nick', 'is_active', 'created_at', 'updated_at', 'version', 'owner_id'},
            'Las columnas de participants no coinciden con la Fase 1.')
    require(set(logos) == {'participant_id', 'content'}, 'Las columnas de participant_logos no coinciden.')
    for column in list(participants.values()) + list(logos.values()):
        require(not column['nullable'], 'Una columna obligatoria admite valores nulos: ' + column['name'])

    for name in ('id', 'is_active', 'version'):
        require(isinstance(participants[name]['type'], Integer), 'Tipo incorrecto en participants.' + name)
    require(isinstance(logos['participant_id']['type'], Integer), 'El identificador del logo debe ser entero.')
    require(isinstance(participants['nick']['type'], String) and participants['nick']['type'].length == 24,
            'El nick debe ser VARCHAR(24).')
    require(isinstance(logos['content']['type'], MEDIUMBLOB), 'El logo debe ser binario.')
    for name in ('created_at', 'updated_at'):
        require(isinstance(participants[name]['type'], DateTime), 'Fecha incorrecta: ' + name)
    require(inspector.get_pk_constraint('participants')['constrained_columns'] == ['id'], 'Clave primaria incorrecta en participants.')
    require(inspector.get_pk_constraint('participant_logos')['constrained_columns'] == ['participant_id'], 'Clave primaria incorrecta en logos.')

    unique_keys = inspector.get_unique_constraints('participants')
    require(any(key['column_names'] == ['owner_id', 'nick'] for key in unique_keys), 'Falta la unicidad del nick.')
    owner_keys = inspector.get_foreign_keys('participants')
    require(any(key['constrained_columns'] == ['owner_id'] and key['referred_table'] == 'users' for key in owner_keys), 'Falta la cuenta propietaria de los jugadores.')
    foreign_keys = inspector.get_foreign_keys('participant_logos')
    require(any(key['constrained_columns'] == ['participant_id'] and key['referred_table'] == 'participants'
                and key['referred_columns'] == ['id'] and key['options'].get('ondelete') == 'CASCADE'
                for key in foreign_keys), 'Falta la relación entre participante y logo.')
    indexes = inspector.get_indexes('participants')
    require(any(index['column_names'] == ['is_active'] for index in indexes), 'Falta el índice de estado.')
    checks = inspector.get_check_constraints('participants')
    require({'ck_participants_nick_length', 'ck_participants_is_active', 'ck_participants_version'}
            <= {check['name'] for check in checks}, 'Faltan restricciones de validación.')
    collations = connection.exec_driver_sql('SHOW FULL COLUMNS FROM participants').mappings().all()
    nick_column = next(column for column in collations if column['Field'] == 'nick')
    require(nick_column['Collation'] == 'utf8mb4_unicode_ci', 'La intercalación del nick no es la esperada.')
    users = {column['name']: column for column in inspector.get_columns('users')}
    sessions = {column['name']: column for column in inspector.get_columns('user_sessions')}
    require(set(users) == {'id','username','password_hash','created_at'}, 'Columnas de cuentas incorrectas.')
    require(set(sessions) == {'token_hash','user_id','expires_at'}, 'Columnas de sesiones incorrectas.')
    for column in list(users.values()) + list(sessions.values()):
        require(not column['nullable'], 'Cuenta o sesión con columna obligatoria nula.')
    require(inspector.get_pk_constraint('users')['constrained_columns'] == ['id'], 'Clave de cuentas incorrecta.')
    require(inspector.get_pk_constraint('user_sessions')['constrained_columns'] == ['token_hash'], 'Clave de sesiones incorrecta.')
    require(any(key['column_names'] == ['username'] for key in inspector.get_unique_constraints('users')), 'Falta usuario único.')
    require(any(key['constrained_columns'] == ['user_id'] and key['referred_table'] == 'users'
                and key['options'].get('ondelete') == 'CASCADE' for key in inspector.get_foreign_keys('user_sessions')), 'Falta relación de sesión con cuenta.')
    require(isinstance(users['username']['type'],String) and users['username']['type'].length == 24, 'Tipo de usuario incorrecto.')
    require(isinstance(users['password_hash']['type'],String) and users['password_hash']['type'].length == 255, 'Tipo de contraseña incorrecto.')
    require(isinstance(sessions['token_hash']['type'],String) and sessions['token_hash']['type'].length == 64, 'Tipo de sesión incorrecto.')
    require(isinstance(sessions['expires_at']['type'],DateTime), 'Caducidad de sesión incorrecta.')
    require(isinstance(participants['owner_id']['type'],Integer), 'Tipo de propietario incorrecto.')
    for table in ('participants', 'participant_logos', 'users', 'user_sessions'):
        options = inspector.get_table_options(table)
        require(options.get('mysql_engine', '').lower() == 'innodb', 'El motor de ' + table + ' debe ser InnoDB.')

    verify_tournament_schema(connection)

def verify_tournament_schema(connection):
    from .conexion import Base
    from . import modelos
    inspector = inspect(connection)
    for name in ('tournaments','tournament_entries','tournament_stages','tournament_group_members',
                 'tournament_rounds','tournament_matches','tournament_slots','match_results','group_draws','tournament_partners'):
        require(inspector.has_table(name), 'Falta '+name+'. Ejecuta python -m bd.preparar')
        model = Base.metadata.tables[name]
        columns = {column['name']:column for column in inspector.get_columns(name)}
        require(set(columns) == set(model.columns.keys()), 'Columnas incorrectas en '+name)
        for column in model.columns:
            actual = columns[column.name]
            require(actual['nullable'] == column.nullable, 'Nulabilidad incorrecta en '+name+'.'+column.name)
            if isinstance(column.type,Integer):
                require(isinstance(actual['type'],Integer), 'Se esperaba entero en '+name+'.'+column.name)
            elif isinstance(column.type,DateTime):
                require(isinstance(actual['type'],DateTime), 'Se esperaba fecha en '+name+'.'+column.name)
            elif isinstance(column.type,String):
                require(isinstance(actual['type'],String) and actual['type'].length == column.type.length,
                        'Longitud incorrecta en '+name+'.'+column.name)
        require(inspector.get_pk_constraint(name)['constrained_columns'] == [c.name for c in model.primary_key], 'Clave primaria incorrecta en '+name)
        from sqlalchemy import UniqueConstraint, CheckConstraint
        actual_unique = [tuple(key['column_names']) for key in inspector.get_unique_constraints(name)]
        for constraint in model.constraints:
            if isinstance(constraint,UniqueConstraint):
                require(tuple(c.name for c in constraint.columns) in actual_unique, 'Falta unicidad en '+name)
            if isinstance(constraint,CheckConstraint):
                require(constraint.name in {c['name'] for c in inspector.get_check_constraints(name)}, 'Falta validación en '+name)
        actual_fk = inspector.get_foreign_keys(name)
        for key in model.foreign_keys:
            require(any(item['constrained_columns'] == [key.parent.name] and item['referred_table'] == key.column.table.name
                        and item['referred_columns'] == [key.column.name] and item['options'].get('ondelete', 'RESTRICT') == key.ondelete for item in actual_fk),
                    'Falta relación en '+name+'.'+key.parent.name)


def main():
    with engine.connect() as connection:
        version = connection.exec_driver_sql('SELECT VERSION()').scalar_one()
        require('MariaDB' in version, 'El servidor no se identifica como MariaDB.')
        verify_schema(connection)
    print('Tablas, columnas, claves y restricciones: OK.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # No imprimir mensajes del driver que puedan incluir datos de conexión.
        if isinstance(error, RuntimeError):
            print(str(error))
        else:
            print('No se pudo comprobar MariaDB. Revisa la conexión de backend/.env.')
        raise SystemExit(1)
