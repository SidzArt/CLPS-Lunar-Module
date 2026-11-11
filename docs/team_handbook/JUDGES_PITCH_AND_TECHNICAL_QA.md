# Judges' Pitch Playbook & Deep Technical Cross-Examination Q&A

> **Purpose:** Complete presentation script, live demo choreography, contingency runbook, and 60+ deep jury Q&As so every member of the CLPS Luna Browser team can pitch confidently and defend architectural, scientific, security, AI, and hardware-safety decisions under expert scrutiny.
>
> **Golden Rule of Credibility:** **Never overclaim.** Never claim NASA certification, NASA endorsement, or operational flight qualification. Never claim the physical CODEX motors or Moon LED array were bench-tested (`Phase 5` hardware verification remains `[BLOCKED BY HARDWARE]`). Judges reward transparent, engineering-grade honesty paired with verifiable tests (`115` backend pytest tests at `91%` coverage, `22` Vitest tests, Clean `ruff`/`mypy`/`tsc`/0 `npm audit` vulnerabilities).

---

## 1. Pitch Scripts

### 1.1 30-Second Elevator Hook
> *"NASA's Commercial Lunar Payload Services (CLPS) send commercial landers to extreme lunar destinations like Mons Mouton near the South Pole—where millimeter changes in solar elevation angle decide whether a solar-powered lander survives or freezes, and crater rims block Direct-to-Earth radio. Most public tools are either static picture galleries or fragile scripts. **CLPS Luna Browser** is a full-stack scientific decision platform backed by PostgreSQL, real JPL DE440 NAIF SPICE kernels, 80-meter LOLA South Pole terrain raycasting, finite-disk eclipse bisection, a hallucination-proof local AI planner, an audited 7-role Admin Portal, and a cryptographically signed CODEX hardware controller pipeline—with zero fake mock numbers hidden in production."*

### 1.2 2-Minute Main Stage Pitch

1. **The Problem (~25s):** Choosing a CLPS landing site isn't browsing a 2D map. At the Lunar South Pole (`~85°–90°S`), the Sun circles near the horizon, casting `100 km`-long mountain shadows. Conventional tools treat craters as flat planes, assume the Sun is a point source, or break mathematically right at the South Pole (`azlcpo` singularity).
2. **Scientific Core (~35s):** We fuse real **JPL DE440 SPICE ephemerides** (`MOON_ME` frame, `"LT+S"` light-time/aberration correction) with **NASA GSFC PGDA LOLA GeoTIFF DEMs (`80 m/px` and `240 m/px`, including laser shot count `LDEC` and `1-sigma` error `_ERR` grids)**. For every candidate site, an out-of-process worker raycasts **360 azimuth bins out to `100 km` in curved 3D**, models the **finite circular segment of the solar and Earth disks**, and uses **24-iteration bisection** to pinpoint sunrise/sunset and Direct-to-Earth comms transitions to **`≤ 1.0 s`**.
3. **Decision & AI Architecture (~25s):** Teams can explore `5` seeded historical/Artemis sites (*Mons Mouton*, *Pragyan / Chandrayaan-3*, *Yutu*, *Lunokhod 1*, *Lunokhod 2*) on a **SSR + Three.js `MOON_ME`-aligned 3D globe**, compare two sites side-by-side under weighted mission profiles (`solar_maximization`, `direct_earth_comm`, `volatile_prospecting`, `geological_research`, `general_exploration`), or describe mission needs in natural language to **local Ollama (`gemma4:e4b`)**. Crucially, **AI never computes scores**—it extracts strict JSON weights/constraints while pure Python computes repeatable, source-provenanced rankings with automatic rule-based fallback.
4. **Governance & CODEX Hardware Twin (~35s):** An audited **7-role Admin Portal** supports CSV/XLSX/GeoJSON dataset staging with proximity checks and rollback, split-pane firmware template editing, and **CODEX**—a 3-controller (`ESP32` bridge, `Arduino Uno` steppers, `ESP32-S3` 13-region Moon LED globe) pipeline protected by `codex.v1` HMAC-SHA256, `0xAA55` CRC16 UART framing, and a **16-step live pre-flight gate** that visibly locks hardware actuation whenever bench calibration is unverified.

---

## 2. 5-Minute Live Judging Demo Choreography

*(Recommended pre-demo launch: `./run_clps.sh check` then `./run_clps.sh start` — SSR runs at `http://localhost:3000`, FastAPI at `:8000`)*

