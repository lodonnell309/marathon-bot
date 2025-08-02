import os
import logging
import asyncio
import uuid
import httpx
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import RedirectResponse

# Load environment variables at the very beginning of the script
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
load_dotenv(os.path.join(os.path.dirname(__file__), 'marathon-bot', '.env'))


# --- ADK Specific Imports ---
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai import types
from main_agent.agent import main_agent

# --- Local Imports ---
from database import init_db, get_athlete_id_by_telegram_chat_id, get_telegram_chat_id_by_athlete_id, DATABASE_URL
from strava_client import (
    get_auth_url, exchange_code_for_tokens, get_authenticated_client,
    store_activities, get_activity, delete_activity_from_db, update_activity_in_db
)
# Explicitly import all models so SQLAlchemy's Base.metadata.create_all() can find them.
from models import Base, Token, Activity, MarathonPlan, Meal, UserTarget

app = FastAPI()

logging.basicConfig(level=logging.INFO)

# Now that the environment variables are loaded, we can call init_db().
# This ensures DATABASE_URL is available.
logging.info("Calling init_db() to create tables...")
init_db()
logging.info("Database initialization call complete.")


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    logging.warning("TELEGRAM_BOT_TOKEN not found in environment variables. Telegram messages will not be sent.")

STRAVA_VERIFY_TOKEN = os.getenv("STRAVA_VERIFY_TOKEN")
if not STRAVA_VERIFY_TOKEN:
    logging.error("STRAVA_VERIFY_TOKEN not found. Webhook verification will fail.")


session_service = DatabaseSessionService(db_url=DATABASE_URL)
APP_NAME = "strava-telegram-bot"
runner = None

@app.on_event("startup")
async def startup_event():
    global runner
    logging.info("Initializing ADK Runner...")
    runner = Runner(
        agent=main_agent,
        app_name=APP_NAME,
        session_service=session_service
    )
    logging.info("ADK Runner initialized.")

def create_initial_state(telegram_chat_id: int) -> dict:
    """Helper to create an initial state for a new user session."""
    try:
        initial_state = {
            "name": "Runner",
            "user_id": str(telegram_chat_id),
            "strava_authenticated": False,
            "strava_athlete_id": None
        }
        logging.info(f"Initial state created: {initial_state}")
        return initial_state
    except KeyError as e:
        logging.error(f"Error creating initial state: {e}. Using default values.")
        return { "name": "Unknown", "user_id": "Unknown", "strava_authenticated": False, "strava_athlete_id": None }


@app.get("/")
async def index():
    logging.info("Redirecting to Strava authentication URL.")
    return RedirectResponse(url=get_auth_url())

@app.get("/webhook")
async def strava_webhook_verification(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge")
):
    logging.info("Webhook verification GET request received.")
    
    if hub_mode == "subscribe" and hub_verify_token == STRAVA_VERIFY_TOKEN:
        logging.info("Webhook verified successfully.")
        return {"hub.challenge": hub_challenge}
    else:
        logging.error("Webhook verification failed: Invalid mode or token.")
        raise HTTPException(status_code=403, detail="Forbidden: Invalid verify token.")

