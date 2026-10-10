# Disaster Response Platform: Backend

FastAPI + MongoDB Atlas (PyMongo async API). Initial scaffold: health checks and the
database connection only.

## Requirements
- Python 3.12 (3.11+ should work; only 3.12 has been tested)
- A MongoDB Atlas cluster with a dedicated database user and your IP allowed under Network Access

## Setup (Windows PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
notepad .env          # set MONGODB_URI
```

If activation is blocked: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned`

## Run (from the project root, where .env lives)

```powershell
python -m uvicorn app.main:app --reload
```

Interactive docs: http://127.0.0.1:8000/docs

## Test (needs no MongoDB, credentials or network)

```powershell
python -m pytest -v
```

## Health endpoints

| Endpoint | Meaning | Healthy | Unhealthy |
|---|---|---|---|
| `GET /health/live` | The process is running. Never touches MongoDB. | 200 `{"status":"ok","checks":{"application":"up"}}` | n/a |
| `GET /health/ready` | MongoDB answers a ping (checked on every call). | 200 `{"status":"ok","checks":{"database":"up"}}` | 503 `{"status":"unavailable","checks":{"database":"down"}}` |

Responses never contain connection strings, hostnames or driver error text.

## Configuration

See `.env.example`. `MONGODB_URI` is required. `LOG_LEVEL` must be uppercase
(`DEBUG`, `INFO`, `WARNING`, `ERROR`). Never commit `.env`.
