import pytest
from app.services.voice_processor import VoiceProcessor

processor = VoiceProcessor()

def test_status_command_triggers_impact_endpoint():
    """Test 'What's the status?' maps to GET /api/impact"""
    result = processor.process_command("What's the status?")
    assert result["action"] == "get_impact"
    assert result["endpoint"] == "GET /api/impact"

def test_approve_incident_command():
    """Test 'Approve incident [ID]' maps to POST /api/incidents/{id}/approve"""
    result = processor.process_command("Approve incident 123")
    assert result["action"] == "approve_incident"
    assert result["incident_id"] == "123"
    assert result["endpoint"] == "POST /api/incidents/123/approve"

def test_start_patrol_command():
    """Test 'Start patrol' maps to POST /api/patrol/start"""
    result = processor.process_command("Start patrol")
    assert result["action"] == "start_patrol"
    assert result["endpoint"] == "POST /api/patrol/start"

def test_unknown_command_returns_error():
    """Test unknown commands return error response"""
    result = processor.process_command("Invalid command")
    assert result["action"] == "unknown"
    assert "error" in result
