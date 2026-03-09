"""
Tools used by ADK agents: database queries, marathon plans, meals, and run summaries.
"""
import logging
import time
from typing import List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from database import get_db_session, engine
from models import Activity, MarathonPlan, Meal, UserTarget
from google.adk.tools import ToolContext

def model_to_dict(obj):
    """Converts a SQLAlchemy model instance to a dictionary, excluding internal state."""
    if not obj:
        return None
    return {c.key: getattr(obj, c.key) for c in inspect(obj).mapper.column_attrs}


def get_current_date():
    """
    Return the current date in YYYY-MM-DD format.
    """
    return time.strftime("%Y-%m-%d")

def list_tables_in_db() -> list:
    """
    List all user-facing tables in database.
    
    outputs: list of table names in the database
    """
    with get_db_session() as session:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        # Exclude ADK's internal session tables and the tokens table
        tables_to_exclude = {'tokens','adk_sessions','adk_session_messages'}
        user_facing_tables = [table for table in tables if table not in tables_to_exclude]
        return user_facing_tables

def get_strava_db_schema(table_name: str) -> dict:
    """
    Returns the schema for the specified table using SQLAlchemy introspection.
    inputs:
             table_name: str - Name of the table to get the schema for
    outputs: dict - Dictionary containing the table schema with column names as keys and their types as values
    """
    try:
        with get_db_session() as session:
            inspector = inspect(engine)
            columns = inspector.get_columns(table_name)
            schema = {column['name']: str(column['type']) for column in columns}
            return schema
    except Exception as e:
        logging.error(f"An error occurred getting schema for table '{table_name}': {e}")
        return {}

def execute_query(query: str, strava_athlete_id: int) -> list | str:
    """
    Execute a query on the database and return the results.
    This function enforces that all queries must be filtered by athlete_id to ensure data privacy.

    inputs:
            query: str - The SQL query to execute, e.g., "SELECT * FROM activities LIMIT 5;"
            strava_athlete_id: int - The ID of the authenticated Strava athlete.
    outputs: A list of dictionaries containing the query results, or an error string.

    """
    logging.info("Executing query for authenticated user.")
    
    # Check if the query is a SELECT statement for security
    if not query.strip().upper().startswith("SELECT") or "athlete_id" not in query.lower():
        error_msg = "Security Error: Query must be a SELECT statement and must filter on 'athlete_id'."
        logging.error(error_msg)
        return error_msg

    # Use SQLAlchemy's text() construct for raw SQL execution
    try:
        with get_db_session() as session:
            # Use SQLAlchemy's text() construct with parameter binding to prevent SQL injection.
            # The LLM is instructed to include `athlete_id = :strava_athlete_id` in its query.
            stmt = text(query)
            result = session.execute(stmt, {"strava_athlete_id": strava_athlete_id})
            columns = result.keys()
            results = [dict(zip(columns, row)) for row in result]
            return results
    except SQLAlchemyError as e:
        logging.error(f"An SQLAlchemy error occurred: {e}")
        return f"Database query failed: {e}"

class PlanDetailsItem(BaseModel):
    date: str = Field(..., description="The date of the workout in 'YYYY-MM-DD' format.")
    run_type: str = Field(..., description="The type of run (e.g., 'Easy Run', 'Long Run', 'Tempo').")
    distance_miles: float = Field(..., description="The distance for the run in miles.")

def create_marathon_plan(athlete_id: int, start_date: str, plan_details: List[PlanDetailsItem]) -> str:
    """
    Creates a new marathon training plan for a user and stores it in the marathon_plan table.
    It clears any existing plan for the athlete and inserts the new one.
    """
    try:
        with get_db_session() as session:
            # First, delete any existing plan for this athlete
            session.query(MarathonPlan).filter(MarathonPlan.athlete_id == athlete_id).delete()
            
            # Then, insert the new plan
            for workout in plan_details:
                new_workout = MarathonPlan(
                    athlete_id=athlete_id,
                    date=workout.date,
                    run_type=workout.run_type,
                    distance_miles=workout.distance_miles
                )
                session.add(new_workout)
            
            session.commit()
            logging.info(f"Successfully created a marathon plan for athlete {athlete_id} starting on {start_date}.")
            return f"Marathon plan created successfully for athlete ID {athlete_id}."
    
    except SQLAlchemyError as e:
        logging.error(f"Failed to create marathon plan for athlete {athlete_id}: {e}")
        return f"Failed to create marathon plan: {e}"

def delete_marathon_plan(athlete_id: int) -> str:
    """Deletes the marathon training plan for a user."""
    try:
        with get_db_session() as session:
            result = session.query(MarathonPlan).filter(MarathonPlan.athlete_id == athlete_id).delete()
            session.commit()
            
            if result == 0:
                logging.warning(f"No marathon plan found for athlete {athlete_id} to delete.")
                return f"Warning: No marathon plan found for athlete ID {athlete_id}."
            
            logging.info(f"Successfully deleted marathon plan for athlete {athlete_id}.")
            return f"Marathon plan deleted successfully for athlete ID {athlete_id}."
    
    except SQLAlchemyError as e:
        logging.error(f"Failed to delete marathon plan for athlete {athlete_id}: {e}")
        return f"Failed to delete marathon plan: {e}"

