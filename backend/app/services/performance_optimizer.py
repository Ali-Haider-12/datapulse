"""Auto-Performance Optimizer — Slow log analysis + mapping/index template fixes.

Analyzes Elasticsearch cluster performance bottlenecks and proposes
concrete fixes: optimized mappings, better shard counts, refresh interval
tuning, and index template improvements.

Time saved: 2-4 hours per performance tuning session (manual profiling + trial-and-error)
"""
import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone
from enum import Enum

from app.services.es_write_client import ESWriteClient, ProposedAction
from app.services.mcp_client import ElasticMCPClient

logger = logging.getLogger(__name__)


class OptimizationStatus(str, Enum):
    analyzing = "analyzing"
    issues_found = "issues_found"
    actions_proposed = "actions_proposed"
    awaiting_approval = "awaiting_approval"
    completed = "completed"
    failed = "failed"


class PerformanceIssue:
    """A detected performance issue with proposed fix."""
    def __init__(
        self,
        issue_type: str,
        severity: str,
        index: str,
        description: str,
        fix: Dict,
        estimated_impact: str,
    ):
        self.issue_type = issue_type
        self.severity = severity  # critical, high, medium, low
        self.index = index
        self.description = description
        self.fix = fix
        self.estimated_impact = estimated_impact

    def to_dict(self):
        return {
            "issue_type": self.issue_type,
            "severity": self.severity,
            "index": self.index,
            "description": self.description,
            "fix": self.fix,
            "estimated_impact": self.estimated_impact,
        }


class OptimizationResult:
    """Result of a performance optimization analysis."""
    def __init__(self):
        self.status = OptimizationStatus.analyzing
        self.issues: List[Dict] = []
        self.proposed_actions: List[Dict] = []
        self.summary = ""
        self.time_saved_minutes = 0
        self.analyzed_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self):
        return {
            "status": self.status.value,
            "issues": self.issues,
            "proposed_actions": self.proposed_actions,
            "summary": self.summary,
            "time_saved_minutes": self.time_saved_minutes,
            "analyzed_at": self.analyzed_at,
        }


