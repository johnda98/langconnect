#!/usr/bin/env bash
set -euo pipefail

# Deploy the staging Cloud Run service using the staging Cloud SQL instance and cloudrun-staging.env values.
# Usage:
#   1) Populate cloudrun-staging.env (see cloudrun-staging.env.example).
#   2) From repo root: chmod +x scripts/deploy-cloudrun-staging.sh
#   3) ./scripts/deploy-cloudrun-staging.sh

PROJECT=your-vehicle-ai-staging
REGION=us-central1
SERVICE=langconnect-staging
REPO=langconnect
IMAGE=us-central1-docker.pkg.dev/$PROJECT/$REPO/$SERVICE:$(git rev-parse --short HEAD)
SERVICE_ACCOUNT=langconnect-staging-sa@your-vehicle-ai-staging.iam.gserviceaccount.com
CLOUDSQL_INSTANCE=your-vehicle-ai-staging:us-central1:langconnect-staging-sql

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
  --env-vars-file cloudrun-staging.env \
  --add-cloudsql-instances "$CLOUDSQL_INSTANCE" \
  --service-account "$SERVICE_ACCOUNT" \
  --allow-unauthenticated \
  --memory 1Gi \
  --max-instances 5

echo "Done. Remember to add the new Cloud Run URL to ALLOW_ORIGINS in cloudrun-staging.env if browsers will call it directly."
