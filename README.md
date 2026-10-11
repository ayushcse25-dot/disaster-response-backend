# Disaster Response Platform: Backend

FastAPI + MongoDB (PyMongo async API). Floods MVP: flood events, affected locations,
observations, resource needs and inventory, response teams, NGOs, rule-based NGO selection
and allocation plans, human approval, field tasks for NGO workers, and a scripted demo.
No LLM or paid API is used anywhere.

## Requirements
- Python 3.12 (3.11+ should work; only 3.12 has been tested)
- MongoDB 7 **running as a replica set** (plan approval uses transactions): a local
  single-node replica set (below) or MongoDB Atlas.

## Setup (Fedora)

```bash
sudo dnf install python3.12 podman
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
${EDITOR:-nano} .env               # set MONGODB_URI and AUTH_SECRET
```

Local MongoDB as a single-node replica set, with a named volume so data survives restarts:

```bash
podman run -d --name disaster-mongo -p 27017:27017 -v disaster-mongo-data:/data/db \
  docker.io/library/mongo:7 --replSet rs0 --bind_ip_all
podman exec disaster-mongo mongosh --quiet --eval \
  'rs.initiate({_id:"rs0",members:[{_id:0,host:"localhost:27017"}]})'   # first time only
```

Then in `.env`: `MONGODB_URI=mongodb://localhost:27017/?replicaSet=rs0`.
After a reboot: `podman start disaster-mongo`.

## Setup (Windows PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
notepad .env          # set MONGODB_URI
```

## Run (from the project root, where .env lives)

```bash
python -m uvicorn app.main:app --reload
DEMO_ENABLED=true python -m uvicorn app.main:app --reload    # with the demo director
```

Interactive docs: http://127.0.0.1:8000/docs

To reach the API from a phone on the same Wi-Fi:

```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
sudo firewall-cmd --add-port=8000/tcp          # current session only
```

Then use `http://<your-LAN-IP>:8000` (find it with `ip -4 addr`).

## Test

```bash
python -m pytest -q
```

Unit and API tests need no database. Integration tests (plan lifecycle, orchestration, auth,
tasks, demo) use a throwaway `drp_test_*` database on
`mongodb://localhost:27017/?replicaSet=rs0` (override with `TEST_MONGODB_URI`), drop it
afterwards, and are skipped when no replica set is reachable.

## Sample data and accounts

```bash
python -m scripts.seed_sample --confirm
```

Writes 3 NGOs (`sample-org-001` River Aid Patna and `sample-org-002` Ganga Seva Hajipur are in
range of the Patna event; `sample-org-003` in Guwahati is out of range), 3 flood events,
5 affected locations (with `population_affected` where known), 5 observations, 3 sources,
4 inventory records and 3 response teams (all `sample-org-001`), 5 resource needs and 2 plans
(`sample-plan-001` READY, `sample-plan-002` BLOCKED). Every sample record has an ID starting
with `sample-` and `is_sample: true`; records later derived from sample data (orchestration,
approval, demo) also carry `is_sample: true`.

It also (re)creates four sample accounts and **prints their passwords once in the seed
output** (new random passwords on every run; only hashes are stored):

| Role | Login |
|---|---|
| AUTHORITY | `authority@sample.local` |
| NGO_ADMIN (sample-org-001) | `ngo1@sample.local` |
| NGO_ADMIN (sample-org-002) | `ngo2@sample.local` |
| WORKER (sample-org-001) | ngo_code `RIVERAID`, worker_id `W-001` |

Refuses to run without `--confirm`. Idempotent. Never modifies non-sample records.

## Authentication

- `POST /api/v1/auth/login` `{email, password}` (authority, NGO admin) and
  `POST /api/v1/auth/worker-login` `{ngo_code, worker_id, password}` return
  `{access_token, expires_in, user}`. Send `Authorization: Bearer <token>`.
- Tokens are HMAC-SHA256 signed with `AUTH_SECRET` and carry `sub`, `role`, `ngo_id`, `exp`.
  The account is re-read on every request, so disabling it takes effect immediately.
  Passwords are stored as PBKDF2-SHA256 hashes.
- Every route except `/health/*` and the two login routes needs a token. Staff routes accept
  AUTHORITY and NGO_ADMIN; orchestration, plan generation and the demo are AUTHORITY only;
  workers can use `/me` and `/tasks` only. NGO admins see and act on only their own
  organisation's plans, tasks and workers (403 `NGO_SCOPE`).
- NGO admins create workers with `POST /api/v1/ngos/{ngo_id}/workers`; the response contains
  the issued `worker_id` and a temporary password, shown only once.

## Errors