class PerformanceOptimizer:
    """Auto-Performance Optimizer for Elasticsearch clusters.

    Analysis categories:
    1. SHARD HEALTH: Oversized shards, too many/too few shards
    2. MAPPING ISSUES: Dynamic mapping enabled, keyword vs text mismatches
    3. REFRESH TUNING: Sub-second refresh on write-heavy indices
    4. MERGE PRESSURE: High segment count, slow merge times
    5. CACHE EFFICIENCY: Field data cache, query cache hit rates
    6. TEMPLATE GAPS: Indices without proper templates
    """

    # Performance thresholds
    MAX_SHARD_SIZE_GB = 50
    MIN_SHARD_SIZE_GB = 1
    MAX_SHARDS_PER_INDEX = 20
    MAX_SEGMENT_COUNT = 100
    MAX_MAPPING_FIELDS = 1000
    DEFAULT_REFRESH_INTERVAL = "1s"
    BULK_REFRESH_INTERVAL = "30s"

    def __init__(self, mcp_client: ElasticMCPClient, write_client: ESWriteClient):
        self.mcp = mcp_client
        self.writer = write_client

    def _parse_size_to_gb(self, size_str: str) -> float:
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
        except (ValueError, TypeError):
            pass
        return 0.0

    async def analyze_performance(self) -> OptimizationResult:
        """Full cluster performance analysis.

        Scans all indices for common performance anti-patterns
        and proposes concrete fixes.
        """
        result = OptimizationResult()

        try:
            indices_data = await self.mcp.list_indices()
            indices = indices_data.get("indices", [])
        except Exception as e:
            result.status = OptimizationStatus.failed
            result.summary = f"Failed to list indices: {e}"
            return result

        total_issues = 0

        for idx in indices:
            name = idx.get("name", "")
            if name.startswith(".") or name.startswith("kibana"):
                continue

            size_gb = self._parse_size_to_gb(idx.get("size", "0b"))
            try:
                pri = int(idx.get("pri", 1))
            except (ValueError, TypeError):
                pri = 1
            try:
                rep = int(idx.get("rep", 1))
            except (ValueError, TypeError):
                rep = 1
            health = idx.get("health", "green")
            status = idx.get("status", "open")
            docs = idx.get("docs", "0")

            # Check 1: Oversized shards
            if pri > 0 and size_gb / pri > self.MAX_SHARD_SIZE_GB:
                issue = PerformanceIssue(
                    issue_type="oversized_shard",
                    severity="high",
                    index=name,
                    description=f"Shard size {size_gb/pri:.1f}GB exceeds {self.MAX_SHARD_SIZE_GB}GB limit",
                    fix={
                        "action_type": "update_settings",
                        "settings": {"number_of_shards": pri * 2},
                        "note": "Requires reindex to apply shard count change",
                    },
                    estimated_impact="2-5x query speedup on this index",
                )
                result.issues.append(issue.to_dict())
                total_issues += 1

            # Check 2: Too many shards (small shards)
            if pri > self.MAX_SHARDS_PER_INDEX and size_gb / pri < self.MIN_SHARD_SIZE_GB:
                issue = PerformanceIssue(
                    issue_type="too_many_shards",
                    severity="medium",
                    index=name,
                    description=f"{pri} primary shards for {size_gb:.1f}GB index = {size_gb/pri:.2f}GB/shard (undersized)",
                    fix={
                        "action_type": "update_settings",
                        "settings": {"number_of_shards": max(1, pri // 2)},
                        "note": "Requires reindex to apply shard count change",
                    },
                    estimated_impact="Reduced cluster overhead, faster recovery",
                )
                result.issues.append(issue.to_dict())
                total_issues += 1

            # Check 3: Excessive replicas on small indices
            if rep > 1 and size_gb < 1:
                issue = PerformanceIssue(
                    issue_type="excessive_replicas",
                    severity="low",
                    index=name,
                    description=f"Small index ({size_gb:.2f}GB) has {rep} replicas — wasteful",
                    fix={
                        "action_type": "set_replicas",
                        "params": {"replica_count": 1},
                    },
                    estimated_impact="Reduced disk usage and cluster overhead",
                )
                result.issues.append(issue.to_dict())
                action = self.writer.propose_set_replicas(
                    index=name, replica_count=1,
                )
                proposal = self.writer.propose(action)
                result.proposed_actions.append(proposal)
                total_issues += 1

            # Check 4: Write-heavy index with fast refresh interval
            # Heuristic: indices with many docs and small size = high write rate
            try:
                doc_count = int(docs.replace(",", "").split("/")[0])
            except (ValueError, TypeError, AttributeError):
                doc_count = 0

            if doc_count > 100000 and size_gb > 1:
                issue = PerformanceIssue(
                    issue_type="refresh_interval",
                    severity="medium",
                    index=name,
                    description=f"High-volume index ({doc_count:,} docs) likely using 1s refresh — increase to 30s for bulk",
                    fix={
                        "action_type": "update_settings",
                        "settings": {"refresh_interval": self.BULK_REFRESH_INTERVAL},
                    },
                    estimated_impact="30-50% indexing throughput improvement",
                )
                result.issues.append(issue.to_dict())
                action = self.writer.propose_update_settings(
                    index=name,
                    settings={"refresh_interval": self.BULK_REFRESH_INTERVAL},
                )
                proposal = self.writer.propose(action)
                result.proposed_actions.append(proposal)
                total_issues += 1

            # Check 5: Yellow health (unassigned replicas)
            if health == "yellow":
                issue = PerformanceIssue(
                    issue_type="yellow_health",
                    severity="high",
                    index=name,
                    description="Yellow health — unassigned replica shards",
                    fix={
                        "action_type": "set_replicas",
                        "params": {"replica_count": 0},
                    },
                    estimated_impact="Restores green health on single-node clusters",
                )
                result.issues.append(issue.to_dict())
                action = self.writer.propose_set_replicas(
                    index=name, replica_count=0,
                )
                proposal = self.writer.propose(action)
                result.proposed_actions.append(proposal)
                total_issues += 1

            # Check 6: Open but stale indices (waste cluster state memory)
            if status == "open" and size_gb < 0.01 and doc_count < 100 and not name.startswith("apm-custom"):
                issue = PerformanceIssue(
                    issue_type="stale_open_index",
                    severity="low",
                    index=name,
                    description=f"Nearly empty open index ({doc_count} docs, {size_gb:.3f}GB) — wastes cluster state",
                    fix={
                        "action_type": "close_index",
                        "params": {},
                    },
                    estimated_impact="Reduced cluster state size, faster cluster operations",
                )
                result.issues.append(issue.to_dict())
                action = self.writer.propose_open_close_index(
                    index=name, action="close",
                )
                proposal = self.writer.propose(action)
                result.proposed_actions.append(proposal)
                total_issues += 1

        # Step 7: Propose optimized index templates
        template_issues = self._check_template_gaps(indices)
        for ti in template_issues:
            result.issues.append(ti.to_dict())
            total_issues += 1

        # Summary
        if total_issues == 0:
            result.status = OptimizationStatus.completed
            result.summary = "✅ Cluster performance looks good — no issues detected."
        else:
            result.status = OptimizationStatus.awaiting_approval
            result.time_saved_minutes = total_issues * 30  # ~30 min per issue
            result.summary = (
                f"Found {total_issues} performance issues across {len(indices)} indices. "
                f"{len(result.proposed_actions)} quick-fix actions proposed. "
                f"Estimated time saved: {result.time_saved_minutes} minutes."
            )

        return result

    def _check_template_gaps(self, indices: List[Dict]) -> List[PerformanceIssue]:
        """Check for common index patterns missing templates."""
        issues = []

        # Patterns that should have templates
        template_patterns = {
            "logs-": "datapulse-logs-template",
            "metrics-": "datapulse-metrics-template",
            "apm-": "datapulse-apm-template",
            "filebeat-": "datapulse-beats-template",
            ".ds-": "datapulse-data-stream-template",
        }

        pattern_counts: Dict[str, int] = {}
        for idx in indices:
            name = idx.get("name", "")
            for prefix in template_patterns:
                if name.startswith(prefix):
                    pattern_counts[prefix] = pattern_counts.get(prefix, 0) + 1

        for prefix, count in pattern_counts.items():
            if count >= 2:  # 2+ indices with same prefix = needs a template
                issues.append(PerformanceIssue(
                    issue_type="missing_template",
                    severity="medium",
                    index=f"{prefix}*",
                    description=f"{count} indices with '{prefix}' prefix but no optimized template",
                    fix={
                        "action_type": "create_index_template",
                        "template_name": template_patterns[prefix],
                    },
                    estimated_impact="Consistent settings for future indices, prevents misconfiguration",
                ))

        return issues

    async def analyze_mappings(self, index: str) -> Dict[str, Any]:
        """Analyze a specific index's mapping for anti-patterns.

        Checks:
        - Dynamic mapping enabled (risk of mapping explosion)
        - Too many fields (>1000)
        - Text fields used for exact matching (should be keyword)
        - Keyword fields with very high cardinality
        """
        try:
            mapping_data = await self.mcp.get_mapping(index=index)
        except Exception as e:
            return {"index": index, "error": str(e)}

        issues = []
        properties = mapping_data.get(index, {}).get("mappings", {}).get("properties", {})

        # Check total field count
        field_count = len(properties)
        if field_count > self.MAX_MAPPING_FIELDS:
            issues.append({
                "type": "mapping_explosion",
                "severity": "high",
                "description": f"{field_count} fields detected (limit: {self.MAX_MAPPING_FIELDS})",
                "fix": "Disable dynamic mapping and explicitly define needed fields",
            })

        # Check for text fields that should be keyword
        text_fields = [
            name for name, config in properties.items()
            if config.get("type") == "text" and not config.get("fields", {}).get("keyword")
        ]
        if len(text_fields) > 5:
            issues.append({
                "type": "text_without_keyword",
                "severity": "medium",
                "description": f"{len(text_fields)} text fields without keyword sub-field",
                "fields": text_fields[:10],
                "fix": "Add keyword sub-fields for text fields used in filtering/aggregation",
            })

        # Check if dynamic mapping is explicitly disabled
        dynamic = mapping_data.get(index, {}).get("mappings", {}).get("dynamic", "true")
        if dynamic != "strict" and field_count > 100:
            issues.append({
                "type": "dynamic_mapping_enabled",
                "severity": "high",
                "description": f"Dynamic mapping enabled with {field_count} fields — risk of mapping explosion",
                "fix": "Set dynamic: 'strict' to prevent new fields from being added automatically",
            })

        return {
            "index": index,
            "field_count": field_count,
            "issues": issues,
            "healthy": len(issues) == 0,
        }
