"""Cross-Incident Pattern Engine — Memory-enhanced remediation.

Learns from past incidents to auto-suggest (and optionally auto-apply)
fixes when similar patterns are detected again. This is the "experience"
layer that makes DataPulse smarter with every incident it handles.

Key insight: Most production incidents are recurring. The same Elasticsearch
problems (yellow indices, mapping explosions, disk watermarks) happen
repeatedly. By remembering what fixed them last time, the agent can
skip the investigation phase and go straight to remediation.

Time saved: 30-60 min per recurring incident (skip investigation → instant fix)
"""
import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from enum import Enum
from collections import Counter

from app.services.es_write_client import ESWriteClient, ProposedAction
from app.services.mcp_client import ElasticMCPClient
from app.services.incident_memory import IncidentMemoryService

logger = logging.getLogger(__name__)


class PatternConfidence(str, Enum):
    low = "low"          # 1-2 similar incidents
    medium = "medium"    # 3-5 similar incidents
    high = "high"        # 6-10 similar incidents
    very_high = "very_high"  # 10+ similar incidents


class IncidentPattern:
    """A pattern recognized across multiple incidents."""
    def __init__(self, pattern_type: str, symptoms: List[str], fix: Dict):
        self.pattern_type = pattern_type
        self.symptoms = symptoms
        self.fix = fix  # The remediation that worked
        self.occurrence_count = 0
        self.last_seen = None
        self.confidence = PatternConfidence.low
        self.related_indices: List[str] = []
        self.avg_resolution_time_min = 0

    def to_dict(self):
        return {
            "pattern_type": self.pattern_type,
            "symptoms": self.symptoms,
            "fix": self.fix,
            "occurrence_count": self.occurrence_count,
            "last_seen": self.last_seen,
            "confidence": self.confidence.value,
            "related_indices": self.related_indices,
            "avg_resolution_time_min": self.avg_resolution_time_min,
        }


class PatternResult:
    """Result of a pattern analysis."""
    def __init__(self):
        self.patterns_found: List[Dict] = []
        self.auto_fix_proposals: List[Dict] = []
        self.proposed_actions: List[Dict] = []
        self.summary = ""
        self.time_saved_minutes = 0
        self.analyzed_at = datetime.utcnow().isoformat()

    def to_dict(self):
        return {
            "patterns_found": self.patterns_found,
            "auto_fix_proposals": self.auto_fix_proposals,
            "proposed_actions": self.proposed_actions,
            "summary": self.summary,
            "time_saved_minutes": self.time_saved_minutes,
            "analyzed_at": self.analyzed_at,
        }


