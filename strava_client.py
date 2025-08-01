import os
import sqlite3
import re
from dotenv import load_dotenv
from stravalib import Client
from database import get_tokens, store_tokens, get_athlete_id_by_telegram_chat_id
from typing import Optional

load_dotenv()

client_id = os.getenv("STRAVA_CLIENT_ID")
client_secret = os.getenv("STRAVA_CLIENT_SECRET")
redirect_uri = os.getenv("STRAVA_REDIRECT_URI")


def init_strava_db():
    conn = sqlite3.connect('strava.db')
    c = conn.cursor()
    
    # Create the activities table (your existing code)
    c.execute('''
        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY,
            athlete_id INTEGER,
            name TEXT,
            type TEXT,
            start_date_local DATETIME,
            distance_meters REAL,
            distance_miles REAL,
            moving_time_seconds INTEGER,
            moving_time_minutes REAL,
            average_heartrate REAL,
            max_heartrate REAL
        )
    ''')
    
    # Create the marathon_plan table
    c.execute('''
        CREATE TABLE IF NOT EXISTS marathon_plan (
            athlete_id INTEGER,
            date TEXT,
            run_type TEXT,
            distance_miles REAL,
            PRIMARY KEY (athlete_id, date),
            FOREIGN KEY (athlete_id) REFERENCES tokens(athlete_id)
        )
    ''')

    # --- NEW: Create the two nutrition tables ---

    # Table 1: Meals and their macros
    c.execute('''
        CREATE TABLE IF NOT EXISTS meals (
            meal_id INTEGER PRIMARY KEY AUTOINCREMENT,
            meal_name TEXT NOT NULL,
            protein_grams REAL,
            carbs_grams REAL,
            fat_grams REAL,
            calories REAL
            athlete_id INTEGER,
            FOREIGN KEY (athlete_id) REFERENCES tokens(athlete_id)
        )
    ''')

    # Table 2: User's target macros
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_targets (
            athlete_id INTEGER PRIMARY KEY,
            target_protein_grams REAL,
            target_carbs_grams REAL,
            target_fat_grams REAL,
            target_calories REAL,
            FOREIGN KEY (athlete_id) REFERENCES tokens(athlete_id)
        )
    ''')
    # --- END NEW ---
    
    conn.commit()
    conn.close()

def meters_to_miles(meters: float) -> float:
    """
    Converts meters to miles.
    :param meters: Distance in meters.
    :return: Distance in miles.
    """
    return round(meters * 0.000621371,2)

def prettify_activity_type(type_str: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", " ", type_str)


def store_activities(athlete_id: int, activities: list):
    init_strava_db()  # Ensure table exists
    conn = sqlite3.connect('strava.db')
    c = conn.cursor()

    for activity in activities:
        raw_type = getattr(activity.type, "root", activity.type)
        readable_type = prettify_activity_type(str(raw_type))
        miles = meters_to_miles(activity.distance) if activity.distance else None
        minutes = round(activity.moving_time / 60,2) if activity.moving_time else None

        # Safely convert date
        try:
            start_date = activity.start_date_local.astimezone(None).replace(tzinfo=None).isoformat()
        except Exception:
            start_date = None

        c.execute('''
            INSERT OR REPLACE INTO activities (
                id, athlete_id, name, type, start_date_local, distance_meters,distance_miles, moving_time_seconds,moving_time_minutes, average_heartrate, max_heartrate
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            activity.id,
            athlete_id,
            activity.name,
            readable_type,
            start_date,
            activity.distance,
            miles,
            activity.moving_time,
            minutes,
            activity.average_heartrate,
            activity.max_heartrate
        ))

    conn.commit()
    conn.close()


def get_user_activities(athlete_id: int):
    """
    Fetches activities for a specific athlete from the database.
    :param athlete_id: ID of the athlete whose activities are to be fetched.
    :return: List of activities for the athlete.
    """
    conn = sqlite3.connect("strava.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM activities WHERE athlete_id = ?", (athlete_id,))
    results = cursor.fetchall()
    conn.close()
    return results


def get_activities(after: str='2025-01-01', limit: int = 50, strava_client=None):
    if strava_client is None:
        raise ValueError("Strava client is required.")
    return list(strava_client.get_activities(after=after, limit=limit))


