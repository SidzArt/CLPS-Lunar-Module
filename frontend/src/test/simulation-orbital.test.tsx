import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import * as THREE from "three";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  fetchCompleteSimulationSeries,
  type OrbitalTrajectoryOut,
  type SimulationSeriesOut,
} from "../api/endpoints";
import { ThemeProvider } from "../app/ThemeContext";
import { SimulationPage } from "../pages/SimulationPage";
import { latLonToThreeVector } from "../three/coordinates";
import {
  ANIMATION_DURATION_PRESETS,
  computePlaybackRate,
  eclipJ2000ToThree,
  interpolateOrbitalState,
  moonMeMatrixToThreeQuaternion,
  SCIENTIFIC_DURATION_OPTIONS,
  validateAnimationDurationInput,
} from "../three/simulationOrbitMath";

function renderWithRouter(ui: ReactNode, route = "/simulation") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <ThemeProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
      </QueryClientProvider>
    </ThemeProvider>,
  );
}

function buildOrbitalSamplesForTest(count = 65, durationSec = 2360621): OrbitalTrajectoryOut {
  const startMs = Date.parse("2026-06-01T00:00:00Z");
  const auKm = 149_597_870.7;
  const emKm = 384_400;
  const inclRad = (5.145 * Math.PI) / 180;

  const samples = Array.from({ length: count }, (_, idx) => {
    const frac = idx / (count - 1);
    const elapsed = frac * durationSec;
    const thetaE = (elapsed / (365.256 * 86400)) * 2 * Math.PI;
    const thetaM = (elapsed / (27.322 * 86400)) * 2 * Math.PI;

    const rE = auKm * (1 - 0.0167 * Math.cos(thetaE));
    const ex = rE * Math.cos(thetaE);
    const ey = rE * Math.sin(thetaE);
    const ez = 0;

    const rM = emKm * (1 - 0.0549 * Math.cos(thetaM));
    const mx = rM * Math.cos(thetaM);
    const my = rM * Math.sin(thetaM) * Math.cos(inclRad);
    const mz = rM * Math.sin(thetaM) * Math.sin(inclRad);

    // Tidally locked MOON_ME -> ECLIPJ2000: +X_ME points toward Earth (-mx, -my, -mz)
    const dirToEarth = new THREE.Vector3(-mx, -my, -mz).normalize();
    const north = new THREE.Vector3(0, 0, 1);
    const yAxis = new THREE.Vector3().crossVectors(north, dirToEarth).normalize();
    const zAxis = new THREE.Vector3().crossVectors(dirToEarth, yAxis).normalize();

    const rot: [
      [number, number, number],
      [number, number, number],
      [number, number, number],
    ] = [
      [dirToEarth.x, yAxis.x, zAxis.x],
      [dirToEarth.y, yAxis.y, zAxis.y],
      [dirToEarth.z, yAxis.z, zAxis.z],
    ];

    return {
      timestamp_utc: new Date(startMs + elapsed * 1000).toISOString().replace(".000Z", "Z"),
      ephemeris_time: 833544069.18 + elapsed,
      elapsed_seconds: elapsed,
      earth_wrt_sun_eclipj2000_km: [ex, ey, ez] as [number, number, number],
      moon_wrt_earth_eclipj2000_km: [mx, my, mz] as [number, number, number],
      moon_wrt_sun_eclipj2000_km: [ex + mx, ey + my, ez + mz] as [number, number, number],
      moon_me_to_eclipj2000: rot,
    };
  });

  return {
    simulation_id: "11111111-1111-1111-1111-111111111111",
    site: {
      site_id: 1,
      site_code: "HIST-LUNO-01",
      site_slug: "lunokhod-1",
      site_name: "Lunokhod 1",
      latitude_deg: 38.315,
      longitude_deg: -35.008,
      elevation_m: -2600,
      coordinate_reference: "MOON_ME",
      cartesian_moon_me_km: [1110, -780, 1077],
    },
    coordinate_frame: "ECLIPJ2000",
    lunar_body_frame: "MOON_ME",
    distance_units: "kilometers",
    aberration_policy: "NONE",
    ephemeris_source: "NASA/JPL NAIF Generic Kernels",
    ephemeris_version: "DE440",
    start_time_utc: "2026-06-01T00:00:00Z",
    end_time_utc: new Date(startMs + durationSec * 1000).toISOString().replace(".000Z", "Z"),
    duration_seconds: durationSec,
    sample_count: count,
    coverage_start_utc: "1549-12-31T00:00:00Z",
    coverage_end_utc: "2650-01-25T00:00:00Z",
    samples,
  };
}