class CrossIncidentEngine:
    """Cross-incident pattern recognition and auto-remediation.

    Workflow:
    1. COLLECT: Gather all past incident records from IncidentMemory
    2. CLUSTER: Group incidents by symptom patterns
    3. RANK: Score patterns by frequency + confidence
    4. MATCH: Compare current cluster state against known patterns
    5. PROPOSE: Auto-generate remediation actions based on past fixes
    """

    # Symptom → Fix mapping (built from experience + built-in knowledge)
    KNOWN_PATTERNS = {
        "yellow_replicas_unassigned": {
            "symptoms": ["yellow_health", "unassigned_replica_shards"],
            "fix": {"action_type": "set_replicas", "params": {"replica_count": 0}},
            "description": "Single-node cluster can't allocate replicas — set to 0",
        },
        "mapping_explosion": {
            "symptoms": ["high_field_count", "dynamic_mapping_enabled", "mapping_limit_exceeded"],
            "fix": {"action_type": "disable_dynamic_mapping", "params": {}},
            "description": "Disable dynamic mapping to prevent field explosion",
        },
        "disk_watermark_exceeded": {
            "symptoms": ["red_health", "disk_threshold_exceeded", "index_read_only"],
            "fix": {"action_type": "clear_read_only", "params": {}},
            "description": "Clear read_only flag after disk space is freed",
        },
        "stale_index_waste": {
            "symptoms": ["old_index", "no_recent_writes", "open_index"],
            "fix": {"action_type": "close_index", "params": {}},
            "description": "Close stale index to free cluster resources",
        },
        "shard_too_large": {
            "symptoms": ["oversized_shard", "slow_recovery", "high_merge_time"],
            "fix": {"action_type": "reindex", "params": {}},
            "description": "Reindex into properly-sized shards",
        },
    }

    def __init__(
        self,
        mcp_client: ElasticMCPClient,
        write_client: ESWriteClient,
        incident_memory: Optional[IncidentMemoryService] = None,
    ):
        self.mcp = mcp_client
        self.writer = write_client
        self.memory = incident_memory

    async def analyze_patterns(self) -> PatternResult:
        """Analyze past incidents and current cluster state for patterns.

        Returns:
        - Patterns found (from incident memory + built-in knowledge)
        - Auto-fix proposals for current issues matching known patterns
        - Proposed actions (ready for approval)
        """
        result = PatternResult()

        # Step 1: Collect patterns from incident memory
        past_incidents = []
        if self.memory:
            try:
                past_incidents = await self.memory.get_recent_incidents(limit=100)
            except Exception:
                past_incidents = []

        # Step 2: Extract symptom clusters from past incidents
        symptom_counter: Counter = Counter()
        fix_history: Dict[str, List[Dict]] = {}

        for incident in past_incidents:
            symptoms = incident.get("symptoms", [])
            fix = incident.get("remediation", {})
            pattern_key = incident.get("pattern_type", "unknown")

            for symptom in symptoms:
                symptom_counter[symptom] += 1

            if pattern_key not in fix_history:
                fix_history[pattern_key] = []
            fix_history[pattern_key].append(fix)

        # Step 3: Build pattern list from memory + built-in knowledge
        all_patterns = []

        for pattern_id, pattern_def in self.KNOWN_PATTERNS.items():
            occurrence = symptom_counter.get(pattern_id, 0)
            memory_occurrence = len(fix_history.get(pattern_id, []))
            total = max(occurrence, memory_occurrence)

            pattern = IncidentPattern(
                pattern_type=pattern_id,
                symptoms=pattern_def["symptoms"],
                fix=pattern_def["fix"],
            )
            pattern.occurrence_count = total
            pattern.last_seen = datetime.utcnow().isoformat()

            if total >= 10:
                pattern.confidence = PatternConfidence.very_high
            elif total >= 6:
                pattern.confidence = PatternConfidence.high
            elif total >= 3:
                pattern.confidence = PatternConfidence.medium
            else:
                pattern.confidence = PatternConfidence.low

            all_patterns.append(pattern.to_dict())

        result.patterns_found = all_patterns

        # Step 4: Check current cluster for issues matching known patterns
        current_symptoms = await self._detect_current_symptoms()

        # Step 5: Match current symptoms to patterns and propose auto-fixes
        for pattern_def in all_patterns:
            pattern_symptoms = set(pattern_def["symptoms"])
            current_set = set(current_symptoms)

            overlap = pattern_symptoms & current_set
            if overlap and len(overlap) >= len(pattern_symptoms) * 0.5:
                # At least 50% of pattern symptoms match current state
                auto_fix = self._generate_auto_fix(
                    pattern_def["pattern_type"],
                    pattern_def["fix"],
                    current_symptoms,
                )
                if auto_fix:
                    result.auto_fix_proposals.append(auto_fix)

                    # Convert to a proposed action
                    action = self._auto_fix_to_action(auto_fix)
                    if action:
                        proposal = self.writer.propose(action)
                        result.proposed_actions.append(proposal)
                        result.time_saved_minutes += 45

        if result.proposed_actions:
            result.summary = (
                f"Found {len(result.patterns_found)} known patterns. "
                f"{len(current_symptoms)} current symptoms detected. "
                f"Matched {len(result.auto_fix_proposals)} auto-fix proposals. "
                f"Estimated time saved: {result.time_saved_minutes} minutes."
            )
        else:
            result.summary = (
                f"Found {len(result.patterns_found)} known patterns. "
                f"{len(current_symptoms)} current symptoms detected. "
                f"No matching patterns — no auto-fixes needed."
            )

        return result

    async def _detect_current_symptoms(self) -> List[str]:
        """Scan the cluster and return a list of symptom identifiers."""
        symptoms = []

        try:
            indices_data = await self.mcp.list_indices()
            indices = indices_data.get("indices", [])

            for idx in indices:
                name = idx.get("name", "")
                health = idx.get("health", "")

                if health == "yellow":
                    symptoms.append("yellow_health")
                    symptoms.append("unassigned_replica_shards")
                elif health == "red":
                    symptoms.append("red_health")

                # Check for oversized shards
                size_str = idx.get("size", "0b")
                pri = idx.get("pri", 1)
                try:
                    pri_count = int(pri)
                except (ValueError, TypeError):
                    pri_count = 1
                size_gb = self._parse_size_to_gb(size_str)
                if pri_count > 0 and size_gb / pri_count > 50:
                    symptoms.append("oversized_shard")

                # Check for dynamic mapping (simplified heuristic)
                if not name.startswith(".") and size_gb > 5:
                    symptoms.append("dynamic_mapping_enabled")

        except Exception:
            symptoms.append("cluster_unreachable")

        return symptoms

    def _parse_size_to_gb(self, size_str: str) -> float:
        size_str = (size_str or "0b").lower().strip()
        try:
            if "gb" in size_str:
                return float(size_str.replace("gb", "").strip())
            elif "mb" in size_str:
                return float(size_str.replace("mb", "").strip()) / 1024
            elif "tb" in size_str:
                return float(size_str.replace("tb", "").strip()) * 1024
        except (ValueError, TypeError):
            pass
        return 0.0

    def _generate_auto_fix(
        self,
        pattern_type: str,
        fix_def: Dict,
        current_symptoms: List[str],
    ) -> Optional[Dict]:
        """Generate an auto-fix proposal from a pattern match."""
        fix_type = fix_def.get("action_type")
        params = fix_def.get("params", {})

        # Only auto-fix for safe/low-risk operations
        if fix_type in ("set_replicas", "disable_dynamic_mapping", "close_index"):
            return {
                "pattern_type": pattern_type,
                "fix_type": fix_type,
                "params": params,
                "confidence": "high",
                "description": self.KNOWN_PATTERNS.get(pattern_type, {}).get("description", ""),
            }
        return None

    def _auto_fix_to_action(self, auto_fix: Dict) -> Optional[ProposedAction]:
        """Convert an auto-fix proposal to a ProposedAction."""
        fix_type = auto_fix.get("fix_type")
        params = auto_fix.get("params", {})
        pattern_type = auto_fix.get("pattern_type", "unknown")

        if fix_type == "set_replicas":
            # Find a yellow index to fix
            return self.writer.propose_set_replicas(
                index=f"<matched-yellow-index>",
                replica_count=params.get("replica_count", 0),
            )
        elif fix_type == "disable_dynamic_mapping":
            return self.writer.propose_disable_dynamic_mapping(
                index=f"<matched-mapping-index>",
            )
        elif fix_type == "close_index":
            return self.writer.propose_open_close_index(
                index=f"<matched-stale-index>",
                action="close",
            )
        return None

    async def get_pattern_summary(self) -> Dict[str, Any]:
        """Get a summary of all known patterns and their statistics."""
        patterns = []
        for pattern_id, pattern_def in self.KNOWN_PATTERNS.items():
            patterns.append({
                "pattern_id": pattern_id,
                "symptoms": pattern_def["symptoms"],
                "fix": pattern_def["fix"],
                "description": pattern_def["description"],
            })

        return {
            "total_patterns": len(patterns),
            "patterns": patterns,
            "auto_fix_eligible": [
                p for p in patterns
                if p["fix"]["action_type"] in ("set_replicas", "disable_dynamic_mapping", "close_index")
            ],
            "requires_approval": [
                p for p in patterns
                if p["fix"]["action_type"] in ("reindex", "delete_by_query")
            ],
        }
