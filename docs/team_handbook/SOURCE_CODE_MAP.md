# Complete Repository Source Code & Architecture Map

> **Purpose:** Authoritative directory-by-directory, file-by-file inventory and dependency map of the CLPS Luna Browser repository (`backend/`, `frontend/`, `firmware/`, `data/`, `docs/`, and root orchestration), enabling any teammate to locate functionality, trace cross-module dependencies, and distinguish source code from tests, controlled assets, generated artifacts, and gitignored files.
> **Baseline Date:** Audited against workspace state on `2026-11-11` (`[VERIFIED IN SOURCE]`).

---

## 1. Repository Root Layout & Classification `[VERIFIED IN SOURCE]`

```text
CLPS Lunar Module/
├── .gitignore                        (42 lines)   — Config: excludes .venv, .env*, firmware secrets.h/config.h, storage/, big SPICE/DEM binaries, dist/, node_modules/
├── Readme                            (12 lines)   — Docs: local dev login credentials (test_super_admin, test_viewer) & quick start command
├── run_clps.sh                       (1,286 lines)— Infra/Launcher: bash 3.2-safe macOS orchestrator (check/start/stop/status/migrate/prod)
├── backend/                                       — Python 3.12 + FastAPI + SQLAlchemy 2 + Alembic + Worker + Pytest suite
│   ├── pyproject.toml                (57 lines)   — Deps & lint config (ruff, mypy, pytest)
│   ├── uv.lock                       (137,565 B)  — Locked Python dependency tree (64 distributions documented in Phase 8)
│   ├── alembic.ini / alembic/                     — Migration framework + 7 versioned schema/seed scripts
│   ├── app/                                       — 84 production Python modules (~20.1k lines documented in Phase 8)
│   ├── tests/                                     — 8 pytest modules (~4,417 test lines, 115 test functions verified passing)
│   └── storage/                                   — Gitignored local filesystem storage (uploaded WebP media & staged import fixtures)
├── frontend/                                      — React 19 + TypeScript 5.8 + Vite 7 + Three.js/R3F + Express 5 SSR + Vitest + Playwright
│   ├── package.json / package-lock.json           — 324 npm packages documented in Phase 8 (0 audit vulnerabilities verified)
│   ├── vite.config.ts / tsconfig.json / playwright.config.ts
│   ├── index.html                                 — Vite HTML shell with <!--app-head--> and <!--app-html--> SSR placeholders
│   ├── public/                                    — Static Moon albedo/bump 2K WebP textures, ATTRIBUTION.json, favicon.svg
│   ├── server/                                    — Express 5 SSR renderer, security headers/CSP nonce, gzip compression, SEO routes & /api proxy
│   ├── src/                                       — 51 production TS/TSX/CSS/test files: pages, admin portal, Three.js canvases, SEO, generated OpenAPI types
│   └── tests/e2e/                                 — Playwright end-to-end suites (public workflows + admin portal RBAC & mutations)
├── firmware/                                      — Three C++/Arduino sketches + per-board templates (compile-guarded, no secrets committed)
│   ├── esp32-wifi-bridge/                         — ESP32 DevKit HTTP-to-UART bridge
│   ├── arduino-uno-motion/                        — Arduino Uno + CNC Shield v3 stepper controller + hardware ESTOP
│   └── esp32-s3-moon-led/                         — ESP32-S3 26-NeoPixel Moon globe beacon controller
├── data/                                          — Controlled scientific datasets & import test fixtures
│   ├── spice-kernels/                             — manifest.json (tracked) + 6 JPL/NAIF kernels (.tls, .tpc, .tf, .bpc, .bsp — gitignored)
│   ├── lunar-dem/                                 — manifest.json (tracked) + 4 LOLA South Pole GeoTIFFs (.TIF — gitignored)
│   └── test_fixtures/                             — sample_artemis_sites.{csv,geojson,xlsx}
└── docs/
    ├── project_tracking/                          — Historical Phase 1–8 reports, matrices, hardware trackers, test evidence ledger (7 Markdown files)
    └── team_handbook/                             — Complete Technical Master Handbook & 6 companion engineering guides (this documentation suite)
```

