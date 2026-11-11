import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  cancelSimulation,
  createSimulation,
  fetchSimulationEvents,
  fetchSimulationSeries,
  fetchSimulationStatus,
  fetchSites,
  type HorizonCurveOut,
  type SimulationSampleOut,
} from "../api/endpoints";
import { queryKeys } from "../api/queryKeys";
import { PauseIcon, PlayIcon } from "../components/Icons";
import { SiteHeader } from "../components/SiteHeader";
import { UtilitiesFooter } from "../components/UtilitiesFooter";
import { HeadTags } from "../seo/HeadTags";
import { SimulationOrreryCanvas } from "../three/SimulationOrreryCanvas";
import {
  formatDurationSeconds,
  formatLatLon,
  formatNumber,
  formatUtcTimestamp,
} from "../utils/formatting";

function HorizonSvgChart({
  horizon,
  sample,
}: {
  horizon?: HorizonCurveOut | null;
  sample?: SimulationSampleOut;
}) {
  const width = 560;
  const height = 160;
  const padL = 38;
  const padR = 14;
  const padT = 14;
  const padB = 26;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;

  const toX = (az: number) => padL + ((az % 360) / 360) * plotW;
  const toY = (el: number) => {
    const clamped = Math.max(-20, Math.min(90, el));
    return padT + ((90 - clamped) / 110) * plotH;
  };

  const horizonPath = useMemo(() => {
    if (!horizon || horizon.azimuths_deg.length === 0) {
      return "";
    }
    return horizon.azimuths_deg
      .map((az, idx) => {
        const el = horizon.horizon_elevations_deg[idx] ?? 0;
        return `${idx === 0 ? "M" : "L"}${toX(az).toFixed(1)},${toY(el).toFixed(1)}`;
      })
      .join(" ");
  }, [horizon]);

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      style={{ width: "100%", height: "auto", display: "block" }}
      role="img"
      aria-label="Topocentric Azimuth versus Elevation and Terrain Horizon profile"
    >
      <rect
        x={padL}
        y={padT}
        width={plotW}
        height={plotH}
        fill="rgba(5, 7, 11, 0.72)"
        stroke="rgba(255, 255, 255, 0.14)"
      />
      {/* 0-deg Geometric Horizon */}
      <line
        x1={padL}
        y1={toY(0)}
        x2={padL + plotW}
        y2={toY(0)}
        stroke="rgba(255, 255, 255, 0.25)"
        strokeDasharray="4 4"
      />
      <text x={4} y={toY(0) + 4} fill="#7c899e" fontSize="10">
        0°
      </text>
      <text x={4} y={toY(60) + 4} fill="#7c899e" fontSize="10">
        60°
      </text>

      {/* DEM Horizon Profile */}
      {horizonPath && (
        <path
          d={horizonPath}
          fill="none"
          stroke="#f5b83d"
          strokeWidth="1.8"
          opacity={0.85}
        />
      )}

      {/* Current Sun Position */}
      {sample && (
        <>
          <circle
            cx={toX(sample.sun.azimuth_deg)}
            cy={toY(sample.sun.elevation_deg)}
            r={5.5}
            fill="#f5b83d"
          />
          <circle
            cx={toX(sample.earth.azimuth_deg)}
            cy={toY(sample.earth.elevation_deg)}
            r={5}
            fill="#5ad2e6"
          />
        </>
      )}

      <text x={padL} y={height - 6} fill="#7c899e" fontSize="10">
        0° N
      </text>
      <text x={toX(90) - 8} y={height - 6} fill="#7c899e" fontSize="10">
        90° E
      </text>
      <text x={toX(180) - 10} y={height - 6} fill="#7c899e" fontSize="10">
        180° S
      </text>
      <text x={toX(270) - 10} y={height - 6} fill="#7c899e" fontSize="10">
        270° W
      </text>
    </svg>
  );
}

