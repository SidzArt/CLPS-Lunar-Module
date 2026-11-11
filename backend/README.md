# CLPS Luna Browser — Backend

Modular monolith backend for the **CLPS Luna Browser** platform, built with Python 3.12, FastAPI, SQLAlchemy 2.0, psycopg 3, and PostgreSQL 18.

## System Architecture

```
backend/
├── app/
│   ├── main.py              # FastAPI application factory & lifespan
│   ├── core/
│   │   ├── config.py        # Pydantic Settings & environment variables
│   │   ├── logging.py       # Structured logging with Request ID propagation
│   │   ├── middleware.py    # Request ID, timing, and security headers
│   │   └── security.py      # Password hashing & cryptographic tokens
│   ├── db/
│   │   ├── base.py          # SQLAlchemy 2.0 DeclarativeBase
│   │   ├── session.py       # Engine pool & database session generator
│   │   └── init_db.py       # Readiness check & connection verification
│   ├── models/              # Relational domain entities (SQLAlchemy 2.0)
│   │   ├── catalogue.py     # NASA regions, landing sites, content, media
│   │   ├── metrics.py       # Parameter definitions, site metrics, observations
│   │   ├── comparison.py    # Mission comparison profiles, runs, results
│   │   ├── simulation.py    # Simulation runs, time series, event windows
│   │   ├── codex.py         # Hardware configs, code versions, runs, events
│   │   ├── admin.py         # Admin accounts, roles, sessions, audit logs
│   │   └── operations.py    # Background jobs, contact messages, builds
│   ├── schemas/             # Pydantic v2 validation contracts
│   └── api/v1/              # Thin API routes
├── alembic/                 # Versioned schema migrations
├── tests/                   # Pytest automated test suites
├── pyproject.toml           # Locked Python dependencies managed via uv
└── alembic.ini              # Alembic migration configuration
```

## Local Development Setup

1. **Prerequisites:**
   - PostgreSQL 18+ running on `localhost:5432`
   - Python 3.12 managed via `uv`

2. **Database Provisioning:**
   ```bash
   createuser clps_app --pwprompt
   createdb clps_luna --owner=clps_app
   ```

3. **Install Dependencies:**
   ```bash
   uv sync --extra dev
   ```

4. **Run Database Migrations:**
   ```bash
   uv run alembic upgrade head
   ```

5. **Start Development Server:**
   ```bash
   uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

6. **Run Test Suite:**
   ```bash
   uv run pytest
   ```