---

## 2. Backend Module Inventory (`backend/`) `[VERIFIED IN SOURCE]`

### 2.1 Configuration, Security & Database Plumbing (`backend/app/core/`, `db/`, `worker/`, root `app/`)

| File | Lines | Bytes | Type | Responsibility & Dependencies |
|---|---:|---:|---|---|
| `backend/app/__init__.py` | 3 | 76 | Source | Package marker |
| `backend/app/main.py` | 131 | 5,499 | Source | FastAPI app factory: mounts CORS, `TrustedHostMiddleware`, `GlobalExceptionHandlerMiddleware`, GZip (`>=1000B`), `/api/v1` router, `/storage` media static mount, startup SpiceKernelManager preflight + CSRF cookie wiring. Depends on all API routers & `core/*`. |
| `backend/app/core/config.py` | 144 | 5,579 | Source | Pydantic `BaseSettings` reading `.env` & env vars (`DATABASE_URL`, `OLLAMA_*`, `SIM_*`, `CODEX_*`, `SPICE_KERNEL_DIR`, `DEM_ROOT`, `PUBLIC_BASE_URL`). Resolves relative data dirs robustly from either `repo/` or `backend/`. |
| `backend/app/core/security.py` | 45 | 1,777 | Source | `Argon2id` password hashing/verification (`pwdlib`) and cryptographically random `session_token` (`secrets.token_urlsafe`) + SHA-256 hashing (`hash_session_token`). |
| `backend/app/core/auth_dependency.py` | 124 | 4,328 | Source | FastAPI cookie auth (`clps_session`), DB lookup joining `admin_sessions` + `admin_users` + `roles` + `role_permissions`, `60 s` throttled `last_active_at` update, `RequireRole(...)` & `RequirePermission(...)` RBAC dependencies. |
| `backend/app/core/csrf.py` | 171 | 6,131 | Source | Stateless + session-bound HMAC-SHA256 `clps_csrf` double-submit token generation & timing-safe verification (`require_csrf`), automatically triggered on unsafe HTTP verbs when session cookie is present. |
| `backend/app/core/middleware.py` | 60 | 2,450 | Source | Global catch-all exception middleware translating unhandled errors into sanitized JSON `{code, detail, request_id}` without leaking stack traces; injects `X-Request-Id`. |
| `backend/app/core/rate_limit.py` | 131 | 4,210 | Source | Thread-safe in-memory sliding-window IP/route rate limiters (`auth`, `contact`, `ai_assist`, `simulation`, `codex`) returning HTTP 429 + `Retry-After`. |
| `backend/app/core/audit.py` | 74 | 2,097 | Source | `log_audit(...)` helper writing structured `before_snapshot` / `after_snapshot` / `actor` / `ip_address` rows into `audit_logs`. |
| `backend/app/core/logging.py` | 39 | 1,337 | Source | Structured application logging formatter with request context. |
| `backend/app/db/base.py` | 7 | 200 | Source | SQLAlchemy 2 `DeclarativeBase` (`Base`). |
| `backend/app/db/session.py` | 33 | 774 | Source | Sync SQLAlchemy engine (`pool_pre_ping=True`, `psycopg` v3 driver) + `SessionLocal` factory + FastAPI `get_db()` generator dependency. |
| `backend/app/worker/__init__.py` | 1 | 73 | Source | Package marker |
| `backend/app/worker/simulation_worker.py` | 244 | 8,503 | Worker | Out-of-process polling worker (`claim_next_queued_run` via `FOR UPDATE SKIP LOCKED`), stale lease recovery, cooperative cancel polling, calls `simulation_service.execute_claimed_simulation`, updates `system_components`. |

### 2.2 FastAPI API Routers (`backend/app/api/v1/`)

#### Public & Authenticated Non-Admin Routes