| Time | Route | Action in UI | Point to Highlight for Judges |
|---:|---|---|---|
| `0:00` | `/` | Land on Intro page; inspect DevTools Network tab / View Page Source | Instant **Express 5 SSR HTML**, per-request 128-bit CSP nonce, zero tokens in `localStorage`. |
| `0:40` | `/browser` | Rotate 3D Moon globe; use Search Drawer (`Mons Mouton`) | True `MOON_ME -> [x, z, -y]` right-handed 3D alignment; PostgreSQL `tsvector` + `pg_trgm` fuzzy search; fallback toggle if WebGL restricted. |
| `1:20` | `/sites/mons-mouton` | Scroll sections, facts, horizon stats & provenance metrics | Uncapped PostgreSQL editorial text (`verified/provisional/unverified` provenance badges attached to metrics). |
| `1:50` | `/compare` | Compare *Mons Mouton* vs *Pragyan (Chandrayaan-3)* under `solar_maximization` | Explainable normalized `[0, 1]` weighted breakdown + missing-data transparency (`complete` vs `partial` vs `insufficient_data`). |
| `2:25` | `/ai-assist` | Submit: *"Long solar survival near south pole with flat slope under 15 deg and Earth line of sight"* | Ollama `gemma4:e4b` JSON schema extraction (or seamless `rule-based-fallback` badge if offline); deterministic Python ranking; zero SQL/fabrication by LLM. |
| `3:05` | `/simulation` | Launch 7-day South Pole simulation for *Mons Mouton*, inspect live 3D Orrery & telemetry plot | Async PostgreSQL `FOR UPDATE SKIP LOCKED` worker claim, LOLA `80 m/px` 3D curved horizon occlusion, finite solar disk & DTE visibility export (CSV/JSON). |
| `3:55` | `/codex` & `/admin/login` | Show header pill `CODEX · Mock / Blocked`, open `/codex`, then sign in as `test_super_admin` -> `/admin/codex` & `/admin/codex/firmware` | Honest hardware boundary disclosure, 16-step safety pre-flight, Split-Pane C++ template allow-list editor, No Auto-Flash policy & persistent E-STOP. |

---

## 3. Demo Contingency Runbook

| Risk During Live Demo | Immediate Symptom | Recovery Action & Talking Point |
|---|---|---|
| **Ollama daemon stopped / slow laptop GPU** | `/ai-assist` takes >15s or trips 3-failure breaker | Let automatic **`rule-based-fallback`** complete cleanly. Say: *"Notice our circuit breaker cleanly switched to deterministic keyword extraction in milliseconds—our UX never hangs on an LLM."* |
| **Judge laptop / projector disables WebGL** | Blank 3D canvas context loss | Point to automatic **`MoonFallbackView`** SVG polar UI & `ErrorBoundary` recovery—scientific charts and horizon curves remain 100% functional. |
| **Judge asks "Where is the spinning physical Moon globe?"** | No MCU hardware plugged in | Show `/codex` (`MOCK / DEMONSTRATION MODE` vs `REAL HARDWARE MODE — BLOCKED`), show the **active `#error "SAFETY BLOCK:"`** lines in Arduino `.ino` files, and explain why energizing uncalibrated steppers or an unverified 5V WS2812B LED rail without a 3.3V↔5V shifter is unsafe engineering. |
| **Slow cold DEM load on first `Mons Mouton` sim** | First run reads GeoTIFF window from disk | Second simulation hits **deterministic SHA horizon cache** (`terrain_horizon_profiles`) and completes vastly faster; explain cache key includes DEM SHA-256 checksum & algorithm version! |

---

## 4. Deep Technical Cross-Examination Q&A (65+ Questions Across 12 Domains)

### Domain A — CLPS Mission Context & Problem Framing
1. **Q: What does CLPS stand for, and why does your platform target it?**
   - **A:** **Commercial Lunar Payload Services** (NASA Artemis commercial lander contracts delivering science instruments to the Moon). Commercial partners and researchers need integrated access to site characterization, illumination/Earth-comms windows, terrain slope limits, and multi-criteria trade studies without stitching together separate SPICE scripts, GIS desktop tools, and spreadsheets.
2. **Q: Is this certified or endorsed by NASA for flight planning?**
   - **A:** **No.** `[VERIFIED IN SOURCE]` We state clearly in our documentation and honest boundaries that this is an educational/hackathon decision-support and visualization platform using public NASA/JPL DE440 SPICE kernels and NASA PGDA LOLA GeoTIFF datasets—not flight-certified mission assurance software.
3. **Q: What published sites come seeded out of the box?**
   - **A:** `[VERIFIED IN SOURCE]` Migration `004_comparison_profiles.py` seeds 5 reference sites: **Lunokhod 1** (`lunokhod-1`), **Lunokhod 2** (`lunokhod-2`), **Yutu (Jade Rabbit)** (`yutu-jade-rabbit`), **Pragyan (Chandrayaan-3)** (`pragyan-chandrayaan-3`), and **Mons Mouton** (`mons-mouton`). Admins can stage/import more via CSV/XLSX/GeoJSON.

### Domain B — NAIF SPICE Ephemeris & Coordinate Frames
4. **Q: Why use NAIF SPICE (`spiceypy`) instead of a 50-line simplified Keplerian solar/lunar formula?**
   - **A:** `[VERIFIED IN SOURCE]` Near lunar poles, grazing solar elevations vary by fractions of a degree (`±0.27°` solar radius). Analytic circular formulas ignore N-body perturbations, lunar libration (`~±8°` optical + physical librations), light-time, and stellar aberration. Loading JPL `de440.bsp`, `moon_pa_de440_200625.bpc`, `moon_de440_250416.tf`, `moon_assoc_me.tf`, `pck00011.tpc`, and `naif0012.tls` gives sub-arcsecond fidelity across `1549-12-31` to `2650-01-25`.
5. **Q: Why did you avoid `spice.azlcpo()` for azimuth/elevation calculations?**
   - **A:** `[VERIFIED IN SOURCE]` (`ephemeris.py` + `geometry.py`) Near exact poles (`±90°` latitude), `CSPICE`'s built-in `azlcpo` raises `SPICE(POINTONZAXIS)` due to degenerate meridian cross-products. We call `spice.spkcpo(..., observer_frame="MOON_ME", abcorr="LT+S")` in Cartesian coordinates and project onto an analytical pole-safe local East-North-Up (`local_enu_basis`) orthonormal frame.
