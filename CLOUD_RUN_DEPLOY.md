# Google Cloud Run Deployment Guide

## Prerequisites

1. **Google Cloud Account** with billing enabled
2. **Google Cloud SDK (gcloud CLI)** installed:
   ```bash
   # macOS
   brew install google-cloud-sdk
   
   # Ubuntu/Debian
   curl https://sdk.cloud.google.com | bash
   
   # Verify
   gcloud --version
   ```
3. **Docker** installed and running
4. **Google Cloud Project** created (note the PROJECT_ID)

---

## Step 1: Authenticate

```bash
# Login to Google Cloud
gcloud auth login

# Set your project
gcloud config set project YOUR_PROJECT_ID

# Configure Docker for gcr.io
gcloud auth configure-docker
```

---

## Step 2: Build & Push Backend Image

```bash
cd /path/to/datapulse/

# Build backend image
docker build -f Dockerfile.backend -t gcr.io/YOUR_PROJECT_ID/datapulse-backend .

# Push to Google Container Registry
docker push gcr.io/YOUR_PROJECT_ID/datapulse-backend
```

---

## Step 3: Build & Push Frontend Image

```bash
# Build frontend image
docker build -f Dockerfile.frontend -t gcr.io/YOUR_PROJECT_ID/datapulse-frontend .

# Push to Google Container Registry
docker push gcr.io/YOUR_PROJECT_ID/datapulse-frontend
```

---

## Step 4: Deploy Backend to Cloud Run

```bash
gcloud run deploy datapulse-backend \
  --image gcr.io/YOUR_PROJECT_ID/datapulse-backend \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars="ES_URL=...,MCP_SERVER_URL=...,GOOGLE_APPLICATION_CREDENTIALS=...,GOOGLE_CHAT_SPACE_ID=..."
```

**Get the backend URL:**
```bash
BACKEND_URL=$(gcloud run services describe datapulse-backend \
  --region us-central1 \
  --format='value(status.url)')
echo "Backend URL: $BACKEND_URL"
```

---

## Step 5: Deploy Frontend to Cloud Run

```bash
gcloud run deploy datapulse-frontend \
  --image gcr.io/YOUR_PROJECT_ID/datapulse-frontend \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars="NEXT_PUBLIC_API_URL=$BACKEND_URL"
```

**Get the frontend URL:**
```bash
FRONTEND_URL=$(gcloud run services describe datapulse-frontend \
  --region us-central1 \
  --format='value(status.url)')
echo "Frontend URL: $FRONTEND_URL"
```

---

## Step 6: Verify Deployment

```bash
# Test backend health
curl $BACKEND_URL/health

# Test frontend
curl $FRONTEND_URL/

# Test impact endpoint
curl $BACKEND_URL/api/impact
```

---

## Environment Variables for Backend

| Variable | Description | Example |
|----------|-------------|---------|
| `ES_URL` | Elasticsearch URL | `https://...es.googleapis.com` |
| `MCP_SERVER_URL` | Elastic MCP Server URL | `http://...` |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to service account key | `/app/credentials.json` |
| `GOOGLE_CHAT_SPACE_ID` | Google Chat space ID | `spaces/XXX` |
| `GMAIL_MCP_URL` | Gmail MCP URL | `http://...` |
| `CALENDAR_MCP_URL` | Calendar MCP URL | `http://...` |

---

## Notes

- **Vertex AI** is already integrated (see `app/services/agent.py`)
- **Google Chat Bot** is integrated (see `app/services/google_chat.py`)
- **Multi-MCP servers** are supported (Elastic, Gmail, Calendar, Slack)
- **Cost:** Cloud Run free tier covers 2 million requests/month

---

## Quick Deploy Script

If you have `gcloud` installed, just run:
```bash
chmod +x deploy_cloud_run.sh
./deploy_cloud_run.sh
```

**Edit `deploy_cloud_run.sh` first** to set `PROJECT_ID` and environment variables.