| File | Lines | Bytes | Routes Prefix | Responsibility |
|---|---:|---:|---|---|
| `health.py` | 70 | 2,190 | `/api/v1/health` | Process liveness & dependency readiness (`PostgreSQL`, `Ollama`, `SPICE`, `LOLA DEM`). |
| `auth.py` | 387 | 12,702 | `/api/v1/auth` | Session login, logout, current profile + permissions (`/me`), explicit CSRF refresh (`/csrf`), change-password, and active session revocation. |
| `sites.py` | 180 | 6,122 | `/api/v1/sites` | Published site list, site filters, site detail by slug, 3-query FTS/metadata sub-resources, map markers. Depends on `catalogue_service`. |
| `search.py` | 25 | 863 | `/api/v1/search` | Unified PostgreSQL `ILIKE` (`pg_trgm` GIN) + `to_tsvector`/`plainto_tsquery` global landing-site & science search. Depends on `search_service`. |
| `compare.py` | 46 | 1,594 | `/api/v1/compare` | Comparison mission profiles listing & deterministic two-site weighted scorecard calculation. Depends on `comparison_service`. |
| `ai_assist.py` | 30 | 1,132 | `/api/v1/ai-assist` | Natural-language mission intent -> strict JSON extraction (Ollama `gemma4:e4b` + keyword fallback) -> deterministic candidate ranking. |
| `simulations.py` | 143 | 4,844 | `/api/v1/simulations` | Simulation queue submit, status polling, telemetry timeseries/events/horizon export (CSV/JSON), cancellation, site horizons. |
| `codex.py` | 133 | 4,053 | `/api/v1/codex` | Public CODEX status/overlay inspection (`GET /status`) plus operator-authorized run preparation (`POST /runs/prepare`), confirmed execution (`POST /runs`), run status/event polling (`GET /runs/{run_id}`, `/events`), and hardware E-STOP (`POST /estop`). |
| `contact.py` | 27 | 988 | `/api/v1/contact` | Rate-limited team/mission inquiry submission persisted in PostgreSQL `contact_messages`. |

#### Admin Portal Routes (`backend/app/api/v1/admin/`)

| File | Lines | Bytes | Roles & Responsibility |
|---|---:|---:|---|
| `sites_admin.py` | 819 | 27,384 | Full site CRUD, content sections, key facts/pros-cons, milestones/history, metrics provenance binding, publish/archive workflow (`super_admin`, `site_editor`, `research_admin`, `system_admin`, `viewer` reads). |
| `media_admin.py` | 283 | 9,443 | Safe Pillow upload validation, auto-WebP + thumbnail conversion to `storage/media/`, site gallery attachment & reordering (`site_editor`). |
| `imports_admin.py` | 240 | 7,858 | CSV/XLSX/GeoJSON dataset staging, coordinate & duplicate proximity checks, transactional batch commit & rollback (`research_admin`, read with `site_editor`/`system_admin`). |
| `simulations_admin.py` | 42 | 1,314 | Authenticated diagnostic view (`GET /admin/simulations/diagnostics`) reporting SPICE coverage, DEM availability, horizon cache & worker queue without leaking host paths. |
| `codex_admin.py` | 413 | 14,359 | Device provisioning, `/probe` liveness, calibration verification, Moon LED region editing, firmware template CRUD/rendering/diffing, and admin run listing/creation under `/admin/codex/*` and `/admin/hardware/*` (`hardware_admin`, `system_admin`, plus `super_admin` bypass). |
| `users.py` | 386 | 13,008 | User lifecycle management, role assignment, password reset, session audit/revocation (`super_admin`). |
| `audit.py` | 675 | 23,170 | Audit trail filtering (`audit_logs`), system component live probes (`spice_ephemeris`, `lola_dem_rasters`, `ollama_llm`, `simulation_worker`), comparison parameters & data sources CRUD. |

### 2.3 ORM Models, Repositories, Pydantic Schemas & Services

