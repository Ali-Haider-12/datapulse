"""ES Write Client — Action-oriented Elasticsearch operations with approval gates.

This is what makes DataPulse an AGENT, not a chatbot.
All write operations require explicit approval before execution.
"""
import httpx
import json
import logging
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class ApprovalStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    executed = "executed"
    failed = "failed"
    rolled_back = "rolled_back"


class ProposedAction:
    """A proposed write action that requires human approval."""

    def __init__(
        self,
        action_type: str,
        description: str,
        es_method: str,
        es_path: str,
        es_body: Optional[Dict] = None,
        risk_level: str = "medium",
        rollback_action: Optional[Dict] = None,
        index: Optional[str] = None,
    ):
        self.action_id = f"ACT-{uuid.uuid4().hex[:8].upper()}"
        self.action_type = action_type
        self.description = description
        self.es_method = es_method  # PUT, POST, DELETE
        self.es_path = es_path
        self.es_body = es_body
        self.risk_level = risk_level  # safe, low, medium, high
        self.status = ApprovalStatus.pending
        self.result = None
        self.error = None
        self.rollback_action = rollback_action
        self.index = index
        self.created_at = datetime.utcnow().isoformat()
        self.executed_at = None

    def to_dict(self):
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "description": self.description,
            "es_method": self.es_method,
            "es_path": self.es_path,
            "es_body": self.es_body,
            "risk_level": self.risk_level,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "has_rollback": self.rollback_action is not None,
            "index": self.index,
            "created_at": self.created_at,
            "executed_at": self.executed_at,
        }


