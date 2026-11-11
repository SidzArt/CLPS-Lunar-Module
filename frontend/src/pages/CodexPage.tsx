import { useMutation, useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  fetchAdminProfile,
  fetchCodexStatus,
  fetchSites,
  prepareCodexRun,
  type CodexRunPrepareOut,
} from "../api/endpoints";
import { queryKeys } from "../api/queryKeys";
import { SiteHeader } from "../components/SiteHeader";
import { UtilitiesFooter } from "../components/UtilitiesFooter";
import { HeadTags } from "../seo/HeadTags";
import { LunarMoonCanvas } from "../three/LunarMoonCanvas";
import { formatUtcTimestamp } from "../utils/formatting";

export function CodexPage() {
  const [searchParams] = useSearchParams();
  const initialSimId = searchParams.get("simulationId") ?? "";

  const sitesQuery = useQuery({
    queryKey: queryKeys.sites({ status: "published", page_size: 50 }),
    queryFn: () => fetchSites({ status: "published", page_size: 50 }),
    staleTime: 60_000,
  });

  const statusQuery = useQuery({
    queryKey: queryKeys.codexStatus(),
    queryFn: () => fetchCodexStatus(),
    staleTime: 10_000,
  });

  const authQuery = useQuery({
    queryKey: queryKeys.adminMe(),
    queryFn: () => fetchAdminProfile(),
    retry: false,
  });

  const [simulationId, setSimulationId] = useState(initialSimId);
  const [executionMode, setExecutionMode] = useState<"full_codex" | "led_only">("full_codex");
  const [prepareResult, setPrepareResult] = useState<CodexRunPrepareOut | null>(null);

  const prepareMutation = useMutation({
    mutationFn: (payload: Parameters<typeof prepareCodexRun>[0]) =>
      prepareCodexRun(payload),
    onSuccess: (res) => {
      setPrepareResult(res);
    },
  });

  function handlePreparePreview(event: FormEvent) {
    event.preventDefault();
    if (!simulationId.trim()) {
      return;
    }
    prepareMutation.mutate({
      simulation_id: simulationId.trim(),
      execution_mode: executionMode,
      clamp_to_travel_limits: false,
      allow_unverified_preview: true,
      allow_centroid_led_fallback: false,
    });
  }

  const status = statusQuery.data;
  const isMock = !status || status.transport_mode === "mock";

  return (
    <div className="page-shell">
      <HeadTags
        meta={{
          title: "Run CODEX — Hardware Bench Status — CLPS Luna Browser",
          description:
            "Inspect the three-controller CODEX hardware chain status, Phase 5 mock transport boundary, and non-actuating dry-run preflight calculator.",
          canonicalPath: "/codex",
          robots: "noindex,nofollow",
          ogType: "website",
          breadcrumbs: [
            { name: "Home", path: "/" },
            { name: "Run CODEX", path: "/codex" },
          ],
        }}
      />

      <div className="ambient-bg-layer" aria-hidden="true">
        <LunarMoonCanvas mode="ambient" sites={sitesQuery.data?.items ?? []} />
      </div>

      <SiteHeader
        subtitle="CODEX Bench & Dry-Run Preview"
        rightActions={
          <Link to="/browser" className="btn">
            &lt;- Browser
          </Link>
        }
      />

      <main id="main-content" className="page-content-layer container">
        <div style={{ marginBottom: "1rem" }}>
          <h1 style={{ margin: 0, fontSize: "1.65rem" }}>Run CODEX</h1>
          <p style={{ margin: "0.2rem 0 0", color: "var(--text-secondary)", fontSize: "0.92rem" }}>
            Mechanical orbital demonstrator and three-controller hardware orchestration status.
          </p>
        </div>

        {/* Explicit Mock vs Blocked Real Hardware Banner */}
        <div className="responsive-grid-2" style={{ marginBottom: "1.15rem" }}>
          <div className="glass-panel notice-banner cyan" style={{ display: "block" }}>
            <strong style={{ display: "block", marginBottom: "0.3rem" }}>
              MOCK / DEMONSTRATION MODE ({status?.transport_mode ?? "mock"})
            </strong>
            <p style={{ margin: 0, fontSize: "0.86rem", color: "var(--text-secondary)" }}>
              Software orchestration, 16-step pre-flight checklist validation, Kepler reference
              kinematics, and `MockCodexTransport` are active for dry-run inspection without moving
              physical hardware.
            </p>
          </div>

          <div className="glass-panel notice-banner warn" style={{ display: "block" }}>
            <strong style={{ display: "block", marginBottom: "0.3rem" }}>
              REAL HARDWARE MODE — BLOCKED (PHASE 5 PARTIAL)
            </strong>
            <p style={{ margin: 0, fontSize: "0.86rem", color: "var(--text-secondary)" }}>
              Physical stepper motor calibration, ESP32-WROOM / Uno / ESP32-S3 bench UART
              verification, and lunar globe LED wiring tests remain{" "}
              <strong>BLOCKED — HARDWARE TEAM REQUIRED</strong>. Actuation &amp; upload controls are
              intentionally disabled.
            </p>
          </div>
        </div>

        {statusQuery.isError && (
          <div className="notice-banner error" role="alert" style={{ marginBottom: "1rem" }}>
            <span>Unable to load `/api/v1/codex/status`: {statusQuery.error.message}</span>
          </div>
        )}

        {status && (
          <>
            <section
              className="glass-panel-strong"
              style={{ padding: "1.15rem", marginBottom: "1.15rem" }}
              aria-label="Overall bench readiness"
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  flexWrap: "wrap",
                  gap: "0.6rem",
                  marginBottom: "0.85rem",
                }}
              >
                <div>
                  <span className="eyebrow">Safety Interlock Summary</span>
                  <h2 style={{ margin: "0.15rem 0 0", fontSize: "1.15rem" }}>
                    Bench Status: {status.overall_status.toUpperCase()} ({isMock ? "Mock Transport" : "Serial/WiFi"})
                  </h2>
                </div>
                <span className="pill-badge amber">
                  Require Verified Bench: {status.require_verified_bench ? "True" : "False"}
                </span>
              </div>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))",
                  gap: "0.75rem",
                  fontSize: "0.84rem",
                }}
              >
                <div className="glass-panel" style={{ padding: "0.7rem" }}>
                  <span className="eyebrow">Motors Ready</span>
                  <div>{status.motors_ready ? "Yes" : "No (Blocked)"}</div>
                </div>
                <div className="glass-panel" style={{ padding: "0.7rem" }}>
                  <span className="eyebrow">LEDs Ready</span>
                  <div>{status.led_ready ? "Yes" : "No (Blocked)"}</div>
                </div>
                <div className="glass-panel" style={{ padding: "0.7rem" }}>
                  <span className="eyebrow">Calibration Verified</span>
                  <div>{status.calibration_verified ? "Verified" : "Unverified"}</div>
                </div>
                <div className="glass-panel" style={{ padding: "0.7rem" }}>
                  <span className="eyebrow">LED Mapping</span>
                  <div>{status.led_mapping_verified ? "Verified" : "Unverified"}</div>
                </div>
                <div className="glass-panel" style={{ padding: "0.7rem" }}>
                  <span className="eyebrow">E-STOP Latch</span>
                  <div>{status.estop_latched ? "LATCHED" : "Released"}</div>
                </div>
              </div>

              {status.blockers && status.blockers.length > 0 && (
                <div className="notice-banner warn" style={{ marginTop: "0.85rem" }}>
                  <div>
                    <strong style={{ display: "block", marginBottom: "0.25rem" }}>
                      Reported Blockers
                    </strong>
                    <ul style={{ margin: 0, paddingLeft: "1.15rem", fontSize: "0.84rem" }}>
                      {status.blockers.map((b) => (
                        <li key={b}>{b}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}
            </section>

            <section aria-label="Three-controller registry" style={{ marginBottom: "1.25rem" }}>
              <h2 style={{ margin: "0 0 0.7rem", fontSize: "1.15rem" }}>
                Controller Nodes ({status.controllers?.length ?? 0})
              </h2>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
                  gap: "0.9rem",
                }}
              >
                {(status.controllers ?? []).map((c) => (
                  <article key={c.controller_key} className="glass-panel-strong" style={{ padding: "1rem" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.5rem" }}>
                      <strong>{c.board_model}</strong>
                      <span className="pill-badge amber">{c.health_state}</span>
                    </div>
                    <div className="mono" style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: "0.2rem" }}>
                      {c.controller_key} · {c.device_role}
                    </div>
                    <dl
                      style={{
                        margin: "0.65rem 0 0",
                        display: "grid",
                        gridTemplateColumns: "1fr 1fr",
                        gap: "0.35rem",
                        fontSize: "0.8rem",
                      }}
                    >
                      <dt style={{ color: "var(--text-muted)" }}>Verification</dt>
                      <dd style={{ margin: 0 }}>{c.verification_status}</dd>
                      <dt style={{ color: "var(--text-muted)" }}>UART Link</dt>
                      <dd style={{ margin: 0 }}>{c.uart_ok ? "OK" : "Offline"}</dd>
                      <dt style={{ color: "var(--text-muted)" }}>Driver Config</dt>
                      <dd style={{ margin: 0 }}>{c.driver_config_ok ? "OK" : "Pending"}</dd>
                      <dt style={{ color: "var(--text-muted)" }}>Heartbeat</dt>
                      <dd style={{ margin: 0 }}>{c.heartbeat_fresh ? "Fresh" : "Stale"}</dd>
                    </dl>
                    {c.last_heartbeat_at && (
                      <div className="mono" style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>
                        Last heartbeat: {formatUtcTimestamp(c.last_heartbeat_at)}
                      </div>
                    )}
                  </article>
                ))}
              </div>
            </section>
          </>
        )}

        {/* Non-Actuating Dry-Run Calculation Preview */}
        <section className="glass-panel-strong" style={{ padding: "1.15rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "0.6rem", marginBottom: "0.75rem" }}>
            <div>
              <h2 style={{ margin: 0, fontSize: "1.15rem" }}>
                Non-Actuating Dry-Run Calculation Preview (`POST /codex/runs/prepare`)
              </h2>
              <p style={{ margin: "0.2rem 0 0", fontSize: "0.84rem", color: "var(--text-secondary)" }}>
                Computes orbital targets, motor plans, LED plans, and 16-step pre-flight checklist
                without actuating physical motors (`actuation_performed: false`).
              </p>
            </div>
            <button type="button" className="btn" disabled>
              Physical Execution Locked (Phase 5 Incomplete)
            </button>
          </div>

          {!authQuery.data ? (
            <div className="notice-banner">
              <span>
                Dry-run plan preparation requires an authenticated hardware operator session.{" "}
                <Link to="/admin" style={{ color: "var(--accent-amber)", textDecoration: "underline" }}>
                  Sign in via reserved Operator Login -&gt;
                </Link>
              </span>
            </div>
          ) : (
            <form onSubmit={handlePreparePreview} className="responsive-grid-3" style={{ alignItems: "end" }}>
              <div>
                <label htmlFor="codex-sim-id" className="field-label">
                  Completed Simulation ID (UUID)
                </label>
                <input
                  id="codex-sim-id"
                  type="text"
                  className="input mono"
                  value={simulationId}
                  onChange={(event) => setSimulationId(event.target.value)}
                  placeholder="Paste completed simulation UUID..."
                  required
                />
              </div>

              <div>
                <label htmlFor="codex-exec-mode" className="field-label">
                  Preview Mode
                </label>
                <select
                  id="codex-exec-mode"
                  className="select"
                  value={executionMode}
                  onChange={(event) =>
                    setExecutionMode(event.target.value as "full_codex" | "led_only")
                  }
                >
                  <option value="full_codex">Full CODEX (Motors + LED)</option>
                  <option value="led_only">LED Only</option>
                </select>
              </div>

              <button
                type="submit"
                className="btn btn-primary"
                disabled={prepareMutation.isPending}
                style={{ height: "40px" }}
              >
                {prepareMutation.isPending ? "Calculating..." : "Calculate Dry-Run Plan ->"}
              </button>
            </form>
          )}

          {prepareMutation.isError && (
            <div className="notice-banner error" role="alert" style={{ marginTop: "0.8rem" }}>
              <span>{prepareMutation.error.message}</span>
            </div>
          )}

          {prepareResult && (
            <div style={{ marginTop: "1rem", display: "flex", flexDirection: "column", gap: "0.85rem" }}>
              <div className="notice-banner cyan">
                <span>
                  Prepared Run <strong className="mono">{prepareResult.hardware_run_id}</strong> for{" "}
                  <strong>{prepareResult.site_name}</strong> · Preflight Passed:{" "}
                  {prepareResult.preflight_passed_count} / {prepareResult.preflight_total_steps} ·
                  Actuation Performed: <strong>{String(prepareResult.actuation_performed)}</strong>
                </span>
              </div>

              <div className="data-table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Step</th>
                      <th>Check Key</th>
                      <th>Severity</th>
                      <th>Detail</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(prepareResult.preflight_steps ?? []).map((step) => (
                      <tr key={step.step_number}>
                        <td className="mono">#{step.step_number}</td>
                        <td className="mono">{step.key}</td>
                        <td>
                          <span
                            className={`pill-badge ${
                              step.severity === "ok"
                                ? "ok"
                                : step.severity === "warning"
                                  ? "amber"
                                  : "error"
                            }`}
                          >
                            {step.severity}
                          </span>
                        </td>
                        <td>{step.detail}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </section>
      </main>

      <UtilitiesFooter />
    </div>
  );
}
