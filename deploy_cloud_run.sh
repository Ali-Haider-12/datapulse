#!/bin/bash
# Deploy DataPulse to Google Cloud Run

set -e

# Configuration
PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-datapulse-hackathon}"
REGION="${GOOGLE_CLOUD_REGION:-us-central1}"
BACKEND_IMAGE="gcr.io/$PROJECT_ID/datapulse-backend"
FRONTEND_IMAGE="gcr.io/$PROJECT_ID/datapulse-frontend"

echo "🚀 Deploying DataPulse to Google Cloud Run..."
echo "Project: $PROJECT_ID"
echo "Region: $REGION"

# Check gcloud is available
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI not found. Please install it:"
    echo "   https://cloud.google.com/sdk/docs/install"
    echo ""
    echo "Or see CLOUD_RUN_DEPLOY.md for detailed instructions."
    exit 1
fi

# Authenticate
echo "📦 Authenticating..."
gcloud auth login
gcloud config set project $PROJECT_ID

# Build and push backend
echo "🏗️ Building backend image..."
docker build -f Dockerfile.backend -t $BACKEND_IMAGE .
docker push $BACKEND_IMAGE

# Build and push frontend
echo "🏗️ Building frontend image..."
docker build -f Dockerfile.frontend -t $FRONTEND_IMAGE .
docker push $FRONTEND_IMAGE

# Deploy backend to Cloud Run
echo "🚀 Deploying backend..."
gcloud run deploy datapulse-backend \
    --image $BACKEND_IMAGE \
    --region $REGION \
    --set-env-vars="ES_URL=...,MCP_SERVER_URL=...,GOOGLE_APPLICATION_CREDENTIALS=..." \
    --allow-unauthenticated

# Deploy frontend to Cloud Run
echo "🚀 Deploying frontend..."
gcloud run deploy datapulse-frontend \
    --image $FRONTEND_IMAGE \
    --region $REGION \
    --allow-unauthenticated

# Get URLs
echo "✅ Deployment complete!"
echo "Backend URL: $(gcloud run services describe datapulse-backend --region $REGION --format='value(status.url)')"
echo "Frontend URL: $(gcloud run services describe datapulse-frontend --region $REGION --format='value(status.url)')"
