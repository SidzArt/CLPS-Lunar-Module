# CLPS Luna Browser — API & SSR Master Reference

> **Scope:** Complete technical API specification covering **98 FastAPI OpenAPI operations** (`/api/v1/*`, `/health`, `/ready`) and **Express 5 SSR / SEO / reverse-proxy routes** (`/robots.txt`, `/sitemap.xml`, `/site/:slug`, `/sites`, `/api/*`, `/storage/*`, catch-all SSR HTML), including security headers, cookie/CSRF authentication, RBAC matrix, rate limits, request/response schemas, and example payloads.  
> **Evidence Tags:** All paths, schemas, middleware headers, and RBAC dependencies are marked `[VERIFIED IN SOURCE]` directly from FastAPI OpenAPI schema inspection, router modules, `middleware.py`, `csrf.py`, `rate_limit.py`, and `frontend/server/ssr-server.mjs`.

---

## 1. Request Architecture, Reverse Proxy & End-to-End Request Flow

In production/SSR deployments (`run_clps.sh` or Node Express 5 server), browsers interact with a **single origin** (`Express 5 SSR` on port `3000` / `4173`), which renders SSR HTML directly and proxies `/api/*` and `/storage/*` to `FastAPI/Uvicorn` (`127.0.0.1:8000`) `[VERIFIED IN SOURCE]`. Because browser requests hit one origin, `clps_session` (`HttpOnly`) and `clps_csrf` cookies work naturally without third-party cookie blockers `[INFERRED]`.

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant E as "Express 5 SSR Server (:3000/:4173)"
    participant F as "FastAPI Backend (:8000)"
    participant P as "PostgreSQL 18"

    B->>E: GET /sites/lunokhod-1
    E->>E: Generate 128-bit per-request CSP nonce
    E->>F: Internal fetch /api/v1/sites/lunokhod-1 (+ sub-resources)
    F->>P: Query published site dossier
    P-->>F: Site rows
    F-->>E: JSON payloads
    E->>E: Dehydrate TanStack Query state + React SSR
    E-->>B: HTML + strict nonce CSP + security headers

    B->>E: POST /api/v1/admin/sites (Cookie: clps_session, clps_csrf; Header: X-CSRF-Token)
    E->>F: Proxy request forwarding Host/Proto & Set-Cookie headers
    F->>F: RequestIdMiddleware -> CORS -> get_current_admin -> validate_origin + HMAC CSRF -> RequireRole
    F->>P: Transactional write + audit_logs insert
    P-->>F: Commit
    F-->>E: 201 Created + X-Request-ID + X-Process-Time
    E-->>B: Proxied response
```

---

## 2. Middleware, Headers, Errors & Rate Limits

### 2.1 FastAPI Security Middleware & Error Format (`backend/app/core/middleware.py`, `main.py`)
Every response returned by FastAPI includes `[VERIFIED IN SOURCE]`:
- `X-Request-ID`: Echoes client-provided `X-Request-ID` or generates `req_<16-hex>` (bound into structured logs via `request_id_ctx`).
- `X-Process-Time`: Wall-clock execution duration (`"{secs:.4f}s"`).
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: camera=(), microphone=(), geolocation=(), usb=()`
- `Content-Security-Policy`: On `/api/*` JSON routes (excluding `/api/v1/docs`, `/redoc`, `/openapi.json`), sets `default-src 'none'; frame-ancestors 'none'`.
- `Strict-Transport-Security`: Set when `ENABLE_HSTS=true` and protocol is HTTPS or `APP_ENV == "production"`.

**CORS (`CORSMiddleware` in `main.py`):**
- `allow_origins`: Configurable via `CORS_ORIGINS` (defaults: `http://localhost:3000`, `http://127.0.0.1:3000`, `http://localhost:5173`, `http://127.0.0.1:5173`).
- `allow_credentials=True`, methods `["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]`, exposed headers `["X-Request-ID", "X-Process-Time"]` `[VERIFIED IN SOURCE]`.

