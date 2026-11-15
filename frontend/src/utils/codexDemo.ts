/**
 * CODEX Demo Mode Presentation Data & Helpers
 *
 * Provides simulated presentation-only status indicators for demonstration purposes.
 * Does not modify physical hardware state, backend device-health records, or network communication.
 */

export interface DemoCodexController {
  controller_key: string;
  board_model: string;
  device_role: string;
  status: "Connected";
  link: "Online";
  state: "Ready";
  execution: "Running";
  verification_status: "Team Reported — Passed";
  uart_ok: boolean;
  heartbeat_fresh: boolean;
  driver_config_ok: boolean;
  led_controller_ok: boolean;
  last_heartbeat_at: string;
}

export const DEMO_CODEX_CONTROLLERS: DemoCodexController[] = [
  {
    controller_key: "wifi_bridge",
    board_model: "ESP32 DevKit — Wi-Fi Bridge",
    device_role: "Wi-Fi / UART Bridge",
    status: "Connected",
    link: "Online",
    state: "Ready",
    execution: "Running",
    verification_status: "Team Reported — Passed",
    uart_ok: true,
    heartbeat_fresh: true,
    driver_config_ok: true,
    led_controller_ok: false,
    last_heartbeat_at: "2026-11-15T00:00:00Z",
  },
  {
    controller_key: "motion_uno",
    board_model: "Arduino Uno R3 — Motor Controller",
    device_role: "Stepper Motion Controller",
    status: "Connected",
    link: "Online",
    state: "Ready",
    execution: "Running",
    verification_status: "Team Reported — Passed",
    uart_ok: true,
    heartbeat_fresh: true,
    driver_config_ok: true,
    led_controller_ok: false,
    last_heartbeat_at: "2026-11-15T00:00:00Z",
  },
  {
    controller_key: "moon_led_s3",
    board_model: "ESP32-S3 — Moon LED Controller",
    device_role: "Moon Surface LED Controller",
    status: "Connected",
    link: "Online",
    state: "Ready",
    execution: "Running",
    verification_status: "Team Reported — Passed",
    uart_ok: true,
    heartbeat_fresh: true,
    driver_config_ok: true,
    led_controller_ok: true,
    last_heartbeat_at: "2026-11-15T00:00:00Z",
  },
];

export const DEMO_VERIFICATION_MESSAGES = {
  hardwareDemonstration: "Hardware Demonstration: Completed",
  hardwareIntegration: "Hardware Integration: Completed",
  hardwareTestStatus: "Hardware Test Status: Team Reported — 12/12 Passed",
  projectStatus: "Project Status: Operational",
} as const;

const STORAGE_KEY = "codex_demo_mode";
let inMemoryDemoMode = true;

export function isCodexDemoMode(): boolean {
  if (typeof window !== "undefined") {
    try {
      const val = window.localStorage.getItem(STORAGE_KEY);
      if (val !== null && val !== undefined) {
        return val !== "false";
      }
    } catch {
      // Graceful fallback to in-memory state if localStorage is unavailable
    }
  }
  return inMemoryDemoMode;
}

export function setCodexDemoMode(enabled: boolean): void {
  inMemoryDemoMode = enabled;
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(STORAGE_KEY, enabled ? "true" : "false");
    } catch {
      // Graceful fallback if localStorage is disabled or restricted
    }
  }
}
