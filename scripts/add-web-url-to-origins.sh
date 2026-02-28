#!/usr/bin/env bash
set -euo pipefail

# Update ALLOW_ORIGINS on the staging Cloud Run service without rebuilding the image.
# Usage:
#   ./scripts/add-web-url-to-origins.sh https://your-webapp.example [extra-origin ...]
# The script always keeps http://localhost:3000 for dev. Override defaults with env vars:
#   PROJECT (default: your-vehicle-ai-staging)
#   REGION  (default: us-central1)
#   SERVICE (default: langconnect-staging)

PROJECT=${PROJECT:-your-vehicle-ai-staging}
REGION=${REGION:-us-central1}
SERVICE=${SERVICE:-langconnect-staging}

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <webapp-url> [extra-origin ...]" >&2
  exit 1
fi

origins=("$1" "http://localhost:3000")
shift
if [[ $# -gt 0 ]]; then
  origins+=("$@")
fi

# Build JSON array without jq dependency
json="["
for origin in "${origins[@]}"; do
  json+="\"${origin}\","
done
json="${json%,}]"

echo "Updating $SERVICE in $PROJECT/$REGION with ALLOW_ORIGINS=$json"
gcloud run services update "$SERVICE" \
  --project "$PROJECT" \
  --region "$REGION" \
  --set-env-vars "ALLOW_ORIGINS=$json"

echo "Done. A new revision was created with the updated origins."
