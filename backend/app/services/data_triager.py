"""Intelligent Data Triage & Reindexing — Smart index migration and optimization.

Scans indices for issues that require reindexing:
- Mapping conflicts (field type mismatches across time-based indices)
- Oversized shards (>50GB) that need splitting
- Outdated index settings that can only change on reindex
- Cross-index data consolidation

Time saved: 2-3 hours per reindex operation (manual planning + execution + verification)
"""
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
from enum import Enum

from app.services.es_write_client import ESWriteClient, ProposedAction
from app.services.mcp_client import ElasticMCPClient

logger = logging.getLogger(__name__)


class TriageStatus(str, Enum):
    scanning = "scanning"
    candidates_found = "candidates_found"
    actions_proposed = "actions_proposed"
    awaiting_approval = "awaiting_approval"
    executing = "executing"
    completed = "completed"
    failed = "failed"


class TriageResult:
    """Result of a data triage scan."""

    def __init__(self, scan_type: str):
        self.scan_type = scan_type
        self.status = TriageStatus.scanning
        self.candidates: List[Dict] = []
        self.proposed_actions: List[Dict] = []
        self.executed_actions: List[Dict] = []
        self.summary = ""
        self.started_at = datetime.utcnow().isoformat()
        self.completed_at = None
        self.time_saved_minutes = 0

    def to_dict(self):
        return {
            "scan_type": self.scan_type,
            "status": self.status.value,
            "candidates": self.candidates,
            "proposed_actions": self.proposed_actions,
            "executed_actions": self.executed_actions,
            "summary": self.summary,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "time_saved_minutes": self.time_saved_minutes,
        }


