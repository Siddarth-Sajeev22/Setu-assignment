# Payment Events Service

A backend service for ingesting payment lifecycle events, querying transaction state, and detecting reconciliation discrepancies. Built with FastAPI and PostgreSQL.

---

## Architecture

The service follows a three-layer architecture 

```
HTTP Request
     │
     ▼
┌─────────────┐
│   Routers   │   FastAPI route handlers. Validate query params, delegate to services/repos.
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Services   │   Business logic — event processing, state machine, reconciliation.
└──────┬──────┘
       │
       ▼
┌──────────────────┐
│  Repositories    │   One class per table. All SQL lives here. No business logic.
└──────┬───────────┘
       │
       ▼
┌─────────────┐
│  PostgreSQL │   Hosted on Supabase.
└─────────────┘
```

**Routers** (`app/routers/`) handle HTTP concerns — request parsing, response shaping, HTTP status codes, and error translation.

**Services** (`app/services/`) own business logic. The event processor enforces the payment state machine and three-layer idempotency. The reconciliation service derives discrepancy types and reasons from already-loaded data.

**Repositories** (`app/repositories/`) are the only layer that touches the database. Each repository maps to one table and returns ORM objects. All filtering, aggregation, sorting, and pagination happens in SQL here 

---

## Data Model

```
merchants
  id            PK
  merchant_id   VARCHAR(100)  UNIQUE   -- external string ID (e.g. "merchant_1")
  merchant_name VARCHAR(255)
  created_at    DATETIME

transactions
  id             PK
  transaction_id VARCHAR(36)   UNIQUE  -- UUID from the event payload
  merchant_id    FK → merchants.id
  amount         NUMERIC(15,2)
  currency       VARCHAR(3)
  status         VARCHAR(20)           -- initiated | processed | failed | settled
  created_at     DATETIME
  updated_at     DATETIME

payment_events
  id             PK
  event_id       VARCHAR(36)   UNIQUE  -- UUID, enforces idempotency at DB level
  transaction_id FK → transactions.id
  event_type     VARCHAR(20)           -- payment_initiated | payment_processed | payment_failed | settled
  timestamp      DATETIME              -- event time from the payload
  created_at     DATETIME              -- ingestion time
```

### Indexes

UNIQUE constraints on `merchant_id`, `transaction_id`, and `event_id` implicitly create B-tree indexes, so no redundant separate indexes are added for those columns.

Additional indexes created for query patterns:

| Index | Columns | Reason |
|---|---|---|
| `idx_transactions_merchant_id` | `merchant_id` | Joining merchants to transactions |
| `idx_transactions_status` | `status` | Filtering by status |
| `idx_transactions_created_at` | `created_at` | Filtering by date range |
| `idx_transaction_merchant_status` | `merchant_id, status` | Combined merchant + status filter |
| `idx_transaction_created_status` | `created_at, status` | Combined date + status filter |
| `idx_payment_events_transaction_event_type` | `transaction_id, event_type` | Discrepancy subqueries filter on both columns together |

---

## Payment State Machine

Events drive state transitions on a transaction. Invalid transitions are rejected.

```
payment_initiated → payment_processed → settled
payment_initiated → payment_failed    (terminal)
```

- `failed` and `settled` are terminal states. Any event targeting a transaction in these states is rejected.
- A transaction's first event must always be `payment_initiated`.

---

## Idempotency

Event ingestion is idempotent at three layers:

1. **Pydantic validation** — rejects malformed requests before any DB access.
2. **Business logic check** — queries the `event_id` UNIQUE index before attempting an insert. Returns the existing record with HTTP 200 if already seen.
3. **Database UNIQUE constraint** — acts as the final safety net for race conditions where two identical requests arrive simultaneously.

---

## Discrepancy Detection

Discrepancies are detected entirely in SQL using correlated subqueries, with no post-processing in Python:

