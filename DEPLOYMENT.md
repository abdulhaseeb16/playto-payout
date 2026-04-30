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

## 6. Railway Backend Deployment

Use Railway for the backend runtime: PostgreSQL, Redis, Django API, Celery worker, and Celery beat. Use Vercel only for the React frontend.

Official references:

- Railway Django guide: `https://docs.railway.com/guides/django`
- Railway build/start commands: `https://docs.railway.com/reference/build-and-start-commands`
- Railway service variables: `https://docs.railway.com/variables`
- Railway Redis: `https://docs.railway.com/databases/redis`

### 6.1 Push the Correct Branch to GitHub

Use the production-ready branch:

```bash
git switch production-readiness
git status
git push -u origin production-readiness
```

If you want Railway to deploy from `main`, merge the branch first:

```bash
git switch main
git merge production-readiness
git push origin main
```

Recommended for first deployment: deploy `production-readiness`, verify everything, then merge into `main`.

### 6.2 Create the Railway Project

1. Open Railway.
2. Click `New Project`.
3. Choose `Deploy from GitHub repo`.
4. Select:

   ```text
   abdulhaseeb16/playto-payout
   ```

5. Choose the branch:

   ```text
   production-readiness
   ```

6. Railway may create an initial service. If it points at the repo root, keep it but configure it as the backend API in the next step.

### 6.3 Configure the Backend API Service

Open the Railway service settings for the backend API.

Set the root directory:

```text
playto-payout/backend
```

Set the start command:

```bash
python manage.py collectstatic --noinput && python manage.py migrate && gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
```

Why this command:

- `collectstatic` prepares Django static files for WhiteNoise.
- `migrate` applies schema changes on deploy.
- `gunicorn` runs Django in production.

If Railway complains about variable expansion with `$PORT`, use the shell-wrapped form:

```bash
sh -c "python manage.py collectstatic --noinput && python manage.py migrate && gunicorn config.wsgi:application --bind 0.0.0.0:$PORT"
```

### 6.4 Add PostgreSQL on Railway

1. In the Railway project canvas, click `New`.
2. Choose `Database`.
3. Choose `PostgreSQL`.
4. Wait for the database service to finish provisioning.
5. Open the PostgreSQL service.
6. Go to `Variables`.
7. Confirm Railway exposes a PostgreSQL connection URL.

Use that value as the backend service `DATABASE_URL`.

Typical value:

```env
DATABASE_URL=${{Postgres.DATABASE_URL}}
```

The exact service name may differ. Use Railway's variable picker to reference the PostgreSQL service instead of typing credentials manually.

### 6.5 Add Redis on Railway

1. In the Railway project canvas, click `New`.
2. Choose `Database` or search for `Redis`.
3. Add the Redis template/service.
4. Wait for Redis to finish provisioning.
5. Open the Redis service.
6. Go to `Variables`.
7. Confirm Railway exposes:

   ```text
   REDIS_URL
   ```

Use that value as the backend service `REDIS_URL`.

Typical value:

```env
REDIS_URL=${{Redis.REDIS_URL}}
```

Again, use Railway's variable picker if the service name is different.

### 6.6 Add Backend API Environment Variables

Open the backend API service, go to `Variables`, and add:

```env
DJANGO_SETTINGS_MODULE=config.settings.production
DEBUG=False
SECRET_KEY=<generate-a-long-random-secret>
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
ALLOWED_HOSTS=<temporary-backend-domain>
CORS_ALLOWED_ORIGINS=<temporary-frontend-origin>
CSRF_TRUSTED_ORIGINS=<temporary-frontend-origin>
SECURE_SSL_REDIRECT=True
```

At this point, you may not have the final Railway or Vercel domains yet. Use placeholders, deploy once, generate the domains, then come back and replace them.

Generate a strong secret locally:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Do not commit the generated value.

### 6.7 Deploy the Backend API Once

1. Click `Deploy` or let Railway deploy after variables are saved.
2. Open deployment logs.
3. Confirm these steps complete:

   ```text
   collectstatic
   migrate
   gunicorn listening
   ```

4. Open service `Settings`.
5. Go to `Networking`.
6. Click `Generate Domain`.
7. Copy the backend URL.

Example:

```text
https://playto-payout-api.up.railway.app
```

Now update backend API variables:

```env
ALLOWED_HOSTS=playto-payout-api.up.railway.app
```

If you do not have the Vercel frontend URL yet, leave CORS/CSRF temporary and update it after Vercel deployment.

Redeploy the backend after changing variables.

### 6.8 Verify the Backend API

Open:

```text
https://<railway-backend-domain>/healthz/
```

Expected:

```json
{"status": "ok"}
```

Open:

```text
https://<railway-backend-domain>/api/v1/
```

Expected:

- JSON response
- `name` is `Playto Payout API`
- `endpoints` are listed

If this fails with `DisallowedHost`, fix `ALLOWED_HOSTS`.

If this redirects too much, temporarily set:

```env
SECURE_SSL_REDIRECT=False
```

Then redeploy and inspect Railway proxy headers.

### 6.9 Create the Celery Worker Service

In Railway:

1. Click `New`.
2. Choose `GitHub repo`.
3. Select the same repo and branch.
4. Name the service:

   ```text
   celery-worker
   ```

5. Set root directory:

   ```text
   playto-payout/backend
   ```

6. Set start command:

   ```bash
   celery -A config worker --loglevel=info --concurrency=4
   ```

