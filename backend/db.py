"""
Gestion des connexions PostgreSQL via un pool SQLAlchemy.
get_conn() reste utilisable exactement comme avant (conn.cursor(), etc.),
mais est maintenant un context manager : la connexion est automatiquement
rendue au pool (et jamais fuitée) même en cas d'exception.
"""
import os
from contextlib import contextmanager

from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", 5432)
DB_NAME = os.getenv("DB_NAME")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


engine = create_engine(
    DATABASE_URL,
    pool_size=5,        # connexions maintenues ouvertes en permanence
    max_overflow=10,     # connexions supplémentaires autorisées en pic de charge
    pool_timeout=30,     # attente max pour obtenir une connexion du pool
    pool_pre_ping=True,  # vérifie que la connexion est toujours valide avant usage
)


@contextmanager
def get_conn():
    """Fournit une connexion psycopg2 issue du pool SQLAlchemy.
    Usage : with get_conn() as conn: ...
    La connexion est toujours rendue au pool à la sortie du bloc `with`,
    même en cas d'exception."""
    conn = engine.raw_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()  