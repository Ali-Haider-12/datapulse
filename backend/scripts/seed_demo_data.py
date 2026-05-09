"""
Seed Elasticsearch with realistic demo data for the DataPulse demo.
Creates indices with log data, error patterns, and anomalies.

Usage:
    python scripts/seed_demo_data.py [--es-url http://localhost:9200]
"""
import httpx
import json
import random
import argparse
from datetime import datetime, timezone, timedelta
import asyncio

SERVICES = [
    "api-gateway", "auth-service", "payment-processor",
    "user-service", "order-service", "inventory-service", "notification-service",
]
LOG_LEVELS = ["info", "info", "info", "info", "warn", "warn", "error", "error", "error", "debug"]
ERROR_TYPES = [
    "ConnectionTimeout", "RateLimitExceeded", "DatabaseError",
    "AuthenticationFailed", "ValidationError", "OutOfMemory",
]
HTTP_CODES = [200, 200, 200, 200, 201, 301, 400, 401, 403, 404, 500, 502, 503]


async def create_indices(es_url: str):
    """Create demo indices with proper mappings."""
    async with httpx.AsyncClient() as client:
        # Create logs index
        logs_mapping = {
            "mappings": {
                "dynamic": "strict",
                "properties": {
                    "timestamp": {"type": "date"},
                    "level": {"type": "keyword"},
                    "service": {"type": "keyword"},
                    "message": {"type": "text"},
                    "error_type": {"type": "keyword"},
                    "http_code": {"type": "integer"},
                    "response_time_ms": {"type": "float"},
                    "host": {"type": "keyword"},
                },
            },
            "settings": {"number_of_shards": 3, "number_of_replicas": 1},
        }
        resp = await client.put(f"{es_url}/logs-2026-05", json=logs_mapping)
        print(f"  logs-2026-05: {resp.status_code}")

        # Create metrics index
        metrics_mapping = {
            "mappings": {
                "dynamic": "strict",
                "properties": {
                    "timestamp": {"type": "date"},
                    "service": {"type": "keyword"},
                    "cpu_percent": {"type": "float"},
                    "memory_mb": {"type": "float"},
                    "request_count": {"type": "integer"},
                    "error_count": {"type": "integer"},
                    "avg_latency_ms": {"type": "float"},
                },
            },
            "settings": {"number_of_shards": 1, "number_of_replicas": 1},
        }
        resp = await client.put(f"{es_url}/metrics-2026-05", json=metrics_mapping)
        print(f"  metrics-2026-05: {resp.status_code}")

        # Create products index (dynamic mapping for explosion demo)
        products_mapping = {
            "mappings": {
                "dynamic": True,
                "properties": {
                    "name": {"type": "text"},
                    "category": {"type": "keyword"},
                    "price": {"type": "float"},
                    "in_stock": {"type": "boolean"},
                },
            },
        }
        resp = await client.put(f"{es_url}/products", json=products_mapping)
        print(f"  products: {resp.status_code}")

        # Create orders index
        orders_mapping = {
            "mappings": {
                "dynamic": "strict",
                "properties": {
                    "timestamp": {"type": "date"},
                    "customer_id": {"type": "keyword"},
                    "total": {"type": "float"},
                    "status": {"type": "keyword"},
                    "items": {"type": "integer"},
                },
            },
        }
        resp = await client.put(f"{es_url}/orders", json=orders_mapping)
        print(f"  orders: {resp.status_code}")


