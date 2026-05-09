# DataPulse — Full-Stack Single Container
# Runs: Mock ES (port 9201) + Backend API (port 8001) + Frontend (port 3000)

# ── Stage 1: Build Frontend ──
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Production ──
FROM python:3.11-slim

# Install Node.js for Next.js standalone server
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Copy backend code
COPY backend/ /app/backend/

# Copy built frontend standalone
COPY --from=frontend-builder /app/frontend/.next/standalone /app/frontend/standalone
COPY --from=frontend-builder /app/frontend/.next/static /app/frontend/standalone/.next/static
COPY --from=frontend-builder /app/frontend/public /app/frontend/standalone/public

# Startup script
COPY docker/start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Environment
ENV ES_URL=http://localhost:9201
ENV MCP_SERVER_URL=http://localhost:8080/mcp
ENV BACKEND_PORT=8001
ENV FRONTEND_PORT=3000
ENV ES_PORT=9201

EXPOSE 3000 8001 9201

CMD ["/app/start.sh"]
