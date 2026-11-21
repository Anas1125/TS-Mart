from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

class Config(BaseSettings):
    database_url: str = 'sqlite:///./tsmart.db'
    allowed_origins: list[str] = ['http://127.0.0.1:5173', 'http://localhost:5173']
    cookie_secure: bool = False
    admin_email: str = ''
    admin_password: str = ''
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

config = Config()
# Neon/Vercel provides postgresql:// URLs. Explicitly use psycopg v3,
# which is the installed PostgreSQL driver (not psycopg2).
if config.database_url.startswith('postgresql://'):
    config.database_url = 'postgresql+psycopg://' + config.database_url[len('postgresql://'):]
elif config.database_url.startswith('postgres://'):
    config.database_url = 'postgresql+psycopg://' + config.database_url[len('postgres://'):]
engine = create_engine(config.database_url, connect_args={'check_same_thread': False, 'timeout': 30} if config.database_url.startswith('sqlite') else {}, pool_pre_ping=True)
if config.database_url.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def sqlite_config(connection, record):
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA journal_mode=WAL')
SessionLocal = sessionmaker(engine, expire_on_commit=False)
class Base(DeclarativeBase):
    pass

def get_db():
    with SessionLocal() as db:
        yield db
