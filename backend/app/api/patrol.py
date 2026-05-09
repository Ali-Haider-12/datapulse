"""
Patrol API — Scheduled inspection sweeps.
"""

from fastapi import APIRouter, Request, BackgroundTasks
from datetime import datetime, timezone
import asyncio
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

_patrol_active = False
_patrol_history: list[dict] = []


@router.get("")
async def get_patrol(request: Request):
    """Get current patrol status and history."""
    return {
        "active": _patrol_active,
        "history": _patrol_history[-10:],  # Last 10 patrols
        "total_patrols": len(_patrol_history),
    }


@router.post("/start")
async def start_patrol(request: Request, background_tasks: BackgroundTasks):
    """Start a patrol sweep."""
    global _patrol_active

    if _patrol_active:
        return {"status": "already_running", "message": "Patrol already active"}

    _patrol_active = True

    background_tasks.add_task(_run_patrol)

    return {
        "status": "started",
        "message": "Patrol sweep initiated",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/stop")
async def stop_patrol():
    """Stop a running patrol sweep."""
    global _patrol_active
    _patrol_active = False
    return {"status": "stopped", "message": "Patrol sweep stopped"}


async def _run_patrol():
    """Execute a patrol sweep — check health, detect issues, log findings."""
    global _patrol_active, _patrol_history
    import time

    patrol_start = time.time()
    findings: list[dict] = []

    try:
        from app.main import app
        mcp = getattr(app.state, 'mcp_client', None)
        ha = getattr(app.state, 'health_analyzer', None)
    except Exception:
        mcp = None
        ha = None

    # Step 1: Check cluster health
    if mcp:
        try:
            health = await mcp.list_indices()
            for idx in health.get("indices", []):
                if idx.get("health") in ("red", "yellow"):
                    findings.append({
                        "type": "index_health",
                        "severity": idx.get("health"),
                        "index": idx.get("name"),
                        "message": f"Index {idx.get('name')} is {idx.get('health')}",
                    })
        except Exception as e:
            logger.warning(f"Patrol health check failed: {e}")
            findings.append({
                "type": "check_failure",
                "severity": "critical",
                "message": f"Health check failed: {e}",
            })

        # Step 2: Check shard allocation
        try:
            shards = await mcp.get_shards(index="*")
            for shard in shards.get("shards", []):
                if shard.get("state") == "UNASSIGNED":
                    findings.append({
                        "type": "unassigned_shard",
                        "severity": "critical",
                        "index": shard.get("index"),
                        "shard": shard.get("shard"),
                        "message": f"Unassigned shard {shard.get('shard')} in {shard.get('index')}",
                    })
        except Exception as e:
            logger.warning(f"Patrol shard check failed: {e}")

        # Step 3: Check error rate
        try:
            error_check = await mcp.esql(
                'FROM logs-* | STATS errors = COUNT(*) WHERE level = "error" AND @timestamp >= now-1h'
            )
            for row in error_check.get("values", []):
                error_count = row[-1] if row else 0
                if isinstance(error_count, (int, float)) and error_count > 1000:
                    findings.append({
                        "type": "high_error_rate",
                        "severity": "warning",
                        "error_count": error_count,
                        "message": f"High error rate: {error_count} errors in last hour",
                    })
        except Exception as e:
            logger.debug(f"Patrol error rate check failed: {e}")

    # Step 4: Health analyzer if available
    if ha:
        try:
            report = await ha.comprehensive_health_report()
            if report.get("alerts"):
                for alert in report["alerts"]:
                    findings.append({
                        "type": "health_analyzer",
                        "severity": alert.get("severity", "info"),
                        "title": alert.get("title", ""),
                        "message": alert.get("message", ""),
                    })
        except Exception as e:
            logger.warning(f"Patrol health analyzer failed: {e}")

    duration = round(time.time() - patrol_start, 2)

    patrol_record = {
        "patrol_id": f"PAT-{len(_patrol_history) + 1:04d}",
        "started_at": datetime.utcfromtimestamp(patrol_start).isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": duration,
        "findings_count": len(findings),
        "findings": findings,
        "status": "completed",
    }

    _patrol_history.append(patrol_record)
    _patrol_active = False

    logger.info(f"Patrol {patrol_record['patrol_id']} completed: {len(findings)} findings in {duration}s")

    # Broadcast findings
    try:
        from app.main import alert_manager
        if findings:
            await alert_manager.broadcast({
                "type": "patrol_complete",
                "patrol_id": patrol_record["patrol_id"],
                "findings": findings,
            })
    except Exception:
        pass

    return patrol_record


@router.get("/history")
async def get_patrol_history(limit: int = 20):
    """Get patrol history."""
    return {
        "history": _patrol_history[-limit:],
        "total": len(_patrol_history),
    }