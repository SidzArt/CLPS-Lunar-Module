# CLPS Luna Browser — Master Phase Tracking Dashboard

**Current Baseline:** Master Implementation Plan **Version 8.0**  
**Alembic Head:** `007_phase7_admin_and_security` (applied to `clps_luna` and `clps_luna_test`; verified in isolated restore `clps_luna_restore_test`)  
**Overall Release Gate:** **`PHASE 8 SOFTWARE VERIFICATION COMPLETED — OVERALL HARDWARE-DEPENDENT RELEASE GATE BLOCKED`**  
**CODEX Bench Verification Status:** `BLOCKED — HARDWARE TEAM REQUIRED` (Software, mock transport & split-pane firmware workbench complete; `#error "SAFETY BLOCK:"` compile guards & `CODEX_REQUIRE_VERIFIED_BENCH=True` preserved; physical MCU/motor/LED bench checks unverified)

| Phase | Title | Status | Gate / Notes |
| --- | --- | --- | --- |
| Phase 0 | Discovery and Project Setup | `COMPLETED` | Architecture, dependencies, and risk register approved |
| Phase 1 | Backend Core and Database Baseline | `COMPLETED` | FastAPI, SQLAlchemy 2.0, Alembic baseline, Argon2id auth, RBAC |
| Phase 2 | Landing-Site Catalogue and Data Import | `COMPLETED` | 5 published sites + 1 archived (`CLPS-TEST-001`) + staging/UPDATE rollback fixed |
| Phase 3 | Deterministic Comparison & Ollama AI Assist | `COMPLETED` | 5 published sites scored cleanly; unsourced metrics tagged `unverified` in `006`; `illumination_annual_avg` seeded in `004` |
| Phase 4 | Scientific Simulation Engine (SPICE + LOLA DEM) | `COMPLETED` | NAIF DE440/MOON_ME + LOLA 5 m–60 m/px terrain horizon & async worker |
| Phase 5 | CODEX Hardware System | `PARTIAL` | Backend, protocol, firmware skeletons, and 11 Phase 5/close-out test functions (including `#error` safety guard & fault-injection tests) complete; physical bench verification `BLOCKED — HARDWARE TEAM REQUIRED` |
| Phase 6 | Frontend Integration and SSR | `COMPLETED` (with `MockCodexTransport`) | React 19 + Vite 7 SSR, Three.js Moon & Orrery, 6-block Dossier, Contact/provenance APIs, 14 Vitest + E2E passed. Hardware bench remains `BLOCKED` until Phase 8. |
| Phase 7 | Admin Portal and Security Hardening | `COMPLETED` | Migration `007`, cookie + double-submit CSRF, Origin/lockout/RBAC, per-request nonce CSP, full Admin Portal + Split-Pane Firmware Editor (`108` pytest at `89%`, `20` Vitest, `4` Playwright E2E passed). Stopped before Phase 8. |
| Phase 8 | Full System Verification and Production Release | `PARTIAL` (`SOFTWARE COMPLETED — HARDWARE GATE BLOCKED`) | Phase 8 audit, bug fixes, query/Three.js optimisations, dep pruning (`scipy`, `react-helmet-async`), `npm audit` (`0` vulns), orphan media cleanup (`48` files), `pg_dump`/`pg_restore` drill (`45` tables, `4,097` rows), SSR host-header hardening, `115` pytest (`91%` cov), `22` Vitest, `5` Playwright E2E passed. Physical bench calibration & flashing remain `BLOCKED — HARDWARE TEAM REQUIRED` (`AUD-07` / `RSK-HW-01..03`). |

