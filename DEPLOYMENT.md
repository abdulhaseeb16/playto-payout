# Playto Payout Deployment Guide

This document explains how to deploy the Playto Payout application in production or a production-like environment.

The project has six runtime pieces:

- PostgreSQL database
- Redis broker
- Django API service
- Celery worker service
- Celery beat scheduler service
- React frontend served as static files

The backend is the source of truth for payouts, ledger entries, idempotency keys, and background payout processing. The frontend only talks to the backend API through `VITE_API_URL`.

## Quick Production Path

Use this sequence when deploying from a clean branch:

1. Push the production branch.
2. Provision PostgreSQL.
3. Provision Redis.
4. Deploy the Django API service.
5. Run database migrations.
6. Deploy one Celery worker service.
7. Deploy one Celery beat service.
8. Deploy the React frontend with the backend API URL baked into `VITE_API_URL`.
9. Add the frontend domain to backend CORS and CSRF settings.
10. Verify API, frontend, worker logs, and one payout flow.

Do not run the seed script in a real production environment. Use it only for demos or review environments.

## 1. Deployment Checklist

Before deploying, confirm these files exist and are committed:

```text
backend/Dockerfile
backend/requirements.txt
backend/manage.py
backend/config/settings/base.py
backend/config/settings/production.py
backend/ledger/migrations/0001_initial.py
frontend/Dockerfile
frontend/package.json
frontend/package-lock.json
docker-compose.yml
README.md
EXPLAINER.md
DEPLOYMENT.md
```

Do not commit local-only files:

```text
backend/.env
backend/.venv/
backend/celerybeat-schedule.*
frontend/node_modules/
frontend/dist/
__pycache__/
*.pyc
```

## 2. Required Environment Variables

Set these for every backend service: API, Celery worker, and Celery beat.

```env
DJANGO_SETTINGS_MODULE=config.settings.production
DEBUG=False
SECRET_KEY=<strong-random-secret>
DATABASE_URL=postgres://<user>:<password>@<host>:<port>/<database>
REDIS_URL=redis://<host>:<port>/0
ALLOWED_HOSTS=<backend-domain>,localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=https://<frontend-domain>
CSRF_TRUSTED_ORIGINS=https://<frontend-domain>
SECURE_SSL_REDIRECT=True
```

For the frontend build:

```env
VITE_API_URL=https://<backend-domain>/api/v1
```

Important notes:

- `SECRET_KEY` must be unique and private in production.
- `DEBUG` must be `False`.
- `ALLOWED_HOSTS` must include the backend host name exactly.
- `CORS_ALLOWED_ORIGINS` must include the frontend origin exactly, including scheme and port when applicable.
- `CSRF_TRUSTED_ORIGINS` should include the frontend origin and any admin origin that posts to Django.
- `VITE_API_URL` is read during the frontend build. If the backend URL changes, rebuild and redeploy the frontend.

If your platform terminates HTTPS before traffic reaches Django, keep `SECURE_SSL_REDIRECT=True`. The project sets `SECURE_PROXY_SSL_HEADER` so Django respects `X-Forwarded-Proto: https`.

## 3. Step-by-Step Deployment

This is the full production deployment flow.

### Step 1: Push the Production Branch

Create a branch for deployment work:

```bash
git switch -c production-readiness
```

Commit production changes and push:

```bash
git add .
git commit -m "chore: prepare production deployment"
git push -u origin production-readiness
```

When the deployment is verified, merge it into `main`.

### Step 2: Provision PostgreSQL

Create a managed PostgreSQL database on Railway, Render, Supabase, Neon, or another provider.

Copy the database URL. It should look like:

```text
postgres://user:password@host:5432/database
```

The app depends on PostgreSQL row locks through `select_for_update()`. Do not use SQLite for production or concurrency verification.

### Step 3: Provision Redis

Create a managed Redis instance.

Copy the Redis URL. It should look like:

```text
redis://host:6379/0
```

Redis is required by Celery. Without Redis, payout creation can succeed but background processing will not run.

### Step 4: Deploy the Backend API

Deploy the `playto-payout/backend` directory as a web service.

Set environment variables:

```env
DJANGO_SETTINGS_MODULE=config.settings.production
DEBUG=False
SECRET_KEY=<strong-random-secret>
DATABASE_URL=<postgres-url>
REDIS_URL=<redis-url>
ALLOWED_HOSTS=<backend-domain>
CORS_ALLOWED_ORIGINS=https://<frontend-domain>
CSRF_TRUSTED_ORIGINS=https://<frontend-domain>
SECURE_SSL_REDIRECT=True
```

Use this start command:

```bash
gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
```

If the platform does not provide `$PORT`, use:

```bash
gunicorn config.wsgi:application --bind 0.0.0.0:8000
```

### Step 5: Run Migrations

After the backend image builds and before real traffic, run:

```bash
python manage.py migrate
```

Optional for demo deployments only:

```bash
python manage.py shell < seed.py
```

The seed script resets demo data, so do not run it against real production data.

### Step 6: Deploy the Celery Worker

Create a worker service from the same `playto-payout/backend` directory.

Use the same backend environment variables.

Start command:

```bash
celery -A config worker --loglevel=info --concurrency=4
```

The worker processes payout settlement tasks.

### Step 7: Deploy Celery Beat

Create exactly one scheduler service from the same `playto-payout/backend` directory.

Use the same backend environment variables.

Start command:

```bash
celery -A config beat --loglevel=info
```

Only one beat instance should run. More than one can enqueue duplicate periodic jobs.

### Step 8: Deploy the Frontend

Deploy the `playto-payout/frontend` directory as a static Vite app.

Set:

```env
VITE_API_URL=https://<backend-domain>/api/v1
```

Build:

```bash
npm ci
npm run build
```

Publish:

```text
dist
```

After the frontend receives a public URL, update the backend:

```env
CORS_ALLOWED_ORIGINS=https://<frontend-domain>
CSRF_TRUSTED_ORIGINS=https://<frontend-domain>
```

Redeploy the backend after changing these values.

### Step 9: Verify the Deployment

Check the health endpoint:

```text
https://<backend-domain>/healthz/
```

Expected:

```json
{"status": "ok"}
```

Check the API index:

```text
https://<backend-domain>/api/v1/
```

Open the frontend:

```text
https://<frontend-domain>
```

Confirm:

- The page loads without browser console CORS errors.
- The merchant dropdown loads.
- Dashboard balances load.
- Payout and ledger tables load.
- A small demo payout can be created in a demo environment.
- Worker logs show payout processing.

### Step 10: Rollback

If deployment fails:

1. Roll back the frontend to the previous static deployment.
2. Roll back the API service to the previous backend image or commit.
3. Keep PostgreSQL data intact.
4. Stop Celery beat before rolling back workers if duplicate scheduling is suspected.
5. Re-run verification after rollback.

## 4. Backend Service Commands

The backend container image is built from `backend/Dockerfile`.

API start command:

```bash
gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
```

If the platform does not provide `$PORT`, use:

```bash
gunicorn config.wsgi:application --bind 0.0.0.0:8000
```

Celery worker command:

```bash
celery -A config worker --loglevel=info --concurrency=4
```

Celery beat command:

```bash
celery -A config beat --loglevel=info
```

Run migrations before accepting traffic:

```bash
python manage.py migrate
```

Seed demo data only when you want deterministic demo merchants and sample rows:

```bash
python manage.py shell < seed.py
```

Do not run `seed.py` automatically in a real production environment unless the app is intentionally a demo deployment. The seed script resets app data.

## 5. Docker Compose Deployment

Docker Compose is the fastest production-like deployment for a single VM.

From the project root:

```bash
docker compose up --build -d
```

The Compose file is production-like and does not seed data automatically. To create demo data, run the seed command manually after the services are up.

This starts:

```text
PostgreSQL:      localhost:5432
Redis:           localhost:6379
Django API:      localhost:8000
Frontend:        localhost:80
Celery worker:   background service
Celery beat:     background service
```

Check running services:

```bash
docker compose ps
```

View backend logs:

```bash
docker compose logs -f backend
```

View worker logs:

```bash
docker compose logs -f celery_worker
```

Run migrations manually:

```bash
docker compose exec backend python manage.py migrate
```

Seed demo data manually:

```bash
docker compose exec backend sh -c "python manage.py shell < seed.py"
```

Stop services:

```bash
docker compose down
```

Stop services and remove database volume:

```bash
docker compose down -v
```

Use `down -v` carefully because it deletes local PostgreSQL data.

## 6. Railway Deployment

Railway is a good fit because the app needs PostgreSQL, Redis, a web service, and worker services.

### 6.1 Create Resources

1. Create a Railway project.
2. Add a PostgreSQL service.
3. Add a Redis service.
4. Copy the generated `DATABASE_URL`.
5. Copy the generated `REDIS_URL`.

### 6.2 Backend API Service

Create a backend service from the repository with root directory:

```text
playto-payout/backend
```

Set environment variables:

```env
DEBUG=False
DJANGO_SETTINGS_MODULE=config.settings.production
SECRET_KEY=<strong-random-secret>
DATABASE_URL=<railway-postgres-url>
REDIS_URL=<railway-redis-url>
ALLOWED_HOSTS=<railway-backend-domain>
CORS_ALLOWED_ORIGINS=https://<frontend-domain>
CSRF_TRUSTED_ORIGINS=https://<frontend-domain>
SECURE_SSL_REDIRECT=True
```

Build uses the `backend/Dockerfile`.

Start command:

```bash
gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
```

After the first successful deploy, run:

```bash
python manage.py migrate
```

For a demo deployment only, run:

```bash
python manage.py shell < seed.py
```

### 6.3 Celery Worker Service

Create another service from the same backend folder.

Use the same backend environment variables.

Start command:

```bash
celery -A config worker --loglevel=info --concurrency=4
```

### 6.4 Celery Beat Service

Create a third service from the same backend folder.

Use the same backend environment variables.

Start command:

```bash
celery -A config beat --loglevel=info
```

Only run one Celery beat instance. Multiple beat instances can enqueue duplicate periodic tasks.

### 6.5 Frontend Service

Deploy the frontend separately with root directory:

```text
playto-payout/frontend
```

Set:

```env
VITE_API_URL=https://<railway-backend-domain>/api/v1
```

Build command:

```bash
npm ci && npm run build
```

Output directory:

```text
dist
```

After the frontend domain is created, update the backend API service:

```env
CORS_ALLOWED_ORIGINS=https://<frontend-domain>
```

Redeploy the backend after changing CORS.

## 7. Vercel Frontend Deployment

Vercel is a clean option for the React frontend.

Project settings:

```text
Framework preset: Vite
Root directory: playto-payout/frontend
Build command: npm run build
Output directory: dist
Install command: npm ci
```

Environment variable:

```env
VITE_API_URL=https://<backend-domain>/api/v1
```

After Vercel gives you a frontend URL, add it to the backend:

```env
CORS_ALLOWED_ORIGINS=https://<your-vercel-app>.vercel.app
CSRF_TRUSTED_ORIGINS=https://<your-vercel-app>.vercel.app
```

Then redeploy the backend.

## 8. Render Deployment

Render can host the backend, worker, Redis, PostgreSQL, and static frontend.

Suggested services:

- PostgreSQL database
- Redis instance
- Web service for Django API
- Background worker for Celery worker
- Background worker for Celery beat
- Static site for frontend

Django web service:

```text
Root directory: playto-payout/backend
Build command: pip install -r requirements.txt
Start command: gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
```

Celery worker:

```text
Root directory: playto-payout/backend
Build command: pip install -r requirements.txt
Start command: celery -A config worker --loglevel=info --concurrency=4
```

Celery beat:

```text
Root directory: playto-payout/backend
Build command: pip install -r requirements.txt
Start command: celery -A config beat --loglevel=info
```

Frontend static site:

```text
Root directory: playto-payout/frontend
Build command: npm ci && npm run build
Publish directory: dist
```

Set the same environment variables described above.

## 9. Post-Deployment Verification

Open the health endpoint:

```text
https://<backend-domain>/healthz/
```

Expected response:

```json
{"status": "ok"}
```

Open the API index:

```text
https://<backend-domain>/api/v1/
```

Expected response:

