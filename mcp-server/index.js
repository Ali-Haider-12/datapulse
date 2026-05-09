/**
 * Elastic MCP Server — Streamable HTTP wrapper
 * Wraps the @elastic/mcp-server-elasticsearch npm package
 * to expose it via HTTP (required by our FastAPI backend).
 */
const express = require("express");
const { Client } = require("@elastic/elasticsearch");
const { McpServer } = require("@modelcontextprotocol/sdk/server/mcp.js");
const { StreamableHTTPServerTransport } = require("@modelcontextprotocol/sdk/server/streamableHttp.js");
const { z } = require("zod");

const ES_URL = process.env.ES_URL || "http://localhost:9200";
const PORT = process.env.PORT || 8080;

const app = express();
app.use(express.json());

// Create ES client
const esClient = new Client({ node: ES_URL });

// Create MCP server
const server = new McpServer({ name: "elastic-mcp", version: "1.0.0" });

// Register tools
server.tool("list_indices", "List all Elasticsearch indices", {}, async () => {
  const resp = await esClient.cat.indices({ format: "json" });
  return { content: [{ type: "text", text: JSON.stringify(resp.body) }] };
});

server.tool(
  "get_mappings",
  "Get index mappings",
  { index: z.string().describe("Index name") },
  async ({ index }) => {
    const resp = await esClient.indices.getMapping({ index });
    return { content: [{ type: "text", text: JSON.stringify(resp.body) }] };
  }
);

server.tool(
  "search",
  "Search an Elasticsearch index",
  {
    index: z.string().describe("Index name"),
    query: z.string().describe('Elasticsearch query as JSON string, e.g. \'{"match_all":{}}\''),
  },
  async ({ index, query }) => {
    const resp = await esClient.search({ index, body: { query: JSON.parse(query) } });
    return { content: [{ type: "text", text: JSON.stringify(resp.body) }] };
  }
);

server.tool(
  "esql",
  "Run an ES|QL query",
  { query: z.string().describe("ES|QL query string") },
  async ({ query }) => {
    const resp = await esClient.esql.query({ query });
    return { content: [{ type: "text", text: JSON.stringify(resp) }] };
  }
);

server.tool(
  "get_shards",
  "Get shard information for indices",
  { index: z.string().optional().describe("Index name (optional, defaults to all)") },
  async ({ index }) => {
    const resp = await esClient.cat.shards({ index: index || "_all", format: "json" });
    return { content: [{ type: "text", text: JSON.stringify(resp.body) }] };
  }
);

// Set up Streamable HTTP transport
const transport = new StreamableHTTPServerTransport({
  sessionIdGenerator: undefined,
});

// Connect server to transport
server.connect(transport).then(() => {
  // Mount the MCP handler at /mcp
  app.use("/mcp", (req, res) => {
    transport.handleRequest(req, res);
  });

  app.listen(PORT, () => {
    console.log(`Elastic MCP Server running on port ${PORT}`);
    console.log(`Elasticsearch URL: ${ES_URL}`);
    console.log(`MCP endpoint: http://localhost:${PORT}/mcp`);
  });
});
