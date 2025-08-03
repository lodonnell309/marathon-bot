import pytest
from fastapi.testclient import TestClient
from app import app

# Create a TestClient instance to make requests to your app
client = TestClient(app)

def test_root_redirects_to_strava_auth():
    """Tests that the root endpoint '/' correctly redirects to the Strava authorization URL."""
    # Make a request to the root endpoint, but do not follow the redirect
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307, "The root endpoint should issue a temporary redirect."
    assert "location" in response.headers, "The redirect response must contain a 'location' header."
    assert "strava.com/oauth/authorize" in response.headers["location"], "The redirect location should be the Strava authorization URL."