| Layer | Directory | Files & Line Totals | Responsibility & Pattern |
|---|---|---|---|
| **Models (8 domains + init)** | `backend/app/models/` | `__init__.py` (127), `catalogue.py` (274), `metrics.py` (125), `provenance.py` (112), `comparison.py` (153), `simulation.py` (217), `codex.py` (370), `admin.py` (140), `operations.py` (117) | 44 SQLAlchemy 2 `Mapped[...]` ORM tables mapping directly to PostgreSQL constraints, JSONB columns, `tsvector`, and cascades. |
| **Repositories (6)** | `backend/app/repositories/` | `site_repo.py` (313), `comparison_repo.py` (149), `simulation_repo.py` (459), `codex_repo.py` (559), `import_repo.py` (78), `media_repo.py` (87) | Encapsulate complex SQL: `FOR UPDATE SKIP LOCKED` job claim, `ON CONFLICT DO NOTHING` deduplication, 2-query subresource batching (`selectin`), FTS ranking. |
| **Schemas (12)** | `backend/app/schemas/` | `catalogue.py` (214), `comparison.py` (140), `ai_assist.py` (89), `simulation.py` (241), `codex.py` (487), `admin_portal.py` (328), `auth.py` (47), `common.py` (39), `contact.py` (41), `imports.py` (65), `search.py` (17), `__init__.py` (82) | Strict Pydantic v2 validation models forming the OpenAPI 3.1 contract exported to `frontend/src/api/generated/schema.ts`. |
| **Services (16)** | `backend/app/services/` | `catalogue_service.py` (316), `search_service.py` (108), `scoring.py` (188), `comparison_service.py` (491), `ai_assist_service.py` (394), `import_service.py` (524), `media_service.py` (98), `contact_service.py` (34), `geometry.py` (221), `horizon.py` (446), `visibility.py` (413), `simulation_service.py` (1,181), `codex_kinematics.py` (381), `moon_led_mapping.py` (384), `codex_template_engine.py` (267), `codex_service.py` (2,395) | All pure domain logic, scientific raycasting, root bisection, multi-criteria scoring, 16-step hardware pre-flight, template injection filtering, and orchestration. |
| **Integrations (8 modules)** | `backend/app/integrations/` | `spice/kernel_manager.py` (353), `spice/ephemeris.py` (215), `terrain/coordinate_transform.py` (112), `terrain/dem_reader.py` (387), `ollama/client.py` (147), `ollama/prompts.py` (108), `codex/protocol.py` (269), `codex/client.py` (490) | External I/O boundaries: SHA-256 verified SPICE & GeoTIFF loaders, Ollama HTTP client + circuit breaker, `codex.v1` HMAC signer & `Mock`/`Http` transports. |

### 2.4 Alembic Migrations & Pytest Suite

- **Migrations (`backend/alembic/versions/`):**
  1. `356b56f822c2_initial_schema.py` (1,200 lines) — Core 36 catalogue, admin, metrics, provenance, comparison, simulation (`simulation_runs`, `simulation_metrics`, `simulation_event_windows`), audit, and initial hardware tables & constraints.
  2. `002_search_indexes.py` (38 lines) — `pg_trgm` extension, GIN FTS (`idx_site_content_fts`) & trigram (`idx_landing_sites_name_trgm`) search indexes.
  3. `003_seed_standard_roles.py` (58 lines) — Seeds initial 5 base RBAC roles (`super_admin`, `site_editor`, `research_admin`, `hardware_operator`, `viewer`).
  4. `004_comparison_profiles.py` (626 lines) — Adds comparison profiles, 7 parameter definitions, 4 data sources, 3 regions, and 5 published landing sites + metrics.
  5. `005_simulation_engine.py` (277 lines) — Extends `background_jobs` & `simulation_runs`; adds `simulation_samples` and `terrain_horizon_profiles`.
  6. `006_codex_hardware_system.py` (533 lines) — Adds 4 CODEX safety tables (`hardware_devices`, `moon_led_region_pixels`, `codex_command_nonces`, `hardware_command_acknowledgements`), extends `hardware_runs`/`moon_led_regions`/`motor_calibration_profiles`, seeds 3 unverified devices & 13 Moon LED regions, and adds `hardware_admin`/`system_admin`.
  7. `007_phase7_admin_and_security.py` (91 lines) — Adds `admins.password_updated_at` & `password_must_rotate`, upserts all 7 canonical roles, and seeds 6 baseline `system_components`.