6. **Q: Explain `"MOON_ME"` vs `"MOON_PA"` vs `"IAU_MOON"`, and why does LOLA GeoTIFF alignment matter?**
   - **A:** `MOON_ME` (Mean Earth / Polar Axis) aligns the Moon-fixed frame so `+X` faces mean sub-Earth `0°` and `+Z` is rotation pole; `MOON_PA` (Principal Axes) differs by ~860 meters on the surface. NASA PGDA LOLA products use `MOON_ME` (`DE421`-aligned, sub-meter difference from `DE440` `MOON_ME_DE440_ME421`). Using `IAU_MOON` or `MOON_PA` directly against a `MOON_ME` DEM would introduce horizontal frame-Shift errors!
7. **Q: Is `CSPICE` thread-safe if FastAPI handles concurrent requests or multi-threaded workers run?**
   - **A:** **No!** The underlying NASA C library maintains a global non-reentrant kernel pool (`furnsh`/`ktotal`). That is why `SpiceKernelManager` wraps every SPICE pool call (`str2et`, `spkcpo`, kernel inspection) inside a process-wide re-entrant lock (`threading.RLock()`).
8. **Q: How do you protect against silent kernel tampering or wrong dates?**
   - **A:** `[VERIFIED IN SOURCE]` `kernel_manager.py` verifies every file's lowercase **SHA-256 checksum** in `1 MiB` streaming chunks against `data/spice-kernels/manifest.json`, rejects path traversal (`/` / `..`), checks `REQUIRED_FRAMES` and `REQUIRED_SPK_BODIES` (`10, 301, 399`), and raises `SpiceCoverageError` with valid `[common_start_utc, common_end_utc]` bounds if a user requests out-of-range dates.

### Domain C — LOLA DEMs & 3D Horizon Raycasting
9. **Q: Why can't you just use `atan2(z_ridge - z_obs, distance)` for lunar horizon elevations?**
   - **A:** Over our `100 km` raycast radius (`SIM_HORIZON_MAX_RADIUS_M = 100,000 m`), lunar spherical curvature (`R = 1,737,400 m`) drops terrain away by $\approx s^2 / (2R) \approx 2,878\text{ m}$ (`~3.3°` horizon drop). Flat-plane math turns curved lunar peaks invisible from orbit or grossly overestimates rim heights! `horizon.py` projects radial arcs $\sigma = s / R$ along $\hat{u}_2(\sigma) = \cos\sigma\,\hat{u}_{\text{obs}} + \sin\sigma\,\hat{d}_{\text{horiz}}$ and computes true 3D Cartesian line-of-sight vector angles.
10. **Q: Which LOLA DEM datasets are bundled, and what happens for non-polar sites?**
    - **A:** `[VERIFIED IN SOURCE]` `LDEM_80S_80MPP_ADJ.TIF` (`80 m/px`, `7600 × 7600`, covering `±304 km` around the South Pole with paired `LDEC` shot count and `_ERR` `1-sigma` error TIFFs) and `LDEM_60S_240MPP_ADJ.TIF` (`240 m/px` broader South Pole coverage). `DEMRegistry.select_asset_for_site` picks the finest asset having `min_edge_margin_m >= 100 km`, falling back to `240 m/px` at boundary edges, or explicitly flagging **`geometric_only`** (smooth sphere `0°` horizon) for low-latitude sites like `Lunokhod 1` or `Yutu` outside South Pole coverage—never fabricating fake hills.
11. **Q: How do you account for noisy or interpolated pixels in LOLA polar DEMs?**
    - **A:** `[VERIFIED IN SOURCE]` Alongside elevation, `dem_reader.py` slices the companion `LDEC` (laser shot count) and `_ERR` (uncertainty in meters) GeoTIFFs. `horizon.py` propagates observer + peak-ridge elevation errors in quadrature ($\sqrt{\sigma_{\text{obs}}^2 + \sigma_{\text{ridge}}^2}$) into degree uncertainties (`uncertainty_deg`) and attaches an explicit warning when `zero_shot_frac > 0.5` (`LDEC = 0`).
12. **Q: How do you avoid OOM crashes if someone adds a 5 m/px DEM later?**
    - **A:** `read_window_for_site` computes a bounded GeoTIFF window (`±100 km`), reads the exact site center elevation at native `1:1` pixel resolution, and caps window arrays to `max_window_pixels_per_side = 2600` via Rasterio `out_shape` scaling while updating the affine `window_transform`.
13. **Q: Why use the GeoTIFF's embedded WKT/PROJ4 CRS instead of hardcoding `EPSG:3031` or lunar stereographic EPSG codes?**
    - **A:** `[VERIFIED IN SOURCE]` Planetary LOLA GeoTIFFs rarely share standard terrestrial EPSG IDs (`coordinate_transform.py`). Reading `ds.crs`, ellipsoid semi-major axis (`datum_radius_m`), and `AREA_OR_POINT` dynamically with PyProj `always_xy=True` guarantees exact axis order `(lon, lat) -> (x, y)` without east/north transposition bugs.