Every error body is `{"detail": ..., "code": "..."}` with a stable `code`, e.g.
`UNAUTHENTICATED`, `FORBIDDEN_ROLE`, `NGO_SCOPE`, `PLAN_NOT_FOUND`, `VERSION_CONFLICT`,
`MANUAL_ALLOCATION_INVALID`, `INVALID_TRANSITION`, `ORCHESTRATION_BLOCKED`, `NO_ELIGIBLE_NGO`,
`WAITING_FOR_APPROVAL`, `DEMO_DISABLED`, `VALIDATION_ERROR`, `DATABASE_UNAVAILABLE`.

## Routes

All business routes are under `/api/v1`. Responses use `snake_case`; lists are plain arrays.
"Staff" = AUTHORITY or NGO_ADMIN.

| Method | Path | Who |
|---|---|---|
| GET | `/health/live`, `/health/ready` | public |
| POST | `/api/v1/auth/login`, `/api/v1/auth/worker-login` | public |
| GET | `/api/v1/me` | any signed-in user |
| POST, GET | `/api/v1/ngos/{ngo_id}/workers` | NGO admin (own NGO), authority |
| POST | `/api/v1/ngos/{ngo_id}/workers/{worker_id}/disable` | NGO admin (own NGO), authority |
| POST | `/api/v1/orchestration/run` `{event_id}` | authority |
| POST, GET | `/api/v1/flood-events` | staff |
| GET | `/api/v1/flood-events/{event_id}` | staff |
| GET | `/api/v1/flood-events/{event_id}/observations` | staff |
| GET | `/api/v1/flood-events/{event_id}/affected-locations` | staff |
| GET | `/api/v1/flood-events/{event_id}/resource-needs` | staff |
| POST | `/api/v1/flood-events/{event_id}/allocation-plans` | authority |
| GET | `/api/v1/flood-events/{event_id}/allocation-plans` | staff (NGO: own plans only) |
| POST, GET | `/api/v1/flood-events/{event_id}/field-reports` | staff |
| GET | `/api/v1/flood-events/{event_id}/reallocation-recommendations` | staff |
| POST | `/api/v1/affected-locations` | staff |
| GET | `/api/v1/affected-locations/{location_id}` | staff |
| POST | `/api/v1/resource-needs` | staff |
| GET | `/api/v1/resource-needs/{need_id}` | staff |
| POST | `/api/v1/resource-inventory` | staff |
| GET | `/api/v1/resource-inventory/{inventory_id}` | staff |
| GET | `/api/v1/organisations/{organisation_id}/resource-inventory` | staff |
| POST | `/api/v1/response-teams` | staff |
| GET | `/api/v1/response-teams/{team_id}` | staff |
| GET | `/api/v1/organisations/{organisation_id}/response-teams` | staff |
| PATCH | `/api/v1/response-teams/{team_id}/status`, `/location` | staff |
| GET | `/api/v1/allocation-plans/{plan_id}` | staff (NGO: own plans) |
| POST | `/api/v1/allocation-plans/{plan_id}/approve`, `/reject` | staff (NGO: own plans) |
| POST | `/api/v1/allocation-plans/{plan_id}/replan` | staff (NGO: own plans) |
| POST | `/api/v1/allocation-plans/{plan_id}/manual-allocation` | staff (NGO: own plans) |
| GET | `/api/v1/tasks`, `/api/v1/tasks/{task_id}` | worker (own), NGO admin (own NGO), authority |
| POST | `/api/v1/tasks/{task_id}/assign` `{worker_id}` | NGO admin, authority |
| POST | `/api/v1/tasks/{task_id}/acknowledge`, `/start`, `/problem`, `/submit` | assigned worker |
| POST | `/api/v1/tasks/{task_id}/verify`, `/reject` | NGO admin, authority |
| POST | `/api/v1/demo/reset`, `/api/v1/demo/step`; GET `/api/v1/demo/state` | authority, `DEMO_ENABLED=true` |

## How the pipeline works

### Orchestration (`app/services/orchestration/`)

`POST /api/v1/orchestration/run {event_id}`:
1. Gate: the event must be ACTIVE, VERIFIED and have a location (422 `ORCHESTRATION_BLOCKED`).
2. `need_estimation`: severity + `population_affected` per location → advisory needs from a
   fixed rate table; locations missing either input are listed in `missing_inputs`, never guessed.
3. `ngo_selection`: hard filters (status APPROVED, event within `service_radius_km` of
   `base_location`), then a weighted score — distance 0.30, capability coverage 0.30, usable
   (allocation-eligible) resources 0.25, workload 0.15 — tie-break on distance then ID, with a
   templated explanation.
4. The existing allocation engine runs on the selected NGO's inventory and teams; the READY
   plan is stored (`ngo_id` set, next version) with an `ngo_assignments` record and an
   `NGO_SELECTED` decision audit.
5. Idempotent: an input digest covers every record that can change the outcome; rerunning on
   unchanged data returns the stored result with `reused: true`.

Nothing is approved automatically.

### Plan versions and replanning