- **Test Suite (`backend/tests/`, 115 tests verified passing, 91% coverage):**
  - `conftest.py` (174 lines): Isolated `clps_luna_test` DB engine/session rollback fixtures & seed helpers.
  - `test_database_contract.py` (297 lines, 10 tests)
  - `test_catalogue_and_import.py` (708 lines, 22 tests)
  - `test_comparison_and_ai.py` (770 lines, 29 tests)
  - `test_simulation_engine.py` (1,238 lines, 28 tests)
  - `test_codex_hardware.py` (1,026 lines, 11 tests)
  - `test_phase7_admin_and_security.py` (887 lines, 8 tests)
  - `test_phase8_audit_optimizations.py` (315 lines, 7 tests)

---

## 3. Frontend & SSR Server Inventory (`frontend/`) `[VERIFIED IN SOURCE]`

### 3.1 Express 5 SSR Server & Build Configuration (`frontend/server/`, root)

| File | Lines | Scope | Responsibility |
|---|---:|---|---|
| `frontend/package.json` | 44 | Build/Run | Scripts (`dev`, `build:client`, `build:server`, `preview`, `typecheck`, `test`, `test:e2e`, `generate:api-types`) & React 19 / R3F 9 / Three 0.175 / Express 5 dependencies. |
| `frontend/vite.config.ts` | 41 | Build/Dev | React plugin, dev proxy (`/api` & `/storage` -> `BACKEND_ORIGIN`), manual client chunk splitting (`three-vendor`, `react-vendor`), Vitest jsdom config excluding `tests/e2e/**`. |
| `frontend/server/ssr-server.mjs` | 278 | Production/Dev Server | Express 5 server: validates `Host` header against allow-list, attaches gzip compression + HSTS + per-request 128-bit cryptographic CSP nonce (`script-src 'nonce-...'`), proxies `/api` and `/storage` via streaming `fetch` (preserving `set-cookie`, timeout, body limits), delegates `/robots.txt` & `/sitemap.xml` to `seo-routes.mjs`, runs React `renderToString` SSR via Vite middleware (dev) or `dist/server/entry-server.js` (prod), populates `DehydratedState` for TanStack Query, returns semantic HTTP `404` on unknown routes. |
| `frontend/server/seo-routes.mjs` | 102 | SEO | Generates dynamic XML sitemap (`/sitemap.xml`) from live `/api/v1/sites` published slugs and serves `/robots.txt` blocking `/admin` & `/api`. |

### 3.2 Frontend Application Source (`frontend/src/`)

#### App Entry, Routing, Styling & API Client

| File | Lines | Responsibility |
|---|---|---|
| `src/entry-client.tsx` | 47 | Client hydration (`hydrateRoot`), restores SSR `QueryClient` dehydrated cache cleanly. |
| `src/entry-server.tsx` | 166 | Server-side SSR renderer: fetches route-critical public API data on server (`Browser`, `Compare`, `SiteInfo`, etc.) so crawlers & slow networks receive complete HTML immediately. |
| `src/app/AppRoutes.tsx` | 95 | Declares all `KNOWN_EXACT_PATHS`, `isKnownDynamicRoute()`, skip link, `<Routes>`, and `<CookieConsent />`. |
| `src/app/ThemeContext.tsx` | 82 | Dark-mode (`lunar-obsidian`) / theme persistence context. |
| `src/api/client.ts` | 153 | Fetch wrapper automatically reading `clps_csrf` cookie for `X-CSRF-Token`, handling HTTP 401/403/422 typed `ApiError`, credential cookie inclusion. |
| `src/api/endpoints.ts` | 284 | Typed public & simulation/AI/CODEX API calls backed by generated OpenAPI schema. |
| `src/api/adminEndpoints.ts` | 645 | Typed Admin Portal calls (auth, sites, media, imports, users, audit, CODEX workbench & firmware templates). |
| `src/api/generated/schema.ts` | 8,233 | Generated (`openapi-typescript`) end-to-end TypeScript definitions matching FastAPI OpenAPI 3.1 spec. |
| `src/api/queryKeys.ts` | 17 | Centralized TanStack Query cache keys. |
| `src/seo/HeadTags.tsx` & `metadata.ts` | 139 + 66 | Injects SSR & client canonical links, OpenGraph/Twitter tags, and Schema.org JSON-LD safely escaped cleanly against `</script>`. |
| `src/styles/{tokens,global,print}.css` | 75 + 1,171 + 43 | NASA telemetry dark aesthetic design tokens, custom responsive grids/cards, print styles. |
| `src/utils/formatting.ts` | 51 | Coordinate formatting (`°N/°S`, `°E/°W`), UTC timestamps, duration formatting. |

