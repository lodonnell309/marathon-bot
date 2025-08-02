import os
import requests
from dotenv import load_dotenv
import logging
import json

# Set up basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def create_webhook_subscription():
    """
    Creates a new Strava webhook subscription by making a POST request to the Strava API.
    
    This script reads the necessary credentials from a local .env file.
    It constructs the callback URL using the NGROK_URL and the '/webhook' endpoint.
    If successful, it prints the subscription ID.
    """
    logging.info("Loading environment variables from .env file...")
    load_dotenv()
    
    # Strava API endpoints and credentials
    STRAVA_API_URL = "https://www.strava.com/api/v3/push_subscriptions"
    
    # Retrieve required environment variables
    try:
        client_id = os.getenv("STRAVA_CLIENT_ID")
        client_secret = os.getenv("STRAVA_CLIENT_SECRET")
        verify_token = os.getenv("STRAVA_VERIFY_TOKEN")
        callback_url = os.getenv("STRAVA_WEBHOOK_URL")
        
        if not all([client_id, client_secret, verify_token, callback_url]):
            raise ValueError("Missing one or more required environment variables (STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_VERIFY_TOKEN, STRAVA_WEBHOOK_URL).")
    except ValueError as e:
        logging.error(f"Error: {e}")
        return

    logging.info(f"Using callback URL: {callback_url}")

    # Step 1: Check for existing subscriptions and delete them
    try:
        logging.info("Checking for existing webhook subscriptions...")
        response = requests.get(STRAVA_API_URL, params={'client_id': client_id, 'client_secret': client_secret})
        response.raise_for_status()
        
        subscriptions = response.json()
        logging.info(f"Strava API response for existing subscriptions: {json.dumps(subscriptions)}")
        
        if isinstance(subscriptions, list) and len(subscriptions) > 0:
            for sub in subscriptions:
                if 'id' in sub:
                    sub_id = sub['id']
                    logging.warning(f"Found existing subscription with ID {sub_id}. Deleting it now...")
                    delete_url = f"{STRAVA_API_URL}/{sub_id}"
                    delete_response = requests.delete(delete_url, params={'client_id': client_id, 'client_secret': client_secret})
                    delete_response.raise_for_status()
                    logging.info(f"Successfully deleted subscription ID: {sub_id}")
            logging.info("All existing subscriptions have been deleted.")
        else:
            logging.info("No existing subscriptions found. Proceeding with creation.")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error checking for existing subscriptions: {e}")
        # We can continue and try to create a new one anyway, as the error might be temporary
        pass

    # Step 2: Attempt to create a new subscription
    data = {
        'client_id': client_id,
        'client_secret': client_secret,
        'callback_url': callback_url,
        'verify_token': verify_token
    }
    
    try:
        logging.info("Attempting to create Strava webhook subscription...")
        # Sending parameters as form data, which is recommended by the docs
        response = requests.post(STRAVA_API_URL, data=data)
        response.raise_for_status()

        subscription_info = response.json()
        subscription_id = subscription_info.get('id')
        if subscription_id:
            logging.info(f"Successfully created webhook subscription with ID: {subscription_id}")
            print(f"Webhook subscription created successfully. Subscription ID: {subscription_id}")
        else:
            logging.error(f"Failed to create webhook. Strava API Response: {response.text}")
            print(f"Error: Failed to create webhook. Response was: {response.text}")

    except requests.exceptions.HTTPError as e:
        logging.error(f"An HTTP error occurred: {e}")
        try:
            error_response = e.response.json()
            logging.error(f"Strava API error details: {error_response}")
            print(f"An HTTP error occurred: {e}")
            print(f"Strava API error details: {error_response}")
        except json.JSONDecodeError:
            logging.error(f"Strava API error details: {e.response.text}")
            print(f"An HTTP error occurred: {e}")
            print(f"Strava API error details: {e.response.text}")
    except requests.exceptions.RequestException as e:
        logging.error(f"An error occurred during the API request: {e}")
        print(f"An error occurred during the API request: {e}")

if __name__ == '__main__':
    create_webhook_subscription()
