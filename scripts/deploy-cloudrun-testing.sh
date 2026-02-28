#!/usr/bin/env bash
set -euo pipefail

# Deploy the testing Cloud Run service using the testing Cloud SQL clone and .env values.
# Usage:
#   1) Populate cloudrun-testing.env (see cloudrun-testing.env.example).
#   2) From repo root: chmod +x scripts/deploy-cloudrun-testing.sh
#   3) ./scripts/deploy-cloudrun-testing.sh

PROJECT=your-vehicle-ai-staging
REGION=us-central1
SERVICE=langconnect-testing
REPO=langconnect
IMAGE=us-central1-docker.pkg.dev/$PROJECT/$REPO/$SERVICE:$(git rev-parse --short HEAD)
SERVICE_ACCOUNT=langconnect-staging-sa@your-vehicle-ai-staging.iam.gserviceaccount.com

echo "Setting project to $PROJECT"
gcloud config set project "$PROJECT"

echo "Ensuring Artifact Registry repo '$REPO' exists in $REGION"
gcloud artifacts repositories describe "$REPO" --location="$REGION" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "$REPO" --repository-format=docker --location="$REGION" --description="LangConnect images"

echo "Building image $IMAGE"
gcloud builds submit --tag "$IMAGE"

echo "Deploying $SERVICE to Cloud Run in $REGION"
gcloud run deploy "$SERVICE" \
  --project "$PROJECT" \
  --region "$REGION" \
  --image "$IMAGE" \
  --env-vars-file cloudrun-testing.env \
  --add-cloudsql-instances your-vehicle-ai-staging:us-central1:langconnect-testing-sql \
  --service-account "$SERVICE_ACCOUNT" \
  --allow-unauthenticated \
  --memory 1Gi \
  --max-instances 3

echo "Done. Remember to add the new Cloud Run URL to ALLOW_ORIGINS if you want to call it directly."