#### Public Pages (`frontend/src/pages/`) & Shared Components (`frontend/src/components/`)

| File | Lines | Route(s) / Component Role |
|---|---:|---|
| `IntroPage.tsx` | 246 | `/` — Mission hero, NASA CLPS primer, live catalogue stats, entry points into 3D Browser, Simulation & CODEX. |
| `BrowserPage.tsx` | 343 | `/browser` — Split interactive 3D lunar globe (`LunarMoonCanvas`), site search/filter, telemetry cards, quick comparison tray. |
| `SiteInfoPage.tsx` | 726 | `/sites/:siteSlug` — Long-form editorial site dossier: key facts grid, horizon profile chart, milestones, provenance metrics, image gallery. |
| `ComparePage.tsx` | 485 | `/compare` — Profile selector (`Balanced`, `Solar`, `DTE`, etc.) & custom weights driving side-by-side two-site normalized score breakdown. |
| `AiAssistPage.tsx` | 379 | `/ai-assist` — Prompt builder, Ollama/fallback badge, extracted parameter chips & deterministic ranked candidate recommendations. |
| `SimulationPage.tsx` | 742 | `/simulation`, `/simulation/:simulationId` — SPICE interval config, async queue poller, interactive 3D Sun-Moon-Earth orrery (`SimulationOrreryCanvas`), dual illumination/DTE curves, CSV/JSON export. |
| `CodexPage.tsx` | 393 | `/codex` — Public read-only CODEX digital twin & controller health monitor showing LED region overlay and run status without admin write controls. |
| `ContactPage.tsx` | 180 | `/contact` — Validated mission inquiry form with rate-limit/success feedback. |
| `LegalPages.tsx` / `NotFoundPage.tsx` | 138 / 46 | `/privacy`, `/terms`, `*` (404). |
| `components/*` (8 files) | 1,074 | `SiteHeader.tsx` (133), `SearchDrawer.tsx` (221), `CodexDrawer.tsx` (276), `UtilitiesFooter.tsx` (69), `CookieConsent.tsx` (94), `ErrorBoundary.tsx` (54), `CopyButton.tsx` (41), `Icons.tsx` (141). |

#### Three.js Visualization Layer (`frontend/src/three/`)

| File | Lines | Responsibility |
|---|---|---|
| `coordinates.ts` | 124 | Canonical right-handed `spiceMoonMeToThree([x,y,z], s) = [x*s, z*s, -y*s]`, lat/lon -> spherical Cartesian helpers. |
| `LunarMoonCanvas.tsx` / `LunarMoonCanvasClient.tsx` | 62 / 362 | SSR-safe lazy dynamic import wrapper (`LunarMoonCanvas`) rendering textured 2K WebP Moon globe (`moon_albedo_2k.webp`, `moon_bump_2k.webp`), orbit controls, clickable 3D site pins, & WebGL fallback. |
| `SimulationOrreryCanvas.tsx` / `SimulationOrreryCanvasClient.tsx` | 59 / 360 | Animated topocentric & orbital orrery visualizing live SPICE Sun vector, Earth vector, crater horizon silhouette & eclipse state over time scrubber. |
| `MoonFallbackView.tsx` | 56 | Accessible SVG/DOM 2D lunar polar projection fallback when WebGL is disabled or running under headless SSR/tests. |