def update_marathon_plan(athlete_id: int, date: str, new_run_type: str, new_distance_miles: float) -> str:
    """Updates a single workout in the marathon training plan for a user on a specific date."""
    try:
        with get_db_session() as session:
            workout_to_update = session.query(MarathonPlan).filter(
                MarathonPlan.athlete_id == athlete_id,
                MarathonPlan.date == date
            ).one_or_none()
            
            if workout_to_update:
                workout_to_update.run_type = new_run_type
                workout_to_update.distance_miles = new_distance_miles
                session.commit()
                logging.info(f"Successfully updated marathon plan for athlete {athlete_id} on {date}.")
                return f"Marathon plan updated successfully for the workout on {date}."
            else:
                logging.warning(f"No workout found for athlete {athlete_id} on date {date} to update.")
                return f"Warning: No workout found for {date} to update."
    
    except SQLAlchemyError as e:
        logging.error(f"Failed to update marathon plan for athlete {athlete_id}: {e}")
        return f"Failed to update marathon plan: {e}"

def upload_meal_to_db(athlete_id:int, meal_name: str, date:str,
                      protein_grams: float, carbs_grams: float,
                      fat_grams: float, calories: float) -> str:
    """Creates an entry in the meals table in the database."""
    try:
        with get_db_session() as session:
            new_meal = Meal(
                athlete_id=athlete_id,
                meal_name=meal_name,
                date=date,
                protein_grams=protein_grams,
                carbs_grams=carbs_grams,
                fat_grams=fat_grams,
                calories=calories
            )
            session.add(new_meal)
            session.commit()
            return f"Meal '{meal_name}' on {date} successfully added for athlete_id {athlete_id}."
    except SQLAlchemyError as e:
        logging.error(f"Failed to add meal: {e}")
        return f"Failed to add meal: {e}"

def update_user_targets(athlete_id: int,
                        target_protein_grams: float,
                        target_carbs_grams: float,
                        target_fat_grams: float,
                        target_calories: float):
    """Updates the user's target macronutrients in the user_targets table."""
    try:
        with get_db_session() as session:
            user_target = session.get(UserTarget, athlete_id)
            if not user_target:
                user_target = UserTarget(athlete_id=athlete_id)
                session.add(user_target)
            
            user_target.target_protein_grams = target_protein_grams
            user_target.target_carbs_grams = target_carbs_grams
            user_target.target_fat_grams = target_fat_grams
            user_target.target_calories = target_calories
            
            session.commit()
            return f"User targets successfully updated for athlete_id {athlete_id}."
    except SQLAlchemyError as e:
        logging.error(f"Failed to update user targets: {e}")
        return f"Failed to update user targets: {e}"

def get_last_x_runs(strava_athlete_id: int, x: int) -> list:
    """Gets the last x runs for a given athlete."""
    try:
        with get_db_session() as session:
            runs = session.query(Activity).filter(Activity.athlete_id == strava_athlete_id)\
                          .order_by(Activity.start_date_local.desc())\
                          .limit(x)\
                          .all()
            
            return [model_to_dict(run) for run in runs]
    except SQLAlchemyError as e:
        logging.error(f"Error in get_last_x_runs: {e}")
        return []

def get_recent_run_summary(strava_athlete_id: int, x: int) -> str:
    """
    Retrieves and summarizes the last x runs for a user.
    """
    try:
        runs = get_last_x_runs(strava_athlete_id, x)
        if not runs:
            return "No runs found for your account."

        summary = f"Your last {len(runs)} runs:\n"
        for i, run in enumerate(runs):
            name = run.get('name', 'N/A')
            distance = round(run.get('distance_miles', 0), 2)
            moving_time = run.get('moving_time_minutes', 0)
            date_obj = run.get('start_date_local')
            date_str = date_obj.strftime('%Y-%m-%d') if date_obj else 'N/A'
            
            summary += f"{i+1}. '{name}' on {date_str}: {distance} miles in {moving_time} minutes.\n"
        return summary

    except Exception as e:
        return f"An error occurred while summarizing your runs: {e}"


def transfer_to_agent(agent_name: str, tool_context: ToolContext) -> str:
    """
    Transfers the conversation to another agent.
    This is an ADK-specific tool.
    Signals to the ADK framework to transfer the conversation to another agent.
    This tool modifies the tool_context to instruct the runner to perform the transfer.
    """
    tool_context.actions.transfer_to_agent = agent_name
    # This return value is for logging/debugging; the transfer is handled by the framework.
    return f"Signaling transfer to {agent_name}."
