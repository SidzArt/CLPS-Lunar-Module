import { useEffect } from "react";
import { Link } from "react-router-dom";
import type { PublicCodexStatusOut } from "../api/endpoints";
import { formatUtcTimestamp } from "../utils/formatting";
import { CloseIcon } from "./Icons";

export interface CodexDrawerProps {
  open: boolean;
  onClose: () => void;
  status?: PublicCodexStatusOut;
  isLoading: boolean;
  error?: Error | null;
}

export function CodexDrawer({
  open,
  onClose,
  status,
  isLoading,
  error,
}: CodexDrawerProps) {
  useEffect(() => {
    if (!open) {
      return;
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  const isMock = !status || status.transport_mode === "mock";
  const hardwareVerified =
    Boolean(status?.calibration_verified) &&
    Boolean(status?.led_mapping_verified) &&
    Boolean(status?.motors_ready) &&
    Boolean(status?.led_ready) &&
    !status?.estop_latched &&
    !isMock;

  return (
    <div
      className="drawer-backdrop no-print"
      role="presentation"
      onClick={onClose}
    >
      <div
        className="glass-panel-strong drawer-panel"
        role="dialog"
        aria-modal="true"
        aria-label="CODEX hardware bench status"
        onClick={(event) => event.stopPropagation()}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: "1rem",
          }}
        >
          <div>
            <p className="eyebrow" style={{ margin: 0 }}>
              Phase 5 Hardware Integration
            </p>
            <h2 style={{ margin: "0.15rem 0 0", fontSize: "1.18rem" }}>
              CODEX Bench Status
            </h2>
          </div>
          <button
            type="button"
            className="btn"
            aria-label="Close CODEX status drawer"
            onClick={onClose}
          >
            <CloseIcon />
          </button>
        </div>

        <div className="notice-banner warn" style={{ marginBottom: "0.9rem" }}>
          <div>
            <strong style={{ display: "block", marginBottom: "0.2rem" }}>
              {isMock
                ? "MOCK / DEMONSTRATION MODE ACTIVE"
                : hardwareVerified
                  ? "REAL HARDWARE BENCH READY"
                  : "REAL HARDWARE MODE — BLOCKED"}
            </strong>
            <span style={{ fontSize: "0.82rem", color: "var(--text-secondary)" }}>
              Phase 5 is PARTIAL: backend orchestration and `MockCodexTransport` are
              verified, while physical motor calibration, bench UART/Wi-Fi telemetry, and
              Moon LED wiring remain blocked pending hardware team sign-off.
            </span>
          </div>
        </div>

        {isLoading && (
          <p style={{ color: "var(--text-secondary)", fontSize: "0.88rem" }}>
            Loading controller telemetry...
          </p>
        )}

        {error && (
          <div className="notice-banner error" role="alert">
            <span>Unable to query `/api/v1/codex/status`: {error.message}</span>
          </div>
        )}

        {status && (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }}>
            <div className="glass-panel" style={{ padding: "0.85rem" }}>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: "0.5rem",
                  fontSize: "0.82rem",
                }}
              >
                <div>
                  <span className="eyebrow">Transport Mode</span>
                  <div className="mono">{status.transport_mode}</div>
                </div>
                <div>
                  <span className="eyebrow">Overall State</span>
                  <div className="mono">{status.overall_status}</div>
                </div>
                <div>
                  <span className="eyebrow">Calibration</span>
                  <div>{status.calibration_verified ? "Verified" : "Unverified"}</div>
                </div>
                <div>
                  <span className="eyebrow">LED Mapping</span>
                  <div>{status.led_mapping_verified ? "Verified" : "Unverified"}</div>
                </div>
                <div>
                  <span className="eyebrow">Motors Ready</span>
                  <div>{status.motors_ready ? "Yes" : "No (Blocked)"}</div>
                </div>
                <div>
                  <span className="eyebrow">E-STOP Latch</span>
                  <div>{status.estop_latched ? "Latched" : "Released"}</div>
                </div>
              </div>
              <div
                style={{
                  marginTop: "0.65rem",
                  fontSize: "0.74rem",
                  color: "var(--text-muted)",
                }}
              >
                Last checked: {formatUtcTimestamp(status.checked_at)}
              </div>
            </div>

            {status.blockers && status.blockers.length > 0 && (
              <div className="glass-panel" style={{ padding: "0.85rem" }}>
                <div className="eyebrow" style={{ marginBottom: "0.45rem" }}>
                  Active Safety Blockers
                </div>
                <ul
                  style={{
                    margin: 0,
                    paddingLeft: "1.15rem",
                    fontSize: "0.82rem",
                    color: "var(--text-secondary)",
                    display: "flex",
                    flexDirection: "column",
                    gap: "0.3rem",
                  }}
                >
                  {status.blockers.map((blocker) => (
                    <li key={blocker}>{blocker}</li>
                  ))}
                </ul>
              </div>
            )}

            <div>
              <div className="eyebrow" style={{ marginBottom: "0.5rem" }}>
                Three-Controller Chain ({status.controllers?.length ?? 0})
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
                {(status.controllers ?? []).map((ctrl) => (
                  <div
                    key={ctrl.controller_key}
                    className="glass-panel"
                    style={{ padding: "0.75rem 0.85rem" }}
                  >
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        gap: "0.5rem",
                      }}
                    >
                      <strong style={{ fontSize: "0.9rem" }}>{ctrl.board_model}</strong>
                      <span
                        className={`pill-badge ${
                          ctrl.health_state === "ready" &&
                          ctrl.verification_status === "verified"
                            ? "ok"
                            : "amber"
                        }`}
                      >
                        <span className="status-dot" />
                        {ctrl.health_state}
                      </span>
                    </div>
                    <div
                      className="mono"
                      style={{
                        fontSize: "0.75rem",
                        color: "var(--text-muted)",
                        marginTop: "0.2rem",
                      }}
                    >
                      {ctrl.controller_key} · {ctrl.device_role} ·{" "}
                      {ctrl.verification_status}
                    </div>
                    <div
                      style={{
                        display: "flex",
                        flexWrap: "wrap",
                        gap: "0.65rem",
                        marginTop: "0.45rem",
                        fontSize: "0.76rem",
                        color: "var(--text-secondary)",
                      }}
                    >
                      <span>UART: {ctrl.uart_ok ? "OK" : "Unavailable"}</span>
                      <span>
                        Heartbeat: {ctrl.heartbeat_fresh ? "Fresh" : "Stale"}
                      </span>
                      <span>
                        Battery:{" "}
                        {ctrl.battery_voltage_available &&
                        ctrl.battery_voltage_v !== null &&
                        ctrl.battery_voltage_v !== undefined
                          ? `${ctrl.battery_voltage_v.toFixed(2)} V`
                          : "No Sensor"}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div style={{ display: "flex", gap: "0.6rem", marginTop: "0.3rem" }}>
              <Link
                to="/codex"
                className="btn btn-primary"
                style={{ flex: 1 }}
                onClick={onClose}
              >
                Open Run CODEX Workspace -&gt;
              </Link>
              <button type="button" className="btn" disabled>
                Physical Upload (Locked)
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

