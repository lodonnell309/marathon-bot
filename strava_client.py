import os
import logging
import re
from dotenv import load_dotenv
from stravalib import Client
from typing import Optional

# --- Local Imports ---
# Now using the refactored database functions and models
from database import get_db_session, get_tokens, store_tokens, get_telegram_chat_id_by_athlete_id, get_athlete_id_by_telegram_chat_id
from models import Activity

# --- Load Environment Variables ---
load_dotenv()
client_id = os.getenv("STRAVA_CLIENT_ID")
client_secret = os.getenv("STRAVA_CLIENT_SECRET")
redirect_uri = os.getenv("STRAVA_REDIRECT_URI")

# --- Helper Functions ---

def meters_to_miles(meters: float) -> float:
    """Converts meters to miles."""
    return round(meters * 0.000621371, 2)

def prettify_activity_type(type_str: str) -> str:
    """Converts 'CamelCase' to 'Camel Case'."""
    return re.sub(r"(?<!^)(?=[A-Z])", " ", type_str)

# --- Core Authentication and Token Management ---

def get_auth_url():
    """Generates the Strava authorization URL."""
    client = Client()
    return client.authorization_url(
        client_id=client_id,
        redirect_uri=redirect_uri,
        scope=["read_all", "activity:read_all", "activity:write"],
    )

def exchange_code_for_tokens(code: str, telegram_chat_id: int):
    """
    Exchanges an authorization code for tokens and stores them.
    This is the final step of the OAuth flow.
    """
    client = Client()
    token_response = client.exchange_code_for_token(
        client_id=client_id,
        client_secret=client_secret,
        code=code
    )
    
    # Use the client to get the athlete's ID
    client.access_token = token_response['access_token']
    athlete = client.get_athlete()
    athlete_id = athlete.id
    
    # Store the new tokens in the database using the refactored function
    store_tokens(
        athlete_id=athlete_id,
        access_token=token_response['access_token'],
        refresh_token=token_response['refresh_token'],
        expires_at=token_response['expires_at'],
        telegram_chat_id=telegram_chat_id
    )
    logging.info(f"Successfully stored tokens for athlete {athlete_id}.")

    # Load recent activities into the database
    activities = get_activities(limit=100, strava_client=client)
    store_activities(athlete_id, activities)
    
    return athlete

def update_token(token_data: dict, athlete_id: int):
    """
    Callback function used by stravalib to store a refreshed token.
    """
    logging.info(f"Token has been refreshed for athlete {athlete_id}. Updating database.")
    # Corrected the function call here. Previously it was get_telegram_chat_id_by_telegram_chat_id
    telegram_chat_id = get_telegram_chat_id_by_athlete_id(athlete_id)
    if telegram_chat_id:
        store_tokens(
            athlete_id=athlete_id,
            access_token=token_data['access_token'],
            refresh_token=token_data['refresh_token'],
            expires_at=token_data['expires_at'],
            telegram_chat_id=telegram_chat_id
        )
        logging.info(f"Refreshed and stored token for athlete_id: {athlete_id}.")
    else:
        logging.error(f"Could not refresh token for athlete {athlete_id} because telegram_chat_id was not found.")

def get_authenticated_client(athlete_id: int) -> Optional[Client]:
    """
    Retrieves tokens from the database and returns an authenticated stravalib client.
    """
    # Use the refactored database function to get token info
    token_info = get_tokens(athlete_id)
    if not token_info:
        logging.error(f"No token found for athlete_id {athlete_id}")
        return None

    client = Client()
    client.access_token = token_info['access_token']
    client.refresh_token = token_info['refresh_token']
    client.expires_at = token_info['expires_at']
    client.client_id = client_id
    client.client_secret = client_secret
    client.token_updater = lambda token_data: update_token(token_data, athlete_id)
    
    return client

# --- Activity Management ---

def get_activities(after: str='2020-01-01', limit: int = 50, strava_client: Optional[Client] = None):
    """Fetches activities from the Strava API."""
    if strava_client is None:
        raise ValueError("Strava client is required.")
    return list(strava_client.get_activities(after=after, limit=limit))

def store_activities(athlete_id: int, activities: list):
    """
    Stores or updates a list of activities in the database using SQLAlchemy.
    """
    with get_db_session() as session:
        for activity_data in activities:
            raw_type = getattr(activity_data.type, "root", activity_data.type)
            readable_type = prettify_activity_type(str(raw_type))
            miles = meters_to_miles(float(activity_data.distance)) if activity_data.distance else None
            
            # The stravalib moving_time is a Duration object. Cast it to an integer
            # to get the total number of seconds.
            moving_time_seconds = int(activity_data.moving_time) if activity_data.moving_time else None
            minutes = round(moving_time_seconds / 60, 2) if moving_time_seconds is not None else None

            # Safely convert date, stravalib returns a datetime object
            start_date = None
            if activity_data.start_date_local:
                try:
                    start_date = activity_data.start_date_local.astimezone(None).replace(tzinfo=None)
                except Exception:
                    start_date = None

            activity_obj = Activity(
                id=activity_data.id,
                athlete_id=athlete_id,
                name=activity_data.name,
                type=readable_type,
                start_date_local=start_date,
                distance_meters=float(activity_data.distance) if activity_data.distance else None,
                distance_miles=miles,
                moving_time_seconds=moving_time_seconds,
                moving_time_minutes=minutes,
                average_heartrate=activity_data.average_heartrate,
                max_heartrate=activity_data.max_heartrate
            )
            # session.merge() will INSERT a new record or UPDATE an existing one based on the primary key.
            session.merge(activity_obj)
        session.commit()

def get_activity(activity_id: int, strava_client: Client):
    """Fetches a single activity by its ID from the Strava API."""
    if not strava_client:
        raise ValueError("An authenticated Strava client is required.")
    return strava_client.get_activity(activity_id)

def update_activity_in_db(athlete_id: int, activity_id: int, strava_client: Client):
    """
    Fetches the latest data for an activity and updates it in the database.
    """
    if not strava_client:
        raise ValueError("An authenticated Strava client is required.")
    
    updated_activity = get_activity(activity_id, strava_client)
    if updated_activity:
        store_activities(athlete_id, [updated_activity])

def delete_activity_from_db(activity_id: int):
    """Deletes an activity from the local database."""
    with get_db_session() as session:
        activity_to_delete = session.get(Activity, activity_id)
        if activity_to_delete:
            session.delete(activity_to_delete)
            session.commit()
            logging.info(f"Deleted activity {activity_id} from the database.")
        else:
            logging.warning(f"Attempted to delete activity {activity_id}, but it was not found in the database.")