class DataTriager:
    """Intelligent data triage engine — identifies indices needing reindex.

    Reindexing is the "surgery" of ES operations — it fixes structural
    problems that settings changes can't address. This engine:
    1. Scans for reindex candidates (oversized shards, mapping conflicts, etc.)
    2. Plans the reindex operation (source → dest, settings, pipeline)
    3. Proposes the action with rollback plan
    4. Executes on approval with verification
    """

    # Shard size thresholds
    OVERSIZED_SHARD_GB = 50  # Shards >50GB need splitting
    UNDERSIZED_SHARD_MB = 500  # Shards <500MB can be merged

    def __init__(self, mcp_client: ElasticMCPClient, write_client: ESWriteClient):
        self.mcp = mcp_client
        self.writer = write_client

    def _parse_size_to_gb(self, size_str: str) -> float:
        """Parse ES size string like '45.2gb' or '1024mb' to GB float."""
        size_str = (size_str or "0b").lower().strip()
        try:
            if "gb" in size_str:
                return float(size_str.replace("gb", "").strip())
            elif "mb" in size_str:
                return float(size_str.replace("mb", "").strip()) / 1024
            elif "tb" in size_str:
                return float(size_str.replace("tb", "").strip()) * 1024
            elif "kb" in size_str:
                return float(size_str.replace("kb", "").strip()) / 1024 / 1024
            elif "b" in size_str:
                return float(size_str.replace("b", "").strip()) / 1024 / 1024 / 1024
        except (ValueError, TypeError):
            pass
        return 0.0

    async def scan_oversized_shards(self) -> TriageResult:
        """Find indices with shards >50GB that need splitting via reindex.

        Oversized shards cause:
        - Slow recovery during node failures
        - Long merge times
        - Uneven data distribution

        Fix: Reindex into multiple smaller indices with a time-based pattern.
        Time saved: 2-3 hours per index (manual split planning + execution)
        """
        result = TriageResult("oversized_shards")

        try:
            indices_data = await self.mcp.list_indices()
            indices = indices_data.get("indices", [])
        except Exception as e:
            result.status = TriageStatus.failed
            result.summary = f"Failed to list indices: {e}"
            return result

        for idx in indices:
            name = idx.get("name", "")
            if name.startswith(".") or name.startswith("kibana"):
                continue
            size_gb = self._parse_size_to_gb(idx.get("size", "0b"))
            pri = idx.get("pri", 1)
            try:
                pri_count = int(pri)
            except (ValueError, TypeError):
                pri_count = 1

            shard_size_gb = size_gb / pri_count if pri_count > 0 else size_gb

            if shard_size_gb > self.OVERSIZED_SHARD_GB:
                result.candidates.append({
                    "index": name,
                    "total_size_gb": round(size_gb, 2),
                    "primary_shards": pri_count,
                    "avg_shard_size_gb": round(shard_size_gb, 2),
                    "recommended_shards": max(pri_count * 2, int(size_gb / 30) + 1),
                    "issue": f"Shards average {shard_size_gb:.1f}GB — exceeds {self.OVERSIZED_SHARD_GB}GB threshold",
                })

        if not result.candidates:
            result.status = TriageStatus.completed
            result.summary = "No oversized shards found — all indices within size limits."
            return result

        result.status = TriageStatus.candidates_found

        # Propose reindex with more shards
        for candidate in result.candidates:
            index_name = candidate["index"]
            dest_name = f"{index_name}-reindexed"
            new_shards = candidate["recommended_shards"]

            # Create a reindex proposal
            action = self.writer.propose_reindex(
                source_index=index_name,
                dest_index=dest_name,
            )
            proposal = self.writer.propose(action)

            # Also propose creating an index template for future indices
            template_action = self.writer.propose_create_index_template(
                template_name=f"{index_name}-template",
                template_body={
                    "index_patterns": [f"{index_name}-*"],
                    "template": {
                        "settings": {
                            "number_of_shards": new_shards,
                            "number_of_replicas": 1,
                        }
                    },
                },
            )
            template_proposal = self.writer.propose(template_action)

            result.proposed_actions.extend([proposal, template_proposal])
            result.time_saved_minutes += 150  # ~2.5 hours per operation

        result.status = TriageStatus.awaiting_approval
        result.summary = (
            f"Found {len(result.candidates)} indices with oversized shards. "
            f"Proposed reindex + template for each. "
            f"Estimated time saved: {result.time_saved_minutes} minutes."
        )
        return result

    async def scan_mapping_conflicts(self) -> TriageResult:
        """Find time-series index patterns with mapping conflicts.

        When a field type changes between rolling indices (e.g., log-2026.05
        has 'user_id' as integer, log-2026.06 has 'user_id' as keyword),
        cross-index queries fail or return wrong results.

        Fix: Reindex the conflicting index to align field types.
        Time saved: 3-4 hours (manual mapping analysis + reindex + verify)
        """
        result = TriageResult("mapping_conflicts")

        try:
            indices_data = await self.mcp.list_indices()
            indices = indices_data.get("indices", [])
        except Exception as e:
            result.status = TriageStatus.failed
            result.summary = f"Failed to list indices: {e}"
            return result

        # Group indices by pattern (prefix before date/version suffix)
        patterns: Dict[str, List[Dict]] = {}
        for idx in indices:
            name = idx.get("name", "")
            if name.startswith(".") or name.startswith("kibana"):
                continue
            # Extract base pattern: everything before the last '-' segment
            # that looks like a date/version (e.g., 2026.05.05, v2, 20260505)
            parts = name.rsplit("-", 1)
            if len(parts) == 2:
                base = parts[0]
                patterns.setdefault(base, []).append(idx)

        # Check mappings within each pattern group
        for base, group in patterns.items():
            if len(group) < 2:
                continue  # Need at least 2 indices to have conflicts

            # Get mappings for each index in the group
            field_types: Dict[str, Dict[str, str]] = {}  # field_name -> {index: type}
            for idx in group[:5]:  # Limit to first 5 to avoid excessive API calls
                try:
                    mappings_data = await self.mcp.get_mappings(index=idx["name"])
                    for index_key, mapping in mappings_data.items():
                        props = mapping.get("mappings", {}).get("properties", {})
                        for field_name, field_def in props.items():
                            ftype = field_def.get("type", "object")
                            field_types.setdefault(field_name, {})[idx["name"]] = ftype
                except Exception:
                    continue

            # Find conflicts: same field name, different types
            conflicts = []
            for field_name, type_map in field_types.items():
                unique_types = set(type_map.values())
                if len(unique_types) > 1:
                    conflicts.append({
                        "field": field_name,
                        "types": type_map,
                        "indices_affected": list(type_map.keys()),
                    })

            if conflicts:
                result.candidates.append({
                    "pattern": base,
                    "indices_in_group": len(group),
                    "conflicts": conflicts,
                    "conflict_count": len(conflicts),
                })

        if not result.candidates:
            result.status = TriageStatus.completed
            result.summary = "No mapping conflicts found across index patterns."
            return result

        result.status = TriageStatus.candidates_found

        # Propose reindex for conflicting indices
        for candidate in result.candidates:
            for conflict in candidate.get("conflicts", []):
                # Find the "wrong" type (minority) and reindex to align with majority
                type_counts: Dict[str, int] = {}
                for t in conflict["types"].values():
                    type_counts[t] = type_counts.get(t, 0) + 1
                majority_type = max(type_counts, key=type_counts.get)

                for idx_name, field_type in conflict["types"].items():
                    if field_type != majority_type:
                        action = self.writer.propose_reindex(
                            source_index=idx_name,
                            dest_index=f"{idx_name}-fixed",
                        )
                        proposal = self.writer.propose(action)
                        result.proposed_actions.append(proposal)
                        result.time_saved_minutes += 180  # ~3 hours

        result.status = TriageStatus.awaiting_approval
        result.summary = (
            f"Found {len(result.candidates)} index patterns with mapping conflicts. "
            f"Proposed reindex operations to resolve. "
            f"Estimated time saved: {result.time_saved_minutes} minutes."
        )
        return result

    async def scan_undersized_shards(self) -> TriageResult:
        """Find indices with tiny shards that waste cluster resources.

        Many small shards (<500MB) cause:
        - Excessive heap usage (each shard ~20-50MB overhead)
        - Slower cluster state updates
        - Poor search performance (too many segments)

        Fix: Reindex/merge into fewer, larger shards.
        Time saved: 1-2 hours per consolidation
        """
        result = TriageResult("undersized_shards")

        try:
            indices_data = await self.mcp.list_indices()
            indices = indices_data.get("indices", [])
        except Exception as e:
            result.status = TriageStatus.failed
            result.summary = f"Failed to list indices: {e}"
            return result

        for idx in indices:
            name = idx.get("name", "")
            if name.startswith(".") or name.startswith("kibana"):
                continue
            size_mb = self._parse_size_to_gb(idx.get("size", "0b")) * 1024
            pri = idx.get("pri", 1)
            try:
                pri_count = int(pri)
            except (ValueError, TypeError):
                pri_count = 1

            if pri_count > 1:
                shard_size_mb = size_mb / pri_count
                if shard_size_mb < self.UNDERSIZED_SHARD_MB and size_mb > 0:
                    result.candidates.append({
                        "index": name,
                        "total_size_mb": round(size_mb, 2),
                        "primary_shards": pri_count,
                        "avg_shard_size_mb": round(shard_size_mb, 2),
                        "recommended_shards": max(1, int(size_mb / 300) + 1),
                        "issue": f"Shards average {shard_size_mb:.0f}MB — below {self.UNDERSIZED_SHARD_MB}MB threshold",
                    })

        if not result.candidates:
            result.status = TriageStatus.completed
            result.summary = "No undersized shards found."
            return result

        result.status = TriageStatus.candidates_found

        for candidate in result.candidates:
            action = self.writer.propose_reindex(
                source_index=candidate["index"],
                dest_index=f"{candidate['index']}-consolidated",
            )
            proposal = self.writer.propose(action)
            result.proposed_actions.append(proposal)
            result.time_saved_minutes += 90

        result.status = TriageStatus.awaiting_approval
        result.summary = (
            f"Found {len(result.candidates)} indices with undersized shards. "
            f"Proposed consolidation reindex for each. "
            f"Estimated time saved: {result.time_saved_minutes} minutes."
        )
        return result

    async def full_triage(self) -> TriageResult:
        """Run all triage scans and return combined results."""
        combined = TriageResult("full_triage")

        scans = [
            self.scan_oversized_shards(),
            self.scan_mapping_conflicts(),
            self.scan_undersized_shards(),
        ]

        for scan in scans:
            scan_result = await scan
            combined.candidates.extend(scan_result.candidates)
            combined.proposed_actions.extend(scan_result.proposed_actions)
            combined.time_saved_minutes += scan_result.time_saved_minutes

        if not combined.candidates:
            combined.status = TriageStatus.completed
            combined.summary = "✅ All indices are optimally configured — no reindex needed."
        else:
            combined.status = TriageStatus.awaiting_approval
            combined.summary = (
                f"Found {len(combined.candidates)} reindex candidates. "
                f"Proposed {len(combined.proposed_actions)} actions. "
                f"Estimated time saved: {combined.time_saved_minutes} minutes."
            )

        combined.completed_at = datetime.utcnow().isoformat()
        return combined