**Error Envelopes (`main.py`):**
- **Pydantic Validation (`422`):**
  ```json
  {
    "code": "VALIDATION_ERROR",
    "message": "Input validation failed. Inspect field errors.",
    "field_errors": [{"field": "body.latitude_deg", "message": "Input should be less than or equal to 90"}],
    "request_id": "req_a1b2c3d4e5f60718"
  }
  ```
- **Unhandled Exceptions (`500`):** Same envelope with `"code": "INTERNAL_SERVER_ERROR"` and stack trace withheld `[VERIFIED IN SOURCE]`.
- **Standard Route `HTTPException` (`400`, `401`, `403`, `404`, `409`, `423`, `429`):** FastAPI default `{"detail": "..."}` JSON response `[VERIFIED IN SOURCE]`.

### 2.2 Express 5 SSR Security & SEO Controls (`frontend/server/ssr-server.mjs`, `seo-routes.mjs`)
- **Host Header Spoofing Defense (`resolveRequestBaseUrl`):** Uses `PUBLIC_BASE_URL` if configured; otherwise reads `x-forwarded-host`/`x-forwarded-proto` **ONLY** when `TRUST_PROXY=true`, and validates hostname against `ALLOWED_HOSTS` (default `127.0.0.1,localhost,[::1]`) + regex `/^(\[::1\]|[a-zA-Z0-9.-]+)(?::(\d{1,5}))?$/` `[VERIFIED IN SOURCE]`.
- **Per-Request CSP Nonce (`214-250`):** Injects 128-bit random Base64 `nonce-...` onto inline script tags (excluding `application/ld+json` structured data) and sets `script-src 'self' 'nonce-...'`, `object-src 'none'`, `frame-ancestors 'self'`, `base-uri 'self'`, `form-action 'self'` `[VERIFIED IN SOURCE]`.
- **SSR Admin Cache Prevention:** Any request starting with `/admin` receives `Cache-Control: no-store, max-age=0` `[VERIFIED IN SOURCE]`.
- **Static Media Proxy & Storage:** `/storage/*` proxies directly to FastAPI `/storage/media` mount (`.webp` images/thumbnails) `[VERIFIED IN SOURCE]`.

| Express Route | Behavior | Source Verification |
|---|---|---|
| `GET /robots.txt` | Allows `/`, `/browser`, `/sites/`, `/contact`, `/privacy`, `/terms`; disallows `/compare`, `/ai-assist`, `/simulation`, `/codex`, `/admin`, `/api/`; links dynamic `Sitemap:` URL | `[VERIFIED IN SOURCE]` |
| `GET /sitemap.xml` | Fetches published sites from FastAPI `/api/v1/sites?status=published` (up to 10 pages × 100); gracefully degrades to static entries if backend offline | `[VERIFIED IN SOURCE]` |
| `GET /sites` | HTTP `301` redirect to `/browser` | `[VERIFIED IN SOURCE]` |
| `GET /site/:slug` | HTTP `301` redirect to `/sites/<encoded_slug>` | `[VERIFIED IN SOURCE]` |
| `USE /api`, `USE /storage` | Raw-body binary/multipart transparent reverse proxy preserving multi-value `Set-Cookie`; returns `502 BACKEND_UNAVAILABLE` if FastAPI unreachable | `[VERIFIED IN SOURCE]` |
| `GET`/`HEAD` catch-all | Server-side React + TanStack Query SSR render returning semantic status codes (`200` or `404` on unknown routes) | `[VERIFIED IN SOURCE]` |

### 2.3 Sliding-Window In-Memory Rate Limiters (`backend/app/core/rate_limit.py`)
Per-client-IP sliding 60-second window + active concurrency semaphore (`HTTP 429` + `Retry-After` header) `[VERIFIED IN SOURCE]`:

| Limiter | Applied Routes | Requests / Min | Max Concurrent |
|---|---|---|---|
| `compare_rate_limiter` | `POST /api/v1/compare` | 60 | 20 |
| `codex_rate_limiter` | `POST /api/v1/codex/runs/prepare`, `POST /api/v1/codex/runs` | 30 | 4 |
| `simulation_rate_limiter` | `POST /api/v1/simulations` | 20 | 5 |
| `ai_assist_rate_limiter` | `POST /api/v1/ai-assist/recommend` | 15 | 2 |
| `auth_login_rate_limiter` | `POST /api/v1/auth/login` | `15` (`AUTH_RATE_LIMIT_MAX_ATTEMPTS`) | 10 |
| `contact_rate_limiter` | `POST /api/v1/contact` | 10 | 5 |

