"""Autonomous incident response engine for DataPulse.

Handles multi-step incident workflows:
1. DETECT: Proactive health checks find anomalies
2. INVESTIGATE: Agent calls multiple tools to understand the problem
3. DIAGNOSE: Synthesize findings into a root cause
4. PROPOSE: Generate a remediation plan with specific actions
5. EXECUTE: Carry out approved remediation actions
"""

import httpx
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from enum import Enum

from app.services.mcp_client import ElasticMCPClient
from app.services.google_chat import GoogleChatClient

logger = logging.getLogger(__name__)


class IncidentSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IncidentStatus(str, Enum):
    DETECTED = "detected"
    INVESTIGATING = "investigating"
    DIAGNOSED = "diagnosed"
    REMEDIATION_PROPOSED = "remediation_proposed"
    REMEDIATION_APPROVED = "remediation_approved"
    REMEDIATING = "remediating"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


class Incident:
    """Represents an infrastructure incident with full lifecycle."""

    def __init__(
        self,
        title: str,
        severity: IncidentSeverity,
        index_name: Optional[str] = None,
        detection_details: Optional[Dict] = None,
    ):
        self.id = f"INC-{uuid.uuid4().hex[:8].upper()}"
        self.title = title
        self.severity = severity
        self.index_name = index_name
        self.status = IncidentStatus.DETECTED
        self.detection_details = detection_details or {}
        self.investigation_steps: List[Dict[str, Any]] = []
        self.diagnosis: Optional[Dict[str, Any]] = None
        self.remediation_actions: List[Dict[str, Any]] = []
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = self.created_at

    def add_investigation_step(self, tool: str, args: Dict, result_summary: str):
        self.investigation_steps.append({
            "step": len(self.investigation_steps) + 1,
            "tool": tool,
            "args": args,
            "result_summary": result_summary,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def set_diagnosis(self, root_cause: str, impact: str, confidence: float, details: Dict = None):
        self.diagnosis = {
            "root_cause": root_cause,
            "impact": impact,
            "confidence": confidence,
            "details": details or {},
        }
        self.status = IncidentStatus.DIAGNOSED
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def add_remediation_action(self, action_type: str, description: str, risk_level: str = "low", estimated_impact: str = "", **kwargs):
        action = {
            "action_id": f"ACT-{uuid.uuid4().hex[:6].upper()}",
            "action_type": action_type,
            "description": description,
            "risk_level": risk_level,
            "estimated_impact": estimated_impact,
            "status": "proposed",
            "index": self.index_name,
            **kwargs,
        }
        self.remediation_actions.append(action)
        self.status = IncidentStatus.REMEDIATION_PROPOSED
        self.updated_at = datetime.now(timezone.utc).isoformat()
        return action

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "severity": self.severity.value,
            "index_name": self.index_name,
            "status": self.status.value,
            "detection_details": self.detection_details,
            "investigation_steps": self.investigation_steps,
            "diagnosis": self.diagnosis,
            "remediation_actions": self.remediation_actions,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class IncidentResponseEngine:
    """Autonomous incident response engine.

    Orchestrates multi-step investigation and remediation workflows.
    Each workflow is a sequence of tool calls that build on each other.
    """

    def __init__(self, mcp_client: ElasticMCPClient):
        self.mcp_client = mcp_client
        self.active_incidents: Dict[str, Incident] = {}
        self.chat_client = GoogleChatClient()

    async def detect_incidents(self) -> List[Incident]:
        """Run proactive detection across all indices."""
        incidents = []

        # Step 1: Get cluster overview
        indices_data = await self.mcp_client.list_indices()
        indices = indices_data.get("indices", [])

        for idx in indices:
            name = idx.get("name", "")
            health = idx.get("health", "unknown")
            if health == "red":
                incident = Incident(
                    title=f"Index {name} is RED — shards unassigned",
                    severity=IncidentSeverity.CRITICAL,
                    index_name=name,
                    detection_details={"health": health, "docs": idx.get("docs", 0)},
                )
                incidents.append(incident)
                self.active_incidents[incident.id] = incident
                # Send Google Chat alert
                await self._send_chat_alert(incident)
            elif health == "yellow":
                incident = Incident(
                    title=f"Index {name} is YELLOW — replica shards not allocated",
                    severity=IncidentSeverity.HIGH,
                    index_name=name,
                    detection_details={"health": health, "docs": idx.get("docs", 0)},
                )
                incidents.append(incident)
                self.active_incidents[incident.id] = incident
                await self._send_chat_alert(incident)

        # Step 2: Check for error spikes in logs
        try:
            esql_result = await self.mcp_client.esql(
                'FROM logs-* | STATS error_count = COUNT(*) WHERE level = "error" BY service | SORT error_count DESC | LIMIT 5'
            )
            values = esql_result.get("values", [])
            for row in values:
                service = row[0] if len(row) > 0 else "unknown"
                error_count = row[1] if len(row) > 1 else 0
                if isinstance(error_count, (int, float)) and error_count > 100:
                    incident = Incident(
                        title=f"Error spike in {service}: {int(error_count)} errors detected",
                        severity=IncidentSeverity.HIGH,
                        detection_details={"service": service, "error_count": int(error_count)},
                    )
                    incidents.append(incident)
                    self.active_incidents[incident.id] = incident
        except Exception as e:
            logger.warning(f"ES|QL error spike detection failed: {e}")

        # Step 3: Check for mapping explosion
        for idx in indices:
            name = idx.get("name", "")
            try:
                mappings = await self.mcp_client.get_mappings(name)
                props = mappings.get(name, mappings).get("mappings", {}).get("properties", {})
                field_count = len(props)
                if field_count > 100:
                    incident = Incident(
                        title=f"Mapping explosion risk in {name}: {field_count} fields",
                        severity=IncidentSeverity.MEDIUM,
                        index_name=name,
                        detection_details={"field_count": field_count, "dynamic": True},
                    )
                    incidents.append(incident)
                    self.active_incidents[incident.id] = incident
            except Exception:
                pass

        return incidents

    async def investigate(self, incident: Incident) -> Incident:
        """Deep-dive investigation of an incident using multi-step tool calls."""
        incident.status = IncidentStatus.INVESTIGATING
        incident.updated_at = datetime.now(timezone.utc).isoformat()

        if incident.index_name:
            # Step 1: Get index details
            try:
                indices_data = await self.mcp_client.list_indices()
                for idx in indices_data.get("indices", []):
                    if idx.get("name") == incident.index_name:
                        incident.add_investigation_step(
                            "list_indices",
                            {},
                            f"Index {incident.index_name}: health={idx.get('health')}, docs={idx.get('docs')}, size={idx.get('size')}"
                        )
                        break
            except Exception as e:
                incident.add_investigation_step("list_indices", {}, f"Failed: {e}")

            # Step 2: Check shards
            try:
                shards_data = await self.mcp_client.get_shards(index=incident.index_name)
                unassigned = [s for s in shards_data.get("shards", []) if s.get("state") == "UNASSIGNED"]
                incident.add_investigation_step(
                    "get_shards",
                    {"index": incident.index_name},
                    f"{len(shards_data.get('shards', []))} total shards, {len(unassigned)} unassigned"
                )
            except Exception as e:
                incident.add_investigation_step("get_shards", {"index": incident.index_name}, f"Failed: {e}")

            # Step 3: Check mappings if relevant
            if "mapping" in incident.title.lower() or "field" in incident.title.lower():
                try:
                    mappings = await self.mcp_client.get_mappings(incident.index_name)
                    props = mappings.get(incident.index_name, mappings).get("mappings", {}).get("properties", {})
                    incident.add_investigation_step(
                        "get_mappings",
                        {"index": incident.index_name},
                        f"{len(props)} fields in mapping"
                    )
                except Exception as e:
                    incident.add_investigation_step("get_mappings", {"index": incident.index_name}, f"Failed: {e}")

        # Step 4: For error spikes, search for error patterns
        if "error" in incident.title.lower() or "spike" in incident.title.lower():
            service = incident.detection_details.get("service", "")
            try:
                search_result = await self.mcp_client.search(
                    index="logs-*",
                    body={"query": {"bool": {"must": [{"match": {"level": "error"}}]}}, "size": 5, "sort": [{"@timestamp": {"order": "desc"}}]}
                )
                hits = search_result.get("hits", {}).get("hits", [])
                incident.add_investigation_step(
                    "search",
                    {"index": "logs-*", "body": {"query": {"match": {"level": "error"}}}},
                    f"Found {len(hits)} recent error logs"
                )
            except Exception as e:
                incident.add_investigation_step("search", {"index": "logs-*"}, f"Failed: {e}")

        return incident

    async def diagnose(self, incident: Incident) -> Incident:
        """Generate diagnosis from investigation results."""
        # Map common patterns to diagnoses
        title_lower = incident.title.lower()

        if "red" in title_lower and "shard" in title_lower:
            incident.set_diagnosis(
                root_cause="Primary shard unassigned — likely node failure or disk full",
                impact="Data in this index is partially or fully unavailable. Search queries will return incomplete results.",
                confidence=0.85,
                details={"affected_shards": [s.get("shard") for s in incident.investigation_steps if s.get("tool") == "get_shards"]},
            )
            incident.add_remediation_action(
                action_type="allocate_shard",
                description=f"Reroute unassigned shards for {incident.index_name}",
                risk_level="medium",
                estimated_impact="Restores full data availability within minutes",
            )
        elif "yellow" in title_lower:
            incident.set_diagnosis(
                root_cause="Replica shard not allocated — single node cluster or resource constraints",
                impact="No data redundancy. If the primary shard's node fails, data will be unavailable.",
                confidence=0.9,
            )
            incident.add_remediation_action(
                action_type="update_settings",
                description=f"Reduce replica count to 0 for {incident.index_name} (single-node workaround)",
                risk_level="low",
                estimated_impact="Eliminates yellow status, removes redundancy warning",
            )
        elif "mapping explosion" in title_lower:
            incident.set_diagnosis(
                root_cause="Dynamic mapping enabled with uncontrolled field creation — new fields auto-created from incoming data",
                impact="Mapping explosion degrades search performance and increases memory usage. Index may become unstable.",
                confidence=0.95,
            )
            incident.add_remediation_action(
                action_type="update_settings",
                description=f"Set dynamic=false on {incident.index_name} to prevent new field creation",
                risk_level="medium",
                estimated_impact="Stops mapping growth immediately. New fields with unknown names will be ignored.",
            )
            incident.add_remediation_action(
                action_type="reindex",
                description=f"Reindex {incident.index_name} with strict mapping to remove unused fields",
                risk_level="high",
                estimated_impact="Clean mapping but requires reindexing — brief search downtime possible",
            )
        elif "error spike" in title_lower or "error" in title_lower:
            service = incident.detection_details.get("service", "unknown")
            incident.set_diagnosis(
                root_cause=f"Elevated error rate in {service} — likely downstream dependency failure or overload",
                impact=f"Customers experiencing failures in {service}. Estimated revenue at risk: ${incident.detection_details.get('error_count', 0) * 15}/hour",
                confidence=0.75,
            )
            incident.add_remediation_action(
                action_type="investigate_logs",
                description=f"Deep search of {service} error logs for common error patterns",
                risk_level="low",
                estimated_impact="Provides detailed error breakdown for targeted fix",
            )
        else:
            incident.set_diagnosis(
                root_cause="Under investigation — multi-step analysis required",
                impact="Assessing business impact...",
                confidence=0.5,
            )

        return incident

    async def execute_remediation(self, incident: Incident, action_id: str) -> Dict[str, Any]:
        """Execute an approved remediation action."""
        action = None
        for a in incident.remediation_actions:
            if a["action_id"] == action_id:
                action = a
                break

        if not action:
            return {"error": f"Action {action_id} not found"}

        action["status"] = "executing"
        incident.status = IncidentStatus.REMEDIATING
        result = {"action_id": action_id, "status": "executed", "details": ""}

        try:
            if action["action_type"] == "update_settings":
                # For mapping explosion: set dynamic=false
                if "dynamic" in action.get("description", "").lower():
                    index_name = action.get("index", incident.index_name)
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        resp = await client.put(
                            f"{self.mcp_client.es_url}/{index_name}/_mapping",
                            json={"dynamic": False},
                            headers={"Content-Type": "application/json"},
                        )
                        result["details"] = f"Updated mapping for {index_name}: {resp.status_code}"
                elif "replica" in action.get("description", "").lower():
                    index_name = action.get("index", incident.index_name)
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        resp = await client.put(
                            f"{self.mcp_client.es_url}/{index_name}/_settings",
                            json={"index": {"number_of_replicas": 0}},
                            headers={"Content-Type": "application/json"},
                        )
                        result["details"] = f"Updated replica settings for {index_name}: {resp.status_code}"
                else:
                    result["details"] = f"Update settings action simulated (no matching pattern)"

            elif action["action_type"] == "allocate_shard":
                # Try to allocate unassigned shards
                index_name = action.get("index", incident.index_name)
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        f"{self.mcp_client.es_url}/_cluster/reroute",
                        json={"commands": [{"allocate_stale_primary": {"index": index_name, "shard": 0, "node": "node-1"}}]},
                        headers={"Content-Type": "application/json"},
                    )
                    result["details"] = f"Shard reroute attempted: {resp.status_code}"

            elif action["action_type"] == "reindex":
                index_name = action.get("index", incident.index_name)
                new_index = f"{index_name}-fixed"
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        f"{self.mcp_client.es_url}/_reindex",
                        json={"source": {"index": index_name}, "dest": {"index": new_index}},
                        headers={"Content-Type": "application/json"},
                    )
                    result["details"] = f"Reindex to {new_index}: {resp.status_code}"

            elif action["action_type"] == "investigate_logs":
                # Search for error details
                search_result = await self.mcp_client.search(
                    index="logs-*",
                    body={"query": {"match": {"level": "error"}}, "size": 10, "sort": [{"@timestamp": {"order": "desc"}}]},
                )
                hits = search_result.get("hits", {}).get("hits", [])
                result["details"] = f"Found {len(hits)} error entries. Top errors: {json.dumps([h.get('_source', {}).get('message', '')[:100] for h in hits[:3]])}"
            else:
                result["details"] = f"Action type '{action['action_type']}' execution simulated (no ES write access in demo mode)"

            action["status"] = "executed"
            incident.status = IncidentStatus.RESOLVED
            incident.updated_at = datetime.now(timezone.utc).isoformat()

        except Exception as e:
            action["status"] = "failed"
            result["status"] = "failed"
            result["details"] = str(e)
            logger.error(f"Remediation execution failed: {e}")

        return result

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        return self.active_incidents.get(incident_id)

    async def _send_chat_alert(self, incident: Incident):
        """Send incident alert to Google Chat."""
        try:
            if self.chat_client.space_id:
                card = await self.chat_client.create_incident_card(incident)
                await self.chat_client.send_card(self.chat_client.space_id, card)
                logger.info(f"Sent Google Chat alert for incident {incident.id}")
        except Exception as e:
            logger.error(f"Failed to send Google Chat alert for {incident.id}: {e}")

    def list_incidents(self) -> List[Dict[str, Any]]:
        return [inc.to_dict() for inc in self.active_incidents.values()]

    def approve_action(self, incident_id: str, action_id: str) -> bool:
        incident = self.get_incident(incident_id)
        if not incident:
            return False
        for action in incident.remediation_actions:
            if action["action_id"] == action_id:
                action["status"] = "approved"
                incident.status = IncidentStatus.REMEDIATION_APPROVED
                return True
        return False
