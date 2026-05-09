"""
Voice API — Twilio webhook for voice commands.
"""

from fastapi import APIRouter, Request
from fastapi.responses import Response
from app.services.voice_processor import VoiceProcessor

router = APIRouter()
processor = VoiceProcessor()


@router.post("/incoming")
async def voice_incoming(req: Request):
    """Handle incoming Twilio voice calls."""
    # TwiML response — ask user to speak
    twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" timeout="10" language="en-US" action="/api/voice/process">
        <Say voice="alice">Hello! DataPulse monitoring is active. Say your command, like status, health check, or start patrol.</Say>
    </Gather>
</Response>"""
    return Response(content=twiml, media_type="application/xml")


@router.post("/process")
async def voice_process(req: Request):
    """Process recognized speech from Twilio."""
    form = await req.form()
    speech_result = form.get("SpeechResult", "")

    if not speech_result:
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice">I didn't catch that. Please try again.</Say>
    <Redirect>/api/voice/incoming</Redirect>
</Response>"""
        return Response(content=twiml, media_type="application/xml")

    result = processor.process_command(speech_result)
    response_text = _build_response(result)

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice">{response_text}</Say>
</Response>"""
    return Response(content=twiml, media_type="application/xml")


def _build_response(result: dict) -> str:
    """Build Twilio TTS response from voice processor result."""
    action = result.get("action", "unknown")
    message = result.get("message", "")

    if action == "get_impact":
        return "Here is your current business impact assessment. " + message
    elif action == "get_health":
        return "Here is your infrastructure health status. " + message
    elif action == "start_patrol":
        return "Patrol sweep has been initiated. You will be notified when it completes."
    elif action == "stop_patrol":
        return "Patrol sweep has been stopped."
    elif action == "start_war_room":
        return "War room has been activated. All agents are now investigating."
    elif action == "check_mappings":
        return message
    elif action == "check_errors":
        return message
    elif action == "check_shards":
        return message
    elif action == "ingestion_rate":
        return message
    elif action == "detect_incidents":
        return "Running incident detection now. " + message
    elif action == "list_incidents":
        return message or "No active incidents."
    elif action == "approve_incident":
        return "Approval has been submitted."
    elif action == "goodbye":
        return "Goodbye. DataPulse will continue monitoring your infrastructure."
    elif action == "help":
        return "Available commands: status, health, start patrol, stop patrol, start war room, check mappings, check errors, check shards, ingestion rate, detect incidents, list incidents. You can also ask natural language questions."
    elif action == "unknown":
        suggestion = result.get("did_you_mean", "")
        if suggestion:
            return f"I'm not sure what you meant. Did you say {suggestion}?"
        return "I didn't understand that command. Say help to hear available commands."
    return message or "Command processed."