7. Add the same variables as the backend API:

   ```env
   DJANGO_SETTINGS_MODULE=config.settings.production
   DEBUG=False
   SECRET_KEY=<same-secret-as-api>
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   REDIS_URL=${{Redis.REDIS_URL}}
   ALLOWED_HOSTS=<railway-backend-domain>
   CORS_ALLOWED_ORIGINS=<vercel-frontend-origin>
   CSRF_TRUSTED_ORIGINS=<vercel-frontend-origin>
   SECURE_SSL_REDIRECT=True
   ```

8. Deploy and check logs.

Expected logs include Celery booting and connecting to Redis.

### 6.10 Create the Celery Beat Service

In Railway:

1. Click `New`.
2. Choose `GitHub repo`.
3. Select the same repo and branch.
4. Name the service:

   ```text
   celery-beat
   ```

5. Set root directory:

   ```text
   playto-payout/backend
   ```

6. Set start command:

   ```bash
   celery -A config beat --loglevel=info
   ```

7. Add the same variables as the backend API.
8. Deploy and check logs.

Run exactly one Celery beat service. More than one scheduler can enqueue duplicate periodic jobs.

### 6.11 Optional: Seed Demo Data on Railway

Only do this for a demo or assessment deployment.

In the backend API service shell or Railway command runner, run:

```bash
python manage.py shell < seed.py
```

Do not run this against real production data. The seed script resets demo tables.

After seeding, open:

```text
https://<railway-backend-domain>/api/v1/
```

`seeded_merchants` should contain demo merchants.

## 7. Vercel Frontend Deployment

Use Vercel for the React/Vite frontend only.

Official references:

- Vercel Vite guide: `https://vercel.com/docs/frameworks/frontend/vite`
- Vercel build settings: `https://vercel.com/docs/deployments/configure-a-build`
- Vercel environment variables: `https://vercel.com/docs/environment-variables`
- Vercel CLI deploy: `https://vercel.com/docs/cli/deploy`

### 7.1 Import the GitHub Repository

1. Open Vercel.
2. Click `Add New`.
3. Choose `Project`.
4. Import:

   ```text
   abdulhaseeb16/playto-payout
   ```

5. If Vercel asks which branch to deploy, choose:

   ```text
   production-readiness
   ```

   Or choose `main` if you already merged production changes into `main`.

### 7.2 Configure Vercel Project Settings

Set these values during import:

```text
Framework Preset: Vite
Root Directory: playto-payout/frontend
Install Command: npm ci
Build Command: npm run build
Output Directory: dist
```

Vercel usually detects Vite automatically, but set these explicitly because this repository is nested under `playto-payout/frontend`.

### 7.3 Add Vercel Environment Variables

In Vercel project settings, add this variable for `Production` and `Preview`:

```env
VITE_API_URL=https://<railway-backend-domain>/api/v1
```

Example:

```env
VITE_API_URL=https://playto-payout-api.up.railway.app/api/v1
```

Vite only exposes variables prefixed with `VITE_`, and Vercel injects them during the build. If this value changes, redeploy the frontend.

### 7.4 Deploy the Frontend

Click `Deploy`.

Expected build flow:

```text
npm ci
npm run build
dist uploaded to Vercel
```

After deploy, copy the Vercel production URL.

Example:

```text
https://playto-payout.vercel.app
```

### 7.5 Update Railway CORS and CSRF for Vercel

Go back to Railway backend API service variables.

Set:

```env
CORS_ALLOWED_ORIGINS=https://<vercel-frontend-domain>
CSRF_TRUSTED_ORIGINS=https://<vercel-frontend-domain>
```

Example:

```env
CORS_ALLOWED_ORIGINS=https://playto-payout.vercel.app
CSRF_TRUSTED_ORIGINS=https://playto-payout.vercel.app
```

If you also want Vercel preview deployments to work, add their exact preview origin too:

```env
CORS_ALLOWED_ORIGINS=https://playto-payout.vercel.app,https://playto-payout-git-production-readiness-<team>.vercel.app
CSRF_TRUSTED_ORIGINS=https://playto-payout.vercel.app,https://playto-payout-git-production-readiness-<team>.vercel.app
```

Do not include trailing slashes.

Redeploy the Railway backend API after changing variables.

### 7.6 Verify the Vercel Frontend

Open:

```text
https://<vercel-frontend-domain>
```

Confirm:

- The dashboard loads.
- The merchant dropdown appears.
- Balance cards load from Railway.
- Payout history loads.
- Ledger history loads.
- Creating a small payout works in a demo environment.

If the dashboard does not load:

1. Open browser dev tools.
2. Check the Network tab for the API URL.
3. Confirm it points to:

   ```text
   https://<railway-backend-domain>/api/v1
   ```

4. If it points to `localhost`, fix `VITE_API_URL` in Vercel and redeploy.
5. If it shows a CORS error, fix Railway `CORS_ALLOWED_ORIGINS` and redeploy the backend.

### 7.7 Vercel CLI Alternative

From the repo root:

```bash
npm install -g vercel
vercel --cwd playto-payout/frontend
```

For production:

```bash
vercel --cwd playto-payout/frontend --prod
```

If deploying with CLI, make sure `VITE_API_URL` is configured in Vercel project settings or pass it as a build env:

```bash
vercel --cwd playto-payout/frontend --prod --build-env VITE_API_URL=https://<railway-backend-domain>/api/v1
```

### 7.8 Final Railway + Vercel Verification

Check backend:

```text
https://<railway-backend-domain>/healthz/
https://<railway-backend-domain>/api/v1/
```

Check frontend:

```text
https://<vercel-frontend-domain>
```

Check Celery:

1. Create a payout from the frontend.
2. Open Railway logs for `celery-worker`.
3. Confirm `process_payout` tasks run.
4. Open Railway logs for `celery-beat`.
5. Confirm periodic tasks are being scheduled.

Deployment is complete when the frontend can create payouts and the worker processes them.

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
