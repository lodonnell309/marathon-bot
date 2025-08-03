import os
from contextlib import contextmanager
from typing import Optional, Generator
import logging
import urllib.parse

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, Session

# Import the models defined in models.py
from models import Base, Token, Activity, MarathonPlan, Meal, UserTarget

# The database connection string is now loaded from an environment variable.
# For Supabase PostgreSQL, this URL will look something like:
# "postgresql://[user]:[password]@[host]:[port]/[database_name]"
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    logging.warning("DATABASE_URL not set, falling back to local SQLite for development.")
    DATABASE_URL = "sqlite:///./strava.db"
else:
    logging.info(f"DATABASE_URL successfully loaded.")


# --- Debugging function to print parsed URL components ---
def log_parsed_db_url(url: str):
    """Parses a database URL and logs its components for debugging."""
    try:
        parsed = urllib.parse.urlparse(url)
        logging.info("--- Parsing DATABASE_URL ---")
        logging.info(f"Scheme: {parsed.scheme}")
        logging.info(f"Username: {parsed.username}")
        logging.info(f"Password: {'*' * len(parsed.password) if parsed.password else 'N/A'}")
        logging.info(f"Host: {parsed.hostname}")
        logging.info(f"Port: {parsed.port}")
        logging.info(f"Database: {parsed.path.lstrip('/')}")
        logging.info("--- End of Parsing ---")
    except Exception as e:
        logging.error(f"Failed to parse DATABASE_URL: {e}")


# The engine is the source of database connectivity.
try:
    # Sanitize the DATABASE_URL to remove any potential malformed parts
    parsed_url = urllib.parse.urlparse(DATABASE_URL)
    if "@" in parsed_url.hostname:
        logging.error("Invalid hostname detected in DATABASE_URL. It should not contain a '@' symbol in the host part.")
        # Fallback to a safe URL to prevent a crash
        safe_url = "sqlite:///./strava.db"
        engine = create_engine(safe_url, pool_pre_ping=True)
    else:
        engine = create_engine(DATABASE_URL, pool_pre_ping=True)
except Exception as e:
    logging.error(f"An unexpected error occurred when creating the database engine: {e}. Falling back to SQLite.")
    safe_url = "sqlite:///./strava.db"
    engine = create_engine(safe_url, pool_pre_ping=True)

# Call the debug function to see what the engine is receiving
log_parsed_db_url(DATABASE_URL)


# The Session object is the entry point for all database operations.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """
    Creates all database tables defined in models.py.
    This should be called once during application startup.
    """
    logging.info("Initializing database and creating tables if they don't exist...")
    # This command reads the Base metadata and creates all tables defined in models.py
    Base.metadata.create_all(bind=engine)
    logging.info("Database initialization complete.")

@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Provides a transactional scope around a series of operations."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Refactored Database Functions using SQLAlchemy ORM ---

def store_tokens(athlete_id: int, access_token: str, refresh_token: str, expires_at: int, telegram_chat_id: int):
    """Stores or updates an athlete's Strava tokens and their associated Telegram chat ID."""
    with get_db_session() as session:
        # Use session.get to fetch by primary key, which is faster.
        token = session.get(Token, athlete_id)
        if not token:
            token = Token(athlete_id=athlete_id, telegram_chat_id=telegram_chat_id)
            session.add(token)
        token.access_token = access_token
        token.refresh_token = refresh_token
        token.expires_at = expires_at
        token.telegram_chat_id = telegram_chat_id
        session.commit()

def get_tokens(athlete_id: int) -> Optional[dict]:
    """Retrieves an athlete's tokens from the database."""
    with get_db_session() as session:
        token = session.get(Token, athlete_id)
        return {
            "access_token": token.access_token,
            "refresh_token": token.refresh_token,
            "expires_at": token.expires_at
        } if token else None

def get_athlete_id_by_telegram_chat_id(telegram_chat_id: int) -> Optional[int]:
    """Looks up the Strava athlete ID for a given Telegram chat ID."""
    with get_db_session() as session:
        # Use a SQLAlchemy select statement to query the Token table
        stmt = select(Token).where(Token.telegram_chat_id == telegram_chat_id)
        token = session.execute(stmt).scalar_one_or_none()
        return token.athlete_id if token else None

def get_telegram_chat_id_by_athlete_id(athlete_id: int) -> Optional[int]:
    """Looks up the Telegram chat ID for a given Strava athlete ID."""
    with get_db_session() as session:
        # Use session.get to fetch by primary key (athlete_id)
        token = session.get(Token, athlete_id)
        return token.telegram_chat_id if token else None
