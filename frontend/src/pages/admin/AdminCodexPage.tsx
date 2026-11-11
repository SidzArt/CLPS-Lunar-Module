import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { AdminLayout } from "../../admin/AdminLayout";
import {
  adminQueryKeys,
  createCalibration,
  fetchAdminCalibrations,
  fetchAdminCodexDevices,
  fetchAdminHardwareConfigurations,
  fetchAdminHardwareRuns,
  fetchAdminLedMapping,
  postDeviceHeartbeat,
  updateCalibration,
  upsertHardwareConfiguration,
  upsertLedRegion,
} from "../../api/adminEndpoints";
import { queryKeys } from "../../api/queryKeys";

type CodexTab = "devices" | "calibrations" | "led-mapping" | "runs";

function resolveInitialTab(pathname: string): CodexTab {
  if (pathname.includes("/calibration")) return "calibrations";
  if (pathname.includes("/led-mapping")) return "led-mapping";
  return "devices";
}

function CodexWorkbench() {
  const location = useLocation();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<CodexTab>(() => resolveInitialTab(location.pathname));
  const [notice, setNotice] = useState<{ kind: "cyan" | "warn" | "error"; text: string } | null>(
    null,
  );

  useEffect(() => {
    setTab(resolveInitialTab(location.pathname));
  }, [location.pathname]);

  const devicesQuery = useQuery({
    queryKey: adminQueryKeys.codexDevices,
    queryFn: () => fetchAdminCodexDevices(),
  });
  const configsQuery = useQuery({
    queryKey: adminQueryKeys.configs(),
    queryFn: () => fetchAdminHardwareConfigurations(),
  });
  const calibrationsQuery = useQuery({
    queryKey: adminQueryKeys.calibrations(),
    queryFn: () => fetchAdminCalibrations(),
  });
  const ledQuery = useQuery({
    queryKey: adminQueryKeys.ledMapping,
    queryFn: () => fetchAdminLedMapping(),
  });
  const runsQuery = useQuery({
    queryKey: adminQueryKeys.runs(),
    queryFn: () => fetchAdminHardwareRuns(),
  });

  // Configuration form
  const [cfgController, setCfgController] = useState("motion_uno");
  const [cfgBoard, setCfgBoard] = useState("");
  const [cfgTarget, setCfgTarget] = useState("");
  const [cfgMotor, setCfgMotor] = useState("");
  const [cfgDriver, setCfgDriver] = useState("");
  const [cfgSteps, setCfgSteps] = useState("");
  const [cfgMicro, setCfgMicro] = useState("");
  const [cfgCurrent, setCfgCurrent] = useState("");
  const [cfgLeds, setCfgLeds] = useState("");

  // Calibration form (NO fabricated bench constants!)
  const [calMotorKey, setCalMotorKey] = useState<"nema17" | "byj">("nema17");
  const [calMotorName, setCalMotorName] = useState("");
  const [calVersion, setCalVersion] = useState("");
  const [calRatio, setCalRatio] = useState("");
  const [calStepsRev, setCalStepsRev] = useState("");
  const [calMicrosteps, setCalMicrosteps] = useState("");
  const [calDirection, setCalDirection] = useState<1 | -1>(1);
  const [calMaxRate, setCalMaxRate] = useState("");
  const [calAccel, setCalAccel] = useState("");
  const [calBacklash, setCalBacklash] = useState("0");
  const [calZero, setCalZero] = useState("0");
  const [calMinDeg, setCalMinDeg] = useState("");
  const [calMaxDeg, setCalMaxDeg] = useState("");
  const [calMeasuredBy, setCalMeasuredBy] = useState("");
  const [calNotes, setCalNotes] = useState("");

  // LED Region form
  const [ledIndex, setLedIndex] = useState("1");
  const [ledName, setLedName] = useState("");
  const [ledLat, setLedLat] = useState("");
  const [ledLon, setLedLon] = useState("");
  const [ledPixels, setLedPixels] = useState("");
  const [ledChannel, setLedChannel] = useState("0");
  const [ledTopology, setLedTopology] = useState<
    "addressable_strip" | "discrete_gpio" | "matrix" | "unverified"
  >("addressable_strip");
  const [ledStatus, setLedStatus] = useState<
    "unverified" | "centroid_approximate" | "bench_verified" | "deprecated"
  >("unverified");
  const [ledVersion, setLedVersion] = useState("v1.0");

  const probeMutation = useMutation({
    mutationFn: (controllerKey: string) =>
      postDeviceHeartbeat(controllerKey, {
        probe_via_transport: true,
        reset_estop_latch: false,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminQueryKeys.codexDevices });
      queryClient.invalidateQueries({ queryKey: queryKeys.codexStatus() });
      setNotice({ kind: "cyan", text: "Transport probe completed cleanly." });
    },
    onError: (err) =>
      setNotice({ kind: "error", text: err instanceof Error ? err.message : "Probe failed." }),
  });

  const clearEstopMutation = useMutation({
    mutationFn: (controllerKey: string) =>
      postDeviceHeartbeat(controllerKey, {
        probe_via_transport: false,
        reset_estop_latch: true,
        estop_latched: false,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminQueryKeys.codexDevices });
      queryClient.invalidateQueries({ queryKey: queryKeys.codexStatus() });
      setNotice({ kind: "cyan", text: "Cleared E-STOP latch cleanly." });
    },
    onError: (err) =>
      setNotice({ kind: "error", text: err instanceof Error ? err.message : "Clear E-STOP failed." }),
  });

  const saveConfigMutation = useMutation({
    mutationFn: () =>
      upsertHardwareConfiguration(cfgController, {
        board_model: cfgBoard.trim(),
        firmware_target: cfgTarget.trim(),
        motor_type: cfgMotor.trim() || null,
        driver_model: cfgDriver.trim() || null,
        steps_per_revolution: cfgSteps.trim() ? Number(cfgSteps) : null,
        microstep_setting: cfgMicro.trim() ? Number(cfgMicro) : null,
        current_limit_setting: cfgCurrent.trim() ? Number(cfgCurrent) : null,
        led_count: cfgLeds.trim() ? Number(cfgLeds) : null,
      }),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: adminQueryKeys.configs() });
      queryClient.invalidateQueries({ queryKey: adminQueryKeys.codexDevices });
      queryClient.invalidateQueries({ queryKey: queryKeys.codexStatus() });
      setNotice({
        kind: "cyan",
        text: `Saved active configuration for ${res.controller_key} (${res.board_model}).`,
      });
    },
    onError: (err) =>
      setNotice({ kind: "error", text: err instanceof Error ? err.message : "Config save failed." }),
  });

  const createCalibrationMutation = useMutation({
    mutationFn: () =>
      createCalibration({
        controller_key: "motion_uno",
        motor_key: calMotorKey,
        motor_name: calMotorName.trim(),
        calibration_version: calVersion.trim(),
        gear_reduction_ratio: Number(calRatio),
        full_steps_per_rev: Number(calStepsRev),
        microsteps: Number(calMicrosteps),
        direction_sign: calDirection,
        max_step_rate: Number(calMaxRate),
        acceleration: Number(calAccel),
        backlash_steps: Number(calBacklash) || 0,
        zero_offset_deg: Number(calZero) || 0,
        travel_min_deg: calMinDeg.trim() ? Number(calMinDeg) : null,
        travel_max_deg: calMaxDeg.trim() ? Number(calMaxDeg) : null,
        measured_by: calMeasuredBy.trim() || null,
        verification_status: "unverified",
        calibration_notes: calNotes.trim() || null,
        activate: true,
      }),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: adminQueryKeys.calibrations() });
      queryClient.invalidateQueries({ queryKey: queryKeys.codexStatus() });
      setCalVersion("");
      setNotice({
        kind: "cyan",
        text: `Created unverified calibration profile ${created.calibration_version} (${created.motor_key}).`,
      });
    },
    onError: (err) =>
      setNotice({
        kind: "error",
        text: err instanceof Error ? err.message : "Calibration creation failed.",
      }),
  });

  const saveLedMutation = useMutation({
    mutationFn: () => {
      const pixelIndices = ledPixels
        .split(",")
        .map((s) => Number(s.trim()))
        .filter((n) => Number.isInteger(n) && n >= 0);
      if (pixelIndices.length === 0) {
        throw new Error("Enter at least one non-negative integer pixel index.");
      }
      return upsertLedRegion({
        region_index: Number(ledIndex),
        region_name: ledName.trim(),
        centroid_lat: ledLat.trim() ? Number(ledLat) : null,
        centroid_lon: ledLon.trim() ? Number(ledLon) : null,
        pixel_indices: pixelIndices,
        mapping_version: ledVersion.trim() || "v1.0",
        orientation_reference: "MOON_ME_PRIME_MERIDIAN_CENTER",
        geometry_source: "bench_measurement",
        verification_status: ledStatus,
        output_channel: Number(ledChannel) || 0,
        topology_mode: ledTopology,
        is_active: true,
      });
    },
    onSuccess: (saved) => {
      queryClient.invalidateQueries({ queryKey: adminQueryKeys.ledMapping });
      queryClient.invalidateQueries({ queryKey: queryKeys.codexStatus() });
      setNotice({
        kind: "cyan",
        text: `Saved Moon LED region #${saved.region_index} (${saved.region_name}).`,
      });
    },
    onError: (err) =>
      setNotice({ kind: "error", text: err instanceof Error ? err.message : "LED mapping save failed." }),
  });

  const devicesData = devicesQuery.data;

  return (
    <div style={{ display: "grid", gap: "1rem" }}>
      <div className="notice-banner warn">
        <div>
          <strong>Hardware Safety Boundary:</strong> Active transport mode:{" "}
          <code>{devicesData?.transport_mode ?? "mock"}</code> · Verified bench required:{" "}
          <code>{String(devicesData?.require_verified_bench ?? true)}</code>. Physical motor bench
          calibration and LED GPIO wiring remain <code>BLOCKED — HARDWARE TEAM REQUIRED</code>.
        </div>
        <Link to="/admin/codex/firmware" className="btn btn-cyan">
          Open Firmware Editor
        </Link>
      </div>

      {notice && (
        <div className={`notice-banner ${notice.kind}`} role="status">
          <span>{notice.text}</span>
        </div>
      )}

      <section className="glass-panel-strong" style={{ padding: "1rem 1.2rem" }}>
        <div className="admin-tab-strip" role="tablist" aria-label="CODEX workbench tabs">
          {(
            [
              ["devices", "Controllers & Configs"],
              ["calibrations", "Motor Calibrations"],
              ["led-mapping", "Moon 13-Region LED Map"],
              ["runs", `Hardware Runs (${runsQuery.data?.length ?? 0})`],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={tab === key}
              className={`admin-tab-btn${tab === key ? " active" : ""}`}
              onClick={() => setTab(key)}
            >
              {label}
            </button>
          ))}
        </div>
      </section>

      {tab === "devices" && (
        <div style={{ display: "grid", gap: "1rem" }}>
          <section className="glass-panel-strong" style={{ padding: "1.15rem" }}>
            <h2 style={{ marginTop: 0, fontSize: "1.12rem" }}>Three-Controller Bus Status</h2>
            <div className="admin-table-wrap">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Controller</th>
                    <th>Role &amp; Board</th>
                    <th>Health</th>
                    <th>Verification</th>
                    <th>Firmware</th>
                    <th>E-STOP</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {(devicesData?.devices ?? []).map((dev) => (
                    <tr key={dev.device_id}>
                      <td>
                        <code>{dev.controller_key}</code>
                      </td>
                      <td>
                        <strong>{dev.device_role}</strong>
                        <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                          {dev.board_model} ({dev.transport_type})
                        </div>
                      </td>
                      <td>
                        <span className={`pill-badge ${dev.health_state === "online" ? "ok" : "warn"}`}>
                          {dev.health_state}
                        </span>
                      </td>
                      <td>{dev.verification_status}</td>
                      <td>
                        <code>{dev.reported_firmware_version ?? dev.expected_firmware_version ?? "—"}</code>
                      </td>
                      <td>
                        <span className={`pill-badge ${dev.estop_latched ? "danger" : "ok"}`}>
                          {dev.estop_latched ? "LATCHED" : "Clear"}
                        </span>
                      </td>
                      <td>
                        <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
                          <button
                            type="button"
                            className="btn btn-cyan"
                            disabled={probeMutation.isPending}
                            onClick={() => probeMutation.mutate(dev.controller_key)}
                          >
                            Probe
                          </button>
                          {dev.estop_latched && (
                            <button
                              type="button"
                              className="btn btn-amber"
                              disabled={clearEstopMutation.isPending}
                              onClick={() => clearEstopMutation.mutate(dev.controller_key)}
                            >
                              Clear E-STOP
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="glass-panel-strong" style={{ padding: "1.15rem", display: "grid", gap: "1rem" }}>
            <h2 style={{ margin: 0, fontSize: "1.12rem" }}>Controller Hardware Configurations</h2>
            <div className="admin-table-wrap">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Controller</th>
                    <th>Board Model</th>
                    <th>Firmware Target</th>
                    <th>Motor / Driver</th>
                    <th>LED Count</th>
                    <th>Active</th>
                  </tr>
                </thead>
                <tbody>
                  {(configsQuery.data ?? []).map((cfg) => (
                    <tr key={cfg.hardware_config_id}>
                      <td>
                        <code>{cfg.controller_key}</code>
                      </td>
                      <td>{cfg.board_model}</td>
                      <td>{cfg.firmware_target}</td>
                      <td>{[cfg.motor_type, cfg.driver_model].filter(Boolean).join(" / ") || "—"}</td>
                      <td>{cfg.led_count ?? "—"}</td>
                      <td>{cfg.is_active ? "Yes" : "Historical"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                saveConfigMutation.mutate();
              }}
              className="glass-panel"
              style={{ padding: "1rem", display: "grid", gap: "0.75rem" }}
            >
              <h3 style={{ margin: 0 }}>Record Verified Hardware Configuration</h3>
              <div className="admin-form-grid-3">
                <div>
                  <label className="field-label" htmlFor="cfg-ctrl">
                    Controller
                  </label>
                  <select
                    id="cfg-ctrl"
                    className="input"
                    value={cfgController}
                    onChange={(e) => setCfgController(e.target.value)}
                  >
                    <option value="wifi_bridge">wifi_bridge</option>
                    <option value="motion_uno">motion_uno</option>
                    <option value="moon_led_s3">moon_led_s3</option>
                  </select>
                </div>
                <div>
                  <label className="field-label" htmlFor="cfg-board">
                    Board Model
                  </label>
                  <input
                    id="cfg-board"
                    required
                    className="input"
                    value={cfgBoard}
                    onChange={(e) => setCfgBoard(e.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="cfg-target">
                    Firmware Target
                  </label>
                  <input
                    id="cfg-target"
                    required
                    className="input"
                    value={cfgTarget}
                    onChange={(e) => setCfgTarget(e.target.value)}
                  />
                </div>
              </div>
              <div className="admin-form-grid-3">
                <div>
                  <label className="field-label" htmlFor="cfg-motor">
                    Motor Type
                  </label>
                  <input
                    id="cfg-motor"
                    className="input"
                    value={cfgMotor}
                    onChange={(e) => setCfgMotor(e.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="cfg-drv">
                    Driver Model
                  </label>
                  <input
                    id="cfg-drv"
                    className="input"
                    value={cfgDriver}
                    onChange={(e) => setCfgDriver(e.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="cfg-cur">
                    Current Limit (A)
                  </label>
                  <input
                    id="cfg-cur"
                    type="number"
                    step="0.01"
                    className="input"
                    value={cfgCurrent}
                    onChange={(e) => setCfgCurrent(e.target.value)}
                  />
                </div>
              </div>
              <div className="admin-form-grid-3">
                <div>
                  <label className="field-label" htmlFor="cfg-steps">
                    Steps / Rev
                  </label>
                  <input
                    id="cfg-steps"
                    type="number"
                    className="input"
                    value={cfgSteps}
                    onChange={(e) => setCfgSteps(e.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="cfg-micro">
                    Microsteps
                  </label>
                  <input
                    id="cfg-micro"
                    type="number"
                    className="input"
                    value={cfgMicro}
                    onChange={(e) => setCfgMicro(e.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="cfg-leds">
                    LED Count
                  </label>
                  <input
                    id="cfg-leds"
                    type="number"
                    className="input"
                    value={cfgLeds}
                    onChange={(e) => setCfgLeds(e.target.value)}
                  />
                </div>
              </div>
              <div style={{ display: "flex", justifyContent: "flex-end" }}>
                <button type="submit" className="btn btn-primary" disabled={saveConfigMutation.isPending}>
                  Save Active Configuration
                </button>
              </div>
            </form>
          </section>
        </div>
      )}

      {tab === "calibrations" && (
        <div style={{ display: "grid", gap: "1rem" }}>
          <section className="glass-panel-strong" style={{ padding: "1.15rem" }}>
            <h2 style={{ marginTop: 0, fontSize: "1.12rem" }}>
              Motor Calibration Profiles (Immutable Superseding History)
            </h2>
            <div className="admin-table-wrap">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>ID / Axis</th>
                    <th>Version</th>
                    <th>Ratio / Steps / Micro</th>
                    <th>Max Rate / Accel</th>
                    <th>Zero / Travel</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {(calibrationsQuery.data ?? []).map((c) => (
                    <tr key={c.calibration_id}>
                      <td>
                        <code>{c.motor_key ?? c.motor_name}</code>
                        {c.is_active && <span className="pill-badge ok" style={{ marginLeft: "0.35rem" }}>Active</span>}
                      </td>
                      <td>{c.calibration_version}</td>
                      <td>
                        {c.gear_reduction_ratio}:1 · {c.full_steps_per_rev} · {c.microsteps}x
                      </td>
                      <td>
                        {c.max_step_rate} sps / {c.acceleration} sps&sup2;
                      </td>
                      <td>
                        {c.zero_offset_deg} deg ({c.travel_min_deg ?? "?"}..{c.travel_max_deg ?? "?"})
                      </td>
                      <td>
                        <span
                          className={`pill-badge ${
                            c.verification_status === "bench_verified"
                              ? "ok"
                              : c.verification_status === "deprecated"
                                ? "danger"
                                : "warn"
                          }`}
                        >
                          {c.verification_status}
                        </span>
                      </td>
                      <td>
                        <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap" }}>
                          {c.verification_status !== "bench_verified" && (
                            <button
                              type="button"
                              className="btn btn-cyan"
                              onClick={async () => {
                                await updateCalibration({
                                  calibration_id: c.calibration_id,
                                  verification_status: "bench_verified",
                                  is_active: true,
                                });
                                queryClient.invalidateQueries({
                                  queryKey: adminQueryKeys.calibrations(),
                                });
                                queryClient.invalidateQueries({
                                  queryKey: queryKeys.codexStatus(),
                                });
                              }}
                            >
                              Mark Verified
                            </button>
                          )}
                          {c.verification_status !== "deprecated" && (
                            <button
                              type="button"
                              className="btn btn-amber"
                              onClick={async () => {
                                await updateCalibration({
                                  calibration_id: c.calibration_id,
                                  verification_status: "deprecated",
                                  is_active: false,
                                });
                                queryClient.invalidateQueries({
                                  queryKey: adminQueryKeys.calibrations(),
                                });
                                queryClient.invalidateQueries({
                                  queryKey: queryKeys.codexStatus(),
                                });
                              }}
                            >
                              Deprecate
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="glass-panel-strong" style={{ padding: "1.15rem" }}>
            <h2 style={{ marginTop: 0, fontSize: "1.12rem" }}>
              Create New Calibration Record (Starts Unverified)
            </h2>
            <p style={{ marginTop: 0, fontSize: "0.84rem", color: "var(--text-secondary)" }}>
              Enter only measured mechanical bench parameters from physical encoder/limit testing.
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                createCalibrationMutation.mutate();
              }}
              style={{ display: "grid", gap: "0.75rem" }}
            >
              <div className="admin-form-grid-3">
                <div>
                  <label className="field-label" htmlFor="cal-axis">
                    Motor Axis
                  </label>
                  <select
                    id="cal-axis"
                    className="input"
                    value={calMotorKey}
                    onChange={(e) => setCalMotorKey(e.target.value === "byj" ? "byj" : "nema17")}
                  >
                    <option value="nema17">nema17 (Azimuth)</option>
                    <option value="byj">byj (Elevation / 28BYJ-48)</option>
                  </select>
                </div>
                <div>
                  <label className="field-label" htmlFor="cal-name">
                    Motor Label
                  </label>
                  <input
                    id="cal-name"
                    required
                    className="input"
                    value={calMotorName}
                    onChange={(e) => setCalMotorName(e.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="cal-ver">
                    Calibration Version Tag
                  </label>
                  <input
                    id="cal-ver"
                    required
                    className="input"
                    placeholder="v2.0-bench"
                    value={calVersion}
                    onChange={(e) => setCalVersion(e.target.value)}
                  />
                </div>
              </div>

              <div className="admin-form-grid-3">
                <div>
                  <label className="field-label" htmlFor="cal-ratio">
                    Gear Reduction Ratio
                  </label>
                  <input
                    id="cal-ratio"
                    type="number"
                    step="0.001"
                    required
                    className="input"
                    value={calRatio}
                    onChange={(e) => setCalRatio(e.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="cal-steps">
                    Full Steps / Rev
                  </label>
                  <input
                    id="cal-steps"
                    type="number"
                    required
                    className="input"
                    value={calStepsRev}
                    onChange={(e) => setCalStepsRev(e.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="cal-micro">
                    Microsteps
                  </label>
                  <input
                    id="cal-micro"
                    type="number"
                    required
                    className="input"
                    value={calMicrosteps}
                    onChange={(e) => setCalMicrosteps(e.target.value)}
                  />
                </div>
              </div>

              <div className="admin-form-grid-3">
                <div>
                  <label className="field-label" htmlFor="cal-rate">
                    Max Step Rate (steps/s)
                  </label>
                  <input
                    id="cal-rate"
                    type="number"
                    required
                    className="input"
                    value={calMaxRate}
                    onChange={(e) => setCalMaxRate(e.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="cal-accel">
                    Acceleration (steps/s&sup2;)
                  </label>
                  <input
                    id="cal-accel"
                    type="number"
                    required
                    className="input"
                    value={calAccel}
                    onChange={(e) => setCalAccel(e.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="cal-dir">
                    Direction Sign
                  </label>
                  <select
                    id="cal-dir"
                    className="input"
                    value={calDirection}
                    onChange={(e) => setCalDirection(Number(e.target.value) === -1 ? -1 : 1)}
                  >
                    <option value={1}>+1 (Normal)</option>
                    <option value={-1}>-1 (Inverted)</option>
                  </select>
                </div>
              </div>

              <div className="admin-form-grid-3">
                <div>
                  <label className="field-label" htmlFor="cal-back">
                    Backlash Steps
                  </label>
                  <input
                    id="cal-back"
                    type="number"
                    className="input"
                    value={calBacklash}
                    onChange={(e) => setCalBacklash(e.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="cal-zero">
                    Zero Offset (deg)
                  </label>
                  <input
                    id="cal-zero"
                    type="number"
                    step="0.01"
                    className="input"
                    value={calZero}
                    onChange={(e) => setCalZero(e.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="cal-by">
                    Measured By
                  </label>
                  <input
                    id="cal-by"
                    className="input"
                    value={calMeasuredBy}
                    onChange={(e) => setCalMeasuredBy(e.target.value)}
                  />
                </div>
              </div>

              <div className="admin-form-grid-2">
                <div>
                  <label className="field-label" htmlFor="cal-min">
                    Travel Min (deg)
                  </label>
                  <input
                    id="cal-min"
                    type="number"
                    step="0.1"
                    className="input"
                    value={calMinDeg}
                    onChange={(e) => setCalMinDeg(e.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="cal-max">
                    Travel Max (deg)
                  </label>
                  <input
                    id="cal-max"
                    type="number"
                    step="0.1"
                    className="input"
                    value={calMaxDeg}
                    onChange={(e) => setCalMaxDeg(e.target.value)}
                  />
                </div>
              </div>

              <div>
                <label className="field-label" htmlFor="cal-notes">
                  Bench Verification Notes
                </label>
                <input
                  id="cal-notes"
                  className="input"
                  value={calNotes}
                  onChange={(e) => setCalNotes(e.target.value)}
                />
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end" }}>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={createCalibrationMutation.isPending}
                >
                  Create Calibration Profile
                </button>
              </div>
            </form>
          </section>
        </div>
      )}

      {tab === "led-mapping" && (
        <div style={{ display: "grid", gap: "1rem" }}>
          <section className="glass-panel-strong" style={{ padding: "1.15rem" }}>
            <h2 style={{ marginTop: 0, fontSize: "1.12rem" }}>
              13 NASA Moon Region LED Physical Mapping
            </h2>
            <div className="admin-table-wrap">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Index</th>
                    <th>Region Name</th>
                    <th>Centroid (Lat, Lon)</th>
                    <th>LED Pixels</th>
                    <th>Topology / Ch</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {(ledQuery.data ?? []).map((reg) => {
                    const firstPx = (reg.normalized_pixels?.[0] ?? {}) as {
                      output_channel?: number;
                      topology_mode?: string;
                    };
                    const topo = firstPx.topology_mode ?? "addressable_strip";
                    const ch = firstPx.output_channel ?? 0;
                    const pxList = reg.pixel_indices ?? [];
                    return (
                      <tr key={reg.region_id}>
                        <td>#{reg.region_index}</td>
                        <td>{reg.region_name}</td>
                        <td>
                          {reg.centroid_lat ?? "—"}, {reg.centroid_lon ?? "—"}
                        </td>
                        <td>
                          <code>{pxList.join(", ")}</code>
                        </td>
                        <td>
                          {topo} (ch {ch})
                        </td>
                        <td>
                          <span
                            className={`pill-badge ${
                              reg.verification_status === "bench_verified" ? "ok" : "warn"
                            }`}
                          >
                            {reg.verification_status}
                          </span>
                        </td>
                        <td>
                          <button
                            type="button"
                            className="btn"
                            onClick={() => {
                              setLedIndex(String(reg.region_index));
                              setLedName(reg.region_name);
                              setLedLat(
                                reg.centroid_lat !== null && reg.centroid_lat !== undefined
                                  ? String(reg.centroid_lat)
                                  : "",
                              );
                              setLedLon(
                                reg.centroid_lon !== null && reg.centroid_lon !== undefined
                                  ? String(reg.centroid_lon)
                                  : "",
                              );
                              setLedPixels(pxList.join(", "));
                              setLedChannel(String(ch));
                              setLedTopology(topo as typeof ledTopology);
                              setLedStatus(reg.verification_status as typeof ledStatus);
                              setLedVersion(reg.mapping_version);
                            }}
                          >
                            Load into Form
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          <section className="glass-panel-strong" style={{ padding: "1.15rem" }}>
            <h2 style={{ marginTop: 0, fontSize: "1.12rem" }}>Update Region LED Mapping</h2>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                saveLedMutation.mutate();
              }}
              style={{ display: "grid", gap: "0.75rem" }}
            >
              <div className="admin-form-grid-3">
                <div>
                  <label className="field-label" htmlFor="led-idx">
                    Region Index (1–13)
                  </label>
                  <input
                    id="led-idx"
                    type="number"
                    min={1}
                    max={13}
                    required
                    className="input"
                    value={ledIndex}
                    onChange={(e) => setLedIndex(e.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="led-name">
                    Region Name
                  </label>
                  <input
                    id="led-name"
                    required
                    className="input"
                    value={ledName}
                    onChange={(e) => setLedName(e.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="led-pixels">
                    Pixel Indices (comma separated)
                  </label>
                  <input
                    id="led-pixels"
                    required
                    className="input"
                    placeholder="0, 1, 2"
                    value={ledPixels}
                    onChange={(e) => setLedPixels(e.target.value)}
                  />
                </div>
              </div>
              <div className="admin-form-grid-3">
                <div>
                  <label className="field-label" htmlFor="led-lat">
                    Centroid Lat
                  </label>
                  <input
                    id="led-lat"
                    type="number"
                    step="0.01"
                    className="input"
                    value={ledLat}
                    onChange={(e) => setLedLat(e.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="led-lon">
                    Centroid Lon
                  </label>
                  <input
                    id="led-lon"
                    type="number"
                    step="0.01"
                    className="input"
                    value={ledLon}
                    onChange={(e) => setLedLon(e.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="led-ver">
                    Mapping Version
                  </label>
                  <input
                    id="led-ver"
                    className="input"
                    value={ledVersion}
                    onChange={(e) => setLedVersion(e.target.value)}
                  />
                </div>
              </div>
              <div className="admin-form-grid-3">
                <div>
                  <label className="field-label" htmlFor="led-topo">
                    Topology Mode
                  </label>
                  <select
                    id="led-topo"
                    className="input"
                    value={ledTopology}
                    onChange={(e) => setLedTopology(e.target.value as typeof ledTopology)}
                  >
                    <option value="addressable_strip">addressable_strip</option>
                    <option value="discrete_gpio">discrete_gpio</option>
                    <option value="matrix">matrix</option>
                    <option value="unverified">unverified</option>
                  </select>
                </div>
                <div>
                  <label className="field-label" htmlFor="led-ch">
                    Output Channel
                  </label>
                  <input
                    id="led-ch"
                    type="number"
                    className="input"
                    value={ledChannel}
                    onChange={(e) => setLedChannel(e.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="led-status">
                    Verification Status
                  </label>
                  <select
                    id="led-status"
                    className="input"
                    value={ledStatus}
                    onChange={(e) => setLedStatus(e.target.value as typeof ledStatus)}
                  >
                    <option value="unverified">unverified</option>
                    <option value="centroid_approximate">centroid_approximate</option>
                    <option value="bench_verified">bench_verified</option>
                    <option value="deprecated">deprecated</option>
                  </select>
                </div>
              </div>
              <div style={{ display: "flex", justifyContent: "flex-end" }}>
                <button type="submit" className="btn btn-primary" disabled={saveLedMutation.isPending}>
                  Save LED Region Mapping
                </button>
              </div>
            </form>
          </section>
        </div>
      )}

      {tab === "runs" && (
        <section className="glass-panel-strong" style={{ padding: "1.15rem" }}>
          <h2 style={{ marginTop: 0, fontSize: "1.12rem" }}>CODEX Hardware Runs History</h2>
          <div className="admin-table-wrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Run ID</th>
                  <th>Site ID</th>
                  <th>Status</th>
                  <th>Simulated Start</th>
                  <th>Cal / LED Ver</th>
                  <th>Failure Reason</th>
                </tr>
              </thead>
              <tbody>
                {(runsQuery.data ?? []).length === 0 ? (
                  <tr>
                    <td colSpan={6}>No hardware runs recorded yet.</td>
                  </tr>
                ) : (
                  (runsQuery.data ?? []).map((r) => (
                    <tr key={r.hardware_run_id}>
                      <td>
                        <code>{r.hardware_run_id.slice(0, 8)}...</code>
                      </td>
                      <td>{r.site_id ?? "—"}</td>
                      <td>
                        <span className="pill-badge">{r.status}</span>
                      </td>
                      <td>{new Date(r.start_time_utc).toLocaleString()}</td>
                      <td>
                        {r.calibration_version ?? "—"} / {r.led_mapping_version ?? "—"}
                      </td>
                      <td>{r.failure_reason ?? "—"}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

export function AdminCodexPage() {
  return (
    <AdminLayout
      title="CODEX Hardware Workbench"
      subtitle="Manage three-controller bus telemetry, physical baseline configs, motor calibrations, Moon 13-region LED mapping, and run logs."
      requiredRoles={["hardware_admin", "system_admin"]}
    >
      {() => <CodexWorkbench />}
    </AdminLayout>
  );
}
