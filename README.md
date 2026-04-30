# Playto Payout

Django + React payout engine built around an append-only ledger, database-level concurrency control, idempotent payout creation, and asynchronous payout processing.

## Architecture

- Backend: Django, Django REST Framework, PostgreSQL, Celery, Redis
- Frontend: React, Vite, Tailwind CSS
- Ledger: balance is derived from `LedgerEntry` credits minus debits; no stored balance column
- Payout safety: payout creation uses `transaction.atomic()` and `select_for_update()` on the merchant row
- Idempotency: `Idempotency-Key` is scoped per merchant, stores a SHA-256 request fingerprint, and replays the original response
- State machine: legal transitions are centralized in `ledger/state_machine.py`

## Local Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py shell < seed.py
python manage.py runserver
```

API base URL:

```text
http://localhost:8000/api/v1
```

Open this URL in the browser to see the API index and seeded merchant dashboard links.

## Local Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend URL:

```text
http://localhost:5173
```

The frontend uses the first three deterministic merchant IDs created by `backend/seed.py`.
The seed script creates 10 merchants and demo rows for every ledger app table:
`Merchant`, `BankAccount`, `LedgerEntry`, `Payout`, and `IdempotencyKey`.

## API

```text
GET  /api/v1/merchants/<merchant_id>/dashboard/
POST /api/v1/payouts/
POST /api/v1/merchants/<merchant_id>/payouts/
GET  /api/v1/merchants/<merchant_id>/payouts/<payout_id>/
```

Create payout request:

```bash
curl -X POST http://localhost:8000/api/v1/payouts/ \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: 00000000-0000-4000-8000-000000000001" \
  -d "{\"amount_paise\":5000,\"bank_account_id\":\"<bank_account_uuid>\"}"
```

## Workers

Redis must be running on `localhost:6379` before starting Celery:

```powershell
Test-NetConnection localhost -Port 6379
```

On Windows, use `--pool=solo` for the Celery worker:

```bash
cd backend
.venv\Scripts\activate
celery -A config worker --loglevel=info --pool=solo
celery -A config beat --loglevel=info
```

`process_payout` simulates bank settlement. `retry_stuck_payouts` retries payouts left in `processing`.

## Tests

```bash
cd backend
.venv\Scripts\activate
python manage.py test ledger
```

For the full browser + API verification flow, see [E2E_TESTING.md](E2E_TESTING.md).

The test suite covers:

- concurrent overdraw prevention
- idempotent replay
- idempotency key scoping per merchant
- different-body reuse rejection
- flat `/api/v1/payouts/` compatibility endpoint
- state machine terminal-state enforcement

## Docker Compose

```bash
docker compose up --build
```

Services:

- PostgreSQL on `5432`
- Redis on `6379`
- Django API on `8000`
- Celery worker
- Celery beat
- Frontend on `80`

## Deployment Notes

For Railway-style deployment:

1. Provision PostgreSQL and Redis.
2. Set `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `ALLOWED_HOSTS`, and `CORS_ALLOWED_ORIGINS`.
3. Deploy backend with:

   ```bash
   gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
   ```

4. Run once:

   ```bash
   python manage.py migrate
   python manage.py shell < seed.py
   ```

5. Deploy separate Celery worker and beat services.
6. Deploy the frontend with `VITE_API_URL` pointing to the backend `/api/v1` URL.
