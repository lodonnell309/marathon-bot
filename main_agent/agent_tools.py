from google.adk.agents import Agent
import sqlite3
import time
from stravalib import Client
from flask import current_app
import logging
from typing import List, Optional
from pydantic import BaseModel, Field 

def get_athlete_id_by_telegram_chat_id(db_path: str,telegram_chat_id: int) -> Optional[int]:
    """
    Return the Strava athlete ID for a given Telegram chat ID.

    inputs: db_path: str - Path to the SQLite database file (e.g., 'strava.db')
                telegram_chat_id: int - The Telegram chat ID to look up
    outputs: Optional[int] - The Strava athlete ID if found, otherwise None.
    """
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("""
        SELECT athlete_id FROM tokens WHERE telegram_chat_id = ?
        """, (telegram_chat_id,)).fetchone()
        return row[0] if row else None

def get_current_date():
    """
    Return the current date in YYYY-MM-DD format.
    """
    return time.strftime("%Y-%m-%d")

def list_tables_in_db(db_path: str) -> list:
    """
    List all tables in the SQLite database.
    
    inputs: db_path: str - Path to the SQLite database file
    outputs: list of table names in the database
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        tables = []
    finally:
        conn.close()

    if 'tokens' in tables:
        tables.remove('tokens') 
    
    return tables

def get_strava_db_schema(db_path:str,table_name:str) -> dict:
    """
    Returns the schema for the specified table
    inputs: db_path: str - Path to the SQLite database file
             table_name: str - Name of the table to get the schema for
    outputs: dict - Dictionary containing the table schema with column names as keys and their types as values
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute(f"PRAGMA table_info({table_name});")
        schema = {row[1]: row[2] for row in cursor.fetchall()}
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        schema = {}
    finally:
        conn.close()
    
    return schema