- Plans carry `version` (per event), `source` (ENGINE/MANUAL), `supersedes_plan_id` and
  `superseded_by_plan_id`. A pending plan that is superseded becomes `SUPERSEDED`.
- `POST .../replan {expected_version, actor_id}` reruns the engine as version + 1;
  409 `VERSION_CONFLICT` if the plan is not at that version or is already superseded.
- `POST .../manual-allocation {expected_version, actor_id, reason, items: [{need_id,
  inventory_id, team_id, quantity}]}` validates each item with the engine's eligibility checks
  (need status, freshness, confirmation, stock, unit, type/capability compatibility); returns
  422 `MANUAL_ALLOCATION_INVALID` with `detail: [{index, need_id, reasons}]`, or stores a
  `source: MANUAL` plan as version + 1.
- `replan_suggested` and `replan_reasons` on GET responses are computed at read time: the
  event is no longer ACTIVE/VERIFIED, a planned resource or team is now ineligible (pending
  plans) or stale (approved plans), or a worker reported a problem on one of the plan's tasks.

### Plan approval

Approving or rejecting uses a MongoDB transaction (replica set required; a standalone
`mongod` returns 503 and writes nothing). Approval reserves stock, marks teams ASSIGNED and
creates one task per decision. Replanning an approved plan does not release its reservations.

### Tasks

Tasks are the `deployment_assignments` created on approval, with `ngo_id`, need/inventory/
quantity, the assigned worker, `photo_refs` (plain strings for now) and a `history` of
actor/action/time entries. Flow: APPROVED → `assign` → ASSIGNED → `acknowledge` →
ACKNOWLEDGED → `start` → IN_PROGRESS → `submit` → SUBMITTED → `verify` → NGO_VERIFIED, or
`reject` → FAILED. `problem` (from ACKNOWLEDGED/IN_PROGRESS, note required) → PROBLEM and
flags the plan for replanning; `start` resumes. Invalid transitions return 409.

### Demo director

Off unless `DEMO_ENABLED=true` (otherwise 404 `DEMO_DISABLED`). Uses only sample data and the
real services. `reset` deletes demo-derived sample records and reseeds (accounts are kept).
Each `step` advances one stage on `sample-event-001`:

1. WARNING_RECEIVED — a sample rainfall warning observation is recorded.
2. PLAN_GENERATED — orchestration selects an NGO and stores a READY plan.
3. TASKS_CREATED — **only after a human approves that plan** (409 `WAITING_FOR_APPROVAL`
   until then); tasks are assigned to worker `W-001`.
4. DISRUPTION — W-001 acknowledges and reports a problem (or, with no worker, the planned
   stock turns stale); the plan shows `replan_suggested`.
5. REPLANNED — the plan is replanned as the next version.

`GET /api/v1/demo/state` returns the current step and a timestamped timeline.

### Flood event severity

`severity` and `severity_basis` on flood-event responses are derived on the server
(`app/services/event_severity.py`): the highest severity among the event's affected locations
(CRITICAL > HIGH > MODERATE > LOW), ignoring UNKNOWN locations; UNKNOWN when no location has
a known severity. Clients should display it, not recompute it.

### Resource freshness and eligibility

Inventory and response-team responses include fields derived on the server
(`app/services/resource_freshness.py`):

- `check_in_due_at` = last check-in + `check_in_interval_hours` (inventory: `last_verified_at`
  + 24 h; teams: `last_status_update` + 2 h — the limits the allocation engine applies).
- `freshness`: FRESH before the final 25% of the interval, DUE in the final 25%, STALE at or
  after `check_in_due_at`, UNVERIFIED if there is no check-in or it is in the future.
  `freshness_rule` states this in every response.
- `eligible_for_allocation` and `status_reason`: the same checks the allocation engine uses
  (status, confirmation, age, remaining stock / personnel / existing assignment).

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
`disaster_response`. `AUTH_SECRET` signs tokens (the built-in default is for local
development only). `TOKEN_TTL_MINUTES` defaults to 720. `DEMO_ENABLED` defaults to false.
`LOG_LEVEL` must be uppercase (`DEBUG`, `INFO`, `WARNING`, `ERROR`). Never commit `.env`.

## Status

Built (MVP, runs locally):
- Flood events, observations, affected locations, needs, inventory, teams, freshness.
- NGOs with a service area; need estimation, NGO selection and the orchestration run.
- Rule-based allocation engine; plan versions, replan, manual allocation, replan advice.
- Transactional human approval and rejection; field tasks with history.
- Staff and worker login, role and NGO scope checks, worker creation and disabling.
- Sample seed and demo director.

NOT built:
- Citizen OTP login.
- Contributor / volunteer applications.
- Area alerts.
- Photo upload (photo references are plain strings).
- Push notifications.
- Deployment (no container image, CI or hosted environment).
- Also missing: password change for temporary passwords, token revocation, NGO
  registration/approval endpoints (NGOs exist only through the seed).
