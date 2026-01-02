# LangConnect Staging Deployment (GCP)

Use this checklist whenever `staging` needs to be rebuilt in `your-vehicle-ai-staging`.

## 1. Prerequisites
- Authenticate and select the project:
  ```bash
  gcloud auth login
  gcloud auth application-default login
  gcloud config set account johnallen@your-vehicle-ai.com   # or current owner
  gcloud config set project your-vehicle-ai-staging
  ```
- Enable required services once per project: Cloud Run Admin, Cloud SQL Admin, Artifact Registry, Secret Manager, Cloud Build.
- Create the Artifact Registry repo (one-time):
  ```bash
  gcloud artifacts repositories create langconnect \
    --repository-format=docker \
    --location=us-central1
  ```

## 2. Cloud SQL
1. Provision PostgreSQL 16:
   ```bash
  gcloud sql instances create langconnect-staging-sql \
    --database-version=POSTGRES_16 \
    --region=us-central1 \
    --tier=db-custom-2-7680 \
    --storage-size=50GB \
    --storage-auto-increase \
    --availability-type=ZONAL \
    --edition=ENTERPRISE \
    --root-password='<STRONG_PASSWORD>'
   ```
2. Update the `postgres` user password whenever you rotate credentials:
   ```bash
   gcloud sql users set-password postgres \
     --instance=langconnect-staging-sql \
     --password='<STRONG_PASSWORD>'
   ```
3. Connect via Cloud Shell and enable pgvector:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

## 3. Secrets
Store runtime secrets in Secret Manager (`latest` version referenced during deploy):
```bash
printf '<OPENAI_KEY>' | gcloud secrets create langconnect-openai-key --data-file=-
printf '<SUPABASE_URL>' | gcloud secrets create langconnect-supabase-url --data-file=-
printf '<SUPABASE_KEY>' | gcloud secrets create langconnect-supabase-key --data-file=-
printf 'postgres' | gcloud secrets create langconnect-postgres-user --data-file=-
printf '<DB_PASSWORD>' | gcloud secrets create langconnect-postgres-password --data-file=-
printf 'postgres' | gcloud secrets create langconnect-postgres-db --data-file=-
```
Use `gcloud secrets versions add <secret>` when rotating values.

## 4. Cloud Run Service Account
```bash
gcloud iam service-accounts create langconnect-staging-sa \
  --display-name="LangConnect staging"

SA="langconnect-staging-sa@your-vehicle-ai-staging.iam.gserviceaccount.com"
PROJECT="your-vehicle-ai-staging"

gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:$SA" \
  --role="roles/cloudsql.client"

gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:$SA" \
  --role="roles/secretmanager.secretAccessor"
```
Grant `roles/run.invoker` to any other service account (Next.js, LangGraph, etc.) that needs to call the API.

## 5. Build & Push Container
Run from repo root on the `staging` branch:
```bash
UV_CACHE_DIR=$PWD/.uv-cache uv lock     # keep uv.lock in sync when deps change
gcloud builds submit \
  --tag us-central1-docker.pkg.dev/your-vehicle-ai-staging/langconnect/langconnect:staging
```

## 6. Deploy to Cloud Run
```bash
REGION="us-central1"
INSTANCE="your-vehicle-ai-staging:us-central1:langconnect-staging-sql"
SA="langconnect-staging-sa@your-vehicle-ai-staging.iam.gserviceaccount.com"
IMAGE="us-central1-docker.pkg.dev/your-vehicle-ai-staging/langconnect/langconnect:staging"

gcloud run deploy langconnect-staging \
  --region=$REGION \
  --image=$IMAGE \
  --service-account=$SA \
  --add-cloudsql-instances=$INSTANCE \
  --set-env-vars=POSTGRES_HOST=/cloudsql/$INSTANCE,POSTGRES_PORT=5432 \
  --set-env-vars=ALLOW_ORIGINS='["http://localhost:3000"]' \  # update when Next.js staging URL exists
  --set-secrets=POSTGRES_USER=langconnect-postgres-user:latest \
  --set-secrets=POSTGRES_PASSWORD=langconnect-postgres-password:latest \
  --set-secrets=POSTGRES_DB=langconnect-postgres-db:latest \
  --set-secrets=OPENAI_API_KEY=langconnect-openai-key:latest \
  --set-secrets=SUPABASE_URL=langconnect-supabase-url:latest \
  --set-secrets=SUPABASE_KEY=langconnect-supabase-key:latest \
  --ingress=internal-and-cloud-load-balancing \
  --no-allow-unauthenticated \
  --cpu=2 --memory=2Gi \
  --min-instances=0 --max-instances=10
```

Verify with `gcloud run services describe langconnect-staging --region=$REGION --format='value(status.url)'` and hit `/health` using an authenticated request. Update `ALLOW_ORIGINS` (and optionally add a dedicated secret) when the Next.js staging domain is ready.***
