# End-to-End Testing Guide

This guide verifies the full Playto Payout project from backend API to frontend UI.

## Prerequisites

- Python 3.11+
- Node 18+
- PostgreSQL running locally
- Redis running locally if you want Celery payout processing to execute automatically

The local backend expects:

```env
DATABASE_HOSTNAME=localhost
DATABASE_PORT=5432
DATABASE_USERNAME=postgres
DATABASE_PASSWORD=Haseeb@16
DATABASE_NAME=fastapi
```

## 1. Backend Setup

From PowerShell:

```powershell
cd "C:\Users\Wajida\Downloads\Playto Pay\playto-payout\backend"
.\.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
Get-Content .\seed.py | python manage.py shell
```

Expected seed result:

```text
Merchants: 10
Bank accounts: 10
Ledger entries: 40
Payouts: 40
Idempotency keys: 40
```

## 2. Backend Automated Checks

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test ledger --noinput
```

Expected:

```text
System check identified no issues
No changes detected
9 tests OK
```

## 3. Start Backend

```powershell
python manage.py runserver
```

Open:

```text
http://localhost:8000/api/v1/
```

Expected:

- JSON response named `Playto Payout API`
- `seeded_merchants` contains 10 merchants
- each merchant has a dashboard link

Example dashboard:

```text
http://localhost:8000/api/v1/merchants/11111111-1111-4111-8111-111111111111/dashboard/
```

Expected:

- `merchant`
- `balance`
- `payouts`
- `ledger_entries`

## 4. API Payout Test

First get a real bank account ID:

```powershell
$api = "http://localhost:8000/api/v1"
$merchantId = "11111111-1111-4111-8111-111111111111"
$dashboard = Invoke-RestMethod "$api/merchants/$merchantId/dashboard/"
$bankId = $dashboard.merchant.bank_accounts[0].id
$bankId
```

Create payout:

```powershell
$key = [guid]::NewGuid().ToString()
$body = @{ amount_paise = 5000; bank_account_id = $bankId } | ConvertTo-Json
$payout1 = Invoke-RestMethod "$api/payouts/" `
  -Method Post `
  -ContentType "application/json" `
  -Headers @{ "Idempotency-Key" = $key } `
  -Body $body
$payout1
```

Expected:

- HTTP 201
- payout status starts as `pending`

Replay same request with same idempotency key:

```powershell
$payout2 = Invoke-RestMethod "$api/payouts/" `
  -Method Post `
  -ContentType "application/json" `
  -Headers @{ "Idempotency-Key" = $key } `
  -Body $body

$payout1.id -eq $payout2.id
```

Expected:

```text
True
```

Reuse same key with a different body:

```powershell
$badBody = @{ amount_paise = 6000; bank_account_id = $bankId } | ConvertTo-Json
try {
  Invoke-RestMethod "$api/payouts/" `
    -Method Post `
    -ContentType "application/json" `
    -Headers @{ "Idempotency-Key" = $key } `
    -Body $badBody
} catch {
  [int]$_.Exception.Response.StatusCode
}
```

Expected:

```text
409
```

## 5. Frontend Setup

Open a second PowerShell terminal:

```powershell
cd "C:\Users\Wajida\Downloads\Playto Pay\playto-payout\frontend"
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

Expected:

- dashboard loads
- merchant dropdown shows seeded merchants from the backend
- balance card shows total, held, and available balance
- payout form shows the selected merchant bank account
- payout history shows existing seeded payouts
- recent ledger entries show credits and debits

## 6. Frontend Manual Flow

1. Select `Velocity Creative Agency`.
2. Enter amount `50`.
3. Select the bank account.
4. Click `Request Payout`.
5. Confirm success message appears.
6. Confirm payout history updates.
7. Refresh browser and confirm dashboard still loads from backend.

## 7. Production Build Check

```powershell
cd "C:\Users\Wajida\Downloads\Playto Pay\playto-payout\frontend"
npm run build
```

Expected:

```text
built successfully
```

## 8. Optional Celery Worker Test

Celery requires Redis before the worker or beat can start. If Redis is not running, you will see:

```text
Cannot connect to redis://localhost:6379/0
Error 10061 connecting to localhost:6379
```

Check Redis from PowerShell:

```powershell
Test-NetConnection localhost -Port 6379
```

Expected:

```text
TcpTestSucceeded : True
```

If it is `False`, start Redis first. Pick one option:

Option A, Docker Desktop installed:

```powershell
docker run --name playto-redis -p 6379:6379 redis:7-alpine
```

Option B, WSL Ubuntu:

```bash
sudo apt update
sudo apt install redis-server
redis-server --bind 0.0.0.0 --port 6379
```

Option C, native Windows Redis-compatible server:

- Install Memurai Developer or another local Redis-compatible server.
- Start it on port `6379`.

Then open two extra PowerShell terminals.

Worker:

```powershell
cd "C:\Users\Wajida\Downloads\Playto Pay\playto-payout\backend"
.\.venv\Scripts\activate
celery -A config worker --loglevel=info --pool=solo
```

Beat:

```powershell
cd "C:\Users\Wajida\Downloads\Playto Pay\playto-payout\backend"
.\.venv\Scripts\activate
celery -A config beat --loglevel=info
```

Then create a payout from the frontend and watch it move from `pending` to `processing`, then eventually to `completed`, `failed`, or stay `processing` until retry.

## 9. Reset Demo Data

Any time you want a clean database:

```powershell
cd "C:\Users\Wajida\Downloads\Playto Pay\playto-payout\backend"
Get-Content .\seed.py | python manage.py shell
```

This resets the app tables back to the deterministic 10-merchant demo state.