async def seed_logs(es_url: str):
    """Generate 10,000 log entries over the last 7 days with realistic patterns."""
    bulk_data = []
    now = datetime.now(timezone.utc)
    base_time = now - timedelta(days=7)

    for i in range(10000):
        ts = base_time + timedelta(minutes=random.randint(0, 7 * 24 * 60))
        level = random.choice(LOG_LEVELS)
        service = random.choice(SERVICES)
        http_code = random.choice(HTTP_CODES)

        # Simulate anomaly: error spike in last 2 hours for payment-processor
        if service == "payment-processor" and ts > now - timedelta(hours=2):
            if random.random() < 0.4:
                level = "error"
                http_code = random.choice([500, 502, 503])

        log_entry = {
            "timestamp": ts.isoformat() + "Z",
            "level": level,
            "service": service,
            "message": (
                f"Request processed by {service}"
                if level != "error"
                else f"{random.choice(ERROR_TYPES)} in {service}"
            ),
            "error_type": random.choice(ERROR_TYPES) if level == "error" else None,
            "http_code": http_code,
            "response_time_ms": round(
                random.uniform(10, 2000) if level == "error" else random.uniform(5, 200), 2
            ),
            "host": f"host-{random.randint(1, 5)}",
        }

        bulk_data.append(json.dumps({"index": {"_index": "logs-2026-05"}}))
        bulk_data.append(json.dumps(log_entry))

        # Flush in batches of 1000
        if len(bulk_data) >= 2000:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{es_url}/_bulk",
                    data="\n".join(bulk_data) + "\n",
                    headers={"Content-Type": "application/x-ndjson"},
                )
            bulk_data = []

    # Flush remaining
    if bulk_data:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{es_url}/_bulk",
                data="\n".join(bulk_data) + "\n",
                headers={"Content-Type": "application/x-ndjson"},
            )
    print(f"  Seeded 10,000 log entries")


async def seed_products(es_url: str):
    """Seed product data with dynamic fields to demo mapping issues."""
    bulk_data = []
    categories = ["electronics", "clothing", "books", "home", "toys", "sports"]

    for i in range(500):
        product = {
            "name": f"Product {i}",
            "category": random.choice(categories),
            "price": round(random.uniform(5, 500), 2),
            "in_stock": random.random() > 0.2,
        }
        # Add random dynamic fields (simulating unstructured data)
        if random.random() < 0.3:
            product[f"custom_attr_{random.randint(1, 80)}"] = random.choice(
                ["value_a", "value_b", "value_c"]
            )

        bulk_data.append(json.dumps({"index": {"_index": "products"}}))
        bulk_data.append(json.dumps(product))

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{es_url}/_bulk",
            data="\n".join(bulk_data) + "\n",
            headers={"Content-Type": "application/x-ndjson"},
        )
    print(f"  Seeded 500 products")


async def seed_orders(es_url: str):
    """Seed order data with a recent ingestion drop (anomaly)."""
    bulk_data = []
    now = datetime.now(timezone.utc)
    base_time = now - timedelta(days=3)
    count = 0

    for i in range(3000):
        ts = base_time + timedelta(minutes=random.randint(0, 3 * 24 * 60))

        # Simulate ingestion drop: fewer orders in the last hour
        if ts > now - timedelta(hours=1):
            if random.random() < 0.3:
                continue

        statuses = ["completed", "completed", "completed", "pending", "cancelled", "refunded"]
        order = {
            "timestamp": ts.isoformat() + "Z",
            "customer_id": f"cust-{random.randint(1, 200)}",
            "total": round(random.uniform(10, 500), 2),
            "status": random.choice(statuses),
            "items": random.randint(1, 10),
        }

        bulk_data.append(json.dumps({"index": {"_index": "orders"}}))
        bulk_data.append(json.dumps(order))
        count += 1

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{es_url}/_bulk",
            data="\n".join(bulk_data) + "\n",
            headers={"Content-Type": "application/x-ndjson"},
        )
    print(f"  Seeded {count} orders")


async def main(es_url: str = "http://localhost:9200"):
    print(f"Seeding demo data to {es_url}...")
    print("\nCreating indices:")
    await create_indices(es_url)

    print("\nSeeding data:")
    await seed_logs(es_url)
    await seed_products(es_url)
    await seed_orders(es_url)

    # Refresh all indices
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{es_url}/_all/_refresh")
    print(f"\nRefreshed indices: {resp.status_code}")
    print("Demo data seeded successfully! ✅")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--es-url", default="http://localhost:9200")
    args = parser.parse_args()
    asyncio.run(main(args.es_url))