#### Authenticated Admin Portal (`frontend/src/admin/` & `frontend/src/pages/admin/`)

| File | Lines | Route(s) & Capabilities |
|---|---:|---|
| `AdminLayout.tsx` + `rbac.ts` | 401 + 19 | Role-filtered sidebar shell (`super_admin`, `system_admin`, `site_editor`, `research_admin`, `hardware_admin`, `hardware_operator`, `viewer`), auth guard & session indicator. |
| `AdminLoginPage.tsx` | 185 | `/admin/login` — Cookie-based username/password login + return-to redirect. |
| `AdminDashboardPage.tsx` | 208 | `/admin` — Admin KPI overview, queue health & recent audit feed. |
| `AdminSitesPage.tsx` / `AdminSiteEditorPage.tsx` | 534 / 1,344 | `/admin/sites`, `/admin/sites/:siteId` — Tabbed CRUD editor for site metadata, unlimited sections, facts, milestones, metrics provenance, publish/archive actions. |
| `AdminMediaPage.tsx` | 414 | `/admin/media` — Drag-drop WebP gallery manager & asset previewer. |
| `AdminImportsPage.tsx` | 496 | `/admin/imports` — Multi-format CSV/XLSX/GeoJSON uploader, row validation preview diff, transactional commit & one-click rollback. |
| `AdminUsersPage.tsx` | 470 | `/admin/users` — Role CRUD, account lock/unlock, password resets & active session inspection. |
| `AdminAuditHealthPage.tsx` | 322 | `/admin/audit` — Filterable audit log viewer, live component health probes & contact inbox resolution. |
| `AdminCodexPage.tsx` | 1,144 | `/admin/codex/*` — CODEX Workbench: controller probe, motor calibration verification, Moon 13-region polygon LED editor, live 16-step pre-flight checklist, `prepare -> confirmed execute` modal, and persistent **E-STOP** button. |
| `AdminFirmwareEditorPage.tsx` | 813 | `/admin/codex/firmware/*` — Split-pane template source/parameter form editor, live SHA-256 checksum preview & unified diff viewer against baseline templates. |

### 3.3 Complete Frontend Test Suite Inventory (`frontend/src/test/` & `frontend/tests/e2e/`)

| File | Lines | Framework | Coverage |
|---|---:|---|---|
| `src/test/setup.ts` | 8 | Vitest | `jest-dom` matchers & jsdom setup. |
| `src/test/coordinates.test.ts` | 91 | Vitest | Right-handed `MOON_ME -> Three.js` basis orientation & pole/equator unit checks. |
| `src/test/pages.test.tsx` | 593 | Vitest + RTL | Public pages rendering, mocked React Query flows, comparison/simulation/CODEX states. |
| `src/test/seo-and-ssr.test.ts` | 213 | Vitest | SSR HTML hydration consistency, JSON-LD XSS escaping, sitemap/robots & 404 semantics. |
| `src/test/admin-portal.test.tsx` | 303 | Vitest + RTL | Admin RBAC menu gating, site editor, firmware split-pane & CODEX safety flow tests. *(All 22 tests across 4 Vitest files verified passing).* |
| `tests/e2e/clps-e2e.spec.ts` | 330 | Playwright | End-to-end public journeys against live SSR + backend stack (`[DOCUMENTED, NOT INDEPENDENTLY VERIFIED]` in this session). |
| `tests/e2e/admin-portal.spec.ts` | 222 | Playwright | Live admin login, RBAC enforcement, media/import/CODEX UI E2E (`[DOCUMENTED, NOT INDEPENDENTLY VERIFIED]` in this session). |

---

## 4. Firmware, Controlled Data & Infrastructure Assets `[VERIFIED IN SOURCE]`

### 4.1 Firmware Subdirectories (`firmware/`)

