# Team Revision Playbook, Study Tracks & Judging-Day Readiness Guide

> **Purpose:** Structured revision guide enabling every teammate—regardless of which slice of CLPS Luna Browser they personally built—to learn the entire architecture in `15 minutes`, `1 hour`, or `Deep Specialist` depth, rehearse cross-questioning cleanly, and run safe read-only pre-demo verification checks.

---

## 1. Choose Your Revision Track

### Track A — 15-Minute Pre-Stage Team Briefing (Mandatory for Everyone)
1. **First-Principles Elevator Pitch (3 min):** Read [`JUDGES_PITCH_AND_TECHNICAL_QA.md §1`](file:///Users/siddharthwaikar/Personal/CodexBase/NASA%20Space%20App%20Challenge/CLPS%20Lunar%20Module/docs/team_handbook/JUDGES_PITCH_AND_TECHNICAL_QA.md). Memorize the 3-layer story: **Real Scientific Physics (`SPICE DE440 + LOLA 80m DEM`) + Hallucination-Proof Decision Engine (`Ollama Intent Only -> Pure Python Scoring`) + Safe CODEX Hardware Boundary (`16-Step Pre-Flight + #error Compile Guards`)**.
2. **End-to-End Architecture Diagram (4 min):** Study the Mermaid architecture diagram in [`CLPS_LUNA_BROWSER_COMPLETE_TECHNICAL_HANDBOOK.md §2`](file:///Users/siddharthwaikar/Personal/CodexBase/NASA%20Space%20App%20Challenge/CLPS%20Lunar%20Module/docs/team_handbook/CLPS_LUNA_BROWSER_COMPLETE_TECHNICAL_HANDBOOK.md) — trace one request through `Browser -> Express 5 SSR -> FastAPI -> PostgreSQL / Worker / Ollama / CODEX`.
3. **Know the 3 Unbreakable Honesty Boundaries (3 min):**
   - Do **NOT** say "NASA certified / NASA endorsed / flight-ready". Say: *"Built upon public NASA/JPL DE440 SPICE kernels and NASA GSFC PGDA LOLA terrain datasets."*
   - Do **NOT** say "physical steppers and Moon LEDs are verified on the bench". Say: *"Software orchestration, HMAC-SHA256 protocol, CRC16 UART framing, and fault injection pass in `MockCodexTransport`; physical bench wiring (`RSK-HW-01..03`) remains intentionally safety-blocked via `#error "SAFETY BLOCK:"` compile guards pending hardware availability."*
   - Know our **exact 5 seeded sites** (`Lunokhod 1`, `Lunokhod 2`, `Yutu (Jade Rabbit)`, `Pragyan (Chandrayaan-3)`, `Mons Mouton`) and **7 RBAC roles** (`super_admin`, `system_admin`, `site_editor`, `research_admin`, `hardware_admin`, `hardware_operator`, `viewer`).
4. **Top 5 Judge Trap Questions (5 min):** Review `JUDGES_PITCH_AND_TECHNICAL_QA.md §4` Questions #5 (`azlcpo` pole crash), #9 (`3D curved horizon`), #31 (`LLM anti-hallucination`), #26 (`HttpOnly + CSRF + CSP nonce`), and #40 (`Hardware blockers & 3 static protocol findings`).

### Track B — 1-Hour Full-Stack Comprehension Plan

| Minute Block | Focus Area | Primary Handbook Reference | Key Source Files to Skim |
|---|---|---|---|
| `00–12` | Database Architecture (`45` tables, provenance, FTS, job locks) | [`DATABASE_MASTER_REFERENCE.md`](file:///Users/siddharthwaikar/Personal/CodexBase/NASA%20Space%20App%20Challenge/CLPS%20Lunar%20Module/docs/team_handbook/DATABASE_MASTER_REFERENCE.md) | `backend/alembic/versions/004..007`, `repositories/simulation_repo.py` |
| `12–25` | FastAPI Routes, Express 5 SSR, Security, Auth, CSRF & CSP | [`API_MASTER_REFERENCE.md`](file:///Users/siddharthwaikar/Personal/CodexBase/NASA%20Space%20App%20Challenge/CLPS%20Lunar%20Module/docs/team_handbook/API_MASTER_REFERENCE.md) | `core/auth_dependency.py`, `core/csrf.py`, `frontend/server/ssr-server.mjs` |
| `25–42` | Scientific Computing (SPICE, LOLA Raycast, Finite Sun, Bisection, Three.js) | [`SCIENTIFIC_AND_HARDWARE_REFERENCE.md §1–4`](file:///Users/siddharthwaikar/Personal/CodexBase/NASA%20Space%20App%20Challenge/CLPS%20Lunar%20Module/docs/team_handbook/SCIENTIFIC_AND_HARDWARE_REFERENCE.md) | `ephemeris.py`, `horizon.py`, `visibility.py`, `three/coordinates.ts` |
| `42–52` | Ollama AI + Deterministic Comparison + Imports | [`CLPS_LUNA_BROWSER_COMPLETE_TECHNICAL_HANDBOOK.md §6, §9`](file:///Users/siddharthwaikar/Personal/CodexBase/NASA%20Space%20App%20Challenge/CLPS%20Lunar%20Module/docs/team_handbook/CLPS_LUNA_BROWSER_COMPLETE_TECHNICAL_HANDBOOK.md) | `ai_assist_service.py`, `ollama/client.py`, `scoring.py`, `import_service.py` |
| `52–60` | CODEX Kinematics, 13-Region LED, Pre-Flight & Firmware | [`SCIENTIFIC_AND_HARDWARE_REFERENCE.md §5–8`](file:///Users/siddharthwaikar/Personal/CodexBase/NASA%20Space%20App%20Challenge/CLPS%20Lunar%20Module/docs/team_handbook/SCIENTIFIC_AND_HARDWARE_REFERENCE.md) | `codex_kinematics.py`, `moon_led_mapping.py`, `protocol.py`, `firmware/*` |

### Track C — Deep-Dive Specialist Revision Checklists

#### 1. Backend & Database Specialist Checklist
- [ ] Explain why `alembic_version` makes PostgreSQL have `45` tables (`44` ORM + `1` Alembic tracker).
- [ ] Trace `claim_next_queued_run` (`FOR UPDATE SKIP LOCKED`) and lease recovery (`300 s` TTL) in [`simulation_repo.py`](file:///Users/siddharthwaikar/Personal/CodexBase/NASA%20Space%20App%20Challenge/CLPS%20Lunar%20Module/backend/app/repositories/simulation_repo.py) & [`simulation_worker.py`](file:///Users/siddharthwaikar/Personal/CodexBase/NASA%20Space%20App%20Challenge/CLPS%20Lunar%20Module/backend/app/worker/simulation_worker.py).
- [ ] Explain why `search_service.py` batches into `3` queries (`ILIKE` accelerated by `pg_trgm` GIN + `plainto_tsquery` + hydrated site fetch) and `site_repo.py` uses `2`-query `selectin` hydration.
- [ ] Trace how `auth_dependency.py` hashes `clps_session` with SHA-256 and throttles `last_active_at` DB writes to once every `60 s`.
- [ ] Explain `ON CONFLICT DO NOTHING` deduplication on `terrain_horizon_profiles` and `audit_logs` plus the Phase 8 backup drill record (`45` tables / `4,097` rows `[DOCUMENTED, NOT INDEPENDENTLY VERIFIED]` in this session).

#### 2. Scientific & Graphics Specialist Checklist
- [ ] Explain `MOON_ME` (`DE440` vs `DE421`) vs `MOON_PA` and why all `6` NAIF SPICE kernels must share overlapping coverage windows verified by `SpiceKernelManager`.
- [ ] Explain `spkcpo(..., abcorr="LT+S")` + `local_enu_basis` vs CSPICE `azlcpo` (`SPICE(POINTONZAXIS)` at poles).
- [ ] Write down the curved-Moon raycast step $\hat{u}_2(\sigma) = \cos\sigma\,\hat{u}_{\text{obs}} + \sin\sigma\,\hat{d}_{\text{horiz}}$ (`horizon.py`, `100 km`, `360` bins, `1,400` radial samples) and explain `LDEC` (`>50%` zero-shot warning) + quadrature `_ERR` angular uncertainty propagation.
- [ ] Derive why finite solar disk angular radius (`~0.266°`, `SUN_RADIUS_KM = 695,700`) and circular segment area + `24`-iteration `<= 1.0 s` bisection outperform coarse grid sampling.
- [ ] Prove right-handed invariance ($\det = +1$) of `spiceMoonMeToThree([x, y, z], s) = [x*s, z*s, -y*s]` (`frontend/src/three/coordinates.ts`).

#### 3. Frontend, SSR & Security Specialist Checklist
- [ ] Explain all 4 advantages of Express 5 SSR (`ssr-server.mjs`): SEO pre-rendering (`entry-server.tsx` + dynamic `/sitemap.xml`), Host header allow-list, `/api` + `/storage` streaming cookie proxy, and per-request 128-bit cryptographic CSP nonces.
- [ ] Explain the **double-submit CSRF** pattern (`clps_csrf` HMAC-bound cookie sent automatically by `frontend/src/api/client.ts` as `X-CSRF-Token` alongside `HttpOnly` `clps_session`) and Origin validation.
- [ ] Explain `openapi-typescript` contract generation (`npm run generate:api-types` -> `frontend/src/api/generated/schema.ts`, `8,233` lines).
- [ ] Explain manual Vite chunks (`three-vendor`, `react-vendor`), `MoonFallbackView` WebGL fallback, and XSS-safe JSON-LD escaping (`HeadTags.tsx`).

#### 4. CODEX Hardware & Firmware Specialist Checklist
- [ ] Draw the 3-controller hardware architecture (`wifi_bridge` ESP32 <-> Arduino Uno `motion_uno` over UART2 `RX=16, TX=17` via **3.3V↔5V shifter**; direct HTTP to `moon_led_s3` ESP32-S3 driving `26` NeoPixels on `GPIO 48` via dedicated 5V PSU).
- [ ] Recite the binary UART frame layout (`SOF 0xAA55`, `ver 0x01`, `msg_type`, `seq u32`, `len u16 <= 256`, ASCII payload, `CRC16-CCITT poly 0x1021`).
- [ ] Contrast trapezoidal vs triangular velocity profiles (`total_steps <= v_max^2 / a`) and `5s..300s` physical duration separation from SPICE span.
- [ ] Explain gnomonic centroid tangent polygon projection + `BOUNDARY_EPSILON = 1e-6` + lowest `region_index` tie-break (`moon_led_mapping.py`).
- [ ] Explain all 3 safety interlocks (`#error "SAFETY BLOCK:"` compile guards, `ESTOP Pin 3 INT1` + `WDTO_2S` watchdog + `STEPPER_ENABLE_PIN` active-LOW, `codex_template_engine` C injection denylist & No Auto-Flash policy) AND openly summarize the 3 Phase 5 integration bugs found in source review (`uart_frame_hex` post-sign mutation, unsorted `ArduinoJson`, missing HMAC call inside `handle_estop`).

---

## 2. Team Q&A Ownership Matrix (Suggested Division)

| Judging Question Topic | Primary Presenter | Backup Responder | Go-To Evidence File |
|---|---|---|---|
| Problem Statement, CLPS & Demo Flow | **Team Lead / Product** | Frontend Lead | `JUDGES_PITCH_AND_TECHNICAL_QA.md`, `/` & `/browser` |
| SPICE, `MOON_ME`, LOLA DEM, Horizon & Bisection | **Scientific Lead** | Backend Lead | `SCIENTIFIC_AND_HARDWARE_REFERENCE.md §2–4` |
| PostgreSQL Schema, Search, Comparison & Worker Queue | **Backend / DB Lead** | Scientific Lead | `DATABASE_MASTER_REFERENCE.md` |
| React 19, Three.js Orrery, Express 5 SSR, SEO | **Frontend Lead** | Full-Stack Lead | `SOURCE_CODE_MAP.md §3`, `API_MASTER_REFERENCE.md` |
| Auth, Cookies, CSRF, CSP Nonce, RBAC, Admin Portal | **Security / Backend** | Frontend Lead | `API_MASTER_REFERENCE.md`, `007_phase7_admin_and_security.py` |
| Ollama `gemma4:e4b`, Anti-Hallucination & Circuit Breaker | **AI / Backend Lead** | Team Lead | `ai_assist_service.py`, `ollama/client.py`, `prompts.py` |
| CODEX 3-Controller Design, Kinematics, LEDs & Safety Blockers | **Embedded / Hardware** | Backend Lead | `SCIENTIFIC_AND_HARDWARE_REFERENCE.md §5–8`, `firmware/*` |

---

## 3. Rapid Viva Self-Test (Can You Explain Each in <= 2 Sentences?)

Before judging, each team member should explain every item below cleanly without checking notes:
1. Why is `MOON_ME` vs `MOON_PA` distortion a real lunar engineering bug if mixed with LOLA GeoTIFFs?
2. How does a 15-minute coarse SPICE sample interval still find sunset accurate to `<= 1.0 s`?
3. Why did the team write its own `spkcpo` + analytical ENU basis instead of calling SpiceyPy's `azlcpo`?
4. Why can't Ollama ever fabricate a high score for a non-existent crater or violate slope constraints?
5. Why does our frontend sit behind a custom Express 5 SSR server instead of static files or Nginx?
6. How does `clps_csrf` + `HttpOnly` `clps_session` stop both XSS token theft and cross-site request forgery?
7. What are the 3 hardware controllers, why are there 3 instead of 1, and why is physical actuation currently blocked?
8. What happens if PostgreSQL receives two simulation workers polling at the exact same microsecond?

---

## 4. Safe Pre-Demo & Judging-Day Verification Commands `[READ-ONLY SAFE]`

> **Caution:** Always keep `CODEX_TRANSPORT_MODE=mock` and `CODEX_REQUIRE_VERIFIED_BENCH=True` during software demonstrations unless on an authorized verified bench. Run automated tests strictly against the isolated `clps_luna_test` DB.

### Check Toolchain & Launcher Status (Zero Mutations)
```bash
# 1. Inspect prerequisite readiness (Postgres, .venv, SPICE/DEM files, SSR build, Ollama)
./run_clps.sh check

# 2. Confirm git workspace has zero unapproved source mutations
git status -s
```

### Start & Stop Local Demonstration Stack
```bash
# Start backend (:8000), simulation worker, and Express 5 SSR (:3000)
./run_clps.sh start

# Check live PIDs & health banner
./run_clps.sh status

# Clean shutdown after demo
./run_clps.sh stop
```

### Independent Software Test Verification (Isolated `clps_luna_test`)
```bash
# Backend lint, typecheck & full 115-test pytest suite (from backend/)
.venv/bin/ruff check app tests
.venv/bin/mypy app
.venv/bin/pytest -q

# Frontend typecheck, 22 Vitest tests & dependency audit (from frontend/)
npx tsc --noEmit
npm test -- --run
npm audit
```

*(Note: Full-stack Playwright E2E tests in `frontend/tests/e2e/` require live SSR + backend + DB; run against dedicated test setup rather than dirtying live demo seed state).*

---

## 5. Essential Technical Glossary

| Term | Exact Definition in CLPS Luna Browser |
|---|---|
| **`AREA_OR_POINT`** | GDAL raster pixel registration tag (`Area` = pixel-centered cell; `Point` = corner lattice point) honored by `coordinate_transform.py`. |
| **`abcorr="LT+S"`** | SPICE planetary aberration + one-way light-time correction modeling finite photon travel time & orbital motion of observer. |
| **`azlcpo` vs `spkcpo`** | CSPICE routines: `azlcpo` fails with `SPICE(POINTONZAXIS)` at lunar poles `±90°`; `spkcpo` computes raw target state vectors cleanly anywhere. |
| **`bench_verified`** | DB verification status required on `hardware_devices`, `motor_calibration_profiles`, and `moon_led_regions` before live CODEX actuation passes Step 6/10/11. |
| **`CLPS`** | NASA's **Commercial Lunar Payload Services** initiative contracting commercial landers to deliver science & technology payloads to the Moon. |
| **`codex.v1`** | CLPS Luna's application-layer authenticated JSON protocol carrying monotonic sequence, UUID, nonces, TTL, and `HMAC-SHA256` signature headers. |
| **`CRC16-CCITT`** | 16-bit cyclic redundancy check (`poly 0x1021, init 0xFFFF`) protecting binary UART frames (`0xAA55` SOF) between ESP32 bridge and Arduino Uno. |
| **`CSP Nonce`** | Per-response cryptographic 128-bit random token injected by Express 5 SSR (`script-src 'self' 'nonce-...'`) blocking injected inline scripts. |
| **`DE440` / `DE421`** | JPL planetary/lunar Development Ephemerides (`de440.bsp`, `moon_pa_de440_200625.bpc`; LOLA 2023 DEM datum aligns to DE421 `MOON_ME`). |
| **`DTE`** | **Direct-to-Earth** radio line-of-sight communication visibility modeled against finite Earth disk radius (`6,371 km`). |
| **`E-STOP`** | Hardware/software emergency stop (`INT1 Pin 3` interrupt on Uno + active-LOW CNC shield disable + `/codex/estop` API sequence-bypass override). |
| **`FOR UPDATE SKIP LOCKED`** | PostgreSQL row-level locking pattern letting concurrent `simulation_worker` instances claim non-overlapping queued jobs atomically. |
| **`Geometric-Only Horizon`** | Explicit smooth-sphere `0°` fallback state assigned when a site falls outside `data/lunar-dem/` polar GeoTIFF coverage. |
| **`Gnomonic Projection`** | Projection of spherical boundary polygons onto the tangent plane centered at each LED region's centroid to avoid polar/antimeridian wrap distortion. |
| **`LDEC` / `_ERR`** | Companion LOLA GeoTIFF layers holding per-pixel laser altimetry shot count (`LDEC`) and `1-sigma` vertical error in meters (`_ERR`). |
| **`MOON_ME`** | **Moon Mean Earth / Polar Axis** body-fixed frame (`+X` sub-Earth prime meridian, `+Z` North Pole), primary simulation & Three.js reference frame. |
| **`pg_trgm` / `tsvector`** | PostgreSQL trigram fuzzy matching & English full-text inverted search indexes (`002_search_indexes.py`). |
| **`ShadowCam / LOLA`** | Lunar Reconnaissance Orbiter instruments; bundled elevation rasters are NASA GSFC PGDA LOLA polar GeoTIFFs (`80 m/px`, `240 m/px`). |
| **`SOF 0xAA55`** | 2-byte little-endian Start-Of-Frame magic header (`0x55, 0xAA`) synchronizing UART packet framing (`<HBBIH`). |
| **`Trapezoidal / Triangular Profile`** | Time-bounded stepper ramp geometry enforcing bounded acceleration (`steps/s^2`) and peak step rate (`steps/s`) without stalling motors. |
