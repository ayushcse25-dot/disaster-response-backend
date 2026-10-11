# Disaster Response Platform: Backend

FastAPI + MongoDB Atlas (PyMongo async API). Floods MVP: flood events, affected locations,
observations, resource needs and inventory, response teams, allocation plans and live
field reports.

## Requirements
- Python 3.12 (3.11+ should work; only 3.12 has been tested)
- A MongoDB Atlas cluster with a dedicated database user and your IP allowed under Network Access

## Setup (Fedora / Linux)

```bash
sudo dnf install python3.12        # if `python3.12 --version` fails
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
${EDITOR:-nano} .env               # set MONGODB_URI
```

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

```bash
python -m uvicorn app.main:app --reload
```

Interactive docs: http://127.0.0.1:8000/docs

To reach the API from a phone on the same Wi-Fi, bind to all interfaces and open the port:

```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
sudo firewall-cmd --add-port=8000/tcp          # current session only
```

Then use `http://<your-LAN-IP>:8000` (find it with `ip -4 addr`).

## Test (needs no MongoDB, credentials or network)

```bash
python -m pytest -v
```

The test suite sets a dummy `MONGODB_URI` itself and never connects to a real cluster.

## Sample data

```bash
python -m scripts.seed_sample --confirm
```

Writes 3 flood events, 5 affected locations, 5 observations and 3 sources into the database
named by `MONGODB_DB_NAME`. Every sample record has an ID starting with `sample-`,
`is_sample: true`, and the text `SAMPLE DATA — NOT LIVE FLOOD INFORMATION`.

- Refuses to run without `--confirm`.
- Idempotent: re-running replaces the same records (timestamps are re-based to "now").
- Never modifies non-sample records; if a sample ID is taken by a non-sample record it
  aborts before writing anything.

## Routes

All business routes are under `/api/v1`. Responses use `snake_case` fields; lists are
plain JSON arrays paginated with `?limit=&skip=`.

| Method | Path |
|---|---|
| GET | `/health/live` |
| GET | `/health/ready` |
| POST, GET | `/api/v1/flood-events` |
| GET | `/api/v1/flood-events/{event_id}` |
| GET | `/api/v1/flood-events/{event_id}/observations` |
| GET | `/api/v1/flood-events/{event_id}/affected-locations` |
| GET | `/api/v1/flood-events/{event_id}/resource-needs` |
| POST, GET | `/api/v1/flood-events/{event_id}/allocation-plans` |
| POST, GET | `/api/v1/flood-events/{event_id}/field-reports` |
| GET | `/api/v1/flood-events/{event_id}/reallocation-recommendations` |
| POST | `/api/v1/affected-locations` |
| GET | `/api/v1/affected-locations/{location_id}` |
| POST | `/api/v1/resource-needs` |
| GET | `/api/v1/resource-needs/{need_id}` |
| POST | `/api/v1/resource-inventory` |
| GET | `/api/v1/resource-inventory/{inventory_id}` |
| GET | `/api/v1/organisations/{organisation_id}/resource-inventory` |
| POST | `/api/v1/response-teams` |
| GET | `/api/v1/response-teams/{team_id}` |
| GET | `/api/v1/organisations/{organisation_id}/response-teams` |
| PATCH | `/api/v1/response-teams/{team_id}/status` |
| PATCH | `/api/v1/response-teams/{team_id}/location` |
| GET | `/api/v1/allocation-plans/{plan_id}` |
| POST | `/api/v1/allocation-plans/{plan_id}/approve` |
| POST | `/api/v1/allocation-plans/{plan_id}/reject` |

There is no authentication yet.

### Flood event severity

`severity` and `severity_basis` on flood-event responses are derived on the server
(`app/services/event_severity.py`): the highest severity among the event's affected locations
(CRITICAL > HIGH > MODERATE > LOW), ignoring UNKNOWN locations; UNKNOWN when no location has
a known severity. Clients should display it, not recompute it.

### Observations

`GET /api/v1/flood-events/{event_id}/observations` returns observations newest-observed first,
with `source_name`, `source_category` and `source_approval_status` joined from the source
registry (null if the source is missing). `observed_at` is the time at the source,
`received_at` the time we retrieved it. `freshness` is FRESH (< 1 h), RECENT (< 24 h) or
STALE, based on `observed_at` at request time. `evidence_reference` is never returned.
404 if the event does not exist.

## Health endpoints

| Endpoint | Meaning | Healthy | Unhealthy |
|---|---|---|---|
| `GET /health/live` | The process is running. Never touches MongoDB. | 200 `{"status":"ok","checks":{"application":"up"}}` | n/a |
| `GET /health/ready` | MongoDB answers a ping (checked on every call). | 200 `{"status":"ok","checks":{"database":"up"}}` | 503 `{"status":"unavailable","checks":{"database":"down"}}` |

Responses never contain connection strings, hostnames or driver error text.

## Configuration

See `.env.example`. `MONGODB_URI` is required. `MONGODB_DB_NAME` defaults to
`disaster_response`. `LOG_LEVEL` must be uppercase (`DEBUG`, `INFO`, `WARNING`, `ERROR`).
Never commit `.env`.
