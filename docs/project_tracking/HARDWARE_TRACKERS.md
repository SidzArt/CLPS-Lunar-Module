# CODEX Hardware Subsystems, Calibrations, LED Mapping & Firmware Trackers

## 1. Controller & Device Inventory Tracker (`hardware_devices`)

| Controller Key | Role | Board Model | Transport | Initial Seed State | Expected Bench Requirements |
| --- | --- | --- | --- | --- | --- |
| `wifi_bridge` | `bridge` | ESP32 | `http` (LAN) | `offline`, `unverified` | `secrets.h` provisioned, HMAC-SHA256 verified, 3.3V↔5V level shifter to Uno UART |
| `motion_uno` | `motion_controller` | Arduino Uno R3 | `uart_via_bridge` | `offline`, `unverified` | Framed CRC16 UART, NEMA17 + verified BYJ driver (`config.h`), E-STOP switch, limit switches |
| `moon_led_s3` | `led_controller` | ESP32-S3 | `http` (LAN) | `offline`, `unverified`, `battery_voltage_available=false` | `secrets.h` provisioned, verified 13-region LED count & GPIO (`BENCH_VERIFIED_LED_TOPOLOGY`), external 5V PSU |

## 2. Motor Calibration Tracker (`motor_calibration_profiles`)

- **NEMA 17 (Elliptical-Groove Rotating Arm):** Physical cam geometry (focus, semi-major/minor axes, arm length, backlash, `travel_min_deg`, `travel_max_deg`) currently **UNVERIFIED** (`BLOCKED — HARDWARE TEAM REQUIRED`).
- **BYJ (Earth Frame Actuator):** Exact motor model and unipolar ULN2003 vs bipolar STEP/DIR modification currently **UNVERIFIED**.
- **Rule:** Profiles default to `verification_status='unverified'`. Live `execute` blocks actuation (`calibration_missing`) unless an immutable versioned profile has `verification_status='bench_verified'` with `measured_by` recorded.

## 3. 13-Region Moon LED Mapping Tracker (`moon_led_regions` & `moon_led_region_pixels`)

- Mapping supports exact tangent-plane spherical `boundary_polygon` containment with deterministic lowest-`region_index` boundary tie-breaking, plus normalized GPIO/addressable pixel entries (`output_channel`, `pixel_index`, `pixel_order`, `topology_mode`).
- Centroid-only lookup is isolated under `mapping_mode='approximate_centroid_only'` and rejected during strict execution unless `bench_verified` polygon topology is uploaded via `POST /api/v1/admin/codex/led-mapping`.

## 4. Firmware Targets Tracker (`./firmware/`)

| Firmware Directory | Board FQBN | Compile Guard | Toolchain Status |
| --- | --- | --- | --- |
| `firmware/esp32-wifi-bridge/` | `esp32:esp32:esp32` | Requires `secrets.h` | `BLOCKED — HARDWARE TEAM REQUIRED` (`arduino-cli` unavailable on host) |
| `firmware/arduino-uno-motion/` | `arduino:avr:uno` | Forces `#error` until `BYJ_DRIVER_ULN2003_4WIRE` or `BYJ_DRIVER_BIPOLAR_STEP_DIR` set in `config.h` | `BLOCKED — HARDWARE TEAM REQUIRED` |
| `firmware/esp32-s3-moon-led/` | `esp32:esp32:esp32s3` | Forces `#error` until `BENCH_VERIFIED_LED_TOPOLOGY` set in `secrets.h` | `BLOCKED — HARDWARE TEAM REQUIRED` |

## 5. CODEX Protocol v1 & Uno Binary UART Frame Specification

- **HTTP Command Payload (`codex.v1`):** Includes `protocol_version`, `command_id`, `simulation_id`, `site_id`, `issued_at_utc`, `expires_at_utc`, `nonce`, `sequence_number`, `idempotency_key`, `device_targets`, `configuration_version`, `calibration_version`, `led_mapping_version`, `motor_commands`, `moon_led`.
- **Authentication:** `HMAC-SHA256` over `command_id.issued_at_utc.nonce.sequence_number.canonical_json`, verified constantly (`hmac.compare_digest`), redacted (`[REDACTED]`) in all logs and responses.
- **Uno Binary UART Frame (`115200 8N1`):** `[SOF 0xAA55 LE][VER 0x01][MSG_TYPE][SEQ u32 LE][LEN u16 LE][PAYLOAD <=256B][CRC16-CCITT u16 LE]`.



## Phase 6 Frontend Mock & Honest Disclosure Integration (11 November 2026)

- **Header Status Pill (`frontend/src/components/SiteHeader.tsx`):** Displays live `CODEX · Mock / Blocked` state derived from `GET /api/v1/codex/status`.
- **CODEX Drawer & Workbench (`frontend/src/components/CodexDrawer.tsx`, `frontend/src/pages/CodexPage.tsx`):**
  - Displays both `MOCK / DEMONSTRATION MODE` and `REAL HARDWARE MODE — BLOCKED` indicators transparently.
  - Lists all 3 independent controllers (`wifi_bridge`, `motion_uno`, `moon_led_s3`) with live heartbeat/capability state.
  - Supports non-actuating dry-run `POST /api/v1/codex/runs/prepare` telemetry previews against `MockCodexTransport` while keeping physical actuation disabled.
- **Physical Bench Gate:** Physical motor calibration (`RSK-HW-01`), UART/LED electrical bench checks (`RSK-HW-02`), 13-region physical LED wiring (`RSK-HW-03`), and `arduino-cli` builds remain **`BLOCKED — HARDWARE TEAM REQUIRED`** pending Phase 8 hardware sign-off.

