import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { AdminLayout } from "../../admin/AdminLayout";
import {
  adminQueryKeys,
  fetchAuditLogs,
  fetchSystemHealth,
  type AuditLogEntryOut,
} from "../../api/adminEndpoints";

function AuditAndHealthWorkbench() {
  const [actionFilter, setActionFilter] = useState("");
  const [entityFilter, setEntityFilter] = useState("");
  const [appliedAction, setAppliedAction] = useState("");
  const [appliedEntity, setAppliedEntity] = useState("");
  const [page, setPage] = useState(1);
  const [selectedEntry, setSelectedEntry] = useState<AuditLogEntryOut | null>(null);

  const healthQuery = useQuery({
    queryKey: adminQueryKeys.systemHealth,
    queryFn: () => fetchSystemHealth(),
  });

  const auditParams = {
    action_key: appliedAction || undefined,
    entity_type: appliedEntity || undefined,
    page,
    page_size: 25,
  };

  const auditQuery = useQuery({
    queryKey: adminQueryKeys.auditLogs(auditParams),
    queryFn: () => fetchAuditLogs(auditParams),
  });

  const health = healthQuery.data;

  return (
    <div style={{ display: "grid", gap: "1rem" }}>
      <section className="glass-panel-strong" style={{ padding: "1.15rem" }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "0.75rem",
            marginBottom: "0.85rem",
          }}
        >
          <div>
            <h2 style={{ margin: 0, fontSize: "1.15rem" }}>Live Subsystem Health Probes</h2>
            <p style={{ margin: "0.2rem 0 0", fontSize: "0.84rem", color: "var(--text-secondary)" }}>
              {health
                ? `Overall status: ${health.overall_status} · Last probed ${new Date(health.checked_at).toLocaleString()}`
                : "Running backend readiness probes..."}
            </p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
            {health && (
              <span
                className={`pill-badge ${
                  health.overall_status === "healthy"
                    ? "ok"
                    : health.overall_status === "degraded"
                      ? "warn"
                      : "danger"
                }`}
              >
                {health.overall_status}
              </span>
            )}
            <button
              type="button"
              className="btn btn-cyan"
              disabled={healthQuery.isFetching}
              onClick={() => healthQuery.refetch()}
            >
              {healthQuery.isFetching ? "Probing..." : "Re-Run Probes"}
            </button>
          </div>
        </div>

        <div className="admin-health-grid">
          {(health?.components ?? []).map((comp) => (
            <article key={comp.component_key} className="glass-panel" style={{ padding: "0.9rem" }}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: "0.5rem",
                }}
              >
                <strong style={{ fontSize: "0.95rem" }}>{comp.display_name}</strong>
                <span
                  className={`pill-badge ${
                    comp.status === "healthy"
                      ? "ok"
                      : comp.status === "degraded"
                        ? "warn"
                        : "danger"
                  }`}
                >
                  {comp.status}
                </span>
              </div>
              <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                <code>{comp.component_key}</code> · {comp.component_type}
                {comp.latency_ms !== null && comp.latency_ms !== undefined
                  ? ` · ${comp.latency_ms} ms`
                  : ""}
              </div>
              {comp.error_message && (
                <p style={{ margin: "0.45rem 0 0", color: "var(--accent-amber)", fontSize: "0.8rem" }}>
                  {comp.error_message}
                </p>
              )}
              {comp.details && Object.keys(comp.details).length > 0 && (
                <pre className="admin-json-pre" style={{ marginTop: "0.5rem" }}>
                  {JSON.stringify(comp.details, null, 2)}
                </pre>
              )}
            </article>
          ))}
        </div>
      </section>

      <section className="glass-panel-strong" style={{ padding: "1.15rem" }}>
        <div className="admin-toolbar" style={{ marginBottom: "0.9rem" }}>
          <h2 style={{ margin: 0, fontSize: "1.15rem", marginRight: "auto" }}>
            Redacted Audit Trail ({auditQuery.data?.total ?? 0})
          </h2>
          <input
            type="text"
            className="input"
            aria-label="Filter by action key"
            placeholder="Action key (e.g. AUTH_LOGIN)"
            value={actionFilter}
            onChange={(e) => setActionFilter(e.target.value)}
            style={{ width: "210px" }}
          />
          <input
            type="text"
            className="input"
            aria-label="Filter by entity type"
            placeholder="Entity type (e.g. landing_sites)"
            value={entityFilter}
            onChange={(e) => setEntityFilter(e.target.value)}
            style={{ width: "210px" }}
          />
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              setAppliedAction(actionFilter.trim());
              setAppliedEntity(entityFilter.trim());
              setPage(1);
            }}
          >
            Filter
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => {
              setActionFilter("");
              setEntityFilter("");
              setAppliedAction("");
              setAppliedEntity("");
              setPage(1);
            }}
          >
            Reset
          </button>
        </div>

        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Entity</th>
                <th>IP</th>
                <th>Snapshot</th>
              </tr>
            </thead>
            <tbody>
              {auditQuery.isLoading ? (
                <tr>
                  <td colSpan={6}>Loading audit events...</td>
                </tr>
              ) : (auditQuery.data?.items ?? []).length === 0 ? (
                <tr>
                  <td colSpan={6}>No matching audit log records found.</td>
                </tr>
              ) : (
                (auditQuery.data?.items ?? []).map((row) => (
                  <tr key={row.audit_id}>
                    <td>{new Date(row.occurred_at).toLocaleString()}</td>
                    <td>{row.admin_username ?? row.admin_id ?? "system"}</td>
                    <td>
                      <code>{row.action_key}</code>
                    </td>
                    <td>
                      <code>{row.entity_type}</code>
                      {row.entity_id ? ` #${row.entity_id}` : ""}
                    </td>
                    <td>{row.ip_address ?? "—"}</td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-cyan"
                        onClick={() => setSelectedEntry(row)}
                      >
                        Inspect Diff
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {auditQuery.data && (
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginTop: "0.85rem",
              fontSize: "0.85rem",
              color: "var(--text-secondary)",
            }}
          >
            <span>
              Page {auditQuery.data.page} · Total {auditQuery.data.total} audit rows
            </span>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button
                type="button"
                className="btn"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                Previous
              </button>
              <button
                type="button"
                className="btn"
                disabled={!auditQuery.data.has_more}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </button>
            </div>
          </div>
        )}
      </section>

      {selectedEntry && (
        <div className="modal-backdrop" role="presentation" onClick={() => setSelectedEntry(null)}>
          <div
            className="glass-panel-strong"
            role="dialog"
            aria-modal="true"
            aria-label="Audit Snapshot Diff"
            style={{ width: "min(760px, 100%)", padding: "1.25rem", maxHeight: "88vh", overflowY: "auto" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.5rem" }}>
              <h3 style={{ margin: 0 }}>
                Audit #{selectedEntry.audit_id} · {selectedEntry.action_key}
              </h3>
              <button type="button" className="btn" onClick={() => setSelectedEntry(null)}>
                Close
              </button>
            </div>
            <p style={{ fontSize: "0.84rem", color: "var(--text-secondary)" }}>
              Entity: <code>{selectedEntry.entity_type}</code> ({selectedEntry.entity_id ?? "—"}) ·
              Secrets and raw hashes are redacted before persistence.
            </p>
            <div className="admin-form-grid-2">
              <div>
                <h4 style={{ margin: "0 0 0.4rem", fontSize: "0.88rem" }}>Before Snapshot</h4>
                <pre className="admin-json-pre">
                  {selectedEntry.before_snapshot
                    ? JSON.stringify(selectedEntry.before_snapshot, null, 2)
                    : "null"}
                </pre>
              </div>
              <div>
                <h4 style={{ margin: "0 0 0.4rem", fontSize: "0.88rem" }}>After Snapshot</h4>
                <pre className="admin-json-pre">
                  {selectedEntry.after_snapshot
                    ? JSON.stringify(selectedEntry.after_snapshot, null, 2)
                    : "null"}
                </pre>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function AdminAuditHealthPage() {
  return (
    <AdminLayout
      title="Audit Logs & System Health"
      subtitle="Live database, SPICE, LOLA DEM, Ollama, worker lease, and CODEX probes paired with the redacted audit trail."
      requiredRoles={["system_admin"]}
    >
      {() => <AuditAndHealthWorkbench />}
    </AdminLayout>
  );
}

