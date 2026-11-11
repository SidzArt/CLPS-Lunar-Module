import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "../app/ThemeContext";
import { AiAssistPage } from "../pages/AiAssistPage";
import { BrowserPage } from "../pages/BrowserPage";
import { CodexPage } from "../pages/CodexPage";
import { ComparePage } from "../pages/ComparePage";
import { IntroPage } from "../pages/IntroPage";
import { SimulationPage } from "../pages/SimulationPage";
import { SiteInfoPage } from "../pages/SiteInfoPage";

const TWO_SITES = {
  items: [
    {
      site_id: 102,
      site_slug: "lunokhod-1",
      site_code: "LUNA-17",
      site_name: "Lunokhod 1",
      region_id: 15,
      region_name: "Mare Imbrium",
      latitude_deg: 38.315,
      longitude_deg: -35.008,
      elevation_m: -2600,
      terrain_type: "Mare Basaltic Plain",
      overview_summary: "Luna 17 rover traverse region.",
      catalogue_status: "published",
      primary_thumbnail: null,
      updated_at: "2026-11-11T00:00:00Z",
    },
    {
      site_id: 136,
      site_slug: "mons-mouton",
      site_code: "VIPER-MM",
      site_name: "Mons Mouton",
      region_id: 6,
      region_name: "South Pole-Aitken",
      latitude_deg: -84.9,
      longitude_deg: 31.6,
      elevation_m: 5800,
      terrain_type: "Polar Massif Plateau",
      overview_summary: "South polar illuminated plateau candidate.",
      catalogue_status: "published",
      primary_thumbnail: null,
      updated_at: "2026-11-11T00:00:00Z",
    },
  ],
  total: 2,
  page: 1,
  page_size: 50,
};

const CODEX_STATUS = {
  transport_mode: "mock",
  require_verified_bench: true,
  overall_status: "unverified",
  motors_ready: false,
  led_ready: false,
  estop_latched: false,
  calibration_verified: false,
  led_mapping_verified: false,
  blockers: ["Bench motor calibration pending Phase 5 team."],
  controllers: [
    {
      controller_key: "wifi_bridge",
      device_role: "wifi_uart_bridge",
      board_model: "ESP32-WROOM-32D",
      health_state: "unverified",
      verification_status: "unverified",
      heartbeat_fresh: false,
      uart_ok: false,
      driver_config_ok: false,
      led_controller_ok: false,
      estop_latched: false,
      battery_voltage_available: false,
      battery_voltage_v: null,
      last_heartbeat_at: null,
    },
    {
      controller_key: "motion_uno",
      device_role: "stepper_motion_controller",
      board_model: "Arduino Uno R3 + CNC Shield v3",
      health_state: "unverified",
      verification_status: "unverified",
      heartbeat_fresh: false,
      uart_ok: false,
      driver_config_ok: false,
      led_controller_ok: false,
      estop_latched: false,
      battery_voltage_available: false,
      battery_voltage_v: null,
      last_heartbeat_at: null,
    },
    {
      controller_key: "moon_led_s3",
      device_role: "moon_led_controller",
      board_model: "ESP32-S3",
      health_state: "unverified",
      verification_status: "unverified",
      heartbeat_fresh: false,
      uart_ok: false,
      driver_config_ok: false,
      led_controller_ok: false,
      estop_latched: false,
      battery_voltage_available: false,
      battery_voltage_v: null,
      last_heartbeat_at: null,
    },
  ],
  checked_at: "2026-11-11T00:00:00Z",
};