### Domain D — Visibility, Solar Occlusion & Bisection Solver
14. **Q: How does your model calculate sunrise/sunset partial illumination?**
    - **A:** `[VERIFIED IN SOURCE]` Instead of binary on/off point sun (`visibility.py`), it computes instantaneous solar angular radius $\rho = \arcsin(695,700 / d_{\text{sun}})$ (`~0.266°`), takes clearance $c = \theta_{\text{center}} - \theta_{\text{hor}}(\alpha)$, and when $|c| < \rho$ computes exact visible circular segment fraction $f = (\arccos(-x) + x\sqrt{1 - x^2})/\pi$ for $x = c / \rho$. The same finite-disk model evaluates Direct-to-Earth comms using `EARTH_MEAN_RADIUS_KM = 6,371.0`.
15. **Q: How can coarse 15-minute steps achieve `<= 1.0 s` sunrise/sunset event precision?**
    - **A:** `[VERIFIED IN SOURCE]` Adaptive coarse intervals (`300s` for `≤24h`, `600s` for `≤7d`, `900s` for `≤35d`, `1800s` for `≤180d`, bounded by `SIM_MAX_COARSE_SAMPLES = 20,000`) detect sign transitions across adjacent epochs $[t_k, t_{k+1}]$. `_bisect_bracket` then re-evaluates true `spkcpo` ephemerides via binary search for up to `24` iterations until the interval width is `≤ 1.0 s` (`900s / 2^24 ≈ 0.05 ms` theoretical upper bound).

### Domain E — PostgreSQL Database, Schema & Concurrency
16. **Q: Why PostgreSQL 18 + SQLAlchemy 2 instead of MongoDB or SQLite?**
    - **A:** `[VERIFIED IN SOURCE]` Our domain is deeply relational (provenance chains `site_metrics -> data_sources`, multi-role RBAC, versioned motor calibrations, transactional CSV/XLSX/GeoJSON dataset imports with rollback, and atomic hardware sequence/nonce locks). PostgreSQL gives us `CHECK` constraints, `UNIQUE` partial constraints, `GIN` full-text + `pg_trgm` trigram search (`002_search_indexes.py`), `SELECT ... FOR UPDATE SKIP LOCKED` multi-worker job claiming (`simulation_repo.py`), and `ON CONFLICT DO NOTHING` idempotency (`audit_logs` / `terrain_horizon_profiles`)—none of which SQLite or document stores handle with equivalent transactional isolation.
17. **Q: How many tables exist, and why split horizon arrays / timeseries into dedicated tables?**
    - **A:** `[VERIFIED IN SOURCE]` `45` PostgreSQL tables (`44` SQLAlchemy ORM models + `alembic_version`). `simulation_samples`, `simulation_metrics`, `simulation_event_windows`, and `terrain_horizon_profiles` isolate bulk scientific outputs from lightweight `simulation_runs` status rows so polling `GET /simulations/{id}` never deserializes thousands of rows!
18. **Q: Explain `simulation_worker.py` concurrency guarantees—what if a worker crashes mid-simulation?**
    - **A:** `[VERIFIED IN SOURCE]` Worker claims jobs using `FOR UPDATE SKIP LOCKED` with a `300s` lease (`lease_expires_at`). Periodic lease expiry recovery resets crashed `"running"` jobs (within retry caps) or marks them failed cleanly; cooperative cancellation checks DB state inside the simulation loop so a user's cancel click stops work mid-run cleanly.
19. **Q: Why is there a `test_uncapped_text_storage_in_site_content` test checking `13,500` words?**
    - **A:** `[VERIFIED IN SOURCE]` Editorial research sections (`site_content`) use PostgreSQL `TEXT` rather than bounded `VARCHAR(N)` so scientists are never truncated mid-monograph. `test_database_contract.py` explicitly writes and reads back a `13,500`-word section cleanly.

### Domain F — Backend FastAPI Architecture & Optimization
20. **Q: Why FastAPI over Flask or Django?**
    - **A:** Native **Pydantic v2** validation + automatic **OpenAPI 3.1 schema generation**, which we compile directly into frontend TypeScript via `openapi-typescript` (`frontend/src/api/generated/schema.ts`, `8,233` lines!). That keeps Python API contracts and React UI types compiler-checked together without writing manual client DTOs.
21. **Q: How did you prevent N+1 queries and excessive DB writes during Phase 8?**
    - **A:** `[VERIFIED IN SOURCE]`
      - `search_service.py` replaced recursive multi-join N+1 queries with **3 batched queries**.
      - `site_repo.py` uses `selectinload` / **2-query sub-resource hydration** for `SiteInfoPage`.
      - `auth_dependency.py` throttles `admin_sessions.last_active_at` writes to **`≥ 60 seconds`** between updates instead of committing a DB `UPDATE` on every single admin API request!
22. **Q: Why use an out-of-process worker (`simulation_worker.py`) instead of FastAPI `BackgroundTasks`?**
    - **A:** Horizon raycasting (`360 × 1400` bilinear raster samples) and long SPICE timelines are CPU- and GeoTIFF-I/O heavy. Running them inside FastAPI `BackgroundTasks` would block Uvicorn worker processes, lose jobs on API reload/restart, and break the global `CSPICE` `RLock` across HTTP request latencies. Out-of-process PostgreSQL queueing isolates API responsiveness (`<10 ms` status polls) from multi-second compute jobs.

