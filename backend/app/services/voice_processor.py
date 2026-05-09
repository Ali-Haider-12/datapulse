"""
Enhanced Voice Processor — Natural language command interpreter.

Supports 15+ voice commands with fuzzy matching and context awareness.
"""

import re
from typing import Dict, Any, List, Optional


class VoiceCommand:
    """Represents a parsed voice command."""

    def __init__(self, action: str, params: Dict[str, Any] = None):
        self.action = action
        self.params = params or {}
        self.endpoint: Optional[str] = None
        self.method: str = "GET"
        self.path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "params": self.params,
            "endpoint": self.endpoint,
            "method": self.method,
            "path": self.path,
        }


class VoiceProcessor:
    """
    Process voice commands from Twilio voice calls and map to DataPulse API actions.

    Supports 15+ natural language commands with fuzzy intent matching.
    """

    # Intent patterns — ordered by priority (first match wins)
    INTENT_PATTERNS = [
        # Status queries
        {
            "patterns": [r"status", r"how.*(is|are|does).*(look|going|health)", r"what.*happen", r"report"],
            "action": "get_impact",
            "endpoint": "GET /api/impact",
            "method": "GET",
            "path": "/api/impact",
        },
        # Incident approval
        {
            "patterns": [
                r"approve.*(incident|fix|remediation|action)",
                r"yes.*(do|proceed|go|ahead)",
                r"(okay|ok)\s*(approve|execute|run)",
            ],
            "action": "approve_incident",
            "endpoint": "POST /api/incidents/{incident_id}/approve",
            "method": "POST",
        },
        # Start patrol
        {
            "patterns": [
                r"start.*(patrol|monitoring|watch)",
                r"(begin|activate|kick.?off).*(patrol|monitor)",
            ],
            "action": "start_patrol",
            "endpoint": "POST /api/patrol/start",
            "method": "POST",
            "path": "/api/patrol/start",
        },
        # Stop patrol
        {
            "patterns": [
                r"stop.*(patrol|monitoring|watch)",
                r"(halt|cease|deactivate).*(patrol|monitor)",
            ],
            "action": "stop_patrol",
            "endpoint": "POST /api/patrol/stop",
            "method": "POST",
            "path": "/api/patrol/stop",
        },
        # Start war room
        {
            "patterns": [
                r"(start|open|activate).*(war.?room|warroom)",
                r"(call|assemble).*(team|agents)",
                r"(launch|kick.?off).*(incident|response)",
            ],
            "action": "start_war_room",
            "endpoint": "POST /api/warroom/start",
            "method": "POST",
        },
        # Check war room status
        {
            "patterns": [
                r"(war.?room|warroom).*(status|update|progress)",
                r"(check|get).*(war.?room|team).*status",
            ],
            "action": "get_war_room_status",
            "endpoint": "GET /api/warroom/status",
            "method": "GET",
            "path": "/api/warroom/status",
        },
        # Detect incidents / problems
        {
            "patterns": [
                r"(run|check|scan).*incident",
                r"(detect|find|search).*(issue|problem|anomaly)",
                r"any.*(incident|alert|issue).*right.?now",
                r"do.*(you|we).*(see|have|spot|notice).*(problem|issue|trouble|error|bug)",
                r"(are|is).*(any|some).*(problem|issue|error|bug|alert)",
            ],
            "action": "detect_incidents",
            "endpoint": "POST /api/incidents/detect",
            "method": "POST",
            "path": "/api/incidents/detect",
        },
        # List incidents
        {
            "patterns": [
                r"(list|show|get).*(incident|incidents)",
                r"what.*(incident|alert).*(have|active|open)",
            ],
            "action": "list_incidents",
            "endpoint": "GET /api/incidents",
            "method": "GET",
            "path": "/api/incidents",
        },
        # Health overview (detailed)
        {
            "patterns": [
                r"health",
                r"(check|get).*(cluster|indices|health)",
                r"overview",
            ],
            "action": "get_health",
            "endpoint": "GET /api/health/overview",
            "method": "GET",
            "path": "/api/health/overview",
        },
        # Mapping check
        {
            "patterns": [
                r"(check|get).*mapping",
                r"(mapping|schema).*(status|issue)",
                r"(field|column).*(count|issue)",
            ],
            "action": "check_mappings",
            "endpoint": "GET /api/health/mappings",
            "method": "GET",
            "path": "/api/health/mappings",
        },
        # Error analysis
        {
            "patterns": [
                r"(error|fail|exception).*(trend|count|analysis)",
                r"show.*error",
                r"(what|how).*many.*(error|fail)",
            ],
            "action": "get_error_analysis",
            "endpoint": "GET /api/health/errors",
            "method": "GET",
            "path": "/api/health/errors",
        },
        # Shard status
        {
            "patterns": [
                r"(shard|allocation).*(status|issue|check)",
                r"(check|get).*shard",
            ],
            "action": "get_shard_status",
            "endpoint": "GET /api/health/shards",
            "method": "GET",
            "path": "/api/health/shards",
        },
        # Ingestion rate
        {
            "patterns": [
                r"(ingestion|indexing).*rate",
                r"(data|document).*(flow|rate|speed)",
                r"how.*much.*(data|indexing)",
            ],
            "action": "get_ingestion_rate",
            "endpoint": "GET /api/health/ingestion",
            "method": "GET",
            "path": "/api/health/ingestion",
        },
        # Pause (for Twilio gather)
        {
            "patterns": [
                r"wait",
                r"hold.?on",
                r"pause",
            ],
            "action": "pause",
            "endpoint": None,
            "method": "NONE",
            "path": None,
        },
        # Goodbye
        {
            "patterns": [
                r"(bye|good.?bye|hang|disconnect|end)",
                r"(stop|exit|quit)",
            ],
            "action": "goodbye",
            "endpoint": None,
            "method": "NONE",
            "path": None,
        },
    ]

    def __init__(self):
        self.compiled_patterns = []
        for intent in self.INTENT_PATTERNS:
            compiled = [re.compile(p, re.IGNORECASE) for p in intent["patterns"]]
            self.compiled_patterns.append({
                "patterns": compiled,
                "action": intent["action"],
                "endpoint": intent.get("endpoint"),
                "method": intent.get("method", "GET"),
                "path": intent.get("path"),
            })

    def process_command(self, command_text: str) -> Dict[str, Any]:
        """
        Parse voice command and return mapped API action.

        Args:
            command_text: Transcribed voice command text

        Returns:
            Dict with action, endpoint, method, path, and any required parameters
        """
        command_text = command_text.lower().strip()

        if not command_text:
            return {
                "action": "unknown",
                "error": "Empty command",
                "endpoint": None,
            }

        # Try exact match first for common commands
        exact_commands = {
            "status": self._create_result("get_impact", "GET", "/api/impact"),
            "help": self._create_result("help", None, None),
            "goodbye": self._create_result("goodbye", None, None),
            "hello": self._create_result("greeting", None, None),
            "hi": self._create_result("greeting", None, None),
        }

        if command_text in exact_commands:
            return exact_commands[command_text]

        # Fuzzy pattern matching
        for intent in self.compiled_patterns:
            for pattern in intent["patterns"]:
                match = pattern.search(command_text)
                if match:
                    result = {
                        "action": intent["action"],
                        "method": intent["method"],
                        "endpoint": intent.get("endpoint"),
                        "path": intent.get("path"),
                    }

                    # Extract dynamic parameters
                    params = self._extract_params(intent["action"], command_text, match)
                    if params:
                        result["params"] = params

                    return result

        return {
            "action": "unknown",
            "error": f"Unknown command: {command_text}",
            "endpoint": None,
            "did_you_mean": self._suggest_similar(command_text),
        }

    def process_commands_batch(self, commands: List[str]) -> List[Dict[str, Any]]:
        """Process multiple voice commands at once."""
        return [self.process_command(cmd) for cmd in commands]

    def _create_result(self, action: str, method: str, path: str) -> Dict[str, Any]:
        return {
            "action": action,
            "method": method,
            "path": path,
            "endpoint": f"{method} {path}" if method and path else None,
        }

    def _extract_params(self, action: str, text: str, match) -> Dict[str, Any]:
        """Extract dynamic parameters from command text."""
        params = {}

        if action == "approve_incident":
            id_match = re.search(r"(?:incident|inc)\s*#?(\w[\w-]*)", text)
            if id_match:
                params["incident_id"] = id_match.group(1)
            else:
                hex_match = re.search(r"(?:inc-|INC-)?([a-fA-F0-9]{8})", text)
                if hex_match:
                    params["incident_id"] = f"INC-{hex_match.group(1).upper()}"

        elif action == "start_war_room":
            id_match = re.search(r"(?:incident|inc)\s*#?(\w[\w-]*)", text)
            if id_match:
                params["incident_id"] = id_match.group(1)

        elif action == "get_error_analysis":
            time_match = re.search(r"(?:last|past)\s+(\d+)\s*(hour|minute|hr|min)", text)
            if time_match:
                params["hours"] = int(time_match.group(1))

        return params

    def _suggest_similar(self, command: str) -> Optional[str]:
        """Suggest a similar known command using simple Levenshtein-like matching."""
        known = [
            "status", "start patrol", "stop patrol", "check health", "approve incident",
            "detect incidents", "list incidents", "start war room", "check shards",
            "check errors", "check mappings", "ingestion rate", "goodbye",
        ]

        best_match = None
        best_score = 0
        for known_cmd in known:
            score = self._similarity(command, known_cmd)
            if score > best_score:
                best_score = score
                best_match = known_cmd

        if best_match and best_score > 0.5:
            return f"Did you mean '{best_match}'?"
        return None

    @staticmethod
    def _similarity(a: str, b: str) -> float:
        """Simple Jaccard-like similarity between two strings."""
        a_words = set(a.lower().split())
        b_words = set(b.lower().split())
        if not a_words or not b_words:
            return 0.0
        intersection = a_words & b_words
        union = a_words | b_words
        return len(intersection) / len(union)


def process_twilio_command(command_text: str) -> Dict[str, Any]:
    """
    Convenience function for Twilio webhook integration.
    Maps voice command to API action.
    """
    processor = VoiceProcessor()
    result = processor.process_command(command_text)
    result["twilio_compatible"] = True
    return result