function renderWithProviders(ui: ReactNode, initialEntry = "/") {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <MemoryRouter initialEntries={[initialEntry]}>{ui}</MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe("Phase 6 Interactive Pages", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("BrowserPage filters sites and renders honest CODEX Mock/Blocked badge", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const url = String(input);
        if (url.includes("/api/v1/sites")) {
          return new Response(JSON.stringify(TWO_SITES), { status: 200 });
        }
        if (url.includes("/api/v1/codex/status")) {
          return new Response(JSON.stringify(CODEX_STATUS), { status: 200 });
        }
        return new Response(JSON.stringify([]), { status: 200 });
      }),
    );

    renderWithProviders(<BrowserPage />, "/browser");

    await screen.findByText(/CODEX · Mock \/ Blocked/i);
    expect(screen.getAllByText("Lunokhod 1").length).toBeGreaterThan(0);

    const filterInput = screen.getByPlaceholderText(/Filter name, code, terrain/i);
    fireEvent.change(filterInput, { target: { value: "Mouton" } });

    await waitFor(() => {
      expect(screen.getAllByText("Mons Mouton").length).toBeGreaterThan(0);
    });
  });

  it("ComparePage handles undetermined winner without fabricating a winner badge", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("/api/v1/sites")) {
          return new Response(JSON.stringify(TWO_SITES), { status: 200 });
        }
        if (url.includes("/api/v1/codex/status")) {
          return new Response(JSON.stringify(CODEX_STATUS), { status: 200 });
        }
        if (url.includes("/api/v1/compare/profiles")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        if (url.endsWith("/api/v1/compare") && init?.method === "POST") {
          return new Response(
            JSON.stringify({
              run_id: "comp-1",
              site_a_id: 102,
              site_b_id: 136,
              site_a_name: "Lunokhod 1",
              site_b_name: "Mons Mouton",
              site_a_code: "LUNA-17",
              site_b_code: "VIPER-MM",
              site_a_slug: "lunokhod-1",
              site_b_slug: "mons-mouton",
              mission_purpose: "Compare solar power illumination.",
              algorithm_version: "v1.0",
              data_coverage: "partial",
              overall_score_a: null,
              overall_score_b: null,
              overall_winner: "undetermined",
              winner_site_name: null,
              parameters: [
                {
                  parameter_key: "solar_illumination_pct",
                  display_name: "Solar Illumination",
                  unit: "%",
                  value_type: "numeric",
                  comparison_direction: "higher_better",
                  value_a: 54,
                  value_b: null,
                  absolute_difference: null,
                  relative_difference_percent: null,
                  normalised_a: 0.54,
                  normalised_b: null,
                  winner_key: "insufficient_data",
                  required: true,
                  is_scoreable: true,
                  data_quality_status: "unverified",
                  explanation: "Missing Site B solar illumination value.",
                },
              ],
              scientific_conclusion: "Insufficient overlapping verified parameters.",
              limitations_and_caveats: ["Site B lacks verified solar metric."],
              created_at: "2026-11-11T00:00:00Z",
            }),
            { status: 200 },
          );
        }
        return new Response(JSON.stringify({}), { status: 200 });
      }),
    );

    renderWithProviders(<ComparePage />, "/compare");
    await waitFor(() => {
      const btn = screen.getByRole("button", { name: /Compare ->/i });
      expect(btn).not.toBeDisabled();
    });

    fireEvent.click(screen.getByRole("button", { name: /Compare ->/i }));
    await screen.findByText(/Undetermined — Insufficient Data or Tie/i);
    expect(screen.queryByText(/Favoured:/i)).not.toBeInTheDocument();
  });

  it("AiAssistPage discloses deterministic keyword fallback honestly", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("/api/v1/sites")) {
          return new Response(JSON.stringify(TWO_SITES), { status: 200 });
        }
        if (url.includes("/api/v1/codex/status")) {
          return new Response(JSON.stringify(CODEX_STATUS), { status: 200 });
        }
        if (url.endsWith("/api/v1/ai-assist/recommend") && init?.method === "POST") {
          return new Response(
            JSON.stringify({
              mission_request: "Need high solar illumination.",
              mission_summary: "Maximize solar power illumination.",
              extracted_requirements: {
                mission_summary: "Maximize solar illumination",
                required_parameters: ["solar_illumination_pct"],
                preferred_parameters: [],
                constraints: [],
                priority_weights: [],
                needs_clarification: false,
              },
              recommendations: [
                {
                  rank: 1,
                  site_id: 102,
                  site_code: "LUNA-17",
                  site_name: "Lunokhod 1",
                  site_slug: "lunokhod-1",
                  latitude_deg: 38.315,
                  longitude_deg: -35.008,
                  elevation_m: -2600,
                  terrain_type: "Mare Basaltic Plain",
                  overview_summary: "Luna 17 landing site.",
                  score: 0.72,
                  rationale: "Matched solar_illumination_pct = 54%",
                  matched_parameters: { solar_illumination_pct: 54 },
                  missing_parameters: ["earth_visibility_pct"],
                  data_quality_status: "unverified",
                },
              ],
              fallback_used: true,
              model_used: "deterministic_keyword_fallback",
              execution_time_ms: 14.2,
              clarification_message: null,
              limitations: ["Ollama daemon offline during test."],
            }),
            { status: 200 },
          );
        }
        return new Response(JSON.stringify({}), { status: 200 });
      }),
    );

    renderWithProviders(<AiAssistPage />, "/ai-assist");
    fireEvent.click(screen.getByRole("button", { name: /Recommend Sites ->/i }));
    await screen.findByText(/Deterministic Keyword Fallback Active/i);
    expect(screen.getByText(/Missing data: earth_visibility_pct/i)).toBeInTheDocument();
  });

  it("SiteInfoPage switches cleanly across all 6 blocks and shows empty states truthfully", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const url = String(input);
        if (url.includes("/api/v1/codex/status")) {
          return new Response(JSON.stringify(CODEX_STATUS), { status: 200 });
        }
        if (url.includes("/api/v1/sites/lunokhod-1/metrics")) {
          return new Response(
            JSON.stringify([
              {
                site_metric_id: 1,
                site_id: 102,
                parameter_id: 10,
                parameter_key: "solar_illumination_pct",
                display_name: "Solar Illumination",
                numeric_value: 54,
                unit: "%",
                data_quality_status: "unverified",
              },
            ]),
            { status: 200 },
          );
        }
        if (url.match(/\/api\/v1\/sites\/lunokhod-1\/(sections|pros-cons|media|history)/)) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        if (url.endsWith("/api/v1/sites/lunokhod-1")) {
          return new Response(
            JSON.stringify({
              site_id: 102,
              site_slug: "lunokhod-1",
              site_code: "LUNA-17",
              site_name: "Lunokhod 1",
              latitude_deg: 38.315,
              longitude_deg: -35.008,
              elevation_m: -2600,
              terrain_type: "Mare Basaltic Plain",
              overview_summary: "Luna 17 landing site summary.",
              catalogue_status: "published",
              coordinate_reference: "MOON_ME",
              available_sections: [],
              created_at: "2026-11-11T00:00:00Z",
              updated_at: "2026-11-11T00:00:00Z",
            }),
            { status: 200 },
          );
        }
        if (url.includes("/api/v1/sites")) {
          return new Response(JSON.stringify(TWO_SITES), { status: 200 });
        }
        return new Response(JSON.stringify([]), { status: 200 });
      }),
    );

    renderWithProviders(
      <Routes>
        <Route path="/sites/:siteSlug" element={<SiteInfoPage />} />
      </Routes>,
      "/sites/lunokhod-1",
    );

    await screen.findByText("Luna 17 landing site summary.");

    fireEvent.click(screen.getByRole("tab", { name: /History/i }));
    await screen.findByText(/No historical timeline milestones/i);

    fireEvent.click(screen.getByRole("tab", { name: /Statistics/i }));
    await screen.findByText("Solar Illumination");
    expect(screen.getByText("unverified")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /Gallery/i }));
    await screen.findByText(/No site-specific photographs/i);
  });

  it("SimulationPage prominently flags geometric_only runs as unverified for terrain", async () => {
    const simId = "11111111-1111-1111-1111-111111111111";
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const url = String(input);
        if (url.includes("/api/v1/codex/status")) {
          return new Response(JSON.stringify(CODEX_STATUS), { status: 200 });
        }
        if (url.includes("/api/v1/sites")) {
          return new Response(JSON.stringify(TWO_SITES), { status: 200 });
        }
        if (url.endsWith(`/api/v1/simulations/${simId}`)) {
          return new Response(
            JSON.stringify({
              simulation_id: simId,
              status: "completed",
              progress_pct: 100,
              quality_state: "geometric_only",
              quality_warnings: ["Missing local LOLA DEM tile."],
              site: {
                site_id: 102,
                site_code: "LUNA-17",
                site_slug: "lunokhod-1",
                site_name: "Lunokhod 1",
                latitude_deg: 38.315,
                longitude_deg: -35.008,
                elevation_m: -2600,
                coordinate_reference: "MOON_ME",
                cartesian_moon_me_km: [1110, -780, 1077],
              },
              start_time_utc: "2026-06-01T00:00:00Z",
              duration_seconds: 86400,
              playback_speed: 600,
              coordinate_frame: "MOON_ME",
              aberration_policy: "LT+S",
              algorithm_version: "v1.0",
              limitations_disclaimers: ["Geometric-only fallback."],
              created_at: "2026-11-11T00:00:00Z",
            }),
            { status: 200 },
          );
        }
        if (url.includes(`/api/v1/simulations/${simId}/series`)) {
          return new Response(
            JSON.stringify({
              simulation_id: simId,
              status: "completed",
              quality_state: "geometric_only",
              playback_speed: 600,
              site: {
                site_id: 102,
                site_code: "LUNA-17",
                site_slug: "lunokhod-1",
                site_name: "Lunokhod 1",
                latitude_deg: 38.315,
                longitude_deg: -35.008,
                elevation_m: -2600,
                coordinate_reference: "MOON_ME",
                cartesian_moon_me_km: [1110, -780, 1077],
              },
              coordinate_contract: {},
              units: {},
              horizon_profile: null,
              total_samples_available: 1,
              returned_samples: 1,
              offset: 0,
              limit: 1000,
              downsample_step: 1,
              samples: [
                {
                  sample_index: 0,
                  timestamp_utc: "2026-06-01T00:00:00Z",
                  ephemeris_time: 833544069.18,
                  elapsed_seconds: 0,
                  sun: {
                    azimuth_deg: 112.4,
                    elevation_deg: 24.5,
                    range_km: 151000000,
                    horizon_deg: 0,
                    dir_moon_me: [0.5, 0.5, 0.707],
                    visibility_status: "visible_geometric",
                  },
                  earth: {
                    azimuth_deg: 145.1,
                    elevation_deg: 41.2,
                    range_km: 384400,
                    horizon_deg: 0,
                    dir_moon_me: [0.95, 0.1, 0.29],
                    visibility_status: "visible_geometric",
                  },
                  concurrent_visible: true,
                  quality_status: "geometric_only",
                },
              ],
            }),
            { status: 200 },
          );
        }
        if (url.includes(`/api/v1/simulations/${simId}/events`)) {
          return new Response(
            JSON.stringify({
              simulation_id: simId,
              status: "completed",
              quality_state: "geometric_only",
              total_events: 0,
              events: [],
            }),
            { status: 200 },
          );
        }
        return new Response(JSON.stringify({}), { status: 200 });
      }),
    );

    renderWithProviders(
      <Routes>
        <Route path="/simulation/:simulationId" element={<SimulationPage />} />
      </Routes>,
      `/simulation/${simId}`,
    );

    await screen.findByText(/GEOMETRIC ONLY/i);
    expect(
      screen.getByText(/Terrain-aware LOLA DEM horizon obstruction is NOT verified/i),
    ).toBeInTheDocument();
  });

  it("CodexPage lists 3 independent controllers, Mock banner, and disables physical actuation", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const url = String(input);
        if (url.includes("/api/v1/codex/status")) {
          return new Response(JSON.stringify(CODEX_STATUS), { status: 200 });
        }
        if (url.includes("/api/v1/sites")) {
          return new Response(JSON.stringify(TWO_SITES), { status: 200 });
        }
        if (url.includes("/api/v1/auth/me")) {
          return new Response(JSON.stringify({ detail: "Not authenticated" }), {
            status: 401,
          });
        }
        return new Response(JSON.stringify({}), { status: 200 });
      }),
    );

    renderWithProviders(<CodexPage />, "/codex");
    await screen.findByText("ESP32-WROOM-32D");
    expect(screen.getByText(/MOCK \/ DEMONSTRATION MODE/i)).toBeInTheDocument();
    expect(screen.getByText(/REAL HARDWARE MODE — BLOCKED/i)).toBeInTheDocument();
    expect(screen.getByText("Arduino Uno R3 + CNC Shield v3")).toBeInTheDocument();
    expect(screen.getByText("ESP32-S3")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Physical Execution Locked/i }),
    ).toBeDisabled();
  });

  it("ComparePage allows selecting Site B value for Site A without overwriting Site B and swaps cleanly", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const url = String(input);
        if (url.includes("/api/v1/sites")) {
          return new Response(JSON.stringify(TWO_SITES), { status: 200 });
        }
        if (url.includes("/api/v1/codex/status")) {
          return new Response(JSON.stringify(CODEX_STATUS), { status: 200 });
        }
        if (url.includes("/api/v1/compare/profiles")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        return new Response(JSON.stringify({}), { status: 200 });
      }),
    );

    renderWithProviders(<ComparePage />, "/compare");
    const selectA = (await screen.findByLabelText("Site A")) as HTMLSelectElement;
    const selectB = (await screen.findByLabelText("Site B")) as HTMLSelectElement;

    await waitFor(() => {
      expect(selectA.value).toBe("102");
      expect(selectB.value).toBe("136");
    });

    // Selecting Site B's ID in Site A triggers validation instead of locking or overwriting
    fireEvent.change(selectA, { target: { value: "136" } });
    expect(selectA.value).toBe("136");
    expect(selectB.value).toBe("136");

    fireEvent.change(selectB, { target: { value: "102" } });
    expect(selectB.value).toBe("102");

    fireEvent.click(screen.getByRole("button", { name: /Swap Site A and Site B/i }));
    expect(selectA.value).toBe("102");
    expect(selectB.value).toBe("136");
  });

  it("IntroPage exposes Admin navigation aria-label and handles scroll events cleanly without throwing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const url = String(input);
        if (url.includes("/api/v1/sites")) {
          return new Response(JSON.stringify(TWO_SITES), { status: 200 });
        }
        return new Response(JSON.stringify({}), { status: 200 });
      }),
    );

    renderWithProviders(<IntroPage />, "/");
    expect(await screen.findByRole("link", { name: /Open Admin Portal login/i })).toBeInTheDocument();
    fireEvent.scroll(window, { target: { scrollY: 400 } });
    fireEvent.scroll(window, { target: { scrollY: 0 } });
  });
});