### Domain G — Frontend React 19, Three.js, Vite & Express 5 SSR
23. **Q: Why run an Express 5 SSR server (`ssr-server.mjs`) in front of Vite + React instead of plain `vite preview` or Nginx static hosting?**
    - **A:** `[VERIFIED IN SOURCE]` Four critical reasons:
      1. **SEO & Discoverability:** `entry-server.tsx` pre-fetches live site data and streams populated HTML + Schema.org JSON-LD + dynamic `/sitemap.xml` & `/robots.txt` for crawlers.
      2. **Security Per-Request CSP Nonces:** Static CDNs cannot generate a unique **128-bit cryptographic nonce per HTTP response** (`script-src 'self' 'nonce-...'`). Express 5 injects the nonce dynamically into both headers and `<script>` tags.
      3. **Same-Origin Cookie Proxy:** Proxying `/api` and `/storage` on `:3000` avoids cross-origin cookie/CORS traps while preserving multiple `Set-Cookie` headers (`clps_session` + `clps_csrf`).
      4. **Semantic HTTP Status Codes:** Returns genuine HTTP `404` on invalid paths instead of SPA `200 OK` soft-404s.
24. **Q: Why map `[x, y, z] -> [x*s, z*s, -y*s]` in Three.js (`coordinates.ts`)?**
    - **A:** `[VERIFIED IN SOURCE]` SPICE `MOON_ME` is right-handed **Z-up** (`+Z` = North Pole, `+X` = `0°` prime meridian, `+Y` = `90° E`). Three.js is right-handed **Y-up**. Applying `[x, z, -y]` swaps `+Z -> +Y` (North Up) while keeping $\det = +1$ so surface craters, site pins, solar illumination angle, and Earth direction are neither inside-out nor mirrored East/West. (Tested in `coordinates.test.ts`).
25. **Q: How does `vite.config.ts` optimize bundle weight for users who never open 3D views?**
    - **A:** `[VERIFIED IN SOURCE]` Manual Rollup chunking (`three-vendor`, `react-vendor`) plus lazy SSR-safe client wrappers (`LunarMoonCanvas.tsx`, `SimulationOrreryCanvas.tsx`) mean Three.js (`~600 KB`) never executes on SSR Node and loads cleanly on the client with `MoonFallbackView` ready if WebGL fails.

### Domain H — Cybersecurity, Auth, CSRF, CSP & RBAC
26. **Q: Where do you store auth tokens in the browser—JWT in `localStorage`?**
    - **A:** **Neither!** `[VERIFIED IN SOURCE]` Sessions use opaque URL-safe random tokens (`secrets.token_urlsafe`), hashed with **SHA-256** before storage in `admin_sessions` (so even a DB dump cannot impersonate active cookies). Cookies are **`HttpOnly`**, `SameSite=Lax`, auto-`Secure` behind TLS/production (`settings.is_cookie_secure`), paired with an **HMAC-SHA256 bound `clps_csrf` double-submit token** validated cleanly via `hmac.compare_digest` plus Origin verification on every mutation.
27. **Q: Why use Argon2id (`pwdlib[argon2]`) instead of bcrypt?**
    - **A:** Argon2id resists both GPU/ASIC cracking (memory-hard) and side-channel attacks, supports modern >72-byte passwords cleanly without truncation bugs, and is paired with password strength rules, `AUTH_LOCKOUT_THRESHOLD = 5` failed-attempt `15 min` lockout, IP sliding-window rate limiters (`auth`, `contact`, `ai_assist`, `simulation`, `codex`), and `last_super_admin` demotion/lockout protection (`users.py`).
28. **Q: How many RBAC roles exist, and what prevents privilege escalation in the UI?**
    - **A:** `[VERIFIED IN SOURCE]` **7 canonical roles** seeded in `007_phase7_admin_and_security.py`: `super_admin`, `system_admin`, `site_editor`, `research_admin`, `hardware_admin`, `hardware_operator`, and `viewer`. Client-side `AdminLayout.tsx` / `rbac.ts` hides unauthorized tabs strictly for UX, while **authoritative enforcement lives exclusively in FastAPI `Depends(RequireRole(...))`** on every backend route.
