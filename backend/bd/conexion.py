"""Conexión a MariaDB: lee .env y abre una sesión por petición."""
import os
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import URL, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
file_settings = dotenv_values(BACKEND_DIR / '.env')


def read_setting(name, default):
    # Las variables del sistema tienen prioridad sobre el archivo .env.
    value = os.environ.get(name)
    if value is None:
        value = file_settings.get(name, default)
    if value is None:
        return default
    return value


def get_database_url():
    return URL.create(
        'mysql+pymysql',
        host=read_setting('DB_HOST', '127.0.0.1'),
        port=int(read_setting('DB_PORT', '3306')),
        database=read_setting('DB_NAME', 'ballers'),
        username=read_setting('DB_USER', 'ballers'),
        password=read_setting('DB_PASSWORD', ''),
        query={'charset': 'utf8mb4'},
    )

class Base(DeclarativeBase):
    """Clase base de los modelos de la base de datos."""
    pass


engine = create_engine(
    get_database_url(),
    pool_pre_ping=True,
    connect_args={'connect_timeout': 8, 'init_command': "SET time_zone = '+00:00'"},
    hide_parameters=True,
)
SessionFactory = sessionmaker(engine, expire_on_commit=False)


def get_session():
    # El bloque with cierra la sesión al terminar la petición.
    with SessionFactory() as session:
        yield session