export function SimulationPage() {
  const { simulationId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const initialSiteId = Number(searchParams.get("siteId") ?? 0) || 0;

  const sitesQuery = useQuery({
    queryKey: queryKeys.sites({ status: "published", page_size: 50 }),
    queryFn: () => fetchSites({ status: "published", page_size: 50 }),
    staleTime: 60_000,
  });

  const sites = sitesQuery.data?.items ?? [];

  const [selectedSiteId, setSelectedSiteId] = useState<number>(initialSiteId);
  const [startIso, setStartIso] = useState("2026-06-01T00:00:00Z");
  const [durationSeconds, setDurationSeconds] = useState(259200); // 3 days default (fast compute + clear solar arc)
  const [playbackSpeed, setPlaybackSpeed] = useState(600);

  const [sampleIndex, setSampleIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [visualRate, setVisualRate] = useState(4); // samples per second playback in UI

  useEffect(() => {
    if (sites.length > 0 && selectedSiteId === 0) {
      setSelectedSiteId(sites[0].site_id);
    }
  }, [sites, selectedSiteId]);

  const statusQuery = useQuery({
    queryKey: queryKeys.simulationStatus(simulationId ?? ""),
    queryFn: () => fetchSimulationStatus(simulationId ?? ""),
    enabled: Boolean(simulationId),
    refetchInterval: (query) => {
      const st = query.state.data?.status;
      return st === "queued" || st === "running" ? 1200 : false;
    },
    retry: false,
  });

  const simStatus = statusQuery.data;
  const isReadyForSeries =
    simStatus?.status === "completed" ||
    simStatus?.status === "succeeded";

  const seriesQuery = useQuery({
    queryKey: queryKeys.simulationSeries(simulationId ?? ""),
    queryFn: () =>
      fetchSimulationSeries(simulationId ?? "", {
        offset: 0,
        limit: 1000,
        downsample: 1,
        include_horizon: true,
      }),
    enabled: Boolean(simulationId && isReadyForSeries),
  });

  const eventsQuery = useQuery({
    queryKey: queryKeys.simulationEvents(simulationId ?? ""),
    queryFn: () => fetchSimulationEvents(simulationId ?? ""),
    enabled: Boolean(simulationId && isReadyForSeries),
  });

  const samples = seriesQuery.data?.samples ?? [];
  const activeSample =
    samples.length > 0
      ? samples[Math.min(sampleIndex, samples.length - 1)]
      : undefined;

  useEffect(() => {
    setSampleIndex(0);
    setPlaying(false);
  }, [simulationId]);

  useEffect(() => {
    if (!playing || samples.length <= 1) {
      return;
    }
    const timer = window.setInterval(() => {
      setSampleIndex((prev) => {
        if (prev + 1 >= samples.length) {
          setPlaying(false);
          return prev;
        }
        return prev + 1;
      });
    }, Math.max(40, Math.round(1000 / visualRate)));
    return () => window.clearInterval(timer);
  }, [playing, samples.length, visualRate]);

  const createMutation = useMutation({
    mutationFn: (payload: Parameters<typeof createSimulation>[0]) =>
      createSimulation(payload),
    onSuccess: (created) => {
      navigate(`/simulation/${created.simulation_id}`);
    },
  });

  const cancelMutation = useMutation({
    mutationFn: () => cancelSimulation(simulationId ?? ""),
    onSuccess: () => {
      void statusQuery.refetch();
    },
  });

  function handleRunSimulation(event: FormEvent) {
    event.preventDefault();
    if (!selectedSiteId) {
      return;
    }
    createMutation.mutate({
      site_id: selectedSiteId,
      start_time: startIso,
      duration_seconds: durationSeconds,
      playback_speed: playbackSpeed,
    });
  }

  const effectiveQuality = seriesQuery.data?.quality_state ?? simStatus?.quality_state;
  const isGeometricOnly =
    effectiveQuality === "geometric_only" ||
    effectiveQuality === "degraded";

  return (
    <div className="page-shell">
      <HeadTags
        meta={{
          title: simStatus
            ? `Simulation — ${simStatus.site.site_name} — CLPS Luna Browser`
            : "Topocentric Lunar Simulation — CLPS Luna Browser",
          description:
            "Time-dependent SPICE + LOLA DEM Sun and Earth visibility simulation workspace for lunar landing sites.",
          canonicalPath: simulationId ? `/simulation/${simulationId}` : "/simulation",
          robots: "noindex,nofollow",
          ogType: "website",
          breadcrumbs: [
            { name: "Home", path: "/" },
            { name: "Browser", path: "/browser" },
            { name: "Simulation", path: simulationId ? `/simulation/${simulationId}` : "/simulation" },
          ],
        }}
      />

      <SiteHeader
        subtitle={simStatus ? `Simulation — ${simStatus.site.site_name}` : "SPICE + LOLA Simulation"}
        rightActions={
          <Link to="/browser" className="btn">
            &lt;- Browser
          </Link>
        }
      />

      <main id="main-content" className="page-content-layer container">
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "0.75rem",
            marginBottom: "1rem",
          }}
        >
          <div>
            <h1 style={{ margin: 0, fontSize: "1.6rem" }}>
              {simStatus
                ? `Simulation — ${simStatus.site.site_name}`
                : "Topocentric Lunar Ephemeris Simulation"}
            </h1>
            {simStatus && (
              <div className="mono" style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: "0.2rem" }}>
                {formatLatLon(simStatus.site.latitude_deg, simStatus.site.longitude_deg)} · Frame{" "}
                {simStatus.resolved_frame || simStatus.coordinate_frame} · Status{" "}
                <strong>{simStatus.status}</strong> ({simStatus.progress_pct}%)
              </div>
            )}
          </div>

          {simulationId && simStatus && (
            <div style={{ display: "flex", gap: "0.55rem", flexWrap: "wrap" }}>
              {(simStatus.status === "queued" || simStatus.status === "running") && (
                <button
                  type="button"
                  className="btn"
                  onClick={() => cancelMutation.mutate()}
                  disabled={cancelMutation.isPending}
                >
                  Cancel Simulation
                </button>
              )}
              {isReadyForSeries && (
                <Link
                  to={`/codex?simulationId=${encodeURIComponent(simulationId)}&siteId=${simStatus.site.site_id}`}
                  className="btn btn-primary"
                >
                  Prepare CODEX Dry-Run -&gt;
                </Link>
              )}
            </div>
          )}
        </div>

        <div className="simulation-grid">
          {/* Left Panel: Parameters & Provenance */}
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <form onSubmit={handleRunSimulation} className="glass-panel" style={{ padding: "1.05rem" }}>
              <h2 style={{ margin: "0 0 0.75rem", fontSize: "1.05rem" }}>
                Simulation Parameters
              </h2>

              <div style={{ display: "flex", flexDirection: "column", gap: "0.7rem" }}>
                <div>
                  <label htmlFor="sim-site-select" className="field-label">
                    Landing Site
                  </label>
                  <select
                    id="sim-site-select"
                    className="select"
                    value={selectedSiteId}
                    onChange={(event) => setSelectedSiteId(Number(event.target.value))}
                  >
                    {sites.map((s) => (
                      <option key={s.site_id} value={s.site_id}>
                        {s.site_name} ({s.site_code})
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label htmlFor="sim-start-utc" className="field-label">
                    Start Date &amp; Time (ISO 8601 UTC)
                  </label>
                  <input
                    id="sim-start-utc"
                    type="text"
                    className="input mono"
                    value={startIso}
                    onChange={(event) => setStartIso(event.target.value)}
                    required
                  />
                </div>

                <div>
                  <label htmlFor="sim-duration" className="field-label">
                    Physical Duration
                  </label>
                  <select
                    id="sim-duration"
                    className="select"
                    value={durationSeconds}
                    onChange={(event) => setDurationSeconds(Number(event.target.value))}
                  >
                    <option value={86400}>24 Hours (86,400 s)</option>
                    <option value={259200}>3 Days (259,200 s)</option>
                    <option value={604800}>7 Days (604,800 s)</option>
                    <option value={2592000}>30 Days (2,592,000 s)</option>
                  </select>
                </div>

                <div>
                  <label htmlFor="sim-speed" className="field-label">
                    Timeline Reference Speed Multiplier
                  </label>
                  <select
                    id="sim-speed"
                    className="select"
                    value={playbackSpeed}
                    onChange={(event) => setPlaybackSpeed(Number(event.target.value))}
                  >
                    <option value={1}>1x</option>
                    <option value={60}>60x</option>
                    <option value={600}>600x</option>
                    <option value={3600}>3600x</option>
                  </select>
                </div>

                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={createMutation.isPending || selectedSiteId === 0}
                >
                  {createMutation.isPending ? "Queueing Job..." : "Run Simulation ->"}
                </button>
              </div>

              {createMutation.isError && (
                <div className="notice-banner error" role="alert" style={{ marginTop: "0.75rem" }}>
                  <span>{createMutation.error.message}</span>
                </div>
              )}
            </form>

            {simStatus && (
              <div className="glass-panel" style={{ padding: "1.05rem" }}>
                <h2 style={{ margin: "0 0 0.6rem", fontSize: "1.02rem" }}>
                  Simulation Output &amp; Provenance
                </h2>

                {isGeometricOnly && (
                  <div className="notice-banner warn" style={{ marginBottom: "0.75rem" }}>
                    <div>
                      <strong style={{ display: "block" }}>
                        GEOMETRIC ONLY ({effectiveQuality})
                      </strong>
                      <span style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                        Terrain-aware LOLA DEM horizon obstruction is NOT verified for this
                        simulation. Visibility status reflects astronomical elevation only.
                      </span>
                    </div>
                  </div>
                )}

                {simStatus.error_summary && (
                  <div className="notice-banner error" role="alert" style={{ marginBottom: "0.75rem" }}>
                    <span>{simStatus.error_summary}</span>
                  </div>
                )}

                {activeSample ? (
                  <div
                    className="mono"
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: "0.4rem",
                      fontSize: "0.8rem",
                    }}
                  >
                    <div>
                      <span className="eyebrow">Timestamp:</span>{" "}
                      {formatUtcTimestamp(activeSample.timestamp_utc)}
                    </div>
                    <div>
                      <span className="eyebrow">Sun Az / El / Hzn:</span>{" "}
                      {formatNumber(activeSample.sun.azimuth_deg, 1)}° /{" "}
                      {formatNumber(activeSample.sun.elevation_deg, 1)}° /{" "}
                      {formatNumber(activeSample.sun.horizon_deg, 1)}° (
                      {activeSample.sun.visibility_status})
                    </div>
                    <div>
                      <span className="eyebrow">Earth Az / El / Hzn:</span>{" "}
                      {formatNumber(activeSample.earth.azimuth_deg, 1)}° /{" "}
                      {formatNumber(activeSample.earth.elevation_deg, 1)}° /{" "}
                      {formatNumber(activeSample.earth.horizon_deg, 1)}° (
                      {activeSample.earth.visibility_status})
                    </div>
                    <div>
                      <span className="eyebrow">Earth Range:</span>{" "}
                      {formatNumber(activeSample.earth.range_km, 0)} km
                    </div>
                    <div>
                      <span className="eyebrow">Sun + Earth Concurrent:</span>{" "}
                      {activeSample.concurrent_visible ? "Visible" : "Not concurrent"}
                    </div>
                  </div>
                ) : (
                  <p style={{ margin: 0, fontSize: "0.84rem", color: "var(--text-secondary)" }}>
                    {simStatus.progress_message || `Status: ${simStatus.status}`}
                  </p>
                )}

                {simStatus.limitations_disclaimers &&
                  simStatus.limitations_disclaimers.length > 0 && (
                    <ul
                      style={{
                        margin: "0.75rem 0 0",
                        paddingLeft: "1.1rem",
                        fontSize: "0.76rem",
                        color: "var(--text-muted)",
                      }}
                    >
                      {simStatus.limitations_disclaimers.map((d) => (
                        <li key={d}>{d}</li>
                      ))}
                    </ul>
                  )}
              </div>
            )}
          </div>

          {/* Right Panel: 3D Orrery, Playback Scrubber, Horizon SVG & Events */}
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            {!simulationId && (
              <div className="glass-panel" style={{ padding: "1.5rem" }}>
                <h2 style={{ margin: "0 0 0.45rem", fontSize: "1.15rem" }}>
                  Configure and Launch a Simulation
                </h2>
                <p style={{ margin: 0, color: "var(--text-secondary)" }}>
                  Select a landing site, start UTC timestamp, and physical duration on the left to
                  queue a SPICE ephemeris &amp; terrain horizon computation via the background
                  worker.
                </p>
              </div>
            )}

            {simulationId && statusQuery.isError && (
              <div className="glass-panel notice-banner error" role="alert">
                <span>Failed to load simulation `{simulationId}`.</span>
              </div>
            )}

            {simulationId && simStatus && !isReadyForSeries && (
              <div className="glass-panel" style={{ padding: "1.35rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.5rem" }}>
                  <strong>Simulation Status: {simStatus.status.toUpperCase()}</strong>
                  <span className="mono">{simStatus.progress_pct}%</span>
                </div>
                <div
                  style={{
                    height: "8px",
                    borderRadius: "999px",
                    background: "rgba(255,255,255,0.08)",
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      width: `${simStatus.progress_pct}%`,
                      height: "100%",
                      background: "var(--accent-cyan)",
                    }}
                  />
                </div>
                <p style={{ margin: "0.6rem 0 0", fontSize: "0.84rem", color: "var(--text-secondary)" }}>
                  {simStatus.progress_message ||
                    "Waiting for background simulation worker... Ensure `simulation_worker` is running."}
                </p>
              </div>
            )}

            {seriesQuery.data && samples.length > 0 && (
              <>
                <SimulationOrreryCanvas
                  series={seriesQuery.data}
                  sampleIndex={sampleIndex}
                  interpolationAlpha={0}
                />

                {/* Timeline Playback Scrubber */}
                <div className="glass-panel" style={{ padding: "0.95rem 1.1rem" }}>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      flexWrap: "wrap",
                      gap: "0.65rem",
                      marginBottom: "0.65rem",
                    }}
                  >
                    <div style={{ display: "flex", gap: "0.45rem", flexWrap: "wrap" }}>
                      <button
                        type="button"
                        className="btn btn-primary"
                        onClick={() => setPlaying((p) => !p)}
                      >
                        {playing ? <PauseIcon /> : <PlayIcon />}
                        <span>{playing ? "Pause" : "Play"}</span>
                      </button>
                      <button
                        type="button"
                        className="btn"
                        onClick={() => {
                          setPlaying(false);
                          setSampleIndex((i) => Math.max(0, i - 1));
                        }}
                      >
                        Step -1
                      </button>
                      <button
                        type="button"
                        className="btn"
                        onClick={() => {
                          setPlaying(false);
                          setSampleIndex((i) => Math.min(samples.length - 1, i + 1));
                        }}
                      >
                        Step +1
                      </button>
                    </div>

                    <div style={{ display: "flex", gap: "0.35rem", alignItems: "center" }}>
                      <span className="eyebrow">UI Rate:</span>
                      {[2, 4, 12].map((rate) => (
                        <button
                          key={rate}
                          type="button"
                          className={`btn ${visualRate === rate ? "btn-cyan" : ""}`}
                          style={{ padding: "0.28rem 0.6rem", fontSize: "0.76rem" }}
                          onClick={() => setVisualRate(rate)}
                        >
                          {rate} steps/s
                        </button>
                      ))}
                    </div>
                  </div>

                  <label htmlFor="simulation-timeline-slider" className="sr-only">
                    Simulation keyframe scrubber
                  </label>
                  <input
                    id="simulation-timeline-slider"
                    type="range"
                    min={0}
                    max={Math.max(0, samples.length - 1)}
                    value={sampleIndex}
                    onChange={(event) => {
                      setPlaying(false);
                      setSampleIndex(Number(event.target.value));
                    }}
                    style={{ width: "100%" }}
                  />
                  <div
                    className="mono"
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      fontSize: "0.74rem",
                      color: "var(--text-muted)",
                      marginTop: "0.35rem",
                    }}
                  >
                    <span>
                      Sample {sampleIndex + 1} / {samples.length}
                    </span>
                    <span>
                      Elapsed: {formatDurationSeconds(activeSample?.elapsed_seconds)}
                    </span>
                  </div>
                </div>

                {/* Azimuth-Elevation & DEM Horizon Chart */}
                <div className="glass-panel" style={{ padding: "1rem 1.1rem" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.5rem", flexWrap: "wrap", gap: "0.5rem" }}>
                    <h2 style={{ margin: 0, fontSize: "1.02rem" }}>
                      Azimuth vs Elevation &amp; Horizon Profile
                    </h2>
                    <div style={{ display: "flex", gap: "0.6rem", fontSize: "0.76rem" }}>
                      <span className="pill-badge amber">Sun / Horizon</span>
                      <span className="pill-badge cyan">Earth</span>
                    </div>
                  </div>
                  <HorizonSvgChart
                    horizon={seriesQuery.data.horizon_profile}
                    sample={activeSample}
                  />
                </div>

                {/* Rise/Set & Visibility Events Table */}
                {eventsQuery.data && (
                  <div className="glass-panel" style={{ padding: "1rem 1.1rem" }}>
                    <h2 style={{ margin: "0 0 0.65rem", fontSize: "1.02rem" }}>
                      Visibility Windows &amp; Rise/Set Events ({eventsQuery.data.total_events})
                    </h2>
                    {(eventsQuery.data.events ?? []).length === 0 ? (
                      <p style={{ margin: 0, fontSize: "0.84rem", color: "var(--text-secondary)" }}>
                        No horizon crossing transitions occurred within this simulation span.
                      </p>
                    ) : (
                      <div className="data-table-wrap">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Event / Window</th>
                              <th>Start UTC</th>
                              <th>End UTC</th>
                              <th>Duration</th>
                              <th>Confidence</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(eventsQuery.data.events ?? []).map((ev) => (
                              <tr key={ev.event_id}>
                                <td className="mono">{ev.event_type}</td>
                                <td className="mono">{formatUtcTimestamp(ev.window_start_utc)}</td>
                                <td className="mono">{formatUtcTimestamp(ev.window_end_utc)}</td>
                                <td className="mono">{formatDurationSeconds(ev.duration_seconds)}</td>
                                <td>
                                  <span
                                    className={`pill-badge ${
                                      ev.confidence_status === "verified" ? "ok" : "amber"
                                    }`}
                                  >
                                    {ev.confidence_status}
                                  </span>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </main>

      <UtilitiesFooter />
    </div>
  );
}
