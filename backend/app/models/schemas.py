from pydantic import BaseModel
from typing import Any, Dict, List, Optional


class ChatMessage(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    type: str  # "text", "tool_call", "tool_result", "error"
    content: Optional[str] = None
    tool: Optional[str] = None
    args: Optional[Dict[str, Any]] = None
    result_preview: Optional[str] = None


class HealthOverview(BaseModel):
    total_indices: int
    unhealthy_indices: int
    total_alerts: int
    alerts: List[Dict[str, Any]]
    health_score: int


class Alert(BaseModel):
    severity: str
    index: Optional[str] = None
    message: str
    recommendation: Optional[str] = None


class ESConnectionConfig(BaseModel):
    url: str
    api_key: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None


class PatrolResult(BaseModel):
    timestamp: str
    issues_found: int
    new_alerts: List[Dict[str, Any]]
    health_score: int
    details: Optional[str] = None


class RemediationAction(BaseModel):
    action_id: str
    action_type: str  # "reindex", "update_settings", "allocate_shard", etc.
    index: Optional[str] = None
    description: str
    risk_level: str = "low"  # low, medium, high
    estimated_impact: str = ""
    status: str = "proposed"  # proposed, approved, executed, failed


class RemediationRequest(BaseModel):
    action_id: str
    approved: bool


class ImpactMetrics(BaseModel):
    revenue_at_risk: float = 0.0
    customers_affected: int = 0
    mttr_minutes: float = 0.0
    uptime_percent: float = 99.9
    incidents_last_24h: int = 0
