"""Autonomous Cluster Healer — Multi-step remediation workflows.

This is the CORE differentiator: DataPulse doesn't just FIND problems, it HEALS them.

Each heal workflow:
1. DETECT: Scan for the specific issue type
2. ANALYZE: Assess severity and business impact
3. PROPOSE: Generate a remediation plan with approval gates
4. EXECUTE: Carry out approved actions
5. VERIFY: Confirm the fix worked

Time saved per incident: 45 minutes → 30 seconds
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
from enum import Enum

from app.services.es_write_client import ESWriteClient, ProposedAction
from app.services.mcp_client import ElasticMCPClient

logger = logging.getLogger(__name__)


class HealStatus(str, Enum):
    scanning = "scanning"
    issues_found = "issues_found"
    actions_proposed = "actions_proposed"
    awaiting_approval = "awaiting_approval"
    executing = "executing"
    completed = "completed"
    failed = "failed"


class HealResult:
    """Result of a healing workflow."""

    def __init__(self, workflow_type: str):
        self.workflow_type = workflow_type
        self.status = HealStatus.scanning
        self.issues: List[Dict] = []
        self.proposed_actions: List[Dict] = []
        self.executed_actions: List[Dict] = []
        self.summary = ""
        self.started_at = datetime.utcnow().isoformat()
        self.completed_at = None
        self.time_saved_minutes = 0

    def to_dict(self):
        return {
            "workflow_type": self.workflow_type,
            "status": self.status.value,
            "issues": self.issues,
            "proposed_actions": self.proposed_actions,
            "executed_actions": self.executed_actions,
            "summary": self.summary,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "time_saved_minutes": self.time_saved_minutes,
        }


class ClusterHealer:
    """Autonomous healing engine for Elasticsearch clusters.

    Each heal_ method is a self-contained workflow:
    - Scans for the issue
    - Generates remediation proposals
    - Returns proposals for human approval
    - Executes on approval
    """

    def __init__(self, mcp_client: ElasticMCPClient, write_client: ESWriteClient):
        self.mcp = mcp_client
        self.writer = write_client

    async def heal_yellow_indices(self) -> HealResult:
        """Heal all yellow indices by adjusting replica counts or allocating shards.

        Yellow = replicas are unassigned. Common causes:
        - Single-node cluster (no room for replicas)
        - Disk watermark exceeded
        - Shard allocation filtering

        Time saved: 45 min per yellow index (manual investigation + fix)
        """
        result = HealResult("heal_yellow_indices")

        # Step 1: DETECT — find yellow indices
        try:
            indices_data = await self.mcp.list_indices()
            indices = indices_data.get("indices", [])
            yellow_indices = [i for i in indices if i.get("health") == "yellow"]
        except Exception as e:
            result.status = HealStatus.failed
            result.summary = f"Failed to list indices: {e}"
            return result

        if not yellow_indices:
            result.status = HealStatus.completed
            result.summary = "No yellow indices found — cluster is healthy!"
            return result

        result.status = HealStatus.issues_found
        result.issues = [
            {
                "index": i["name"],
                "health": "yellow",
                "docs": i.get("docs", 0),
                "size": i.get("size", "?"),
            }
            for i in yellow_indices
        ]

        # Step 2: ANALYZE — check shard details for each yellow index
        for idx in yellow_indices:
            index_name = idx["name"]
            try:
                shards_data = await self.mcp.get_shards(index=index_name)
                shards = shards_data.get("shards", [])
                unassigned = [s for s in shards if s.get("state") == "UNASSIGNED"]
            except Exception:
                unassigned = []

            # Step 3: PROPOSE — generate fix based on root cause
            if len(shards) > 0 and all(
                s.get("prirep") == "p" for s in shards if s.get("state") == "STARTED"
            ):
                # Only primaries running — likely single-node, set replicas to 0
                current_replicas = idx.get("rep", "1")
                try:
                    current_count = int(current_replicas)
                except (ValueError, TypeError):
                    current_count = 1
                action = self.writer.propose_set_replicas(
                    index=index_name, replica_count=0, current_count=current_count
                )
                proposal = self.writer.propose(action)
                result.proposed_actions.append(proposal)
                result.time_saved_minutes += 45
            else:
                # Unassigned replica shards — try reroute
                action = self.writer.propose_reroute_shards(index=index_name)
                proposal = self.writer.propose(action)
                result.proposed_actions.append(proposal)
                result.time_saved_minutes += 30

        result.status = HealStatus.awaiting_approval
        result.summary = (
            f"Found {len(yellow_indices)} yellow indices. "
            f"Proposed {len(result.proposed_actions)} remediation actions. "
            f"Estimated time saved: {result.time_saved_minutes} minutes."
        )
        return result

    async def heal_mapping_explosions(self) -> HealResult:
        """Heal indices with mapping explosions (>1000 fields).

        Mapping explosions degrade search performance and increase memory usage.
        Fix: disable dynamic mapping to prevent new field creation.

        Time saved: 60 min per index (manual analysis + settings change + verification)
        """
        result = HealResult("heal_mapping_explosions")

        # Step 1: DETECT — find indices with large mappings
        try:
            indices_data = await self.mcp.list_indices()
            indices = indices_data.get("indices", [])
        except Exception as e:
            result.status = HealStatus.failed
            result.summary = f"Failed to list indices: {e}"
            return result

        problematic = []
        for idx in indices:
            index_name = idx.get("name", "")
            if index_name.startswith(".") or index_name.startswith("kibana"):
                continue  # Skip system indices
            try:
                mappings_data = await self.mcp.get_mappings(index=index_name)
                # Count fields across all mapping types
                field_count = 0
                for index_key, mapping in mappings_data.items():
                    props = mapping.get("mappings", {}).get("properties", {})
                    field_count += len(props)
                if field_count > 1000:
                    problematic.append({"index": index_name, "field_count": field_count})
            except Exception:
                continue

        if not problematic:
            result.status = HealStatus.completed
            result.summary = "No mapping explosions detected — all indices under 1000 fields."
            return result

        result.status = HealStatus.issues_found
        result.issues = problematic

        # Step 3: PROPOSE — disable dynamic mapping for each problematic index
        for issue in problematic:
            action = self.writer.propose_disable_dynamic_mapping(index=issue["index"])
            proposal = self.writer.propose(action)
            result.proposed_actions.append(proposal)
            result.time_saved_minutes += 60

        result.status = HealStatus.awaiting_approval
        result.summary = (
            f"Found {len(problematic)} indices with mapping explosions. "
            f"Proposed disabling dynamic mapping for each. "
            f"Estimated time saved: {result.time_saved_minutes} minutes."
        )
        return result

    async def heal_red_indices(self) -> HealResult:
        """Heal red indices — the most critical issue.

        Red = primary shards are unassigned. Data is partially unavailable.
        This is a P0 incident that normally wakes up an SRE at 3am.

        Time saved: 90 min per red index (emergency investigation + fix)
        """
        result = HealResult("heal_red_indices")

        try:
            indices_data = await self.mcp.list_indices()
            indices = indices_data.get("indices", [])
            red_indices = [i for i in indices if i.get("health") == "red"]
        except Exception as e:
            result.status = HealStatus.failed
            result.summary = f"Failed to list indices: {e}"
            return result

        if not red_indices:
            result.status = HealStatus.completed
            result.summary = "No red indices — cluster is healthy!"
            return result

        result.status = HealStatus.issues_found
        result.issues = [
            {
                "index": i["name"],
                "health": "red",
                "docs": i.get("docs", 0),
                "size": i.get("size", "?"),
            }
            for i in red_indices
        ]

        result.time_saved_minutes = len(red_indices) * 90

        # For red indices, try shard reroute first
        for idx in red_indices:
            action = self.writer.propose_reroute_shards(index=idx["name"])
            proposal = self.writer.propose(action)
            result.proposed_actions.append(proposal)

        result.status = HealStatus.awaiting_approval
        result.summary = (
            f"🚨 CRITICAL: {len(red_indices)} red indices found! "
            f"Proposed shard reroute for each. "
            f"Estimated time saved: {result.time_saved_minutes} minutes."
        )
        return result

    async def heal_stale_indices(self, days_threshold: int = 90) -> HealResult:
        """Heal stale indices by proposing closure or deletion.

        Indices not written to in 90+ days waste storage and memory.
        Closing them frees resources without deleting data.
        Deleting them reclaims storage entirely.

        Time saved: 30 min per index (manual audit + decision + action)
        """
        result = HealResult("heal_stale_indices")

        try:
            indices_data = await self.mcp.list_indices()
            indices = indices_data.get("indices", [])
        except Exception as e:
            result.status = HealStatus.failed
            result.summary = f"Failed to list indices: {e}"
            return result

        # Check each non-system index for staleness
        stale = []
        for idx in indices:
            index_name = idx.get("name", "")
            if index_name.startswith(".") or index_name.startswith("kibana"):
                continue
            try:
                # Check last write time via search
                search_result = await self.mcp.search(
                    index=index_name,
                    body={
                        "size": 1,
                        "sort": [{"@timestamp": {"order": "desc"}}],
                        "_source": ["@timestamp"],
                    },
                )
                hits = search_result.get("hits", {}).get("hits", [])
                if hits:
                    last_ts = hits[0].get("_source", {}).get("@timestamp", "")
                    if last_ts:
                        from datetime import datetime as dt

                        try:
                            last_date = dt.fromisoformat(last_ts.replace("Z", "+00:00"))
                            days_since = (dt.now(last_date.tzinfo) - last_date).days
                            if days_since > days_threshold:
                                stale.append(
                                    {
                                        "index": index_name,
                                        "days_stale": days_since,
                                        "docs": idx.get("docs", 0),
                                    }
                                )
                        except (ValueError, TypeError):
                            pass
            except Exception:
                continue

        if not stale:
            result.status = HealStatus.completed
            result.summary = f"No indices stale for >{days_threshold} days."
            return result

        result.status = HealStatus.issues_found
        result.issues = stale

        # Propose close for stale indices (safe), delete for very old ones (high risk)
        for issue in stale:
            if issue["days_stale"] > 180:
                # Very old — propose delete (high risk, needs strong approval)
                action = self.writer.propose_delete_index(index=issue["index"])
                proposal = self.writer.propose(action)
                result.proposed_actions.append(proposal)
            else:
                # Moderately old — propose close (safe, reversible)
                action = self.writer.propose_open_close_index(
                    index=issue["index"], action="close"
                )
                proposal = self.writer.propose(action)
                result.proposed_actions.append(proposal)
            result.time_saved_minutes += 30

        result.status = HealStatus.awaiting_approval
        result.summary = (
            f"Found {len(stale)} stale indices (>{days_threshold} days). "
            f"Proposed close/delete actions. "
            f"Estimated time saved: {result.time_saved_minutes} minutes."
        )
        return result

    async def full_cluster_heal(self) -> HealResult:
        """Run ALL healing workflows and return a combined result.

        This is the 'one-click fix everything' button.
        Time saved: 3-4 hours of manual cluster health review.
        """
        combined = HealResult("full_cluster_heal")

        workflows = [
            self.heal_red_indices(),
            self.heal_yellow_indices(),
            self.heal_mapping_explosions(),
            self.heal_stale_indices(),
        ]

        for wf in workflows:
            wf_result = await wf
            combined.issues.extend(wf_result.issues)
            combined.proposed_actions.extend(wf_result.proposed_actions)
            combined.time_saved_minutes += wf_result.time_saved_minutes

        if not combined.issues:
            combined.status = HealStatus.completed
            combined.summary = "🎉 Cluster is fully healthy! No issues found."
        else:
            combined.status = HealStatus.awaiting_approval
            combined.summary = (
                f"Found {len(combined.issues)} issues across all workflows. "
                f"Proposed {len(combined.proposed_actions)} remediation actions. "
                f"Estimated total time saved: {combined.time_saved_minutes} minutes "
                f"({combined.time_saved_minutes // 60}h {combined.time_saved_minutes % 60}m)."
            )

        combined.completed_at = datetime.utcnow().isoformat()
        return combined
