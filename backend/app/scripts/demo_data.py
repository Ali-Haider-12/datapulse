"""
Demo Data Generator — Creates realistic Elasticsearch demo data for testing.

Provides static methods that generate index definitions, shard states,
and sample log entries for use in tests and seed scripts.
"""

import random
from datetime import datetime, timedelta
from typing import List, Dict, Any


class DemoDataGenerator:
    """Generate realistic Elasticsearch demo data."""

    SERVICES = [
        "api-gateway", "auth-service", "payment-processor",
        "user-service", "order-service", "inventory-service",
        "notification-service", "search-service",
    ]
    LOG_LEVELS = ["info", "info", "info", "info", "warn", "warn", "error", "error", "debug"]
    ERROR_TYPES = [
        "ConnectionTimeout", "RateLimitExceeded", "DatabaseError",
        "AuthenticationFailed", "ValidationError", "OutOfMemory",
    ]

    @staticmethod
    def generate_indices() -> List[Dict[str, Any]]:
        """Generate a list of Elasticsearch index definitions."""
        return [
            {
                "name": "logs-2026-05",
                "health": "yellow",
                "status": "open",
                "docs": 10234,
                "store_size_mb": 45.2,
                "shards": 3,
                "replicas": 1,
            },
            {
                "name": "logs-2026-04",
                "health": "green",
                "status": "open",
                "docs": 89201,
                "store_size_mb": 312.7,
                "shards": 5,
                "replicas": 1,
            },
            {
                "name": "metrics-2026-05",
                "health": "green",
                "status": "open",
                "docs": 45000,
                "store_size_mb": 128.4,
                "shards": 1,
                "replicas": 1,
            },
            {
                "name": "products",
                "health": "yellow",
                "status": "open",
                "docs": 12500,
                "store_size_mb": 67.8,
                "shards": 2,
                "replicas": 0,
            },
            {
                "name": "orders",
                "health": "green",
                "status": "open",
                "docs": 34500,
                "store_size_mb": 198.3,
                "shards": 3,
                "replicas": 1,
            },
            {
                "name": "users",
                "health": "green",
                "status": "open",
                "docs": 8200,
                "store_size_mb": 22.1,
                "shards": 1,
                "replicas": 1,
            },
        ]

    @staticmethod
    def generate_shard_data() -> List[Dict[str, Any]]:
        """Generate shard allocation data with some unassigned shards."""
        shards = []
        nodes = ["node-1", "node-2", "node-3"]

        for idx_def in DemoDataGenerator.generate_indices():
            for shard_id in range(idx_def["shards"]):
                for replica in range(idx_def["replicas"] + 1):
                    # Primary and some replicas get unassigned to simulate issues
                    if random.random() < 0.15:
                        state = "UNASSIGNED"
                        node = None
                    else:
                        state = random.choice(["STARTED", "STARTED", "STARTED", "RELOCATING", "INITIALIZING"])
                        node = random.choice(nodes)

                    shards.append({
                        "index": idx_def["name"],
                        "shard": shard_id,
                        "primary": replica == 0,
                        "state": state,
                        "node": node,
                        "unassigned_info": {
                            "reason": "NODE_LEFT" if state == "UNASSIGNED" and random.random() > 0.5 else "ALLOCATION_FAILED",
                            "at": (datetime.utcnow() - timedelta(minutes=random.randint(1, 60))).isoformat(),
                        } if state == "UNASSIGNED" else None,
                    })
        return shards

    @staticmethod
    def generate_sample_logs(count: int = 50) -> List[Dict[str, Any]]:
        """Generate sample log entries with realistic distributions."""
        logs = []
        now = datetime.utcnow()

        for i in range(count):
            ts = now - timedelta(minutes=random.randint(0, 1440))
            level = random.choice(DemoDataGenerator.LOG_LEVELS)
            service = random.choice(DemoDataGenerator.SERVICES)

            # Error spike simulation for payment-processor
            if service == "payment-processor" and ts > now - timedelta(hours=2):
                if random.random() < 0.4:
                    level = "error"

            log_entry = {
                "timestamp": ts.isoformat() + "Z",
                "level": level,
                "service": service,
                "message": (
                    f"Request processed by {service}"
                    if level != "error"
                    else f"{random.choice(DemoDataGenerator.ERROR_TYPES)} in {service}"
                ),
                "error_type": (
                    random.choice(DemoDataGenerator.ERROR_TYPES)
                    if level == "error"
                    else None
                ),
                "http_code": random.choice([200, 200, 200, 201, 301, 400, 401, 404, 500, 502, 503]),
                "response_time_ms": round(
                    random.uniform(10, 2000) if level == "error" else random.uniform(5, 200), 2
                ),
                "host": f"host-{random.randint(1, 5)}",
            }
            logs.append(log_entry)

        return logs