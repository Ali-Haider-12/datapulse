import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_incoming_voice_returns_twiml():
    """Test that POST /api/voice/incoming returns valid TwiML with Gather and Say"""
    response = client.post(
        "/api/voice/incoming",
        data={"CallSid": "CA123456", "From": "+1234567890"}
    )
    assert response.status_code == 200
    assert "text/xml" in response.headers.get("content-type", "")
    assert "<Gather" in response.text
    assert "<Say" in response.text

def test_voice_webhook_accepts_twilio_form_data():
    """Test endpoint handles Twilio's form-encoded webhook payload"""
    response = client.post(
        "/api/voice/incoming",
        data={
            "CallSid": "CA123",
            "From": "+1234567890",
            "To": "+0987654321",
            "CallStatus": "in-progress"
        }
    )
    assert response.status_code == 200