- **processed_not_settled** — `status = 'processed'` and no `settled` event exists for that transaction.
- **settled_after_failed** — `status = 'settled'` but a `payment_failed` event also exists.
- **duplicate_initiated** — more than one `payment_initiated` event for the same transaction, detected with `GROUP BY / HAVING COUNT > 1`.

---

## Query Design

All aggregation, filtering, sorting, and pagination happen in SQL. Python only shapes the response. Specifically:

- `GET /transactions` applies all filters and pagination in a single query.
- `GET /reconciliation/summary` uses `GROUP BY` with `COUNT` and `SUM` in SQL, grouped by merchant, date, or status.
- `GET /reconciliation/discrepancies` uses three SQL subqueries combined with `OR` to identify problematic transactions in a single pass.

Merchant and event data is eager-loaded alongside transactions using `joinedload` (JOIN for the many-to-one merchant) and `selectinload` (SELECT IN for the one-to-many events). This means a page of 10 transactions costs 2 queries total regardless of how many events each transaction has, rather than the N+1 pattern that would otherwise fire 21 or more queries.

---

## API Reference

All endpoints return JSON. Error responses follow the format:
```json
{ "error": "message", "detail": "optional detail", "status_code": 400 }
```

### POST /events

Ingest a payment lifecycle event.

**Request body:**
```json
{
  "event_id": "b768e3a7-9eb3-4603-b21c-a54cc95661bc",
  "transaction_id": "2f86e94c-239c-4302-9874-75f28e3474ee",
  "merchant_id": "merchant_1",
  "merchant_name": "Acme Corp",
  "event_type": "payment_initiated",
  "amount": "1500.00",
  "currency": "INR",
  "timestamp": "2026-01-08T10:00:00Z"
}
```

| Field | Type | Notes |
|---|---|---|
| `event_id` | UUID string | Must be unique per event |
| `transaction_id` | UUID string | Groups events into a transaction |
| `merchant_id` | string | External merchant identifier |
| `event_type` | enum | `payment_initiated`, `payment_processed`, `payment_failed`, `settled` |
| `amount` | decimal | Must be positive |
| `currency` | string | 3-character currency code |
| `timestamp` | ISO 8601 datetime | Cannot be in the future |

**Responses:** `201` new event created, `200` duplicate event (idempotent), `400` validation or invalid state transition.

---

### GET /transactions

List transactions with optional filtering, sorting, and pagination.

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `merchant_id` | string | — | Filter by merchant |
| `status` | string | — | `initiated`, `processed`, `failed`, `settled` |
| `start_date` | datetime | — | ISO 8601 |
| `end_date` | datetime | — | ISO 8601 |
| `page` | int | 1 | 1-indexed |
| `limit` | int | 10 | Max 100 |
| `sort_by` | string | `created_at` | `created_at`, `amount`, `merchant_id` |
| `order` | string | `desc` | `asc`, `desc` |

---

### GET /transactions/{transaction_id}

Returns full transaction details including merchant info and complete event history ordered by timestamp.

**Responses:** `200` success, `404` transaction not found.

---

### GET /reconciliation/summary

Returns transaction counts and totals grouped by a dimension.

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `group_by` | string | `merchant` | `merchant`, `date`, `status`, `all` |
| `merchant_id` | string | — | Optional filter |
| `start_date` | datetime | — | Optional filter |
| `end_date` | datetime | — | Optional filter |

---

### GET /reconciliation/discrepancies

Returns transactions with inconsistent payment and settlement state, with a human-readable reason for each.

| Parameter | Type | Default |
|---|---|---|
| `page` | int | 1 |
| `limit` | int | 10 |

---

### GET /health

Returns service and database connectivity status.

---

## Running Locally

### Prerequisites

- Python 3.11+
- A PostgreSQL database (local or hosted)

### Setup

**1. Clone the repository and create a virtual environment:**

```bash
git clone https://github.com/Siddarth-Sajeev22/Setu-assignment.git
cd Setu-assignment
python -m venv .venv
```