```json
{
  "name": "Playto Payout API",
  "version": "v1",
  "endpoints": {
    "merchant_dashboard": "/api/v1/merchants/<merchant_id>/dashboard/",
    "create_payout_flat": "/api/v1/payouts/",
    "create_payout": "/api/v1/merchants/<merchant_id>/payouts/",
    "payout_detail": "/api/v1/merchants/<merchant_id>/payouts/<payout_id>/"
  }
}
```

If demo data is seeded, `seeded_merchants` should contain merchants.

Open the frontend:

```text
https://<frontend-domain>
```

Expected:

- The merchant dropdown loads.
- Balance cards show total, held, and available amounts.
- Payout history loads.
- Ledger history loads.
- Creating a payout returns a success message or a clear validation error.

Check worker behavior:

1. Create a payout.
2. Confirm the payout appears as `pending`.
3. Watch worker logs.
4. Confirm it moves to `processing`, then `completed` or `failed`.

## 10. Operational Notes

### Database

PostgreSQL is required for correct `select_for_update()` behavior. SQLite is not suitable for verifying production concurrency behavior.

Back up the database regularly. The append-only ledger is the audit trail.

### Redis

Redis is required for Celery. If Redis is down:

- API requests can still create payouts.
- Background payout processing will not run.
- Payouts may remain `pending` until Redis and workers recover.

### Celery Beat

Celery beat schedules:

- `process_pending_payouts` every 5 seconds
- `retry_stuck_payouts` every 10 seconds

Run only one beat instance.

### Static Files

The backend uses WhiteNoise for Django static files. The React frontend is built separately and served by Nginx in Docker or by a static hosting provider.

## 11. Common Deployment Issues

### Frontend Cannot Reach Backend

Check:

```env
VITE_API_URL=https://<backend-domain>/api/v1
CORS_ALLOWED_ORIGINS=https://<frontend-domain>
CSRF_TRUSTED_ORIGINS=https://<frontend-domain>
```

Then rebuild the frontend and redeploy the backend.

### Django DisallowedHost Error

Add the backend domain to:

```env
ALLOWED_HOSTS=<backend-domain>
```

### CORS Error in Browser

Add the exact frontend origin:

```env
CORS_ALLOWED_ORIGINS=https://<frontend-domain>
```

Do not include a trailing slash.

### Payouts Stay Pending

Check:

- `REDIS_URL` is set for API, worker, and beat.
- Celery worker is running.
- Celery beat is running.
- Worker logs do not show Redis connection errors.

### Migrations Fail

Check:

- `DATABASE_URL` is correct.
- PostgreSQL is reachable from the backend service.
- The database user has permission to create tables and indexes.

### Static Frontend Uses Old Backend URL

`VITE_API_URL` is compiled into the frontend build. Update the variable, rebuild, and redeploy the frontend.

## 12. Release Process

Use this process for a clean deployment:

1. Commit source changes.
2. Push to the deployment branch.
3. Deploy backend API.
4. Run migrations.
5. Deploy Celery worker.
6. Deploy Celery beat.
7. Deploy frontend with the correct `VITE_API_URL`.
8. Add frontend URL to backend `CORS_ALLOWED_ORIGINS`.
9. Redeploy backend if CORS changed.
10. Verify `/api/v1/`.
11. Verify the frontend dashboard.
12. Create one small payout in a demo merchant.
13. Confirm Celery processes it.

## 13. Minimal Production Configuration

For a real production deployment, use:

```env
DEBUG=False
DJANGO_SETTINGS_MODULE=config.settings.production
SECRET_KEY=<strong-random-secret>
DATABASE_URL=<managed-postgres-url>
REDIS_URL=<managed-redis-url>
ALLOWED_HOSTS=<backend-domain>
CORS_ALLOWED_ORIGINS=https://<frontend-domain>
CSRF_TRUSTED_ORIGINS=https://<frontend-domain>
SECURE_SSL_REDIRECT=True
```

And deploy these commands:

```bash
# API
gunicorn config.wsgi:application --bind 0.0.0.0:$PORT

# Worker
celery -A config worker --loglevel=info --concurrency=4

# Beat
celery -A config beat --loglevel=info
```

Frontend:

```env
VITE_API_URL=https://<backend-domain>/api/v1
```