29. **Q: How do you protect SSR/HTML responses against XSS & host-header poisoning?**
    - **A:** `[VERIFIED IN SOURCE]`
      - Express 5 enforces strict **Host-header allow-list checking** before rendering routes.
      - JSON-LD metadata in `HeadTags.tsx` escapes `<` / `</script>` sequences cleanly.
      - Strict `script-src 'self' 'nonce-<per-request>'` (zero `unsafe-inline` scripts), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` (JSON API) / `frame-ancestors 'self'` (HTML), and `/admin*` pages carry `Cache-Control: no-store, max-age=0`.
      - All unhandled FastAPI 500s are sanitized in `middleware.py` to `{code, detail, request_id}` without stack traces, and `/admin/simulations/diagnostics` omits host OS paths (`PHASE_7_IMPLEMENTATION_REPORT.md`).

### Domain I — Ollama AI Assist & Anti-Hallucination Design
30. **Q: Why run local Ollama (`gemma4:e4b`) instead of calling OpenAI / Gemini cloud APIs?**
    - **A:** Zero external API keys needed during offline hackathon judging venues, zero external data egress/cost, and deterministic local latency bounds (`15.0 s` HTTP timeout + `3`-failure/`60 s` circuit breaker).
31. **Q: How do you guarantee the LLM never hallucinates lunar metrics, coordinates, or site scores?**
    - **A:** `[VERIFIED IN SOURCE]` (`ai_assist_service.py` + `prompts.py`) Architectural separation of concerns:
      - Prompt first passes `sanitize_user_prompt` (stripping 6 injection patterns like `ignore previous instructions`, `drop table`, `<script>`).
      - Ollama receives `EXTRACTION_JSON_SCHEMA` (`format="json"`) and **only outputs parameter keys, constraint operators, and priority weights** from an allow-listed 6-metric enum (`illumination_annual_avg`, `earth_visibility_avg`, `max_slope_deg`, `scientific_value_score`, `water_ice_probability`, `surface_roughness`).
      - **Pure Python `scoring.py`** queries PostgreSQL `SiteMetric`, checks hard constraints, computes normalized scores on `[0, 100]`, and builds the textual **rationale directly from verified numbers** (`RATIONALE_SYSTEM_PROMPT` in `prompts.py` is unused by design right now so not even the explanation string can hallucinate).
32. **Q: What happens if Ollama isn't running during judging?**
    - **A:** After failure / timeout or open circuit breaker, `extract_requirements_rule_based` seamlessly parses domain keywords into weights & constraints, setting `fallback_used=True` and `model_used="rule-based-fallback"` transparently in the UI.

### Domain J — Deterministic Comparison & Multi-Format Data Imports
33. **Q: How does `compare_two_sites` handle missing data cleanly without biasing sites with fewer measurements?**
    - **A:** `[VERIFIED IN SOURCE]` (`scoring.py`, `comparison_service.py`) Each metric uses a bounded direction (`higher` -> `(v-min)/(max-min)`, `lower` -> `(max-v)/(max-min)`, `target` -> `1 - |v-target|/tol`, clamped `[0, 1]`). `calculate_weighted_score` reports `coverage_status` (`complete`, `partial`, or `insufficient_data` if any `required` metric is `None`) and explicitly lists omitted metrics & re-normalized weights in `limitations`.
34. **Q: How does the Admin import workflow avoid corrupting live public data?**
    - **A:** `[VERIFIED IN SOURCE]` (`import_service.py`, `imports_admin.py`) Imports follow **Stage -> Preview -> Transactional Commit -> Optional Rollback**: CSV (`utf-8-sig`), XLSX (`openpyxl data_only=True`), and GeoJSON (`FeatureCollection Point`) rows are validated for spherical Moon bounds & great-circle proximity (`MOON_RADIUS_KM = 1737.4`) against existing sites before any public row is inserted, storing source batches in `dataset_imports` for rollback.

### Domain K — CODEX Kinematics, Moon LED Mapping & Firmware Template Engine
35. **Q: How does CODEX prevent simulation duration (`30 days`) from commanding impossible motor speeds?**
    - **A:** `[VERIFIED IN SOURCE]` (`codex_kinematics.py`) Astronomical time and bench physical time are decoupled (`5 s <= physical_duration_seconds <= 300 s`). Motion planning converts target orbital angles via microstep & gear reduction (`steps_per_rev = full_steps * microsteps * gear_ratio`), adds `backlash_steps`, fits either a **triangular** or **trapezoidal** velocity profile (`accel`, `cruise`, `decel`), and throws `acceleration_time_exceeded` / `max_step_rate_exceeded` / `travel_limit_violation` before any frame is built.
36. **Q: Why use centroid gnomonic projection for the 13 Moon LED regions?**
    - **A:** `[VERIFIED IN SOURCE]` (`moon_led_mapping.py`) Lat/lon polygons tear across the `±180°` antimeridian and pinch at the poles. Projecting spherical vertices onto the local tangent plane around each region centroid, checking edge distance `BOUNDARY_EPSILON = 1e-6` with lowest `region_index` deterministic tie-breaking, and running even-odd raycasting solves pole/antimeridian edge cases accurately. `approximate_centroid_only` fallback is strictly blocked during `/execute`.
37. **Q: Isn't editing C++ firmware templates inside a web dashboard a huge Code Injection security risk?**
    - **A:** `[VERIFIED IN SOURCE]` (`codex_template_engine.py`, `AdminFirmwareEditorPage.tsx`) Two-layer protection:
      1. **Substitution allow-list + C denylist:** Only `{{UPPER_SNAKE_CASE}}` tokens validated against numeric min/max/regex schemas may substitute; values containing `\n`, `\r`, `;`, `#include`, `#define`, `/*`, `*/`, `//`, quotes, or `\` are rejected cleanly before rendering.
      2. **No Auto-Flash Safety Policy:** Templates create immutable SHA-256 checksummed rows in `hardware_code_versions`; activating updates PostgreSQL only; the host never runs unverified flash commands onto connected MCUs (`Toolchain available: false`).

### Domain L — CODEX Wire Security, Hardware Architecture & Known Defects
38. **Q: Why use THREE microcontrollers (`ESP32` bridge + `Arduino Uno` + `ESP32-S3`) instead of one?**
    - **A:** Hardware electrical & library fit cleanly matches real lab modules: the **CNC Shield v3 + A4988/DRV8825 + NEMA17** plugs natively onto an **Arduino Uno R3** with dedicated hardware `INT1` pin-3 E-STOP and AVR 2s watchdog (`WDTO_2S`); an **ESP32 DevKit** handles Wi-Fi & mbedTLS **HMAC-SHA256** verification offloaded via CRC16 binary UART2 (`GPIO 16/17`); and a separate **ESP32-S3** drives `26` WS2812B Moon globe NeoPixels (`GPIO 48`) from its own external 5V PSU without starving stepper interrupts.