Activate it:
```bash
# macOS / Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

**2. Install dependencies:**

```bash
pip install -r requirements.txt
```

**3. Configure environment variables:**

Create a `.env` file in the project root:

```
DATABASE_URL=postgresql://user:password@host:5432/dbname
DEBUG=false
HOST=0.0.0.0
PORT=8000
```

If your database password contains special characters (`@`, `[`, `]`, etc.), URL-encode them. For example `@` becomes `%40`.

**4. Run database migrations:**

```bash
.venv/Scripts/alembic upgrade head   # Windows
# or
.venv/bin/alembic upgrade head       # macOS / Linux
```

This creates the `merchants`, `transactions`, and `payment_events` tables with all indexes.

**5. Start the server:**

```bash
.venv/Scripts/uvicorn app.main:app --reload   # Windows
# or
.venv/bin/uvicorn app.main:app --reload       # macOS / Linux
```

The API will be available at `http://localhost:8000`. Interactive docs are at `http://localhost:8000/docs`.

**6. Load sample data:**

With the server running, in a separate terminal:

```bash
python scripts/load_events.py           # loads all ~10,000 events
python scripts/load_events.py 500       # loads first 500 events only
```

The script POSTs each event to `POST /events` and prints a summary of new events, duplicates, and errors. The target URL defaults to `http://localhost:8000` and can be overridden with the `API_URL` environment variable.

---

## Deployment

The database is hosted on Supabase (PostgreSQL). The application is deployed on Render at `https://setu-assignment.onrender.com`.

Render's free tier spins down instances after periods of inactivity. The first request after a period of inactivity may take 30–60 seconds to respond while the instance warms up. If the first few requests time out or return an error, wait a moment and retry — subsequent requests will be fast.

The Postman collection (`Payment Events Service.postman_collection.json`) is included in the repository. Import it into Postman — the `base_url` variable is already set to the deployed URL.

---

## Assumptions and Tradeoffs

**Single source of truth for transaction status.** Rather than computing status from event history on every read, the `transactions` table maintains a `status` column that is updated on each valid event. This makes reads fast but means the state machine must be enforced strictly on writes — which it is, via the service layer.

**Merchant deduplication is upsert-style.** If a `payment_initiated` event arrives for a known `merchant_id` but with a different `merchant_name`, the existing merchant record is returned as-is and the name is not updated. This avoids a write on every event for an established merchant and keeps merchant data stable.

**State machine and reconciliation are intentionally separate layers.** The state machine at ingestion time rejects logically impossible transitions (e.g. a settled transaction receiving further events, or a transaction starting with anything other than `payment_initiated`). The reconciliation endpoints then operate on data that already passed those checks, detecting business-level inconsistencies — a transaction stuck in `processed` with no settlement following, a settlement recorded alongside a failed event (which can occur when events arrive from multiple upstream systems out of order), or duplicate initiation events. These two layers complement each other; the reconciliation endpoints are not intended to re-detect what the state machine already prevented.

**Discrepancy detection is point-in-time.** The discrepancy queries reflect the current state of the database. They are not stored or cached — each call to `/reconciliation/discrepancies` runs the SQL subqueries live. This is fine at current scale; at higher volume a materialised view or a background job could precompute results.

**No soft deletes or audit trail for transactions.** The assignment does not require it, and adding it would complicate the schema and queries without a stated need.

**currency is stored as a string, not validated against ISO 4217.** The schema accepts any 3-character string. Adding a check constraint or enum is straightforward but was omitted to keep ingestion flexible given the sample data.

**Timestamp validation rejects future dates.** Events with a `timestamp` in the future are rejected at the Pydantic layer. This is a reasonable guard against bad data but could be relaxed if the use case requires pre-scheduling events.

---

## AI Tools Disclosure

Claude (Anthropic) was used during development to assist with code review, identifying N+1 query patterns, Pydantic v2 migration, and writing this README. All architectural decisions, schema design, and implementation were reviewed and directed by the developer.