@app.post("/webhook")
async def strava_webhook_event(request: Request):
    payload = await request.json()
    logging.info(f"Webhook event received: {payload}")
    
    aspect_type = payload.get("aspect_type")
    object_type = payload.get("object_type")
    
    if object_type != "activity":
        logging.info(f"Ignoring webhook event for object type: {object_type}")
        return {"status": "success", "message": "EVENT_RECEIVED"}

    athlete_id = payload.get("owner_id")
    activity_id = payload.get("object_id")
    
    try:
        if aspect_type == "create":
            logging.info(f"New activity created: {activity_id} for athlete: {athlete_id}")
            
            telegram_chat_id = get_telegram_chat_id_by_athlete_id(athlete_id)

            if telegram_chat_id and runner:
                user_id = str(telegram_chat_id)
                response_text = "Sorry, I couldn't process your request."

                session_list_obj = await session_service.list_sessions(
                    app_name=APP_NAME,
                    user_id=user_id,
                )
                current_session = None
                if session_list_obj and len(session_list_obj.sessions) > 0:
                    current_session = session_list_obj.sessions[0]
                else:
                    initial_state = create_initial_state(telegram_chat_id)
                    current_session = await session_service.create_session(
                        app_name=APP_NAME,
                        user_id=user_id,
                        state=initial_state
                    )

                current_session.state['strava_authenticated'] = True
                current_session.state['strava_athlete_id'] = athlete_id
                
                agent_trigger_message = f"Strava activity created with ID {activity_id}. Please motivate me!"
                new_message_content = types.Content(role="user", parts=[types.Part(text=agent_trigger_message)])
                
                async for event in runner.run_async(
                    user_id=user_id,
                    session_id=current_session.id,
                    new_message=new_message_content,
                ):
                    if event.is_final_response():
                        if event.content and event.content.parts:
                            response_text = event.content.parts[0].text
                        break
                
                if TELEGRAM_BOT_TOKEN:
                    await send_telegram_message(telegram_chat_id, response_text)
                else:
                    logging.warning(f"Telegram Bot Token not set. Not sending message to chat_id {telegram_chat_id}: {response_text}")
            else:
                logging.warning(f"Could not find Telegram chat ID for athlete {athlete_id} or ADK runner is not initialized.")
            
            strava_client = get_authenticated_client(athlete_id)
            activity = get_activity(activity_id, strava_client)
            store_activities(athlete_id, [activity])
            logging.info(f"Successfully stored new activity {activity_id} for athlete {athlete_id}.")

        elif aspect_type == "update":
            logging.info(f"Activity updated: {activity_id} for athlete: {athlete_id}")
            
            strava_client = get_authenticated_client(athlete_id)
            update_activity_in_db(athlete_id, activity_id, strava_client)
            logging.info(f"Successfully updated activity {activity_id} for athlete {athlete_id}.")
            
            telegram_chat_id = get_telegram_chat_id_by_athlete_id(athlete_id)
            if telegram_chat_id:
                updated_activity = get_activity(activity_id, strava_client)
                await send_telegram_message(telegram_chat_id, f"✅ Your activity '{updated_activity.name}' has been updated.")

        elif aspect_type == "delete":
            logging.info(f"Activity deleted: {activity_id} for athlete: {athlete_id}")
            
            delete_activity_from_db(activity_id)
            logging.info(f"Successfully deleted activity {activity_id} from the database.")

            telegram_chat_id = get_telegram_chat_id_by_athlete_id(athlete_id)
            if telegram_chat_id:
                await send_telegram_message(telegram_chat_id, "🗑️ An activity was deleted from your Strava account.")

    except Exception as e:
        logging.error(f"Error processing webhook for aspect_type '{aspect_type}': {e}")
            
    return {"status": "success", "message": "EVENT_RECEIVED"}


@app.get("/callback")
async def callback(code: Optional[str] = Query(None), state: Optional[str] = Query(None)):
    logging.info(f"Handling Strava callback. Code: {code}, State: {state}")

    telegram_chat_id = None
    if state:
        try:
            telegram_chat_id = int(state)
            logging.info(f"Retrieved Telegram chat_id from state: {telegram_chat_id}")
        except ValueError:
            logging.warning(f"Could not convert state '{state}' to an integer chat_id.")

    if not code:
        logging.error("Strava callback received without authorization code.")
        return {"error": "Authorization code missing."}

    try:
        athlete = exchange_code_for_tokens(code, telegram_chat_id)
        
        if TELEGRAM_BOT_TOKEN and telegram_chat_id:
            await send_telegram_message(telegram_chat_id, f"🎉 You're now connected to Strava, {athlete.firstname}! I can help you with your running data.")

        return f"Welcome {athlete.firstname}! You are now connected to Strava. You can close this window."
    except Exception as e:
        logging.error(f"Error during Strava callback for chat_id {telegram_chat_id}: {e}")
        if TELEGRAM_BOT_TOKEN and telegram_chat_id:
            await send_telegram_message(telegram_chat_id, f"Oops! There was an error connecting to Strava: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")

@app.get("/profile/{athlete_id}")
async def profile(athlete_id: int):
    logging.info(f"Fetching profile for athlete ID: {athlete_id}")
    try:
        client = get_authenticated_client(athlete_id)
        athlete = client.get_athlete()
        return {"user": f"{athlete.firstname} {athlete.lastname}"}
    except Exception as e:
        logging.error(f"Error fetching profile for athlete ID {athlete_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching profile: {e}")

