"""
Enhanced MCP Registry — Health checks, circuit breaker, dynamic registration.

Manages multiple MCP server connections with automatic failover,
health monitoring, and circuit breaker pattern for resilience.
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

from app.core.config import settings

logger = logging.getLogger(__name__)


class ServerStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    CIRCUIT_OPEN = "circuit_open"


class CircuitBreaker:
    """Circuit breaker pattern for MCP server resilience."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60, half_open_max: int = 3):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max = half_open_max

        self.failures = 0
        self.last_failure_time: Optional[float] = None
        self.state: ServerStatus = ServerStatus.HEALTHY
        self.half_open_attempts = 0

    def record_success(self) -> None:
        """Reset circuit on successful call."""
        if self.state == ServerStatus.CIRCUIT_OPEN:
            logger.info("Circuit breaker transitioning to HALF_OPEN")
            self.state = ServerStatus.DEGRADED
            self.half_open_attempts = 0
        self.failures = 0
        self.state = ServerStatus.HEALTHY

    def record_failure(self) -> None:
        """Record a failure and potentially trip the circuit."""
        self.failures += 1
        self.last_failure_time = time.monotonic()

        if self.failures >= self.failure_threshold:
            if self.state != ServerStatus.CIRCUIT_OPEN:
                logger.warning(f"Circuit breaker OPEN after {self.failures} failures")
            self.state = ServerStatus.CIRCUIT_OPEN

    @property
    def allows_request(self) -> bool:
        """Check if a request should be allowed through."""
        if self.state == ServerStatus.HEALTHY:
            return True
        if self.state == ServerStatus.DEGRADED:
            return True  # Allow probe requests
        if self.state == ServerStatus.CIRCUIT_OPEN:
            # Check if recovery timeout has elapsed
            if self.last_failure_time and (time.monotonic() - self.last_failure_time) > self.recovery_timeout:
                self.state = ServerStatus.DEGRADED
                self.half_open_attempts = 0
                logger.info("Circuit breaker transitioning to HALF_OPEN for probe")
                return True
            return False
        return False