39. **Q: Why put binary `CRC16-CCITT` (`poly 0x1021`) + `SOF 0xAA55` on UART when the HTTP leg already has HMAC-SHA256?**
    - **A:** Stepper motors induce electromagnetic switching noise across bench jumper wires (`3.3V <-> 5V` level shifter). HTTP HMAC authenticates the network sender (`backend -> ESP32`), while **UART CRC16-CCITT** protects the local wire between ESP32 and Uno against RF/EMI bit flips—a flipped digit in `"N:1:5000:1000"` would otherwise spin a cam into a hard stop!
40. **Q: What hardware safety blockers still exist, and are there ANY bugs in your current HTTP-to-ESP32 firmware path?** *(Ultimate Honesty / Trap Question!)*
    - **A:** `[VERIFIED IN SOURCE]` + `[BLOCKED BY HARDWARE]`:
      - Yes—and we proactively surfaced both hardware readiness blockers and 3 specific protocol bugs found during static code review before physical Phase 5 bench wiring:
        1. **`MockCodexTransport` passes all 11 backend CODEX tests cleanly**, verifying HMAC, replay nonces, sequence numbers, and Uno CRC16 decoding in memory; physical `HttpCodexTransport` has NOT run against real silicon (`RSK-HW-01..03`, `arduino-cli` not installed, intentional `#error "SAFETY BLOCK:"` compile guards remain intact in `arduino-uno-motion.ino:16` and `esp32-s3-moon-led.ino:17`).
        2. Static review identified 3 firmware/HTTP parity issues to resolve during Phase 5 bench bring-up:
           - `HttpCodexTransport._post_command` (`client.py:402`) currently appends `body["uart_frame_hex"]` **after** `build_signed_headers()` already signed the payload in `codex_service.py:1387`.
           - Both ESP32 sketches re-serialize parsed JSON via unsorted `ArduinoJson` `serializeJson(doc, ...)` instead of canonical sorted keys, which will mismatch Python `sort_keys=True` on nested maps.
           - `handle_estop()` on both ESP32 sketches immediately triggers E-STOP without calling `verify_request_hmac(doc, true)`—failing safe-closed, but allowing unauthenticated LAN E-STOP triggers until wired.
        - **Why judges love this answer:** It proves genuine reverse-engineering rigor, zero hand-waving, and hardware safety maturity!

---

## 5. Additional Rapid-Fire Cross-Examination Bank (Questions 41–62)