class ESWriteClient:
    """Client for Elasticsearch WRITE operations with approval gates.

    Every write operation goes through:
    1. PROPOSE: Generate a ProposedAction with risk assessment
    2. APPROVE: Human reviews and approves (or rejects)
    3. EXECUTE: Carry out the ES API call
    4. VERIFY: Check the result
    5. ROLLBACK: If execution fails, attempt rollback
    """

    def __init__(
        self,
        es_url: str = "http://localhost:9200",
        api_key: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.es_url = es_url.rstrip("/")
        self.api_key = api_key
        self.username = username
        self.password = password
        self._pending_actions: Dict[str, ProposedAction] = {}
        self._action_history: List[Dict] = []

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"ApiKey {self.api_key}"
        return headers

    # ===== HEAL OPERATIONS (Propose → Approve → Execute) =====

    def propose_reroute_shards(
        self, index: str, node: Optional[str] = None
    ) -> ProposedAction:
        """Propose rerouting unassigned shards for an index."""
        body = {
            "commands": [
                {
                    "allocate_stale_primary": {
                        "index": index,
                        "shard": 0,
                        "node": node or "_primary",
                        "accept_data_loss": False,
                    }
                }
            ]
        }
        return ProposedAction(
            action_type="reroute_shards",
            description=f"Reroute unassigned shards for index '{index}' to restore data availability",
            es_method="POST",
            es_path="/_cluster/reroute",
            es_body=body,
            risk_level="medium",
            rollback_action=None,
            index=index,
        )

    def propose_set_replicas(
        self,
        index: str,
        replica_count: int,
        current_count: Optional[int] = None,
    ) -> ProposedAction:
        """Propose changing replica count for an index."""
        rollback_body = None
        if current_count is not None:
            rollback_body = {
                "es_method": "PUT",
                "es_path": f"/{index}/_settings",
                "es_body": {"index": {"number_of_replicas": current_count}},
            }
        return ProposedAction(
            action_type="set_replicas",
            description=f"Set replica count for '{index}' from {current_count or '?'} to {replica_count}",
            es_method="PUT",
            es_path=f"/{index}/_settings",
            es_body={"index": {"number_of_replicas": replica_count}},
            risk_level="low" if replica_count == 0 else "medium",
            rollback_action=rollback_body,
            index=index,
        )

    def propose_disable_dynamic_mapping(self, index: str) -> ProposedAction:
        """Propose disabling dynamic mapping to prevent mapping explosion."""
        return ProposedAction(
            action_type="disable_dynamic_mapping",
            description=f"Set dynamic=false on '{index}' to prevent mapping explosion",
            es_method="PUT",
            es_path=f"/{index}/_settings",
            es_body={"index": {"mapper": {"dynamic": False}}},
            risk_level="medium",
            rollback_action={
                "es_method": "PUT",
                "es_path": f"/{index}/_settings",
                "es_body": {"index": {"mapper": {"dynamic": True}}},
            },
            index=index,
        )

    def propose_set_refresh_interval(
        self,
        index: str,
        interval: str,
        current_interval: Optional[str] = None,
    ) -> ProposedAction:
        """Propose changing the refresh interval for performance tuning."""
        rollback_body = None
        if current_interval:
            rollback_body = {
                "es_method": "PUT",
                "es_path": f"/{index}/_settings",
                "es_body": {"index": {"refresh_interval": current_interval}},
            }
        return ProposedAction(
            action_type="set_refresh_interval",
            description=f"Change refresh interval for '{index}' to '{interval}'",
            es_method="PUT",
            es_path=f"/{index}/_settings",
            es_body={"index": {"refresh_interval": interval}},
            risk_level="low",
            rollback_action=rollback_body,
            index=index,
        )

    def propose_force_merge(
        self, index: str, max_segments: int = 1
    ) -> ProposedAction:
        """Propose force-merging an index to reduce segment count."""
        return ProposedAction(
            action_type="force_merge",
            description=f"Force merge '{index}' to {max_segments} segment(s) for better search performance",
            es_method="POST",
            es_path=f"/{index}/_forcemerge?max_num_segments={max_segments}",
            es_body=None,
            risk_level="low",
            index=index,
        )

    def propose_delete_index(self, index: str) -> ProposedAction:
        """Propose deleting an index — HIGH RISK."""
        return ProposedAction(
            action_type="delete_index",
            description=f"DELETE index '{index}' — THIS IS IRREVERSIBLE",
            es_method="DELETE",
            es_path=f"/{index}",
            es_body=None,
            risk_level="high",
            index=index,
        )

    def propose_open_close_index(
        self, index: str, action: str = "close"
    ) -> ProposedAction:
        """Propose opening or closing an index."""
        opposite = "open" if action == "close" else "close"
        return ProposedAction(
            action_type=f"{action}_index",
            description=f"{action.capitalize()} index '{index}'",
            es_method="POST",
            es_path=f"/{index}/_{action}",
            es_body=None,
            risk_level="low" if action == "open" else "medium",
            rollback_action={
                "es_method": "POST",
                "es_path": f"/{index}/_{opposite}",
                "es_body": None,
            },
            index=index,
        )

    def propose_delete_by_query(
        self, index: str, query: Dict
    ) -> ProposedAction:
        """Propose deleting documents matching a query — used for GDPR erasure etc."""
        return ProposedAction(
            action_type="delete_by_query",
            description=f"Delete documents matching query from '{index}'",
            es_method="POST",
            es_path=f"/{index}/_delete_by_query",
            es_body=query,
            risk_level="high",
            index=index,
        )

    def propose_reindex(
        self,
        source_index: str,
        dest_index: str,
        source_query: Optional[Dict] = None,
        pipeline: Optional[str] = None,
    ) -> ProposedAction:
        """Propose reindexing from source to destination."""
        body = {
            "source": {"index": source_index},
            "dest": {"index": dest_index},
        }
        if source_query:
            body["source"]["query"] = source_query
        if pipeline:
            body["dest"]["pipeline"] = pipeline
        return ProposedAction(
            action_type="reindex",
            description=f"Reindex from '{source_index}' to '{dest_index}'",
            es_method="POST",
            es_path="/_reindex",
            es_body=body,
            risk_level="medium",
            index=source_index,
        )

    def propose_create_ilm_policy(
        self, policy_name: str, policy_body: Dict
    ) -> ProposedAction:
        """Propose creating an Index Lifecycle Management policy."""
        return ProposedAction(
            action_type="create_ilm_policy",
            description=f"Create ILM policy '{policy_name}'",
            es_method="PUT",
            es_path=f"/_ilm/policy/{policy_name}",
            es_body=policy_body,
            risk_level="low",
            index=None,
        )

    def propose_apply_ilm_policy(
        self, index: str, policy_name: str
    ) -> ProposedAction:
        """Propose applying an ILM policy to an index."""
        return ProposedAction(
            action_type="apply_ilm_policy",
            description=f"Apply ILM policy '{policy_name}' to '{index}'",
            es_method="PUT",
            es_path=f"/{index}/_settings",
            es_body={"index": {"lifecycle": {"name": policy_name}}},
            risk_level="low",
            index=index,
        )

    def propose_create_index_template(
        self, template_name: str, template_body: Dict
    ) -> ProposedAction:
        """Propose creating or updating an index template."""
        return ProposedAction(
            action_type="create_index_template",
            description=f"Create index template '{template_name}'",
            es_method="PUT",
            es_path=f"/_index_template/{template_name}",
            es_body=template_body,
            risk_level="low",
            index=None,
        )

    # ===== APPROVAL & EXECUTION =====

    def propose(self, action: ProposedAction) -> Dict[str, Any]:
        """Register a proposed action for approval."""
        self._pending_actions[action.action_id] = action
        return action.to_dict()

    def approve(self, action_id: str) -> Dict[str, Any]:
        """Approve a pending action for execution."""
        action = self._pending_actions.get(action_id)
        if not action:
            return {"error": f"Action {action_id} not found"}
        if action.status != ApprovalStatus.pending:
            return {"error": f"Action {action_id} is {action.status.value}, cannot approve"}
        action.status = ApprovalStatus.approved
        return action.to_dict()

    def reject(self, action_id: str) -> Dict[str, Any]:
        """Reject a pending action."""
        action = self._pending_actions.get(action_id)
        if not action:
            return {"error": f"Action {action_id} not found"}
        action.status = ApprovalStatus.rejected
        self._move_to_history(action)
        return action.to_dict()

    async def execute(self, action_id: str) -> Dict[str, Any]:
        """Execute an approved action against Elasticsearch."""
        action = self._pending_actions.get(action_id)
        if not action:
            return {"error": f"Action {action_id} not found"}
        if action.status != ApprovalStatus.approved:
            return {"error": f"Action {action_id} is {action.status.value}, must be approved first"}

        try:
            async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
                method = action.es_method.upper()
                url = f"{self.es_url}{action.es_path}"
                kwargs = {"headers": self._headers(), "url": url}
                if action.es_body:
                    kwargs["json"] = action.es_body

                response = await getattr(client, method.lower())(**kwargs)

                if response.status_code < 300:
                    action.status = ApprovalStatus.executed
                    try:
                        action.result = response.json() if response.text else {"status": "ok"}
                    except Exception:
                        action.result = {"status": "ok", "http_status": response.status_code}
                    action.executed_at = datetime.utcnow().isoformat()
                else:
                    action.status = ApprovalStatus.failed
                    action.error = f"ES returned {response.status_code}: {response.text[:500]}"
                    if action.rollback_action:
                        rollback_result = await self._execute_rollback(
                            action.rollback_action
                        )
                        action.error += f" | Rollback: {rollback_result}"

            self._move_to_history(action)
            return action.to_dict()

        except Exception as e:
            action.status = ApprovalStatus.failed
            action.error = str(e)
            self._move_to_history(action)
            return action.to_dict()

    async def _execute_rollback(self, rollback: Dict) -> str:
        """Attempt to execute a rollback action."""
        try:
            async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
                method = rollback["es_method"].lower()
                url = f"{self.es_url}{rollback['es_path']}"
                kwargs = {"headers": self._headers(), "url": url}
                if rollback.get("es_body"):
                    kwargs["json"] = rollback["es_body"]
                response = await getattr(client, method)(**kwargs)
                return (
                    f"success ({response.status_code})"
                    if response.status_code < 300
                    else f"failed ({response.status_code})"
                )
        except Exception as e:
            return f"error: {e}"

    def _move_to_history(self, action: ProposedAction):
        """Move action from pending to history."""
        self._pending_actions.pop(action.action_id, None)
        self._action_history.append(action.to_dict())

    def get_pending_actions(self) -> List[Dict]:
        return [a.to_dict() for a in self._pending_actions.values()]

    def get_action_history(self, limit: int = 50) -> List[Dict]:
        return self._action_history[-limit:]

    def get_action(self, action_id: str) -> Optional[Dict]:
        action = self._pending_actions.get(action_id)
        if action:
            return action.to_dict()
        for h in reversed(self._action_history):
            if h.get("action_id") == action_id:
                return h
        return None

    async def bulk_approve_and_execute(
        self, action_ids: List[str]
    ) -> List[Dict]:
        """Approve and execute multiple actions in sequence."""
        results = []
        for aid in action_ids:
            self.approve(aid)
            result = await self.execute(aid)
            results.append(result)
        return results