## Phase 7 Admin CODEX Workbench, Split-Pane Firmware Editor & Pre-Phase-7 Close-Out (11 November 2026)

- **Pre-Phase-7 Firmware & Protocol Close-Out (`AUD-11`):**
  - Preserved all compile-time safety guards (`#error "SAFETY BLOCK:"` in [`arduino-uno-motion.ino`](file:///Users/siddharthwaikar/Personal/CodexBase/NASA%20Space%20App%20Challenge/CLPS%20Lunar%20Module/firmware/arduino-uno-motion/arduino-uno-motion.ino#L16) and [`esp32-s3-moon-led.ino`](file:///Users/siddharthwaikar/Personal/CodexBase/NASA%20Space%20App%20Challenge/CLPS%20Lunar%20Module/firmware/esp32-s3-moon-led/esp32-s3-moon-led.ino#L17), plus `secrets.h` isolation in [`esp32-wifi-bridge.ino`](file:///Users/siddharthwaikar/Personal/CodexBase/NASA%20Space%20App%20Challenge/CLPS%20Lunar%20Module/firmware/esp32-wifi-bridge/esp32-wifi-bridge.ino#L14)).
  - Verified parity & fault-injection/recovery via `test_firmware_static_safety_guards_and_protocol_parity` and `test_codex_fault_injection_and_recovery` (`11 passed` in [`tests/test_codex_hardware.py`](file:///Users/siddharthwaikar/Personal/CodexBase/NASA%20Space%20App%20Challenge/CLPS%20Lunar%20Module/backend/tests/test_codex_hardware.py)).
- **Authenticated Admin CODEX Workbench ([`AdminCodexPage.tsx`](file:///Users/siddharthwaikar/Personal/CodexBase/NASA%20Space%20App%20Challenge/CLPS%20Lunar%20Module/frontend/src/pages/admin/AdminCodexPage.tsx)):**
  - Role-gated (`hardware_admin`, `system_admin`, `super_admin`) console exposing controller transport probes, device heartbeat inspection, versioned `motor_calibration_profiles`, 13-region `moon_led_regions` polygon/pixel viewer, configuration rotation, hardware run logs, and Emergency Stop trigger while visibly maintaining the hardware safety block boundary.
- **Split-Pane Firmware Editor & Live Variable Reference ([`AdminFirmwareEditorPage.tsx`](file:///Users/siddharthwaikar/Personal/CodexBase/NASA%20Space%20App%20Challenge/CLPS%20Lunar%20Module/frontend/src/pages/admin/AdminFirmwareEditorPage.tsx), [`codex_admin.py`](file:///Users/siddharthwaikar/Personal/CodexBase/NASA%20Space%20App%20Challenge/CLPS%20Lunar%20Module/backend/app/api/v1/admin/codex_admin.py#L279-L413)):**
  - Wired to `GET/POST /api/v1/admin/hardware/code-versions`, `GET /{id}`, `POST /{id}/activate`, `GET /{id}/diff/{other_id}`, `POST /{id}/validate-syntax`, `POST /{id}/render-preview`, and `GET /api/v1/admin/hardware/variables`.
  - Features left-pane C/C++ editor with line numbers, in-file search, C++ syntax highlight view, unified line/placeholder diff viewer, placeholder allow-list escaping controls, and right-pane filterable Live Variable Reference with one-click `Insert`.
  - Enforces an explicit **No Auto-Flash Safety Policy**: saving creates an immutable SHA-256 checksummed database snapshot and activating updates only PostgreSQL state; host toolchain reports `Toolchain available: false` and physical flashing remains **`BLOCKED — HARDWARE TEAM REQUIRED`**.

## Phase 8 Final Hardware & Firmware Verification Gate Status (11 November 2026)

- **Overall Hardware-Dependent Release Gate:** **`BLOCKED — HARDWARE TEAM REQUIRED`** (`AUD-07` / `RSK-HW-01..03`).
- **Safety Invariants Verified in Phase 8:**
  - Compile-time `#error "SAFETY BLOCK:"` guards remain active in `firmware/arduino-uno-motion/arduino-uno-motion.ino` and `firmware/esp32-s3-moon-led/esp32-s3-moon-led.ino`, alongside `secrets.h` isolation in `firmware/esp32-wifi-bridge/esp32-wifi-bridge.ino`.
  - Backend defaults remain `CODEX_REQUIRE_VERIFIED_BENCH=True` and `MockCodexTransport`; unverified calibrations (`verification_status='unverified'`) continue blocking live motor execution.
  - CRC16-CCITT framing refactor (`SIM108`) in `app/integrations/codex/protocol.py` and dead-code cleanup in `codex_repo.py` passed all hardware/protocol unit tests (`test_codex_hardware.py`), `mypy app`, and `ruff check .`.
  - Live SSR/UI E2E confirmed `/codex`, the header pill (`CODEX · Mock / Blocked`), and `/admin/codex` transparently disclose the hardware block without console errors.
- **Physical Items Still Required Before Enabling `HttpCodexTransport` / Live Actuation:** `arduino-cli` installation & compilation of all 3 targets, physical BYJ driver confirmation (`config.h`), optical 13-region LED verification (`BENCH_VERIFIED_LED_TOPOLOGY`), elliptical cam calibration measurement (`bench_verified`), and live UART loopback + E-STOP bench sign-off.