*(Limitation `[INFERRED]`: Rate limiters use single-process `asyncio.Lock` + in-memory `dict[ip, deque]`; scaling Uvicorn to multiple worker processes would partition counters per worker unless moved to Redis/PostgreSQL.)*

---

## 3. Authentication, Double-Submit HMAC CSRF & RBAC Matrix

### 3.1 Session, Password & CSRF Mechanics (`auth.py`, `auth_dependency.py`, `csrf.py`, `security.py`)
- **Dual Auth Support:** Browser UI uses **`clps_session` (`HttpOnly`, `SameSite=Lax`, `Secure` in HTTPS/prod, `24h` TTL)** paired with readable **`clps_csrf` (`HttpOnly=False`)** echoed in **`X-CSRF-Token`**. Automated/CLI clients may pass `Authorization: Bearer <raw_token>` `[VERIFIED IN SOURCE]`.
- **Database Session Storage:** Only SHA-256 `hash_token(raw_token)` is stored in `admin_sessions.token_hash`; `last_active_at` commits are throttled to `>= 60s` intervals `[VERIFIED IN SOURCE]`.
- **HMAC-Bound CSRF:** Token format `{nonce}.{HMAC-SHA256(SESSION_SECRET, f"{token_hash_or_anon}:{nonce}")}`, checked with `hmac.compare_digest` + strict `Origin`/`Referer` validation (`allowed_origins_for_request`) on every cookie-authenticated `POST`, `PUT`, `PATCH`, `DELETE` `[VERIFIED IN SOURCE]`.
- **Password Hashing & Policy (`security.py`):** Argon2id via `pwdlib.PasswordHash((Argon2Hasher(),))`; policy requires `>= 12` chars, upper, lower, digit, and special character `[VERIFIED IN SOURCE]`.
- **Brute-Force Lockout (`auth.py`):** `AUTH_LOCKOUT_THRESHOLD = 5` failed logins lock the account for `AUTH_LOCKOUT_MINUTES = 15` (`HTTP 423 Locked`), resetting `failed_login_count` on success; login rotates prior `clps_session`; `/change-password` revokes all prior active sessions `[VERIFIED IN SOURCE]`.

### 3.2 Complete RBAC Permission Matrix (`RequireRole` across all routers)

