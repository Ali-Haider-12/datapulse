"""
Mock Elasticsearch server for testing DataPulse without a real ES instance.
Runs a lightweight HTTP server that responds to the ES API endpoints
that DataPulse's MCP client and health analyzer use.

Usage:
    python scripts/mock_es_server.py [--port 9200]
"""
import json
import random
import argparse
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta

# Demo data
INDICES = [
    {"health": "green", "status": "open", "index": "logs-2026-05", "uuid": "abc123", "pri": "3", "rep": "1", "docs.count": "10000", "docs.deleted": "0", "store.size": "45.2mb", "pri.store.size": "22.6mb"},
    {"health": "green", "status": "open", "index": "metrics-2026-05", "uuid": "def456", "pri": "1", "rep": "1", "docs.count": "5000", "docs.deleted": "0", "store.size": "12.1mb", "pri.store.size": "6.05mb"},
    {"health": "yellow", "status": "open", "index": "products", "uuid": "ghi789", "pri": "1", "rep": "1", "docs.count": "500", "docs.deleted": "0", "store.size": "2.3mb", "pri.store.size": "2.3mb"},
    {"health": "green", "status": "open", "index": "orders", "uuid": "jkl012", "pri": "1", "rep": "1", "docs.count": "3000", "docs.deleted": "0", "store.size": "8.7mb", "pri.store.size": "4.35mb"},
]

PRODUCTS_MAPPING = {
    "products": {
        "mappings": {
            "dynamic": True,
            "properties": {
                "name": {"type": "text"},
                "category": {"type": "keyword"},
                "price": {"type": "float"},
                "in_stock": {"type": "boolean"},
                **{f"custom_attr_{i}": {"type": "keyword"} for i in range(1, 81)},
            }
        }
    }
}

LOGS_MAPPING = {
    "logs-2026-05": {
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
            }
        }
    }
}

SHARDS = [
    {"index": "logs-2026-05", "shard": "0", "prirep": "p", "state": "STARTED", "docs": "3333", "store": "7.5mb", "node": "node-1"},
    {"index": "logs-2026-05", "shard": "1", "prirep": "p", "state": "STARTED", "docs": "3333", "store": "7.5mb", "node": "node-1"},
    {"index": "logs-2026-05", "shard": "2", "prirep": "p", "state": "STARTED", "docs": "3334", "store": "7.6mb", "node": "node-2"},
    {"index": "logs-2026-05", "shard": "0", "prirep": "r", "state": "STARTED", "docs": "3333", "store": "7.5mb", "node": "node-2"},
    {"index": "logs-2026-05", "shard": "1", "prirep": "r", "state": "STARTED", "docs": "3333", "store": "7.5mb", "node": "node-2"},
    {"index": "logs-2026-05", "shard": "2", "prirep": "r", "state": "UNASSIGNED", "docs": "0", "store": "0b", "node": None},
    {"index": "products", "shard": "0", "prirep": "p", "state": "STARTED", "docs": "500", "store": "2.3mb", "node": "node-1"},
    {"index": "products", "shard": "0", "prirep": "r", "state": "UNASSIGNED", "docs": "0", "store": "0b", "node": None},
    {"index": "orders", "shard": "0", "prirep": "p", "state": "STARTED", "docs": "3000", "store": "4.35mb", "node": "node-1"},
    {"index": "orders", "shard": "0", "prirep": "r", "state": "STARTED", "docs": "3000", "store": "4.35mb", "node": "node-2"},
]

SEARCH_RESULTS = {
    "took": 5,
    "hits": {
        "total": {"value": 10000, "relation": "eq"},
        "hits": [
            {
                "_index": "logs-2026-05",
                "_id": f"log-{i}",
                "_score": 1.0,
                "_source": {
                    "timestamp": (datetime.utcnow() - timedelta(minutes=random.randint(0, 10080))).isoformat() + "Z",
                    "level": random.choice(["info", "warn", "error"]),
                    "service": random.choice(["api-gateway", "auth-service", "payment-processor", "user-service"]),
                    "message": "Request processed" if random.random() > 0.3 else "ConnectionTimeout",
                    "http_code": random.choice([200, 200, 200, 400, 500, 503]),
                }
            }
            for i in range(5)
        ]
    }
}


class MockESHandler(BaseHTTPRequestHandler):
    """Mock Elasticsearch API handler."""

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Elastic-Product", "Elasticsearch")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")

        # Cluster health
        if path == "/_cluster/health":
            self._send_json({
                "cluster_name": "datapulse-demo",
                "status": "yellow",
                "number_of_nodes": 2,
                "number_of_data_nodes": 2,
                "active_primary_shards": 5,
                "active_shards": 8,
                "relocating_shards": 0,
                "initializing_shards": 0,
                "unassigned_shards": 2,
            })
        # Cat indices
        elif path.startswith("/_cat/indices"):
            self._send_json(INDICES)
        # Cat shards
        elif path.startswith("/_cat/shards"):
            self._send_json(SHARDS)
        # Get mapping
        elif "/_mapping" in path:
            index = path.split("/")[1] if len(path.split("/")) > 1 else None
            if index and index in PRODUCTS_MAPPING:
                self._send_json({index: PRODUCTS_MAPPING[index]})
            elif index and index in LOGS_MAPPING:
                self._send_json({index: LOGS_MAPPING[index]})
            else:
                self._send_json({**PRODUCTS_MAPPING, **LOGS_MAPPING})
        # Index stats
        elif path.endswith("/_stats"):
            self._send_json({"_all": {"primaries": {"docs": {"count": 18500}}}})
        # Root
        elif path == "/" or path == "":
            self._send_json({
                "name": "datapulse-demo-node",
                "cluster_name": "datapulse-demo",
                "version": {"number": "8.17.0", "build_flavor": "default"},
                "tagline": "You Know, for Search"
            })
        else:
            self._send_json({"error": f"Unknown endpoint: {path}"}, status=404)

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode() if content_length > 0 else "{}"

        # Search
        if "/_search" in path:
            self._send_json(SEARCH_RESULTS)
        # ES|QL
        elif path == "/_esql" or path == "/_query":
            # Simulate error trend results
            self._send_json({
                "columns": [
                    {"name": "service", "type": "keyword"},
                    {"name": "error_count", "type": "long"},
                ],
                "values": [
                    ["payment-processor", 412],
                    ["api-gateway", 89],
                    ["auth-service", 45],
                    ["user-service", 23],
                    ["order-service", 12],
                ],
            })
        # Bulk
        elif path == "/_bulk":
            self._send_json({"errors": False, "items": [{"index": {"status": 201}}]})
        # Refresh
        elif "/_refresh" in path:
            self._send_json({"_shards": {"total": 5, "successful": 5, "failed": 0}})
        else:
            self._send_json({"error": f"Unknown endpoint: {path}"}, status=404)

    def do_PUT(self):
        path = self.path.rstrip("/")
        # Create index
        index_name = path.split("/")[1] if len(path.split("/")) > 1 else None
        self._send_json({"acknowledged": True, "index": index_name, "shards_acknowledged": True})

    def log_message(self, format, *args):
        """Suppress verbose logging."""
        pass


def run_server(port=9200):
    server = HTTPServer(("0.0.0.0", port), MockESHandler)
    print(f"🚀 Mock Elasticsearch server running on http://localhost:{port}")
    print(f"   Supports: _cat/indices, _cat/shards, _mapping, _search, _esql, _bulk")
    print(f"   Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9200)
    args = parser.parse_args()
    run_server(args.port)