@app.post("/telegram_webhook")
async def telegram_webhook(request: Request):
    if runner is None:
        logging.error("ADK Runner not initialized. Application startup failed or is not complete.")
        raise HTTPException(status_code=503, detail="Service unavailable: ADK Runner not ready.")

    try:
        telegram_update = await request.json()
        logging.info(f"Received Telegram update: {telegram_update}")

        message = telegram_update.get("message")
        if not message:
            logging.warning("No message object in Telegram update.")
            raise HTTPException(status_code=400, detail="No message object in Telegram update")

        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "").strip()

        if not chat_id or not text:
            logging.warning("Missing chat_id or text in Telegram message.")
            raise HTTPException(status_code=400, detail="Missing chat_id or text in Telegram message")

        user_id = str(chat_id)
        response_text = "Sorry, I couldn't process your request."

        # --- SESSION MANAGEMENT: RETRIEVE OR CREATE ---
        session_list_obj = await session_service.list_sessions(
            app_name=APP_NAME,
            user_id=user_id,
        )
        logging.info(f"Retrieved sessions for user_id '{user_id}': {session_list_obj.sessions}")
        current_session = None
        if session_list_obj and len(session_list_obj.sessions) > 0:
            current_session = session_list_obj.sessions[0]
            logging.info(f"Retrieved existing session for user_id '{user_id}': {current_session.id}")
            logging.info(f"Session state before update: {current_session.state}")
        else:
            logging.info(f"No existing session found for user_id '{user_id}'. Creating a new session.")
            initial_state = create_initial_state(chat_id)
            current_session = await session_service.create_session(
                app_name=APP_NAME,
                user_id=user_id,
                state=initial_state
            )
            logging.info(f"Created new session: {current_session.id}")
        
        # --- UPDATE SESSION STATE WITH LATEST ATHLETE_ID ---
        strava_athlete_id = get_athlete_id_by_telegram_chat_id(chat_id)
        logging.info(f"Retrieved Strava athlete ID for chat_id {chat_id}: {strava_athlete_id}")
        
        if strava_athlete_id:
            current_session.state['strava_authenticated'] = True
            current_session.state['strava_athlete_id'] = strava_athlete_id
            logging.info(f"Strava athlete ID {strava_athlete_id} found for chat_id {chat_id}. Updating session state.")
        else:
            current_session.state['strava_authenticated'] = False
            current_session.state['strava_athlete_id'] = None
            logging.error(f"No Strava athlete ID found for chat_id {chat_id}. Session state will not be updated with athlete ID.")
        
        logging.info(f"Updated session state before running agent: {current_session.state}")

        # --- HANDLE SPECIFIC COMMANDS ---
        if text.lower() == "/authenticate":
            auth_url = get_auth_url()
            auth_url_with_state = f"{auth_url}&state={chat_id}"
            response_text = (
                f"Please click this link to connect with Strava: {auth_url_with_state}\n\n"
                "After authenticating, you can send me questions about your running data!"
            )
            await send_telegram_message(chat_id, response_text)
            return {"status": "success", "message": "Sent authentication link"}
            
        # --- PASS MESSAGE TO ADK AGENT ---
        new_message_content = types.Content(role="user", parts=[types.Part(text=text)])
        logging.info(f"Sending message to ADK agent...")
        logging.info(f'Current session state: {current_session.state}')

        async for event in runner.run_async(
            user_id=user_id,
            session_id=current_session.id,
            new_message=new_message_content,
        ):
            if event.is_final_response():
                if event.content and event.content.parts:
                    response_text = event.content.parts[0].text
                    logging.info(f"ADK agent response: {response_text}")
                break
        
        # --- SEND FINAL RESPONSE ---
        if TELEGRAM_BOT_TOKEN:
            await send_telegram_message(chat_id, response_text)
        else:
            logging.warning(f"Telegram Bot Token not set. Not sending message to chat_id {chat_id}: {response_text}")

        return {"status": "success", "message": "Processed Telegram update"}

    except Exception as e:
        logging.exception(f"Error processing Telegram webhook: {e}")
        if TELEGRAM_BOT_TOKEN and chat_id:
            await send_telegram_message(chat_id, "Oops! Something went wrong on my end. Please try again later.")
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")

async def send_telegram_message(chat_id: int, text: str):
    """
    Sends a message back to the Telegram chat.
    """
    telegram_api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(telegram_api_url, json=payload)
            response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
            logging.info(f"Telegram API response: {response.json()}")
    except httpx.RequestError as e:
        logging.error(f"An error occurred while requesting Telegram API: {e}")
    except httpx.HTTPStatusError as e:
        logging.error(f"Error response {e.response.status_code} while sending Telegram message: {e.response.text}")
    except Exception as e:
        logging.error(f"An unexpected error occurred sending Telegram message: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