def execute_query(db_path: str, query: str, strava_athlete_id: int) -> list:
    """
    Execute a query on the SQLite database and return the results as a python dictionary.
    This function enforces that all queries must be filtered by athlete_id to ensure data privacy.

    inputs: db_path: str - Path to the SQLite database file
            query: str - The SQL query to execute, e.g., "SELECT * FROM activities LIMIT 5;"
            strava_athlete_id: int - The ID of the authenticated Strava athlete.
    outputs: list of dictionaries containing the query results
    """
    logging.info(f"Executing query: {query} for athlete_id: {strava_athlete_id}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        secure_query = ""
        
        # Check if the query is a SELECT statement (for security)
        if not query.upper().strip().startswith("SELECT"):
            logging.error("Only SELECT queries are allowed for security reasons.")
            return []

        # We will now use f-strings to inject the athlete_id, which is simpler and more reliable here.
        # This bypasses the parameterized query issue.
        if 'WHERE' in query.upper():
            # If so, append to the existing WHERE clause
            secure_query = query.replace('WHERE', f'WHERE athlete_id = {strava_athlete_id} AND ', 1)
        else:
            # If not, add a WHERE clause to filter by athlete_id
            secure_query = f"{query.rstrip(';')}' WHERE athlete_id = {strava_athlete_id};"
        
        logging.info(f"Executing secure query: {secure_query}") # Log the query for debugging
        
        cursor.execute(secure_query)
        columns = [column[0] for column in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        results = []
    finally:
        conn.close()
    
    return results

# --- NEW: Define a Pydantic model for the plan_details items ---
class PlanDetailsItem(BaseModel):
    date: str = Field(..., description="The date of the workout in 'YYYY-MM-DD' format.")
    run_type: str = Field(..., description="The type of run (e.g., 'Easy Run', 'Long Run', 'Tempo').")
    distance_miles: float = Field(..., description="The distance for the run in miles.")

# --- Corrected create_marathon_plan function signature ---
def create_marathon_plan(athlete_id: int, start_date: str, plan_details: List[PlanDetailsItem]) -> str:
    """
    Creates a new marathon training plan for a user and stores it in the marathon_plan table.
    It clears any existing plan for the athlete and inserts the new one.

    inputs:
        athlete_id: int - The ID of the authenticated Strava athlete.
        start_date: str - The date the plan should start in 'YYYY-MM-DD' format.
        plan_details: list - A list of dictionaries, where each dictionary represents a workout.
    outputs: A string indicating the success or failure of the operation.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("DELETE FROM marathon_plan WHERE athlete_id = ?", (athlete_id,))

        logging.info(f'first 5 workouts in plan_details: {plan_details[:5]}') # Log the first 5 workouts for debugging
        for workout in plan_details:
            cursor.execute(
                """
                INSERT INTO marathon_plan (athlete_id, date, run_type, distance_miles)
                VALUES (?, ?, ?, ?)
                """,
                # --- NEW: Access attributes from the Pydantic model ---
                (athlete_id, workout['date'], workout['run_type'], workout['distance_miles'])
                # --- END NEW ---
            )
        
        conn.commit()
        logging.info(f"Successfully created a marathon plan for athlete {athlete_id} starting on {start_date}.")
        return f"Marathon plan created successfully for athlete ID {athlete_id}."
    
    except (sqlite3.Error, KeyError) as e:
        conn.rollback()
        logging.error(f"Failed to create marathon plan for athlete {athlete_id}: {e}")
        return f"Failed to create marathon plan: {e}"
    finally:
        conn.close()

def delete_marathon_plan(athlete_id: int) -> str:
    """
    Deletes the marathon training plan for a user.

    inputs:
        athlete_id: int - The ID of the authenticated Strava athlete.
    outputs: A string indicating the success or failure of the operation.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("DELETE FROM marathon_plan WHERE athlete_id = ?", (athlete_id,))
        conn.commit()
        
        if cursor.rowcount == 0:
            logging.warning(f"No marathon plan found for athlete {athlete_id} to delete.")
            return f"Warning: No marathon plan found for athlete ID {athlete_id}."
        
        logging.info(f"Successfully deleted marathon plan for athlete {athlete_id}.")
        return f"Marathon plan deleted successfully for athlete ID {athlete_id}."

    except sqlite3.Error as e:
        conn.rollback()
        logging.error(f"Failed to delete marathon plan for athlete {athlete_id}: {e}")
        return f"Failed to delete marathon plan: {e}"
    finally:
        conn.close()

def update_marathon_plan(athlete_id: int, date: str, new_run_type: str, new_distance_miles: float) -> str:
    """
    Updates a single workout in the marathon training plan for a user on a specific date.

    inputs:
        athlete_id: int - The ID of the authenticated Strava athlete.
        date: str - The date of the workout to update in 'YYYY-MM-DD' format.
        new_run_type: str - The new type of run (e.g., 'Tempo Run', 'Long Run').
        new_distance_miles: float - The new distance for the run in miles.
    outputs: A string indicating the success or failure of the operation.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            UPDATE marathon_plan
            SET run_type = ?, distance_miles = ?
            WHERE athlete_id = ? AND date = ?
            """,
            (new_run_type, new_distance_miles, athlete_id, date)
        )
        conn.commit()
        
        if cursor.rowcount == 0:
            logging.warning(f"No workout found for athlete {athlete_id} on date {date} to update.")
            return f"Warning: No workout found for {date} to update."
        
        logging.info(f"Successfully updated marathon plan for athlete {athlete_id} on {date}.")
        return f"Marathon plan updated successfully for the workout on {date}."

    except sqlite3.Error as e:
        conn.rollback()
        logging.error(f"Failed to update marathon plan for athlete {athlete_id}: {e}")
        return f"Failed to update marathon plan: {e}"
    finally:
        conn.close()


def upload_meal_to_db(db_path: str, strava_athlete_id:int, meal_name: str,
                      protein_grams: float, carbs_grams: float,
                      fat_grams: float, calories: float) -> str:
    """
    Creates an entry in the meals table in the Strava SQLite database.
    
    meals table schema:
        meal_id INTEGER PRIMARY KEY AUTOINCREMENT,
        meal_name TEXT NOT NULL,
        protein_grams REAL,
        carbs_grams REAL,
        fat_grams REAL,
        calories REAL,
        athlete_id INTEGER,
        FOREIGN KEY (athlete_id) REFERENCES tokens(athlete_id)
    
    Inputs:
        db_path: the path to the database (e.g., 'strava.db')
        athlete_id: the strava_athlete_id of the user
        meal_name: the name of the meal
        protein_grams: the number of grams of protein in the meal
        carbs_grams: the number of grams of carbs in the meal
        fat_grams: the number of grams of fat in the meal
        calories: the number of calories in the meal
    
    Outputs:
        Result of the database entry indicating success or failure
    """
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute('''
            INSERT INTO meals (meal_name, protein_grams, carbs_grams, fat_grams, calories, athlete_id)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (meal_name, protein_grams, carbs_grams, fat_grams, calories, strava_athlete_id))
        conn.commit()
        return f"Meal '{meal_name}' successfully added for athlete_id {strava_athlete_id}."
    except Exception as e:
        return f"Failed to add meal: {e}"
    finally:
        conn.close()

def update_user_targets(db_path: str, athlete_id: int,
                        target_protein_grams: float,
                        target_carbs_grams: float,
                        target_fat_grams: float,
                        target_calories: float):
    """
    Updates the user's target macronutrients in the user_targets table in the Strava SQLite database.
    input:
        db_path: the path to the database (e.g., 'strava.db')
        athlete_id: the strava_athlete_id of the user
        target_protein_grams: the number of grams of protein the user wants to eat
        target_carbs_grams: the number of grams of carbs the user wants to eat
        target_fat_grams: the number of grams of fat the user wants to eat
        target_calories: the number of calories the user wants to eat
    output:
        Result of the database entry indicating success or failure
    """
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute('''
            INSERT OR REPLACE INTO user_targets (athlete_id, target_protein_grams, target_carbs_grams, target_fat_grams, target_calories)
            VALUES (?, ?, ?, ?, ?)
        ''', (athlete_id, target_protein_grams, target_carbs_grams, target_fat_grams, target_calories))
        conn.commit()
        return f"User targets successfully updated for athlete_id {athlete_id}."
    except Exception as e:
        return f"Failed to update user targets: {e}"
    finally:
        conn.close()


def get_last_x_runs(strava_athlete_id: int, x: int) -> list:
    """
    Gets the last x runs for a given athlete.
    input:
        strava_athlete_id: int
        x: int
    output:
        list of dictionaries
    """
    try:
        conn = sqlite3.connect("strava.db")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM activities WHERE athlete_id = ? ORDER BY start_date_local DESC LIMIT ?",
            (strava_athlete_id, x)
        )
        results = cursor.fetchall()
        columns = [col[0] for col in cursor.description]
        conn.close()
        return [dict(zip(columns, row)) for row in results]
    except Exception as e:
        logging.error(f"Error in get_last_x_runs: {e}")
        return []