> **Rule:** `super_admin` bypasses all role checks universally in [`RequireRole`](file:///Users/siddharthwaikar/Personal/CodexBase/NASA%20Space%20App%20Challenge/CLPS%20Lunar%20Module/backend/app/core/auth_dependency.py#L105-L124) `[VERIFIED IN SOURCE]`. Any authenticated admin with a non-revoked session can access `/api/v1/auth/me`, `/auth/logout`, `/auth/change-password`, and `/admin/overview` (`get_current_admin` returns role-filtered metrics).

| Capability / Router Group | `super_admin` | `system_admin` | `site_editor` | `research_admin` | `hardware_admin` | `hardware_operator` | `viewer` |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Admin Profile / Logout / Overview (`/auth/me`, `/admin/overview`) | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| Admin Read Sites, Media, Params, Regions, Sources, Sim Diagnostics | Yes | Yes | Yes | Yes | *SimDiag* | *SimDiag* | Yes |
| Create/Edit/Archive/Delete Sites, Sections, History, Pros-Cons, Media | Yes | No | **Yes** | *Metrics* | No | No | No |
| Manage Data Sources (`POST`/`PATCH /admin/sources`) | Yes | No | **Yes** | **Yes** | No | No | No |
| List Imports (`GET /admin/imports`) | Yes | **Yes** | **Yes** | **Yes** | No | No | No |
| Upload/Preview/Commit/Rollback Dataset Imports (`/admin/imports/*`) | Yes | No | No | **Yes** | No | No | No |
| CODEX Prepare / Execute / Status / Events / E-STOP (`/codex/*`) | Yes | **Yes** | No | No | **Yes** | **Yes** | No |
| CODEX Admin Devices, Config, Calibrations, LED Map, Firmware Editor (`/admin/codex/*`, `/admin/hardware/*`) | Yes | **Yes** | No | No | **Yes** | No | No |
| System Health Probes & Audit Log Explorer (`/admin/audit-logs`, `/admin/system/health`) | Yes | **Yes** | No | No | No | No | No |
| User & Role Lifecycle, Password Reset, Session Revoke (`/admin/users*`, `/admin/roles`) | **Yes** | No | No | No | No | No | No |

*(Notes `[VERIFIED IN SOURCE]`: `*Metrics*` = `research_admin` shares `PUT /admin/sites/{site_id}/metrics`; `*SimDiag*` = `/admin/simulations/diagnostics` allows `viewer`, `research_admin`, `site_editor`, `hardware_operator`, `hardware_admin`, `system_admin`.)*

---

## 4. Complete FastAPI Route Reference (All 98 Operations)

### 4.1 Health, Readiness & Auth (`/health`, `/ready`, `/api/v1/auth/*`)

| Method | Path | Auth | Params / Body | Response (`Success`, `Errors`) |
|---|---|---|---|---|
| `GET` | `/health`, `/api/v1/health` | Public | `—` | `200 HealthStatus` (`status`, `version`, `timestamp_utc`, `environment`) |
| `GET` | `/ready`, `/api/v1/ready` | Public | `—` | `200 ReadinessStatus` (`status`, `database`, `database_latency_ms`, `components`) |
| `GET` | `/api/v1/auth/csrf` | Optional cookie | Cookie `clps_session` | `200 CsrfTokenOut` (`csrf_token`), sets `clps_csrf` cookie |
| `POST` | `/api/v1/auth/login` | Public + Origin check | `AdminLoginIn` (`username*`, `password*`) | `200 AdminAuthOut` + cookies; `401`, `403`, `423 Locked`, `429` |
| `POST` | `/api/v1/auth/logout` | Cookie + CSRF / Bearer | Optional cookies/header | `200 {"status": "LOGGED_OUT", "message": ...}`, clears cookies |
| `GET` | `/api/v1/auth/me` | Any active admin | Cookie / Bearer | `200 AdminProfileOut`, `401` |
| `POST` | `/api/v1/auth/change-password` | Any active admin + CSRF | `AdminChangePasswordIn` (`current_password*`, `new_password*`) | `200 AdminAuthOut` (rotates all sessions); `400`, `401` |

### 4.2 Public Catalogue & Search (`/api/v1/sites*`, `/api/v1/search`)

| Method | Path | Params / Query | Response Model | Notes |
|---|---|---|---|---|
| `GET` | `/api/v1/sites` | `page`, `page_size` (<=100), `region_id`, `status` (must be `published`), `search`, `sort` (`name`, `elevation_asc`, `elevation_desc`, `updated_at`) | `200 PaginatedResponse[SiteCardOut]` | Enforces `400` if non-`published` requested |
| `GET` | `/api/v1/sites/{site_slug}` | Path `site_slug*` | `200 SiteDetailOut`, `404` | Published sites only |
| `GET` | `/api/v1/sites/{site_slug}/sections` | Path `site_slug*`, Query `section_key` | `200 list[SiteSectionOut]`, `404` | Bounded 2-query lookup |
| `GET` | `/api/v1/sites/{site_slug}/sections/{section_key}` | Path `site_slug*`, `section_key*` | `200 list[SiteSectionOut]` / filtered | Single section key filter |
| `GET` | `/api/v1/sites/{site_slug}/pros-cons` | Path `site_slug*` | `200 list[SiteProConOut]`, `404` | Ordered PRO/CON list |
| `GET` | `/api/v1/sites/{site_slug}/metrics` | Path `site_slug*` | `200 list[SiteMetricOut]`, `404` | Includes provenance citations & quality status |
| `GET` | `/api/v1/sites/{site_slug}/media` | Path `site_slug*` | `200 list[SiteMediaOut]`, `404` | Normalized WebP URLs |
| `GET` | `/api/v1/sites/{site_slug}/history` | Path `site_slug*` | `200 list[SiteHistoryOut]`, `404` | Historical timeline |
| `GET` | `/api/v1/search` | Query `q*`, `limit` | `200 list[SearchResultOut]`, `422` | PostgreSQL trigram + GIN `tsvector` FTS |

### 4.3 Comparison, AI Assist & Support Contact (`/api/v1/compare*`, `/ai-assist/*`, `/contact`)

| Method | Path | Limiter / Body | Response Model |
|---|---|---|---|
| `GET` | `/api/v1/compare/profiles` | Public | `200 list[ComparisonProfileOut]` (5 seeded profiles + weights) |
| `POST` | `/api/v1/compare` | `compare_rate_limiter`; `ComparisonRequestIn` (`site_a_id*`, `site_b_id*`, `mission_purpose*`, `profile_key`, `profile_id`, `custom_parameters`) | `200 ComparisonResultOut` (persists `comparison_runs` + `comparison_results`) |
| `POST` | `/api/v1/ai-assist/recommend` | `ai_assist_rate_limiter`; `AIAssistRequestIn` (`mission_request*`, `max_recommendations`, `min_score_threshold`) | `200 AIAssistResponseOut` (`extracted_requirements`, ranked sites, `fallback_used`, `model_used`) |
| `POST` | `/api/v1/contact` | `contact_rate_limiter`; `ContactSubmitIn` (`sender_name*`, `sender_email*`, `subject*`, `message_body*`, `website` honeypot) | `201 ContactSubmitOut` (`message_id`, `status`, `received_at`, `notice`) |

### 4.4 Scientific Simulation Engine (`/api/v1/simulations*`)

| Method | Path | Params / Body | Response Model |
|---|---|---|---|
| `POST` | `/api/v1/simulations` | `simulation_rate_limiter`; `SimulationCreateIn` (`site_id*`, `start_time*`, `duration_seconds*`, `playback_speed`, `idempotency_key`) | `202 SimulationCreateOut` (creates `simulation_runs` + `background_jobs`) |
| `GET` | `/api/v1/simulations/{simulation_id}` | Path `simulation_id*` (UUID) | `200 SimulationStatusOut` (`quality_state`, `kernel_manifest`, `dem_metadata`, `summary_metrics`, disclaimers) |
| `POST` | `/api/v1/simulations/{simulation_id}/cancel` | Path `simulation_id*` (UUID) | `200 SimulationCancelOut` (cooperative worker cancellation) |
| `GET` | `/api/v1/simulations/{simulation_id}/series` | Path `simulation_id*`; Query `start_time`, `end_time`, `offset`, `limit`, `downsample`, `include_horizon` | `200 SimulationSeriesOut` (samples with Sun/Earth Az/El/Horizon/Dir vectors + 360° horizon profile) |
| `GET` | `/api/v1/simulations/{simulation_id}/events` | Path `simulation_id*`; Query `event_type` | `200 SimulationEventsOut` (`SUNRISE`, `SUNSET`, `EARTH_RISE`, `EARTH_SET`, `CONCURRENT_VISIBLE`, etc.) |

### 4.5 CODEX Operator Endpoints (`/api/v1/codex/*`)

| Method | Path | Auth | Request / Params | Response Model |
|---|---|---|---|---|
| `GET` | `/api/v1/codex/status` | **Public (sanitized)** | `—` | `200 PublicCodexStatusOut` (mode, overall readiness, blockers, controller flags; zero secrets/IPs) |
| `POST` | `/api/v1/codex/runs/prepare` | `hardware_operator`, `hardware_admin`, `system_admin` + `codex_rate_limiter` | `CodexRunPrepareIn` | `200 CodexRunPrepareOut` (no actuation; kinematics + 13-region LED plan + 16-step checklist) |
| `POST` | `/api/v1/codex/runs` | Same + `codex_rate_limiter` | `CodexRunExecuteIn` (`hardware_run_id*`, `confirmed*`, `idempotency_key*`, `execution_mode`) | `201 CodexRunStatusOut` (requires `confirmed=true` + 16-step gate unless mock/fallback policy permits) |
| `GET` | `/api/v1/codex/runs/{run_id}` | Same | Path `run_id*` | `200 CodexRunStatusOut` |
| `GET` | `/api/v1/codex/runs/{run_id}/events` | Same | Path `run_id*` | `200 CodexRunEventsOut` |
| `POST` | `/api/v1/codex/estop` | Same (no limiter) | `CodexEstopIn` (`reason`, `hardware_run_id`) | `200 CodexEstopOut` |

### 4.6 Admin Portal Routes (`/api/v1/admin/*` — 63 Operations)

<details>
<summary>Complete Inventory of All 63 Admin Operations (Click to Expand / Read Linearly)</summary>

**Overview, Provenance, Health & Audit (`audit.py`, `simulations_admin.py`):**
- `GET /api/v1/admin/overview` (Any active admin -> `200 AdminOverviewOut`)
- `GET /api/v1/admin/audit-logs` (`system_admin`; filter `action_key`, `entity_type`, `admin_id`, `date_from`, `date_to`, `page`, `page_size` -> `200 AuditLogPageOut`)
- `GET /api/v1/admin/system/health` (`system_admin` -> `200 SystemHealthSummaryOut`; host paths scrubbed)
- `GET /api/v1/admin/regions` (`site_editor`, `research_admin`, `system_admin`, `viewer` -> `200 list[LunarRegionOut]`)
- `GET /api/v1/admin/sources` (`site_editor`, `research_admin`, `system_admin`, `viewer` -> `200 list[DataSourceOut]`)
- `POST /api/v1/admin/sources` (`research_admin`, `site_editor`; `DataSourceCreateIn` -> `201 DataSourceOut`)
- `PATCH /api/v1/admin/sources/{source_id}` (`research_admin`, `site_editor`; `DataSourceUpdateIn` -> `200 DataSourceOut`)
- `GET /api/v1/admin/simulations/diagnostics` (`viewer`, `research_admin`, `site_editor`, `hardware_operator`, `hardware_admin`, `system_admin` -> `200 AdminSimulationDiagnosticsOut`)

**Users & RBAC (`users.py`, all `super_admin`):**
- `GET /api/v1/admin/roles` -> `200 list[RoleOut]`
- `GET /api/v1/admin/users` -> `200 list[AdminUserOut]` (never exposes `password_hash`)
- `POST /api/v1/admin/users` (`AdminUserCreateIn` -> `201 AdminUserOut`)
- `PATCH /api/v1/admin/users/{admin_id}` (`AdminUserUpdateIn` -> `200 AdminUserOut`)
- `POST /api/v1/admin/users/{admin_id}/reset-password` (`AdminResetPasswordIn` -> `200 AdminUserOut`, revokes active sessions)
- `POST /api/v1/admin/users/{admin_id}/revoke-sessions` -> `200 AdminSessionRevokeOut`

**Sites, Content, History, Pros/Cons & Metrics (`sites_admin.py`):**
- `GET /api/v1/admin/parameters` (`site_editor`, `research_admin`, `system_admin`, `viewer` -> `200 list[ParameterDefinitionAdminOut]`)
- `GET /api/v1/admin/sites` (`site_editor`, `research_admin`, `system_admin`, `viewer` -> `200 PaginatedResponse[SiteCardOut]`)
- `POST /api/v1/admin/sites` (`site_editor`; `SiteCreateIn` -> `201 SiteDetailOut`)
- `GET /api/v1/admin/sites/{site_id}` (`site_editor`, `research_admin`, `system_admin`, `viewer` -> `200 SiteDetailOut`)
- `PATCH /api/v1/admin/sites/{site_id}` (`site_editor`; `SiteUpdateIn` -> `200 SiteDetailOut`)
- `POST /api/v1/admin/sites/{site_id}/archive` (`site_editor` -> `200 SiteDetailOut`)
- `DELETE /api/v1/admin/sites/{site_id}` (`site_editor` -> `200` draft/archived only)
- `GET /api/v1/admin/sites/{site_id}/sections` (Read roles -> `list[SiteSectionOut]`)
- `POST` / `PATCH /{content_id}` / `DELETE /{content_id}` on `/api/v1/admin/sites/{site_id}/sections` (`site_editor`)
- `GET /api/v1/admin/sites/{site_id}/history` (Read roles -> `list[SiteHistoryOut]`)
- `POST` / `PATCH /{history_id}` / `DELETE /{history_id}` on `/api/v1/admin/sites/{site_id}/history` (`site_editor`)
- `GET /api/v1/admin/sites/{site_id}/pros-cons` (Read roles -> `list[SiteProConOut]`)
- `POST` / `PATCH /{point_id}` / `DELETE /{point_id}` on `/api/v1/admin/sites/{site_id}/pros-cons` (`site_editor`)
- `GET /api/v1/admin/sites/{site_id}/media` (Read roles -> `list[SiteMediaOut]`)
- `GET /api/v1/admin/sites/{site_id}/metrics` (Read roles -> `list[SiteMetricOut]`)
- `PUT /api/v1/admin/sites/{site_id}/metrics` (`site_editor`, `research_admin`; `SiteMetricsBulkUpsertIn` -> `200 list[SiteMetricOut]`)

**Media Library (`media_admin.py`):**
- `GET /api/v1/admin/media` (`site_editor`, `research_admin`, `system_admin`, `viewer` -> `200 AdminMediaListOut` including `orphan_files`)
- `POST /api/v1/admin/media/upload` (`site_editor`, multipart image/form-data -> `201 SiteMediaOut`, Pillow-reencoded WebP + thumbnail)
- `PATCH /api/v1/admin/media/{media_id}` (`site_editor`; `MediaUpdateIn` -> `200 SiteMediaOut`)
- `PATCH /api/v1/admin/media/{media_id}/primary` (`site_editor` -> `200 SiteMediaOut`)
- `DELETE /api/v1/admin/media/{media_id}` (`site_editor` -> `200`)

**Dataset Imports (`imports_admin.py`):**
- `GET /api/v1/admin/imports` (`research_admin`, `site_editor`, `system_admin` -> `200 ImportListOut`)
- `POST /api/v1/admin/imports` (`research_admin`, multipart `file` `<=15 MB`, `source_id` -> `201 ImportDetailOut`; `400` on malformed UTF-8/XLSX/GeoJSON)
- `GET /api/v1/admin/imports/{import_id}` (`research_admin` -> `200 ImportDetailOut`)
- `GET /api/v1/admin/imports/{import_id}/preview` (`research_admin` -> `200 ImportPreviewOut`)
- `POST /api/v1/admin/imports/{import_id}/commit` (`research_admin` -> `200 ImportCommitOut`)
- `POST /api/v1/admin/imports/{import_id}/rollback` (`research_admin` -> `200 ImportRollbackOut`)

**CODEX Hardware & Split-Pane Firmware Admin (`codex_admin.py`, all `hardware_admin`, `system_admin`):**
- `GET /api/v1/admin/codex/devices` -> `200 AdminDevicesListOut`
- `POST /api/v1/admin/codex/devices/{controller_key}/heartbeat` (`DeviceHeartbeatIn`) -> `200 AdminHardwareDeviceOut`
- `GET /api/v1/admin/codex/configurations` -> `200 list[HardwareConfigurationOut]`
- `PUT /api/v1/admin/codex/configurations/{controller_key}` (`ConfigurationUpsertIn`) -> `200 HardwareConfigurationOut`
- `GET /api/v1/admin/codex/calibrations` -> `200 list[CalibrationProfileOut]`
- `POST /api/v1/admin/codex/calibrations` (`CalibrationCreateIn`) -> `201 CalibrationProfileOut`
- `PATCH /api/v1/admin/codex/calibrations` (`CalibrationUpdateIn`) -> `200 CalibrationProfileOut`
- `GET /api/v1/admin/codex/led-mapping` -> `200 list[MoonLedRegionOut]`
- `POST /api/v1/admin/codex/led-mapping` (`MoonLedRegionUpsertIn`) -> `200 MoonLedRegionOut`
- `GET /api/v1/admin/codex/runs` -> `200 list[HardwareRunAdminSummaryOut]`
- `GET /api/v1/admin/hardware/code-versions` -> `200 list[CodeVersionOut]`
- `POST /api/v1/admin/hardware/code-versions` (`CodeVersionCreateIn`) -> `201 CodeVersionDetailOut`
- `GET /api/v1/admin/hardware/code-versions/{code_version_id}` -> `200 CodeVersionDetailOut`
- `POST /api/v1/admin/hardware/code-versions/{code_version_id}/activate` -> `200 CodeVersionOut`
- `GET /api/v1/admin/hardware/code-versions/{code_version_id}/diff/{other_version_id}` -> `200 CodeVersionDiffOut`
- `POST /api/v1/admin/hardware/code-versions/{code_version_id}/validate-syntax` -> `200 CodeVersionSyntaxValidationOut`
- `POST /api/v1/admin/hardware/code-versions/{code_version_id}/render-preview` (`CodeVersionRenderIn`) -> `200` preview
- `GET /api/v1/admin/hardware/variables` -> `200 list[HardwareVariableRefOut]`

</details>

---

## 5. Representative Request / Response Examples

### 5.1 Deterministic Site Comparison (`POST /api/v1/compare`)
**Request:**
```json
{
  "site_a_id": 1,
  "site_b_id": 5,
  "mission_purpose": "Continuous south polar photovoltaic operations",
  "profile_key": "solar_maximization"
}
```
**Key Response Fields (`ComparisonResultOut`):**
`run_id` (UUID persisted in `comparison_runs`), `overall_score_a`, `overall_score_b`, `overall_winner` (`"SITE_A" | "SITE_B" | "TIE"`), `data_coverage`, per-parameter rows (`normalised_a`, `normalised_b`, `data_quality_status`, `source_reference`), `scientific_conclusion`, and `limitations_and_caveats` `[VERIFIED IN SOURCE]`.

### 5.2 AI-Assisted Recommendation (`POST /api/v1/ai-assist/recommend`)
**Request:** `{"mission_request": "I need high illumination and gentle terrain slopes for solar lander power", "max_recommendations": 5}`  
**Behavior:** Attempts local Ollama (`gemma4:e4b`) JSON extraction with deterministic Pydantic schema validation. If Ollama times out (`15s`) or trips the circuit breaker (`3` failures -> `60s` open window), falls back seamlessly to keyword/rule extraction and sets `fallback_used: true`, `model_used: "rule-based-fallback"` `[VERIFIED IN SOURCE]`.

### 5.3 Queueing a SPICE + LOLA DEM Simulation (`POST /api/v1/simulations`)
**Request:**
```json
{
  "site_id": 5,
  "start_time": "2026-06-01T00:00:00Z",
  "duration_seconds": 259200,
  "playback_speed": 600,
  "idempotency_key": "ui-sim-mouton-20260601"
}
```
**Response (`202 Accepted`):** Returns `simulation_id`, `job_id`, `status: "queued"`, `quality_state: "pending"`, `sampling_policy`, and immediate `data_coverage_warnings` if the site lies outside available south polar LOLA DEM coverage `[VERIFIED IN SOURCE]`.

---

## 6. TypeScript Client Contract Generation (`frontend/src/api/`)

- `frontend/src/api/generated/schema.ts` is generated from FastAPI's live OpenAPI spec via `openapi-typescript` (`npm run generate:api-types`) `[VERIFIED IN SOURCE]`.
- `frontend/src/api/client.ts` attaches `credentials: "include"`, automatically reads document cookie `clps_csrf`, attaches `X-CSRF-Token` on non-GET/HEAD requests, and handles HTTP `401`/`403` cleanly without storing any authentication token in `localStorage` or `sessionStorage` `[VERIFIED IN SOURCE]`.