- `firmware/esp32-wifi-bridge/`: `esp32-wifi-bridge.ino` (323 lines), `secrets.example.h` (8 lines), `sketch.yaml` (9 lines), `README.md` (16 lines).
- `firmware/arduino-uno-motion/`: `arduino-uno-motion.ino` (230 lines), `config.example.h` (31 lines), `sketch.yaml` (9 lines), `README.md` (14 lines).
- `firmware/esp32-s3-moon-led/`: `esp32-s3-moon-led.ino` (218 lines), `secrets.example.h` (12 lines), `sketch.yaml` (10 lines), `README.md` (14 lines).

> **Gitignore Security Note:** `.gitignore` ignores `firmware/**/secrets.h`, `firmware/**/config.h`, `.env`, `backend/.env`, `storage/`, and large binary SPICE/DEM files (`*.bsp`, `*.bpc`, `*.tls`, `*.tpc`, `*.tf`, `*.TIF`), while keeping `manifest.json` manifests tracked so every clone/CI box can verify integrity cleanly.

### 4.2 Local Orchestration (`run_clps.sh`) & Project Tracking (`docs/project_tracking/`)

- **`run_clps.sh` (1,286 lines):** Bash 3.2-safe macOS launcher providing `check`, `start`, `stop`, `status`, and `--migrate` / `--prod` modes:
  - Validates PostgreSQL availability, Python `.venv`, Node SSR build/dev, SPICE + DEM manifests, and Ollama status (`FALLBACK MODE` cleanly when `gemma4:e4b` or daemon is offline).
  - Launches Uvicorn FastAPI (`BACKEND_PORT=8000` default), `python -m app.worker.simulation_worker`, and Node/Express 5 SSR (`PORT=3000` default) under `/tmp/clps-luna-browser-<uid>/` lock/PID/log management.
- **`docs/project_tracking/`:** Contains `MASTER_PHASE_DASHBOARD.md`, `PHASE_7_IMPLEMENTATION_REPORT.md`, `PHASE_8_FINAL_VERIFICATION_REPORT.md`, `REQUIREMENTS_TRACEABILITY_MATRIX.md`, `HARDWARE_TRACKERS.md`, `CROSS_PHASE_AUDIT_REGISTER.md`, and `TEST_EVIDENCE_TRACKER.md`.

---

## 5. Cross-Module Dependency Matrix `[VERIFIED IN SOURCE]`

| Source Module | Depends On | Depended On By |
|---|---|---|
| `core/config.py` + `db/session.py` | Environment / `.env`, PostgreSQL | Every backend repository, service, router, worker, and script |
| `core/auth_dependency.py` + `core/csrf.py` | `models/admin.py`, `core/security.py` | All `admin/*` routers, `/auth/*`, write endpoints |
| `integrations/spice/*` + `integrations/terrain/*` | `spiceypy`, `rasterio`, `pyproj`, `shapely`, `data/*` manifests | `services/horizon.py`, `services/visibility.py`, `services/simulation_service.py` |
| `services/simulation_service.py` | `spice`, `horizon`, `visibility`, `repositories/simulation_repo.py` | `worker/simulation_worker.py`, `api/v1/simulations.py` |
| `services/scoring.py` | Pure Python math (zero DB/IO dependencies) | `services/comparison_service.py`, `services/ai_assist_service.py` |
| `services/codex_service.py` | `codex_kinematics.py`, `moon_led_mapping.py`, `codex_template_engine.py`, `integrations/codex/*`, `codex_repo.py` | `api/v1/codex.py`, `api/v1/admin/codex_admin.py` |
| `frontend/src/api/generated/schema.ts` | `backend/app/main.py` OpenAPI JSON (`npm run generate:api-types`) | `endpoints.ts`, `adminEndpoints.ts`, all pages & admin components |
| `frontend/server/ssr-server.mjs` | `dist/` or Vite dev middleware, `seo-routes.mjs`, `entry-server.tsx`, FastAPI `/api` | Browser clients, search crawlers, Playwright E2E |
