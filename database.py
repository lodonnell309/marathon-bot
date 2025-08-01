import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = "strava.db"

def init_db():
    Path(DB_PATH).touch(exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS tokens (
            athlete_id INTEGER PRIMARY KEY,
            access_token TEXT,
            refresh_token TEXT,
            expires_at INTEGER,
            telegram_chat_id INTEGER UNIQUE -- NEW COLUMN: Link to Telegram chat
        )
        """)

        ##

def store_tokens(athlete_id, access_token, refresh_token, expires_at, telegram_chat_id: int): # NEW PARAMETER
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
        INSERT OR REPLACE INTO tokens (athlete_id, access_token, refresh_token, expires_at, telegram_chat_id)
        VALUES (?, ?, ?, ?, ?)
        """, (athlete_id, access_token, refresh_token, expires_at, telegram_chat_id))

def get_tokens(athlete_id):
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("""
        SELECT access_token, refresh_token, expires_at FROM tokens WHERE athlete_id = ?
        """, (athlete_id,)).fetchone()
        return dict(zip(["access_token", "refresh_token", "expires_at"], row)) if row else None

def get_athlete_id_by_telegram_chat_id(telegram_chat_id: int) -> Optional[int]:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("""
        SELECT athlete_id FROM tokens WHERE telegram_chat_id = ?
        """, (telegram_chat_id,)).fetchone()
        return row[0] if row else None


def get_telegram_chat_id_by_athlete_id(athlete_id: int) -> Optional[int]:
    """
    Looks up the Telegram chat ID for a given Strava athlete ID.
    """
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("""
        SELECT telegram_chat_id FROM tokens WHERE athlete_id = ?
        """, (athlete_id,)).fetchone()
        return row[0] if row else None