def get_auth_url() -> str:
    client = Client()
    return client.authorization_url(
        client_id=client_id,
        redirect_uri=redirect_uri,
        scope=['read', 'activity:read_all'],
        approval_prompt='auto'
    )


def exchange_code_for_tokens(code: str, telegram_chat_id: Optional[int] = None): # NEW PARAMETER
    client = Client()
    token_response = client.exchange_code_for_token(
        client_id=client_id,
        client_secret=client_secret,
        code=code
    )

    client.access_token = token_response["access_token"]
    athlete = client.get_athlete()

    # Store tokens by athlete ID AND Telegram Chat ID
    store_tokens(
        athlete.id,
        token_response["access_token"],
        token_response["refresh_token"],
        token_response["expires_at"],
        telegram_chat_id # NEW: Pass the telegram_chat_id
    )

    # Load recent activities into the database
    activities = get_activities(after='2020-01-01', limit=100, strava_client=client)
    store_activities(athlete.id, activities)

    return athlete

def update_token(token_data, athlete_id):
    """
    Updates the token in the database after a successful refresh.
    This function is called by the stravalib.Client automatically.
    """
    access_token = token_data['access_token']
    refresh_token = token_data['refresh_token']
    expires_at = token_data['expires_at']

    # Your store_tokens function already handles updating the token
    # Note: store_tokens needs to handle the telegram_chat_id, which we don't have here.
    # We will need to get it from the database first.
    conn = sqlite3.connect("strava.db")
    row = conn.execute("SELECT telegram_chat_id FROM tokens WHERE athlete_id = ?", (athlete_id,)).fetchone()
    telegram_chat_id = row[0] if row else None
    conn.close()

    store_tokens(athlete_id, access_token, refresh_token, expires_at, telegram_chat_id)
    logging.info(f"Refreshed token for athlete_id: {athlete_id}. New token stored.")

def get_authenticated_client(athlete_id):
    conn = sqlite3.connect("strava.db")
    # Retrieve all four columns: access_token, refresh_token, expires_at, and telegram_chat_id
    row = conn.execute("SELECT access_token, refresh_token, expires_at FROM tokens WHERE athlete_id = ?", (athlete_id,)).fetchone()
    conn.close()

    if row:
        access_token, refresh_token, expires_at = row
        
        # --- THIS IS THE CORRECT INITIALIZATION ---
        # 1. Instantiate the client with NO token credentials as constructor arguments.
        client = Client()
        
        # 2. Assign all token credentials as attributes. This is the correct method.
        client.access_token = access_token
        client.refresh_token = refresh_token
        client.expires_at = expires_at
        
        # 3. Assign the client credentials to the client object
        client.client_id = client_id
        client.client_secret = client_secret
        
        # 4. Assign the token_updater function, which tells stravalib how to save new tokens
        client.token_updater = lambda token_data: update_token(token_data, athlete_id)
        # --- END OF CORRECT INITIALIZATION ---

        return client
    else:
        raise ValueError(f"No token found for athlete_id {athlete_id}")


def get_activity(activity_id: int, strava_client=None):
    """
    Fetches a single activity by its ID from the Strava API.
    :param activity_id: The ID of the activity to fetch.
    :param strava_client: An authenticated Strava client.
    :return: The activity object.
    """
    if strava_client is None:
        raise ValueError("Strava client is required.")
    return strava_client.get_activity(activity_id)


def delete_activity_from_db(activity_id: int):
    """
    Deletes an activity from the local database.
    :param activity_id: The ID of the activity to delete.
    """
    conn = sqlite3.connect('strava.db')
    c = conn.cursor()
    c.execute("DELETE FROM activities WHERE id = ?", (activity_id,))
    conn.commit()
    conn.close()

# For 'update' events, a simple strategy is to re-fetch and re-store the activity.
# This ensures all fields are up-to-date in your database.
def update_activity_in_db(athlete_id: int, activity_id: int, strava_client=None):
    """
    Fetches the latest data for an activity and updates it in the database.
    """
    if strava_client is None:
        raise ValueError("Strava client is required.")
    
    # Use your existing functions to get the activity and store it (INSERT OR REPLACE)
    updated_activity = get_activity(activity_id, strava_client)
    store_activities(athlete_id, [updated_activity])