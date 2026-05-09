"""
Postmortem Generator — Creates comprehensive incident postmortems.

Generates HTML and Markdown postmortems with:
- Full incident timeline
- AI-generated root cause analysis
- Impact metrics
- Remediation actions taken
- Lessons learned
- Auto-email via Gmail MCP (when configured)
"""

import io
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services.mcp_client import ElasticMCPClient
from app.services.llm_provider import LLMProvider
from app.services.incident_response import IncidentResponseEngine

logger = logging.getLogger(__name__)


class PostmortemGenerator:
    """Generate comprehensive incident postmortems."""

    def __init__(
        self,
        mcp_client: ElasticMCPClient = None,
        llm_provider: LLMProvider = None,
    ):
        self.mcp_client = mcp_client
        self.llm_provider = llm_provider

    async def generate_postmortem(
        self,
        incident_id: str,
        incident_data: Dict[str, Any] = None,
        engine: IncidentResponseEngine = None,
        format: str = "markdown",
    ) -> Dict[str, Any]:
        """
        Generate a postmortem for an incident.

        Args:
            incident_id: The incident ID
            incident_data: Pre-existing incident data
            engine: IncidentResponseEngine for fetching incident details
            format: Output format ("markdown", "html", "json")

        Returns:
            Dict with postmortem content and metadata
        """
        # Get incident data
        if engine and incident_id in engine.active_incidents:
            incident = engine.active_incidents[incident_id]
            incident_data = incident.to_dict()
        elif not incident_data:
            incident_data = {
                "id": incident_id,
                "title": incident_id,
                "severity": "unknown",
                "status": "resolved",
                "investigation_steps": [],
                "diagnosis": {},
                "remediation_actions": [],
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }

        # Gather timeline data from ES logs
        timeline = await self._get_incident_timeline(incident_data)

        # Generate AI-powered root cause analysis if LLM available
        ai_analysis = await self._get_ai_analysis(incident_data, timeline)

        # Extract key metrics
        metrics = await self._get_incident_metrics(incident_data)

        # Build postmortem content
        postmortem = {
            "incident_id": incident_id,
            "title": incident_data.get("title", f"Incident {incident_id}"),
            "severity": incident_data.get("severity", "unknown"),
            "status": incident_data.get("status", "resolved"),
            "created_at": incident_data.get("created_at", datetime.utcnow().isoformat()),
            "resolved_at": incident_data.get("updated_at", datetime.utcnow().isoformat()),
            "timeline": timeline,
            "root_cause": incident_data.get("diagnosis", {}).get("root_cause", ai_analysis.get("root_cause", "Under investigation")),
            "impact": incident_data.get("diagnosis", {}).get("impact", ai_analysis.get("impact", "Assessed automatically")),
            "confidence": incident_data.get("diagnosis", {}).get("confidence", ai_analysis.get("confidence", 0.0)),
            "ai_analysis": ai_analysis.get("full_analysis", ""),
            "metrics": metrics,
            "remediation_actions": incident_data.get("remediation_actions", []),
            "lessons_learned": self._generate_lessons_learned(incident_data, timeline),
            "preventive_actions": self._generate_preventive_actions(incident_data),
            "generated_at": datetime.utcnow().isoformat(),
        }

        # Render in requested format
        if format == "html":
            postmortem["content_html"] = self._render_html(postmortem)
            postmortem["content_type"] = "text/html"
        elif format == "json":
            postmortem["content_json"] = json.dumps(postmortem, indent=2, default=str)
            postmortem["content_type"] = "application/json"
        else:  # markdown (default)
            postmortem["content_markdown"] = self._render_markdown(postmortem)
            postmortem["content_type"] = "text/markdown"

        return postmortem

    # ── Timeline Gathering ──────────────────────────────────────────

    async def _get_incident_timeline(self, incident_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Build incident timeline from investigation steps and ES logs."""
        timeline = []

        # Add creation event
        timeline.append({
            "timestamp": incident_data.get("created_at", datetime.utcnow().isoformat()),
            "event": "Incident detected",
            "details": incident_data.get("title", ""),
            "severity": "critical",
        })

        # Add investigation steps
        for step in incident_data.get("investigation_steps", []):
            timeline.append({
                "timestamp": step.get("timestamp", ""),
                "event": f"Investigation: {step.get('tool', 'unknown')}",
                "details": step.get("result_summary", ""),
                "severity": "info",
            })

        # Query ES logs for relevant events around the incident
        if self.mcp_client:
            try:
                start_time = incident_data.get("created_at", "")
                query = (
                    'FROM logs-* | WHERE @timestamp >= "'
                    + start_time
                    + '" | STATS count = COUNT(*) BY level | SORT count DESC | LIMIT 5'
                )
                result = await self.mcp_client.esql(query)
                for row in result.get("values", []):
                    if len(row) >= 2:
                        timeline.append({
                            "timestamp": start_time,
                            "event": f"Log analysis: {row[0]}",
                            "details": f"{int(row[1])} log entries",
                            "severity": "warning" if row[0] == "error" else "info",
                        })
            except Exception as e:
                logger.debug(f"Timeline log query failed: {e}")

        # Add resolution event
        timeline.append({
            "timestamp": incident_data.get("updated_at", datetime.utcnow().isoformat()),
            "event": "Incident resolved",
            "details": "Auto-resolved or remediated",
            "severity": "success",
        })

        return sorted(timeline, key=lambda x: x.get("timestamp", ""))

    # ── AI Analysis ──────────────────────────────────────────────────

    async def _get_ai_analysis(
        self, incident_data: Dict[str, Any], timeline: List[Dict]
    ) -> Dict[str, Any]:
        """Use LLM to generate root cause analysis and insights."""
        if not self.llm_provider:
            return {
                "root_cause": "Manual analysis required",
                "impact": "Unable to assess without LLM",
                "confidence": 0.0,
            }

        try:
            prompt = f"""You are a senior SRE performing a postmortem analysis.

Incident: {incident_data.get('title', 'Unknown')}
Severity: {incident_data.get('severity', 'unknown')}
Status: {incident_data.get('status', 'unknown')}

Investigation Steps:
{json.dumps(incident_data.get('investigation_steps', []), default=str)[:2000]}

Timeline Events:
{json.dumps(timeline, default=str)[:2000]}

Remediation Actions:
{json.dumps(incident_data.get('remediation_actions', []), default=str)[:1000]}

Provide:
1. Root cause analysis (what actually went wrong?)
2. Business impact assessment
3. Whether this is a novel failure or known pattern
4. Confidence level (0-1)

Be concise and actionable."""

            response_text = ""
            async for chunk in self.llm_provider.chat(prompt):
                if chunk.get("type") == "text":
                    response_text += chunk.get("content", "")

            # Parse structured response (simplified extraction)
            return {
                "root_cause": self._extract_section(response_text, "Root cause"),
                "full_analysis": response_text,
                "impact": self._extract_section(response_text, "impact"),
                "confidence": 0.8,  # Base confidence for AI-generated analysis
                "is_known_pattern": "known" in response_text.lower(),
            }

        except Exception as e:
            logger.warning(f"AI postmortem analysis failed: {e}")
            return {
                "root_cause": incident_data.get("diagnosis", {}).get("root_cause", "Analysis failed"),
                "full_analysis": "",
                "impact": incident_data.get("diagnosis", {}).get("impact", ""),
                "confidence": 0.0,
            }

    def _extract_section(self, text: str, keyword: str) -> str:
        """Extract a section from analysis text by keyword."""
        lines = text.split("\n")
        capture = False
        result = []
        for line in lines:
            if keyword.lower() in line.lower():
                capture = True
                # Skip the header line itself
                continue
            if capture:
                if line.strip().startswith("**") and "**" in line.strip():
                    break
                result.append(line.strip())
        return " ".join(result)[:500] if result else text[:500]

    # ── Metrics ──────────────────────────────────────────────────────

    async def _get_incident_metrics(self, incident_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate metrics related to the incident."""
        created = incident_data.get("created_at", "")
        resolved = incident_data.get("updated_at", "")

        # Calculate MTTR
        try:
            start = datetime.fromisoformat(created.replace("Z", "+00:00"))
            end = datetime.fromisoformat(resolved.replace("Z", "+00:00"))
            mttr_minutes = (end - start).total_seconds() / 60
        except Exception:
            mttr_minutes = 0.0

        return {
            "mttr_minutes": round(mttr_minutes, 1),
            "investigation_steps_count": len(incident_data.get("investigation_steps", [])),
            "remediation_actions_count": len(incident_data.get("remediation_actions", [])),
            "revenue_at_risk": self._estimate_revenue_impact(incident_data),
        }

    def _estimate_revenue_impact(self, incident_data: Dict[str, Any]) -> float:
        """Estimate revenue impact based on severity and duration."""
        severity_multipliers = {
            "critical": 5000,
            "high": 2000,
            "medium": 500,
            "low": 100,
        }
        severity = incident_data.get("severity", "medium")
        multiplier = severity_multipliers.get(severity, 500)

        try:
            created = datetime.fromisoformat(incident_data.get("created_at", datetime.utcnow().isoformat()).replace("Z", "+00:00"))
            resolved = datetime.fromisoformat(incident_data.get("updated_at", datetime.utcnow().isoformat()).replace("Z", "+00:00"))
            duration_hours = max((resolved - created).total_seconds() / 3600, 0.1)
        except Exception:
            duration_hours = 1.0

        return multiplier * duration_hours

    # ── Recommendations ─────────────────────────────────────────────

    def _generate_lessons_learned(self, incident_data: Dict, timeline: List[Dict]) -> List[str]:
        """Generate lessons learned from the incident."""
        lessons = []
        severity = incident_data.get("severity", "")

        if severity in ("critical", "high"):
            lessons.append("Critical incidents should trigger immediate war room activation — delays compound impact")

        investigation_steps = incident_data.get("investigation_steps", [])
        if len(investigation_steps) > 5:
            lessons.append("Investigation took many steps — consider pre-built diagnostic playbooks")

        remediation_actions = incident_data.get("remediation_actions", [])
        approved_actions = [a for a in remediation_actions if a.get("status") == "executed"]
        if not approved_actions:
            lessons.append("No automated remediation was available — build runbooks for common failures")

        lessons.append("Postmortem should be reviewed within 48 hours while context is fresh")
        lessons.append(f"Detection took {'automated' if len(investigation_steps) < 3 else 'manual'} path — {'keep' if len(investigation_steps) < 3 else 'improve'} monitoring")

        return lessons

    def _generate_preventive_actions(self, incident_data: Dict) -> List[Dict[str, str]]:
        """Generate preventive actions to avoid recurrence."""
        actions = [
            {
                "action": "Add monitoring alert for the detected condition",
                "priority": "HIGH",
                "owner": "SRE Team",
                "deadline": "1 week",
            },
            {
                "action": "Create automated runbook for this incident type",
                "priority": "HIGH",
                "owner": "Platform Team",
                "deadline": "2 weeks",
            },
            {
                "action": "Review capacity planning and add headroom",
                "priority": "MEDIUM",
                "owner": "Infrastructure Team",
                "deadline": "1 month",
            },
            {
                "action": "Update chaos engineering tests to cover this failure mode",
                "priority": "MEDIUM",
                "owner": "QA/SRE Team",
                "deadline": "1 month",
            },
        ]

        severity = incident_data.get("severity", "")
        if severity == "critical":
            actions.insert(0, {
                "action": "Implement circuit breaker or bulkhead for affected service",
                "priority": "CRITICAL",
                "owner": "Architecture Team",
                "deadline": "3 days",
            })

        return actions

    # ── Rendering ────────────────────────────────────────────────────

    def _render_markdown(self, postmortem: Dict[str, Any]) -> str:
        """Render postmortem as Markdown."""
        lines = [
            f"# 📋 Postmortem: {postmortem['title']}",
            "",
            f"**Incident ID**: `{postmortem['incident_id']}`",
            f"**Severity**: {postmortem['severity'].upper()}",
            f"**Status**: {postmortem['status']}",
            f"**Created**: {postmortem['created_at']}",
            f"**Resolved**: {postmortem['resolved_at']}",
            f"**MTTR**: {postmortem['metrics'].get('mttr_minutes', 0)} minutes",
            f"**Generated**: {postmortem['generated_at']}",
            "",
            "---",
            "",
            "## 🔍 Root Cause Analysis",
            "",
            f"**Root Cause**: {postmortem['root_cause']}",
            "",
            f"**Impact**: {postmortem['impact']}",
            "",
            f"**Confidence**: {postmortem.get('confidence', 0) * 100:.0f}%",
            "",
        ]

        if postmortem.get("ai_analysis"):
            lines.extend(["## 🤖 AI-Generated Analysis", "", postmortem["ai_analysis"], ""])

        # Timeline
        lines.extend(["## ⏱️ Incident Timeline", ""])
        for i, event in enumerate(postmortem["timeline"], 1):
            ts = event.get("timestamp", "")[:19] if event.get("timestamp") else "—"
            lines.append(f"{i}. **{ts}** [{event.get('severity', 'info').upper()}] {event.get('event', '')}")
            if event.get("details"):
                lines.append(f"   {event['details']}")
        lines.append("")

        # Remediation Actions
        actions = postmortem.get("remediation_actions", [])
        if actions:
            lines.extend(["## 🔧 Remediation Actions Taken", ""])
            for action in actions:
                status_emoji = "✅" if action.get("status") == "executed" else "⏳" if action.get("status") == "approved" else "❌"
                lines.append(f"- {status_emoji} **{action.get('description', 'N/A')}** (Risk: {action.get('risk_level', 'unknown')})")
            lines.append("")

        # Metrics
        lines.extend(["## 📊 Incident Metrics", ""])
        metrics = postmortem.get("metrics", {})
        lines.append(f"- **MTTR**: {metrics.get('mttr_minutes', 0)} minutes")
        lines.append(f"- **Investigation Steps**: {metrics.get('investigation_steps_count', 0)}")
        lines.append(f"- **Revenue at Risk**: ${metrics.get('revenue_at_risk', 0):,.0f}")
        lines.append("")

        # Lessons Learned
        lessons = postmortem.get("lessons_learned", [])
        if lessons:
            lines.extend(["## 📝 Lessons Learned", ""])
            for lesson in lessons:
                lines.append(f"- {lesson}")
            lines.append("")

        # Preventive Actions
        preventive = postmortem.get("preventive_actions", [])
        if preventive:
            lines.extend(["## 🛡️ Preventive Actions", ""])
            lines.append("| Priority | Action | Owner | Deadline |")
            lines.append("|----------|--------|-------|----------|")
            for action in preventive:
                lines.append(f"| {action.get('priority', '-')} | {action.get('action', '-')} | {action.get('owner', '-')} | {action.get('deadline', '-')} |")
            lines.append("")

        return "\n".join(lines)

    def _render_html(self, postmortem: Dict[str, Any]) -> str:
        """Render postmortem as styled HTML."""
        severity_colors = {
            "critical": "#dc2626",
            "high": "#ea580c",
            "medium": "#ca8a04",
            "low": "#16a34a",
        }
        severity_color = severity_colors.get(postmortem.get("severity", "medium"), "#ca8a04")

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Postmortem: {postmortem['title']}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 0 auto; padding: 2rem; color: #1a1a1a; background: #fafafa; }}
  .header {{ border-bottom: 3px solid {severity_color}; padding-bottom: 1rem; margin-bottom: 2rem; }}
  .header h1 {{ margin: 0; color: #111827; }}
  .meta {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; margin: 1rem 0; }}
  .meta-item {{ background: #f3f4f6; padding: 0.5rem 1rem; border-radius: 0.375rem; }}
  .meta-label {{ font-size: 0.75rem; color: #6b7280; text-transform: uppercase; }}
  .meta-value {{ font-weight: 600; }}
  .severity-badge {{ display: inline-block; padding: 0.25rem 0.75rem; border-radius: 1rem; color: white; font-weight: 600; font-size: 0.85rem; }}
  .severity-critical {{ background: #dc2626; }}
  .severity-high {{ background: #ea580c; }}
  .severity-medium {{ background: #ca8a04; }}
  .severity-low {{ background: #16a34a; }}
  section {{ margin: 2rem 0; }}
  section h2 {{ border-bottom: 1px solid #e5e7eb; padding-bottom: 0.5rem; color: #374151; }}
  .timeline {{ position: relative; padding-left: 2rem; }}
  .timeline::before {{ content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 2px; background: #e5e7eb; }}
  .timeline-item {{ position: relative; margin-bottom: 1rem; padding-left: 1rem; }}
  .timeline-item::before {{ content: ''; position: absolute; left: -2rem; top: 0.5rem; width: 12px; height: 12px; border-radius: 50%; background: {severity_color}; border: 2px solid white; box-shadow: 0 0 0 2px {severity_color}; }}
  table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
  th, td {{ padding: 0.75rem; text-align: left; border-bottom: 1px solid #e5e7eb; }}
  th {{ background: #f9fafb; font-weight: 600; }}
  .lessons li {{ margin-bottom: 0.5rem; }}
  .footer {{ margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 0.85rem; }}
</style>
</head>
<body>

<div class="header">
  <h1>📋 Postmortem: {postmortem['title']}</h1>
  <div style="margin-top: 0.5rem;">
    <span class="severity-badge severity-{postmortem.get('severity', 'medium')}">{postmortem.get('severity', 'unknown').upper()}</span>
  </div>
</div>

<div class="meta">
  <div class="meta-item">
    <div class="meta-label">Incident ID</div>
    <div class="meta-value">{postmortem['incident_id']}</div>
  </div>
  <div class="meta-item">
    <div class="meta-label">MTTR</div>
    <div class="meta-value">{postmortem['metrics'].get('mttr_minutes', 0)} minutes</div>
  </div>
  <div class="meta-item">
    <div class="meta-label">Created</div>
    <div class="meta-value">{postmortem['created_at']}</div>
  </div>
  <div class="meta-item">
    <div class="meta-label">Resolved</div>
    <div class="meta-value">{postmortem['resolved_at']}</div>
  </div>
</div>

<section>
  <h2>🔍 Root Cause Analysis</h2>
  <p><strong>Root Cause:</strong> {postmortem['root_cause']}</p>
  <p><strong>Impact:</strong> {postmortem['impact']}</p>
  <p><strong>Confidence:</strong> {postmortem.get('confidence', 0) * 100:.0f}%</p>
</section>

{"<section><h2>🤖 AI-Generated Analysis</h2><pre>" + postmortem['ai_analysis'] + "</pre></section>" if postmortem.get('ai_analysis') else ''}

<section>
  <h2>⏱️ Incident Timeline</h2>
  <div class="timeline">
"""

        for event in postmortem["timeline"]:
            ts = event.get("timestamp", "")[:19] if event.get("timestamp") else "—"
            html += f"""    <div class="timeline-item">
      <strong>{ts}</strong> [{event.get('severity', 'info').upper()}] {event.get('event', '')}<br>
      <span style="color: #6b7280;">{event.get('details', '')}</span>
    </div>
"""

        html += """  </div>
</section>
"""

        # Remediation Actions
        actions = postmortem.get("remediation_actions", [])
        if actions:
            html += """<section>
  <h2>🔧 Remediation Actions Taken</h2>
  <table>
    <tr><th>Description</th><th>Risk Level</th><th>Status</th></tr>
"""
            for action in actions:
                html += f"""    <tr><td>{action.get('description', 'N/A')}</td><td>{action.get('risk_level', '-')}</td><td>{action.get('status', '-')}</td></tr>
"""
            html += "  </table>\n</section>\n"

        # Metrics
        html += """<section>
  <h2>📊 Incident Metrics</h2>
  <div class="meta">
    <div class="meta-item">
      <div class="meta-label">MTTR</div>
      <div class="meta-value">""" + f"""{postmortem['metrics'].get('mttr_minutes', 0)} min</div>
    </div>
    <div class="meta-item">
      <div class="meta-label">Revenue at Risk</div>
      <div class="meta-value">${postmortem['metrics'].get('revenue_at_risk', 0):,.0f}</div>
    </div>
  </div>
</section>
"""

        # Preventive Actions
        preventive = postmortem.get("preventive_actions", [])
        if preventive:
            html += """<section>
  <h2>🛡️ Preventive Actions</h2>
  <table>
    <tr><th>Priority</th><th>Action</th><th>Owner</th><th>Deadline</th></tr>
"""
            for action in preventive:
                html += f"""    <tr><td>{action.get('priority', '-')}</td><td>{action.get('action', '-')}</td><td>{action.get('owner', '-')}</td><td>{action.get('deadline', '-')}</td></tr>
"""
            html += "  </table>\n</section>\n"

        html += f"""
<div class="footer">
  Generated by DataPulse Postmortem Generator • {postmortem['generated_at']}
</div>

</body>
</html>"""

        return html

    # ── Email Integration ───────────────────────────────────────────

    async def email_postmortem(self, postmortem: Dict[str, Any], recipient: str) -> bool:
        """
        Email postmortem via Gmail MCP.

        Args:
            postmortem: Postmortem data
            recipient: Email address

        Returns:
            True if sent successfully
        """
        try:
            from app.services.mcp_servers.gmail_mcp import GmailMCPServer

            gmail = GmailMCPServer()
            markdown_body = postmortem.get("content_markdown", "")
            html_body = postmortem.get("content_html", markdown_body)

            success = await gmail.send_email(
                to=recipient,
                subject=f"Postmortem: {postmortem['title']} ({postmortem['incident_id']})",
                body=html_body,
                is_html=True,
            )
            return success
        except ImportError:
            logger.warning("Gmail MCP not available — postmortem not emailed")
            return False
        except Exception as e:
            logger.error(f"Failed to email postmortem: {e}")
            return False