class MCPRegistry:
    """
    Enhanced registry for MCP servers with:
    - Health checks (active + passive)
    - Circuit breaker pattern per server
    - Dynamic registration/deregistration
    - Request routing with automatic failover
    """

    def __init__(self, health_check_interval: int = 30):
        self._servers: Dict[str, Dict[str, Any]] = {}  # name -> {url, status, breaker, ...}
        self._health_check_interval = health_check_interval
        self._last_health_check: Dict[str, float] = {}
        self._health_check_task: Optional[asyncio.Task] = None
        self._callbacks: List[callable] = []

    def register(self, server_name: str, url: str, priority: int = 0, metadata: Dict = None) -> None:
        """Register an MCP server with its base URL."""
        if not server_name or not url:
            raise ValueError("Server name and URL must be non-empty")

        self._servers[server_name] = {
            "url": url.rstrip("/"),
            "priority": priority,
            "metadata": metadata or {},
            "breaker": CircuitBreaker(),
            "status": ServerStatus.HEALTHY,
            "stats": {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "avg_response_time_ms": 0,
                "last_request_at": None,
            },
            "last_health": None,
        }
        logger.info(f"Registered MCP server: {server_name} at {url}")
        self._notify_callbacks()

    def deregister(self, server_name: str) -> bool:
        """Remove a server from the registry."""
        if server_name in self._servers:
            del self._servers[server_name]
            logger.info(f"Deregistered MCP server: {server_name}")
            self._notify_callbacks()
            return True
        return False

    def update_url(self, server_name: str, new_url: str) -> bool:
        """Dynamically update a server's URL."""
        if server_name in self._servers:
            self._servers[server_name]["url"] = new_url.rstrip("/")
            logger.info(f"Updated {server_name} URL to {new_url}")
            return True
        return False

    def list_servers(self) -> Dict[str, Dict[str, Any]]:
        """List all registered servers with status info."""
        result = {}
        for name, info in self._servers.items():
            result[name] = {
                "url": info["url"],
                "status": info["status"].value,
                "circuit_breaker_state": info["breaker"].state.value,
                "allows_requests": info["breaker"].allows_request,
                "stats": info["stats"],
                "metadata": info["metadata"],
                "last_health": info.get("last_health"),
            }
        return result

    def get_server_url(self, server_name: str) -> Optional[str]:
        """Get a server's URL if it's available."""
        info = self._servers.get(server_name)
        if info and info["breaker"].allows_request:
            return info["url"]
        return None

    def route_request(self, server_name: str, tool: str, args: Dict[str, Any]) -> Tuple[Optional[str], str, Dict[str, Any]]:
        """
        Route a request to a registered MCP server.

        Returns:
            Tuple of (server_base_url or None, tool_name, arguments)
            Returns None for URL if server is unavailable (circuit open).
        """
        if server_name not in self._servers:
            raise ValueError(f"MCP server '{server_name}' not registered")

        info = self._servers[server_name]

        if not info["breaker"].allows_request:
            logger.warning(f"Circuit breaker open for {server_name}, request blocked")
            return None, tool, args

        return info["url"], tool, args

    def record_request_result(
        self, server_name: str, success: bool, response_time_ms: float = 0
    ) -> None:
        """Record the result of a request to update circuit breaker and stats."""
        if server_name not in self._servers:
            return

        info = self._servers[server_name]
        stats = info["stats"]

        stats["total_requests"] += 1
        stats["last_request_at"] = time.monotonic()

        if response_time_ms > 0:
            # Exponential moving average for response time
            alpha = 0.1
            stats["avg_response_time_ms"] = (
                alpha * response_time_ms + (1 - alpha) * stats["avg_response_time_ms"]
            )

        if success:
            stats["successful_requests"] += 1
            info["breaker"].record_success()
            info["status"] = ServerStatus.HEALTHY
        else:
            stats["failed_requests"] += 1
            info["breaker"].record_failure()
            info["status"] = info["breaker"].state

        self._notify_callbacks()

    def get_servers_sorted_by_health(self) -> List[str]:
        """Get server names sorted by health (healthy first)."""
        def sort_key(name):
            info = self._servers[name]
            # Priority: healthy > degraded > unavailable/circuit_open
            status_order = {
                ServerStatus.HEALTHY: 0,
                ServerStatus.DEGRADED: 1,
                ServerStatus.UNAVAILABLE: 2,
                ServerStatus.CIRCUIT_OPEN: 3,
            }
            return (status_order.get(info["status"], 3), info.get("stats", {}).get("avg_response_time_ms", 9999))

        return sorted(self._servers.keys(), key=sort_key)

    def on_status_change(self, callback) -> None:
        """Register a callback for server status changes."""
        self._callbacks.append(callback)

    async def health_check_all(self) -> Dict[str, Dict[str, Any]]:
        """Run health checks on all registered servers."""
        results = {}
        for name in self._servers:
            results[name] = await self._check_server_health(name)
        return results

    async def _check_server_health(self, server_name: str) -> Dict[str, Any]:
        """Perform a health check on a single server."""
        import httpx

        info = self._servers[server_name]
        url = info["url"]
        start_time = time.monotonic()

        try:
            timeout = httpx.Timeout(5.0, connect=2.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                # Try MCP health endpoint, fallback to root
                try:
                    response = await client.get(f"{url}/mcp/health", follow_redirects=True)
                except Exception:
                    response = await client.get(f"{url}/", follow_redirects=True)

                response_time = time.monotonic() - start_time
                healthy = response.status_code < 500

                result = {
                    "status": "healthy" if healthy else "unhealthy",
                    "response_time_ms": round(response_time * 1000, 2),
                    "status_code": response.status_code,
                    "timestamp": time.monotonic(),
                }

                self.record_request_result(server_name, healthy, response_time * 1000)
                info["last_health"] = result

                logger.debug(f"Health check {server_name}: {result['status']} ({result['response_time_ms']}ms)")
                return result

        except Exception as e:
            response_time = time.monotonic() - start_time
            logger.warning(f"Health check failed for {server_name}: {e}")
            self.record_request_result(server_name, False, response_time * 1000)
            info["last_health"] = {
                "status": "unreachable",
                "error": str(e),
                "timestamp": time.monotonic(),
            }
            return info["last_health"]

    async def start_health_monitoring(self) -> None:
        """Start background health check loop."""
        async def monitor_loop():
            while True:
                try:
                    await self.health_check_all()
                except Exception as e:
                    logger.error(f"Health monitoring error: {e}")
                await asyncio.sleep(self._health_check_interval)

        if not self._health_check_task or self._health_check_task.done():
            self._health_check_task = asyncio.create_task(monitor_loop())
            logger.info(f"Health monitoring started (interval: {self._health_check_interval}s)")

    async def stop_health_monitoring(self) -> None:
        """Stop background health checking."""
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        logger.info("Health monitoring stopped")

    def _notify_callbacks(self) -> None:
        """Notify all registered callbacks of status changes."""
        for callback in self._callbacks:
            try:
                callback(self._servers)
            except Exception as e:
                logger.error(f"Status callback error: {e}")

    def reset_circuit(self, server_name: str) -> bool:
        """Manually reset a circuit breaker (admin action)."""
        if server_name in self._servers:
            self._servers[server_name]["breaker"] = CircuitBreaker()
            self._servers[server_name]["status"] = ServerStatus.HEALTHY
            logger.info(f"Circuit breaker manually reset for {server_name}")
            self._notify_callbacks()
            return True
        return False