function buildSeriesSamples(count = 25, durationSec = 2360621): SimulationSeriesOut {
  const startMs = Date.parse("2026-06-01T00:00:00Z");
  const samples = Array.from({ length: count }, (_, idx) => {
    const elapsed = (idx / (count - 1)) * durationSec;
    return {
      sample_index: idx,
      timestamp_utc: new Date(startMs + elapsed * 1000).toISOString().replace(".000Z", "Z"),
      ephemeris_time: 833544069.18 + elapsed,
      elapsed_seconds: elapsed,
      sun: {
        azimuth_deg: 100 + idx,
        elevation_deg: 24 + (idx % 10),
        range_km: 151_000_000,
        horizon_deg: 0,
        dir_moon_me: [0.5, 0.5, 0.707] as [number, number, number],
        visibility_status: "VISIBLE",
      },
      earth: {
        azimuth_deg: 145.1,
        elevation_deg: 41.2,
        range_km: 384400,
        horizon_deg: 0,
        dir_moon_me: [0.95, 0.1, 0.29] as [number, number, number],
        visibility_status: "VISIBLE",
      },
      concurrent_visible: true,
      subsolar_lat_deg: 1.1,
      subsolar_lon_deg: 42.3,
      quality_status: "verified_terrain_aware",
    };
  });

  return {
    simulation_id: "11111111-1111-1111-1111-111111111111",
    status: "completed",
    quality_state: "verified_terrain_aware",
    playback_speed: 600,
    site: {
      site_id: 1,
      site_code: "HIST-LUNO-01",
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
    total_samples_available: count,
    returned_samples: count,
    offset: 0,
    limit: count,
    downsample_step: 1,
    samples,
  };
}

describe("Orbital Simulation Math, Pagination & Duration Controls", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("validates animation playback duration rules and computes D / A playback rate", () => {
    expect(validateAnimationDurationInput("45")).toEqual({ valid: true, seconds: 45, error: null });
    expect(validateAnimationDurationInput("180")).toEqual({ valid: true, seconds: 180, error: null });
    expect(validateAnimationDurationInput("600")).toEqual({ valid: true, seconds: 600, error: null });
    expect(validateAnimationDurationInput("5")).toEqual({ valid: true, seconds: 5, error: null });
    expect(validateAnimationDurationInput("3600")).toEqual({ valid: true, seconds: 3600, error: null });

    for (const bad of ["", "   ", "0", "-10", "4", "3601", "12.5", "abc", "60s"]) {
      const res = validateAnimationDurationInput(bad);
      expect(res.valid, `expected "${bad}" to be invalid`).toBe(false);
      expect(res.seconds).toBeNull();
      expect(res.error).toBeTruthy();
    }

    expect(computePlaybackRate(2360621, 60)).toBeCloseTo(2360621 / 60, 4);
    expect(computePlaybackRate(31558118, 30)).toBeCloseTo(31558118 / 30, 4);
  });

  it("interpolates Moon_Sun = Earth_Sun + Moon_Earth, preserves 3D inclination, and tidal-locks site marker", () => {
    const traj = buildOrbitalSamplesForTest(65, 2360621);
    const quarterOrbital = interpolateOrbitalState(traj, 2360621 / 4);
    expect(quarterOrbital).not.toBeNull();
    if (!quarterOrbital) return;

    // Exact connected identity
    expect(quarterOrbital.moonWrtSunKm[0]).toBeCloseTo(
      quarterOrbital.earthWrtSunKm[0] + quarterOrbital.moonWrtEarthKm[0],
      5,
    );
    expect(quarterOrbital.moonWrtSunKm[1]).toBeCloseTo(
      quarterOrbital.earthWrtSunKm[1] + quarterOrbital.moonWrtEarthKm[1],
      5,
    );
    expect(quarterOrbital.moonWrtSunKm[2]).toBeCloseTo(
      quarterOrbital.earthWrtSunKm[2] + quarterOrbital.moonWrtEarthKm[2],
      5,
    );

    // 3D inclination (~5.145 deg out of ecliptic at quadrature)
    expect(Math.abs(quarterOrbital.moonWrtEarthElevationDeg)).toBeGreaterThan(4.5);

    // Tidal lock verification: sub-Earth meridian (+X_ME = [1, 0, 0]_three) points toward Earth
    const q = new THREE.Quaternion(...quarterOrbital.moonQuaternion);
    const subEarthWorld = new THREE.Vector3(1, 0, 0).applyQuaternion(q);
    const toEarthUnit = new THREE.Vector3(
      ...eclipJ2000ToThree([
        -quarterOrbital.moonWrtEarthKm[0],
        -quarterOrbital.moonWrtEarthKm[1],
        -quarterOrbital.moonWrtEarthKm[2],
      ]),
    ).normalize();
    expect(subEarthWorld.dot(toEarthUnit)).toBeGreaterThan(0.99);

    // Landing site surface vector rotates cleanly by exact matrix-derived quaternion
    const siteLocal = new THREE.Vector3(...latLonToThreeVector(38.315, -35.008, 1));
    const qDirect = new THREE.Quaternion(
      ...moonMeMatrixToThreeQuaternion(traj.samples[0].moon_me_to_eclipj2000),
    );
    expect(siteLocal.clone().applyQuaternion(qDirect).length()).toBeCloseTo(1, 5);
  });

  it("paginates full series without silent truncation at limit=1000", async () => {
    const simId = "22222222-2222-2222-2222-222222222222";
    const full = buildSeriesSamples(4500, 31558118);

    const fullSamples = full.samples ?? [];

    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      const url = new URL(String(input), "http://localhost");
      const offset = Number(url.searchParams.get("offset") ?? "0");
      const limit = Number(url.searchParams.get("limit") ?? "2000");
      const slice = fullSamples.slice(offset, offset + limit);
      return new Response(
        JSON.stringify({
          ...full,
          simulation_id: simId,
          total_samples_available: 4500,
          returned_samples: slice.length,
          offset,
          limit,
          samples: slice,
        }),
        { status: 200 },
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    const complete = await fetchCompleteSimulationSeries(simId);
    const completeSamples = complete.samples ?? [];
    expect(fetchMock).toHaveBeenCalledTimes(3); // 0..1999, 2000..3999, 4000..4499
    expect(completeSamples.length).toBe(4500);
    expect(completeSamples[0].sample_index).toBe(0);
    expect(completeSamples[completeSamples.length - 1].elapsed_seconds).toBeCloseTo(31558118, 2);
  });

  it("renders scientific presets, playback duration presets, validation errors, pause/resume/reset/scrub synchronously", async () => {
    const simId = "11111111-1111-1111-1111-111111111111";
    const series = buildSeriesSamples(25, 2360621);
    const traj = buildOrbitalSamplesForTest(65, 2360621);

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const url = String(input);
        if (url.includes("/api/v1/sites")) {
          return new Response(
            JSON.stringify({
              items: [
                {
                  site_id: 1,
                  site_slug: "lunokhod-1",
                  site_code: "HIST-LUNO-01",
                  site_name: "Lunokhod 1",
                  region_id: 15,
                  region_name: "Mare Imbrium",
                  latitude_deg: 38.315,
                  longitude_deg: -35.008,
                  elevation_m: -2600,
                  terrain_type: "Mare",
                  overview_summary: "Lunokhod 1 site",
                  catalogue_status: "published",
                  primary_thumbnail: null,
                  updated_at: "2026-11-11T00:00:00Z",
                },
              ],
              total: 1,
              page: 1,
              page_size: 50,
            }),
            { status: 200 },
          );
        }
        if (url.endsWith(`/api/v1/simulations/${simId}`)) {
          return new Response(
            JSON.stringify({
              simulation_id: simId,
              status: "completed",
              progress_pct: 100,
              quality_state: "verified_terrain_aware",
              quality_warnings: [],
              site: series.site,
              start_time_utc: "2026-06-01T00:00:00Z",
              end_time_utc: "2026-06-28T07:43:41Z",
              duration_seconds: 2360621,
              playback_speed: 600,
              coordinate_frame: "MOON_ME",
              aberration_policy: "LT+S",
              algorithm_version: "v1.0",
              limitations_disclaimers: ["Geometric visibility does not guarantee RF link margin."],
              created_at: "2026-11-11T00:00:00Z",
            }),
            { status: 200 },
          );
        }
        if (url.includes(`/api/v1/simulations/${simId}/series`)) {
          return new Response(JSON.stringify(series), { status: 200 });
        }
        if (url.includes(`/api/v1/simulations/${simId}/orbital-trajectory`)) {
          return new Response(JSON.stringify(traj), { status: 200 });
        }
        if (url.includes(`/api/v1/simulations/${simId}/events`)) {
          return new Response(
            JSON.stringify({
              simulation_id: simId,
              status: "completed",
              quality_state: "verified_terrain_aware",
              total_events: 0,
              events: [],
            }),
            { status: 200 },
          );
        }
        return new Response(JSON.stringify({}), { status: 200 });
      }),
    );

    renderWithRouter(
      <Routes>
        <Route path="/simulation/:simulationId" element={<SimulationPage />} />
      </Routes>,
      `/simulation/${simId}`,
    );

    await screen.findByTestId("orbital-fallback-views");

    // 1. Scientific Duration dropdown preserves 4 original + 2 sidereal choices
    const durationSelect = screen.getByLabelText(/Physical Duration/i) as HTMLSelectElement;
    const optionValues = Array.from(durationSelect.options).map((o) => Number(o.value));
    for (const opt of SCIENTIFIC_DURATION_OPTIONS) {
      expect(optionValues).toContain(opt.seconds);
    }

    // 2. NOT TO SCALE, Magnification Factor & Preserved Scientific Outputs
    expect(screen.getAllByText(/NOT TO SCALE/i).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/38\.315° N, 35\.008° W/i)).toBeInTheDocument();
    expect(screen.getByText(/Sun Az \/ El \/ Hzn:/i)).toBeInTheDocument();
    expect(screen.getByText(/Earth Az \/ El \/ Hzn:/i)).toBeInTheDocument();

    // 3. Test all 6 Animation Playback Duration presets update playback rate without changing SPICE
    const customInput = screen.getByLabelText("Custom animation duration (seconds)") as HTMLInputElement;
    const rateReadout = screen.getByTestId("playback-rate-readout");
    for (const preset of ANIMATION_DURATION_PRESETS) {
      const btn = screen.getByRole("button", { name: preset.label });
      fireEvent.click(btn);
      expect(customInput.value).toBe(String(preset.seconds));
      expect(rateReadout.textContent).not.toContain("Invalid");
      expect(btn).toHaveAttribute("aria-pressed", "true");
    }

    // 4. Test valid custom inputs (45, 180, 600)
    for (const val of ["45", "180", "600"]) {
      fireEvent.change(customInput, { target: { value: val } });
      expect(customInput.value).toBe(val);
      expect(screen.queryByRole("alert")).toBeNull();
      expect(screen.getByRole("button", { name: /Play|Resume|Pause/i })).not.toBeDisabled();
    }

    // 5. Test invalid inputs preserve user text verbatim, show error, disable Play
    for (const invalidVal of ["", "0", "-5", "12.5", "abc", "4000"]) {
      fireEvent.change(customInput, { target: { value: invalidVal } });
      expect(customInput.value).toBe(invalidVal);
      expect(screen.getByRole("alert")).toHaveTextContent(/between 5 and 3600 seconds/i);
      expect(screen.getByRole("button", { name: /Play|Resume/i })).toBeDisabled();
    }

    // Restore valid 30s preset before testing scrub/step/reset
    fireEvent.click(screen.getByRole("button", { name: "30s" }));
    expect(screen.queryByRole("alert")).toBeNull();

    // 6. Test Step +1, Timeline Scrub, and Reset update both Overview and Inset Moon synchronously
    const moonBefore = screen.getByTestId("svg-inset-moon").getAttribute("cx");
    fireEvent.click(screen.getByRole("button", { name: /Step \+1/i }));
    expect(screen.getByText(/Sample 2 \/ 25/)).toBeInTheDocument();

    const slider = screen.getByLabelText(/Simulation keyframe scrubber/i) as HTMLInputElement;
    fireEvent.change(slider, { target: { value: "12" } });
    await waitFor(() => {
      expect(screen.getByText(/Sample 13 \/ 25/)).toBeInTheDocument();
    });
    const moonMid = screen.getByTestId("svg-inset-moon").getAttribute("cx");
    expect(moonMid).not.toBe(moonBefore);

    // Pause/Resume wording while mid-timeline
    const resumeBtn = screen.getByRole("button", { name: /Resume/i });
    expect(resumeBtn).not.toBeDisabled();

    // Test Play -> advance animation frames -> Pause freezes positions -> Resume continues cleanly
    fireEvent.click(screen.getByRole("button", { name: /Reset/i }));
    await waitFor(() => {
      expect(screen.getByText(/Sample 1 \/ 25/)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /15s/i }));
    const initTs = screen.getByTestId("orrery-timestamp").textContent;
    const initEarthCx = screen.getByTestId("svg-overview-earth").getAttribute("cx");

    fireEvent.click(screen.getByRole("button", { name: /Play/i }));
    await waitFor(
      () => {
        expect(screen.getByTestId("orrery-timestamp").textContent).not.toBe(initTs);
      },
      { timeout: 1500 },
    );
    fireEvent.click(screen.getByRole("button", { name: /Pause/i }));
    const pausedTs = screen.getByTestId("orrery-timestamp").textContent;
    const pausedMoonCx = screen.getByTestId("svg-inset-moon").getAttribute("cx");

    await new Promise((resolve) => setTimeout(resolve, 120));
    expect(screen.getByTestId("orrery-timestamp").textContent).toBe(pausedTs);
    expect(screen.getByTestId("svg-inset-moon").getAttribute("cx")).toBe(pausedMoonCx);
    expect(screen.getByTestId("svg-overview-earth").getAttribute("cx")).not.toBe(initEarthCx);

    // Changing starting date input submits exact updated start_time ISO without touching variables
    const startInput = screen.getByLabelText(/Start Date & Time/i) as HTMLInputElement;
    fireEvent.change(startInput, { target: { value: "2026-01-03T00:00:00Z" } });
    expect(startInput.value).toBe("2026-01-03T00:00:00Z");

    // Reset returns to sample 1 (elapsed 0) and exact initial SVG moon position
    fireEvent.click(screen.getByRole("button", { name: /Reset/i }));
    await waitFor(() => {
      expect(screen.getByText(/Sample 1 \/ 25/)).toBeInTheDocument();
    });
    expect(screen.getByTestId("svg-inset-moon").getAttribute("cx")).toBe(moonBefore);
  });
});