41. **Why didn't you run Playwright inside the Vitest suite?** — `vite.config.ts` excludes `tests/e2e/**` cleanly from `vitest` jsdom because Playwright tests execute full browser automation against live Express 5 SSR + FastAPI + PostgreSQL.
42. **How do you stop replay attacks on `/codex/command`?** — Monotonic DB sequence counter + cryptographically random `nonce` persisted in `codex_command_nonces` with TTL cleanup (`CODEX_COMMAND_TTL_SECONDS = 300`), plus `16`-entry nonce ring buffers in ESP32 firmware.
43. **Why is E-STOP allowed to bypass monotonic sequence checks?** — Look at `codex_service.py` / `protocol.py` (`allow_estop_bypass_seq`): if a runaway queue had network retries or out-of-order sequences, E-STOP must **never** be rejected for a sequence skew while a motor is moving!
44. **What prevents a user from deleting or demoting the last `super_admin`?** — `users.py` enforces explicit `last_super_admin` guards rejecting self-lock, role strip, or deactivation when only one active `super_admin` remains.
45. **How does `run_clps.sh` remain macOS default-Bash compatible?** — macOS ships Bash 3.2 (GPLv2) without associative arrays (`declare -A`). `run_clps.sh` uses pure POSIX/Bash 3.2 constructs, temp lock directories (`/tmp/clps-luna-browser-<uid>/launcher.lock`), PID state files, and graceful signal traps.
46. **How are uploaded site images secured?** — `media_admin.py` + `media_service.py` validate image payloads with **Pillow**, strip unsafe containers/metadata by re-encoding cleanly to **WebP** + thumbnail pairs in `storage/media/`, never executing untrusted SVGs directly as scriptable active content.
47. **What prevents SSR crashes when FastAPI is temporarily down?** — `ssr-server.mjs` wraps `/api` fetch calls with timeouts (`AbortSignal`), returns clean degraded responses / ErrorBoundary UIs, and prevents Node unhandled promise rejections.
48. **What happens if a CSV dataset import contains a site at latitude `+95°` or `200°` longitude?** — Rejected cleanly during `stage`/`preview` (`import_service.py`) before any DB mutation; only valid `[-90, +90]` / `[-180, +180]` rows pass validation, and proximity checks warn if a site lands within close great-circle `MOON_RADIUS_KM = 1737.4` distance of an existing site.
49. **Why store metrics in `site_metrics` linked to `data_sources` instead of columns on `landing_sites`?** — Multiple missions/papers measure the same parameter (e.g., slope or illumination at different resolutions). Linking `SiteMetric -> ParameterDefinition + DataSource` with `data_quality_status` (`verified`, `provisional`, `unverified`) preserves scientific provenance and extensibility without `ALTER TABLE` migrations for every new metric.
50. **How does search avoid slow sequential scans on landing site names and long research articles?** — Migration `002_search_indexes.py` installs `idx_landing_sites_name_trgm` (`pg_trgm` GIN trigram index accelerating case-insensitive `ILIKE '%substring%'` name/code/slug matching) alongside `idx_site_content_fts` (English `tsvector` GIN full-text index queried via `plainto_tsquery('english', ...)` and highlighted via `ts_headline` in `search_service.py`). *(Note: trigram fuzzy `similarity()` typo correction is not currently wired into `search_service.py`—it runs substring `ILIKE` + stemmed English FTS.)*
51. **Why is there a `clps_luna` AND `clps_luna_test` database?** — Strict isolation: pytest drops/rolls back/recreates fixtures solely inside `clps_luna_test` so automated tests never touch seeded dev/demo records or operator audit logs in `clps_luna`.
52. **Why does `BYJ` stepper need a special `#error` compile guard on Arduino Uno?** — Standard 28BYJ-48 motors are **5-wire unipolar** driven by ULN2003 Darlington arrays (`HALF4WIRE IN1..IN4`), whereas NEMA 17 uses **bipolar `STEP/DIR`** (`A4988`/`DRV8825` on CNC Shield). Plugging an unmodified 5-wire BYJ into a bipolar driver overheats coils or damages drivers; `arduino-uno-motion.ino:16` makes the sketch uncompilable until the bench engineer selects the exact driver!
53. **What enforces watchdog protection if the Arduino Uno hangs during a step sequence?** — `<avr/wdt.h>` (`WDTO_2S` 2-second hardware watchdog enabled in `setup()`, reset each `loop()` iteration) plus CNC Shield active-LOW `STEPPER_ENABLE_PIN = 8` initialized `HIGH` (outputs disabled on reset).
54. **What stops `LIMIT_SWITCH_PIN = 9` or physical E-STOP (`Pin 3`) latency?** — `ESTOP_PIN = 3` binds hardware external interrupt `INT1` on `FALLING` edge (`isrPhysicalEstop` sets `volatile g_estopLatched = true`), and `loop()` immediately invokes `triggerEmergencyStop()` forcing `STEPPER_ENABLE_PIN` `HIGH` and disabling stepper outputs.
55. **Why doesn't the `/sites` public list endpoint use heavy `selectin` joins for full editorial content?** — Keep catalogue cards crisp & sub-millisecond; `SiteInfoPage` (`/api/v1/sites/{slug}`) fetches deep content/metrics/milestones only on demand via bounded 2-query sub-resource fetching.
56. **How does TypeScript stay in sync with FastAPI schemas?** — `npm run generate:api-types` runs `openapi-typescript` directly against `/api/v1/openapi.json` into `src/api/generated/schema.ts`, caught statically by `tsc --noEmit` whenever any API payload drifts.
57. **How does `POST /api/v1/codex/runs` guarantee an accidental double-click doesn't run motors twice?** — Mandatory unique `idempotency_key` (`codex_service.py:1308`) plus strict `run.status == "prepared"` one-shot state transition (second click with same key returns the existing run snapshot; different key on already-executed run returns `409 Conflict`).
58. **Why do you verify `system_components` with `"spice_ephemeris"`/`"lola_dem_rasters"`/`"ollama_llm"`/`"simulation_worker"` dynamically in `audit.py`?** — Remember to mention cleanly: migration `007` seeds 6 baseline keys (`backend-api`, `postgresql`, `spice-ephemeris`, `lola-dem`, `ollama-ai`, `codex-hardware`) while live health probes in `audit.py` upsert detailed keys (`spice_ephemeris`, `lola_dem_rasters`, `ollama_llm`, `simulation_worker`)—both coexist cleanly in `system_components`, and unifying them into one canonical enum is a straightforward cleanup item.
59. **What happens if two simulation workers poll simultaneously?** — PostgreSQL executes `SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1` inside `claim_next_queued_run` (`simulation_repo.py`), guaranteeing atomic mutually exclusive claiming with zero duplicate execution.
60. **Can an admin read another user's plaintext password or CODEX secret in `audit_logs`?** — **Never.** Passwords are stored exclusively as `Argon2id` hashes (`admins.password_hash`), session cookies as `SHA-256` hashes, and `codex.protocol.redact_sensitive_mapping` + `audit.py` scrub tokens/signatures before logging or returning audit JSON.
61. **How did you test database behavior against real PostgreSQL constraints instead of SQLite mocks?** — All 115 pytest tests execute directly against a live **PostgreSQL (`clps_luna_test`)** schema managed by Alembic (`007_phase7_admin_and_security` head), exercising `tsvector`, `pg_trgm`, `FOR UPDATE SKIP LOCKED`, `ON CONFLICT`, and foreign keys for real.
62. **If you had 2 more weeks with physical lab access, what is the exact next engineering sequence?** — (1) Fix `_post_command` pre-signing of `uart_frame_hex`, ESP32 canonical JSON key ordering, and HMAC enforcement on `/codex/estop`; (2) install `arduino-cli` + verify CNC Shield & 3.3V↔5V shifter on bench; (3) characterize backlash/gear/cam travel empirically into `motor_calibration_profiles` (`bench_verified`); (4) illuminate & survey 26 WS2812B LEDs onto the physical Moon globe (`BENCH_VERIFIED_LED_TOPOLOGY`); (5) flip `CODEX_TRANSPORT_MODE=http` and run signed physical E-STOP + closed-loop bench acceptance!
