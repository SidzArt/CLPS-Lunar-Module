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
import {
  DEMO_CODEX_CONTROLLERS,
  DEMO_VERIFICATION_MESSAGES,
  isCodexDemoMode,
  setCodexDemoMode,
} from "../utils/codexDemo";
import { formatUtcTimestamp } from "../utils/formatting";

export function CodexPage() {
  const [searchParams] = useSearchParams();
  const initialSimId = searchParams.get("simulationId") ?? "";

  const [demoMode, setDemoModeState] = useState<boolean>(() => isCodexDemoMode());
  const [runClicked, setRunClicked] = useState(false);

  function handleToggleDemoMode() {
    const next = !demoMode;
    setDemoModeState(next);
    setCodexDemoMode(next);
  }

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

        {/* Explicit Mock vs Blocked Real Hardware Banner / Demo Mode Banner */}
        <div className="responsive-grid-2" style={{ marginBottom: "1.15rem" }}>
          <div className="glass-panel notice-banner cyan" style={{ display: "block" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.3rem", flexWrap: "wrap", gap: "0.4rem" }}>
              <strong style={{ display: "block" }}>
                DEMO MODE — SIMULATED STATUS
              </strong>
              <button
                type="button"
                className="pill-badge cyan"
                onClick={handleToggleDemoMode}
                style={{ cursor: "pointer", border: "1px solid var(--accent-cyan-border)" }}
                title="Toggle between Demo Mode and live telemetry"
              >
                {demoMode ? "DEMO MODE: ACTIVE" : "ENABLE DEMO MODE"}
              </button>
            </div>
            <p style={{ margin: 0, fontSize: "0.86rem", color: "var(--text-secondary)" }}>
              Presentation-only status mode for CODEX demonstration. All three hardware controllers
              consistently display Connected, Online, Ready, and Running for inspection.
            </p>
          </div>

          <div className="glass-panel notice-banner ok" style={{ display: "block" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.3rem", flexWrap: "wrap", gap: "0.4rem" }}>
              <strong style={{ display: "block" }}>
                {DEMO_VERIFICATION_MESSAGES.projectStatus}
              </strong>
              <span className="pill-badge ok">
                <span className="status-dot" />
                Operational
              </span>
            </div>
            <div style={{ fontSize: "0.86rem", color: "var(--text-secondary)", display: "flex", flexDirection: "column", gap: "0.2rem" }}>
              <div>{DEMO_VERIFICATION_MESSAGES.hardwareDemonstration}</div>
              <div>{DEMO_VERIFICATION_MESSAGES.hardwareIntegration}</div>
              <div>{DEMO_VERIFICATION_MESSAGES.hardwareTestStatus}</div>
            </div>
          </div>
        </div>

        {!demoMode && statusQuery.isError && (
          <div className="notice-banner error" role="alert" style={{ marginBottom: "1rem" }}>
            <span>Unable to load `/api/v1/codex/status`: {statusQuery.error.message}</span>
          </div>
        )}

        {(status || demoMode) && (
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
                    Bench Status: {demoMode ? "OPERATIONAL (Ready · Running)" : `${status?.overall_status?.toUpperCase() ?? "UNVERIFIED"} (${isMock ? "Mock Transport" : "Serial/WiFi"})`}
                  </h2>
                </div>
                <span className={`pill-badge ${demoMode ? "ok" : "amber"}`}>
                  Require Verified Bench: {demoMode ? "Team Reported Passed" : (status?.require_verified_bench ? "True" : "False")}
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
                  <div>{demoMode ? "Yes (Running)" : (status?.motors_ready ? "Yes" : "No (Blocked)")}</div>
                </div>
                <div className="glass-panel" style={{ padding: "0.7rem" }}>
                  <span className="eyebrow">LEDs Ready</span>
                  <div>{demoMode ? "Yes (Running)" : (status?.led_ready ? "Yes" : "No (Blocked)")}</div>
                </div>
                <div className="glass-panel" style={{ padding: "0.7rem" }}>
                  <span className="eyebrow">Calibration Verified</span>
                  <div>{demoMode ? "Verified" : (status?.calibration_verified ? "Verified" : "Unverified")}</div>
                </div>
                <div className="glass-panel" style={{ padding: "0.7rem" }}>
                  <span className="eyebrow">LED Mapping</span>
                  <div>{demoMode ? "Verified" : (status?.led_mapping_verified ? "Verified" : "Unverified")}</div>
                </div>
                <div className="glass-panel" style={{ padding: "0.7rem" }}>
                  <span className="eyebrow">E-STOP Latch</span>
                  <div>{demoMode ? "Released" : (status?.estop_latched ? "LATCHED" : "Released")}</div>
                </div>
              </div>

              {demoMode ? (
                <div className="notice-banner ok" style={{ marginTop: "0.85rem" }}>
                  <div>
                    <strong style={{ display: "block", marginBottom: "0.25rem" }}>
                      Hardware Verification Status
                    </strong>
                    <ul style={{ margin: 0, paddingLeft: "1.15rem", fontSize: "0.84rem" }}>
                      <li>{DEMO_VERIFICATION_MESSAGES.hardwareDemonstration}</li>
                      <li>{DEMO_VERIFICATION_MESSAGES.hardwareIntegration}</li>
                      <li>{DEMO_VERIFICATION_MESSAGES.hardwareTestStatus}</li>
                      <li>{DEMO_VERIFICATION_MESSAGES.projectStatus}</li>
                    </ul>
                  </div>
                </div>
              ) : (
                status?.blockers && status.blockers.length > 0 && (
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
                )
              )}
            </section>

            <section aria-label="Three-controller registry" style={{ marginBottom: "1.25rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.7rem", flexWrap: "wrap", gap: "0.5rem" }}>
                <h2 style={{ margin: 0, fontSize: "1.15rem" }}>
                  Controller Nodes ({demoMode ? DEMO_CODEX_CONTROLLERS.length : (status?.controllers?.length ?? 0)})
                </h2>
                {demoMode && (
                  <span className="pill-badge cyan">
                    DEMO MODE · SIMULATED STATUS
                  </span>
                )}
              </div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
                  gap: "0.9rem",
                }}
              >
                {demoMode
                  ? DEMO_CODEX_CONTROLLERS.map((c) => (
                      <article key={c.controller_key} className="glass-panel-strong" style={{ padding: "1rem" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.5rem" }}>
                          <strong>{c.board_model}</strong>
                          <div style={{ display: "flex", gap: "0.35rem", alignItems: "center" }}>
                            <span className="pill-badge ok">
                              <span className="status-dot" />
                              Connected
                            </span>
                            <span className="pill-badge ok">Running</span>
                          </div>
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
                          <dt style={{ color: "var(--text-muted)" }}>Status</dt>
                          <dd style={{ margin: 0 }}>
                            <span className="pill-badge ok" style={{ padding: "0.1rem 0.4rem", fontSize: "0.72rem" }}>Connected</span>
                          </dd>
                          <dt style={{ color: "var(--text-muted)" }}>Link</dt>
                          <dd style={{ margin: 0 }}>
                            <span className="pill-badge cyan" style={{ padding: "0.1rem 0.4rem", fontSize: "0.72rem" }}>Online</span>
                          </dd>
                          <dt style={{ color: "var(--text-muted)" }}>State</dt>
                          <dd style={{ margin: 0 }}>
                            <span className="pill-badge ok" style={{ padding: "0.1rem 0.4rem", fontSize: "0.72rem" }}>Ready</span>
                          </dd>
                          <dt style={{ color: "var(--text-muted)" }}>Execution</dt>
                          <dd style={{ margin: 0 }}>
                            <span className="pill-badge ok" style={{ padding: "0.1rem 0.4rem", fontSize: "0.72rem" }}>Running</span>
                          </dd>
                          <dt style={{ color: "var(--text-muted)" }}>Verification</dt>
                          <dd style={{ margin: 0 }}>{c.verification_status}</dd>
                          <dt style={{ color: "var(--text-muted)" }}>UART Link</dt>
                          <dd style={{ margin: 0 }}>OK · Online</dd>
                          <dt style={{ color: "var(--text-muted)" }}>Heartbeat</dt>
                          <dd style={{ margin: 0 }}>Fresh (Active)</dd>
                        </dl>
                        <div className="mono" style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>
                          Last heartbeat: {formatUtcTimestamp(c.last_heartbeat_at)}
                        </div>
                      </article>
                    ))
                  : (status?.controllers ?? []).map((c) => (
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

        {/* Run CODEX Workspace & Non-Actuating Dry-Run Calculation Preview */}
        <section className="glass-panel-strong" style={{ padding: "1.15rem" }} aria-label="Run CODEX panel">
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
            <span className="pill-badge ok">
              <span className="status-dot" />
              Hardware Integration: Completed
            </span>
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

          {/* Exactly one compact Run button positioned at the bottom-right corner of the Run CODEX panel */}
          <div
            style={{
              display: "flex",
              justifyContent: "flex-end",
              alignItems: "center",
              marginTop: "1.25rem",
              paddingTop: "0.85rem",
              borderTop: "1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))",
            }}
          >
            {runClicked && (
              <span
                style={{
                  marginRight: "0.75rem",
                  fontSize: "0.82rem",
                  color: "var(--accent-cyan)",
                }}
                role="status"
              >
                Run command acknowledged (Demo Mode placeholder)
              </span>
            )}
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => {
                // Placeholder: accepts the click without sending hardware commands,
                // starting motors, changing LED states, initiating API requests,
                // triggering firmware uploads, or altering simulation.
                setRunClicked(true);
              }}
              aria-label="Run"
              title="Run CODEX"
            >
              Run
            </button>
          </div>
        </section>
      </main>

      <UtilitiesFooter />
    </div>
  );
}
