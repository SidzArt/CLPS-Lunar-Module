import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { AdminLayout } from "../../admin/AdminLayout";
import { hasAnyRole, isSuperAdmin } from "../../admin/rbac";
import { adminQueryKeys, fetchAdminOverview } from "../../api/adminEndpoints";
import type { AdminProfileOut } from "../../api/endpoints";

interface QuickAction {
  to: string;
  eyebrow: string;
  title: string;
  description: string;
  cta: string;
  visible: (roles: string[]) => boolean;
}

const QUICK_ACTIONS: QuickAction[] = [
  {
    to: "/admin/sites",
    eyebrow: "Catalogue",
    title: "Landing Sites & Metrics",
    description:
      "Create draft sites, edit sections, history, pros/cons, and provenance-linked metrics.",
    cta: "Manage Sites",
    visible: (r) => hasAnyRole(r, "site_editor", "research_admin", "system_admin", "viewer"),
  },
  {
    to: "/admin/media",
    eyebrow: "Imagery",
    title: "Media & Orphan Scan",
    description:
      "Upload normalized WebP media, designate primary site imagery, and inspect orphan files.",
    cta: "Open Media",
    visible: (r) => hasAnyRole(r, "site_editor", "research_admin", "system_admin", "viewer"),
  },
  {
    to: "/admin/imports",
    eyebrow: "Data Provenance",
    title: "Dataset Imports & Sources",
    description:
      "Stage CSV, XLSX, and GeoJSON bundles with validation previews and curated data sources.",
    cta: "Imports & Sources",
    visible: (r) => hasAnyRole(r, "research_admin", "site_editor", "system_admin"),
  },
  {
    to: "/admin/codex",
    eyebrow: "Hardware Table",
    title: "CODEX Devices & Calibrations",
    description:
      "Inspect transport probes, emergency stops, motor calibrations, and 13-region Moon LEDs.",
    cta: "Open CODEX",
    visible: (r) => hasAnyRole(r, "hardware_admin", "system_admin"),
  },
  {
    to: "/admin/codex/firmware",
    eyebrow: "Controller Source",
    title: "Split-Pane Firmware Editor",
    description:
      "Author immutable controller code drafts, diff revisions, validate syntax, and insert variables.",
    cta: "Open Firmware Editor",
    visible: (r) => hasAnyRole(r, "hardware_admin", "system_admin"),
  },
  {
    to: "/admin/audit",
    eyebrow: "Telemetry",
    title: "Audit Logs & System Health",
    description:
      "Inspect redacted mutation diffs across tables and run live subsystem readiness probes.",
    cta: "Inspect Health",
    visible: (r) => hasAnyRole(r, "system_admin"),
  },
  {
    to: "/admin/users",
    eyebrow: "Access Control",
    title: "Users & RBAC Roles",
    description:
      "Provision operators, rotate credentials, unlock accounts, and revoke active sessions.",
    cta: "Manage Users",
    visible: (r) => isSuperAdmin(r),
  },
];

function DashboardContent({ admin }: { admin: AdminProfileOut }) {
  const overviewQuery = useQuery({
    queryKey: adminQueryKeys.overview,
    queryFn: () => fetchAdminOverview(),
  });

  const ov = overviewQuery.data;
  const roles = admin.roles ?? [];
  const visibleActions = QUICK_ACTIONS.filter((a) => a.visible(roles));

  return (
    <div className="admin-dashboard-rows">
      {/* Row 1: Telemetry Summary Row (3 compact glass cards) */}
      <section className="admin-dashboard-row admin-kpi-row" aria-label="Operations summary metrics">
        <article className="glass-panel admin-kpi-card">
          <p className="eyebrow" style={{ marginTop: 0 }}>
            Catalogue &amp; Imagery
          </p>
          <div className="admin-kpi-value">
            {ov ? `${ov.sites_published} / ${ov.sites_total}` : "..."}
          </div>
          <p className="admin-kpi-meta">
            {ov
              ? `${ov.sites_draft} draft · ${ov.sites_verified} verified · ${ov.sites_archived} archived · ${ov.media_total} media assets`
              : "Loading catalogue summary..."}
          </p>
        </article>

        <article className="glass-panel admin-kpi-card">
          <p className="eyebrow" style={{ marginTop: 0 }}>
            Imports &amp; Simulations
          </p>
          <div className="admin-kpi-value">
            {ov ? `${ov.imports_open} open / ${ov.imports_total}` : "..."}
          </div>
          <p className="admin-kpi-meta">
            {ov
              ? `${ov.simulations_total} SPICE & LOLA DEM simulation runs logged`
              : "Loading pipeline telemetry..."}
          </p>
        </article>

        <article className="glass-panel admin-kpi-card">
          <p className="eyebrow" style={{ marginTop: 0 }}>
            CODEX &amp; Platform Security
          </p>
          {ov && ov.codex_controllers_total !== null ? (
            <>
              <div className="admin-kpi-value">
                {ov.codex_controllers_online ?? 0} / {ov.codex_controllers_total} online
              </div>
              <p className="admin-kpi-meta">
                Transport: <strong>{ov.codex_transport_mode ?? "mock"}</strong> ·{" "}
                {ov.active_firmware_versions_count ?? 0} active firmware
                {ov.recent_audit_count_24h !== null &&
                  ` · ${ov.recent_audit_count_24h} audit events (24h)`}
                {ov.degraded_components_count !== null &&
                  ` · ${ov.degraded_components_count} degraded probes`}
              </p>
            </>
          ) : ov && ov.recent_audit_count_24h !== null ? (
            <>
              <div className="admin-kpi-value">{ov.recent_audit_count_24h} events (24h)</div>
              <p className="admin-kpi-meta">
                {ov.degraded_components_count ?? 0} degraded system probes reported
              </p>
            </>
          ) : (
            <>
              <div className="admin-kpi-value">{roles.join(", ") || "viewer"}</div>
              <p className="admin-kpi-meta">
                Scoped to authorized catalogue and editorial workflows.
              </p>
            </>
          )}
        </article>
      </section>

      {/* Row 2: Role-Filtered Quick-Action Workspace Launcher */}
      <section className="admin-dashboard-row admin-actions-row" aria-label="Admin portal modules">
        {visibleActions.map((action) => (
          <article key={action.to} className="glass-panel admin-action-card">
            <p className="eyebrow" style={{ marginTop: 0 }}>
              {action.eyebrow}
            </p>
            <h2 style={{ margin: "0.2rem 0 0.4rem", fontSize: "1.08rem" }}>{action.title}</h2>
            <p
              style={{
                margin: "0 0 0.85rem",
                color: "var(--text-secondary)",
                fontSize: "0.86rem",
                lineHeight: 1.45,
              }}
            >
              {action.description}
            </p>
            <Link to={action.to} className="btn btn-primary" style={{ marginTop: "auto" }}>
              {action.cta}
            </Link>
          </article>
        ))}
      </section>

      {overviewQuery.isError && (
        <div className="notice-banner error" role="alert">
          <span>
            {overviewQuery.error instanceof Error
              ? overviewQuery.error.message
              : "Failed to load admin overview."}
          </span>
        </div>
      )}
    </div>
  );
}

export function AdminDashboardPage() {
  return (
    <AdminLayout
      title="Operations Overview"
      subtitle="Role-scoped operational status across landing-site curation, dataset ingestion, CODEX hardware, and system telemetry."
    >
      {(admin) => <DashboardContent admin={admin} />}
    </AdminLayout>
  );
}
