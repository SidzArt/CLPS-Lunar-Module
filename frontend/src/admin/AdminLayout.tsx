import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { NavLink, Navigate, useLocation, useNavigate } from "react-router-dom";
import { adminChangePassword, adminQueryKeys } from "../api/adminEndpoints";
import { ApiClientError } from "../api/client";
import { adminLogout, fetchAdminProfile, type AdminProfileOut } from "../api/endpoints";
import { SiteHeader } from "../components/SiteHeader";
import { HeadTags } from "../seo/HeadTags";
import { LunarMoonCanvas } from "../three/LunarMoonCanvas";
import { hasAnyRole, isSuperAdmin } from "./rbac";

export interface AdminLayoutProps {
  title: string;
  subtitle?: string;
  requiredRoles?: string[];
  requireSuperAdmin?: boolean;
  children: (admin: AdminProfileOut) => ReactNode;
}

interface NavItem {
  to: string;
  label: string;
  end?: boolean;
  visible: (roles: string[]) => boolean;
}

const ADMIN_NAV_ITEMS: NavItem[] = [
  { to: "/admin", label: "Overview", end: true, visible: () => true },
  {
    to: "/admin/sites",
    label: "Sites",
    visible: (r) => hasAnyRole(r, "site_editor", "research_admin", "system_admin", "viewer"),
  },
  {
    to: "/admin/media",
    label: "Media",
    visible: (r) => hasAnyRole(r, "site_editor", "research_admin", "system_admin", "viewer"),
  },
  {
    to: "/admin/imports",
    label: "Imports & Sources",
    visible: (r) => hasAnyRole(r, "research_admin", "site_editor", "system_admin"),
  },
  {
    to: "/admin/codex",
    label: "CODEX Hardware",
    visible: (r) => hasAnyRole(r, "hardware_admin", "system_admin"),
  },
  {
    to: "/admin/codex/firmware",
    label: "Firmware Editor",
    visible: (r) => hasAnyRole(r, "hardware_admin", "system_admin"),
  },
  {
    to: "/admin/audit",
    label: "Audit & Health",
    visible: (r) => hasAnyRole(r, "system_admin"),
  },
  {
    to: "/admin/users",
    label: "Users & Roles",
    visible: (r) => isSuperAdmin(r),
  },
];

export function AdminLayout({
  title,
  subtitle,
  requiredRoles,
  requireSuperAdmin = false,
  children,
}: AdminLayoutProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [passwordModalOpen, setPasswordModalOpen] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [pwError, setPwError] = useState<string | null>(null);
  const [pwSuccess, setPwSuccess] = useState<string | null>(null);
  const [pwSaving, setPwSaving] = useState(false);

  const meQuery = useQuery({
    queryKey: adminQueryKeys.me,
    queryFn: () => fetchAdminProfile(),
    retry: false,
    staleTime: 60_000,
  });

  async function handleSignOut() {
    try {
      await adminLogout();
    } catch {
      // Proceed cleanly even if session already expired
    } finally {
      queryClient.removeQueries({ queryKey: ["admin"] });
      navigate("/admin/login", { replace: true });
    }
  }

  async function handlePasswordSubmit(event: React.FormEvent) {
    event.preventDefault();
    setPwError(null);
    setPwSuccess(null);
    if (newPassword !== confirmPassword) {
      setPwError("New password confirmation does not match.");
      return;
    }
    setPwSaving(true);
    try {
      await adminChangePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      await queryClient.invalidateQueries({ queryKey: adminQueryKeys.me });
      setPwSuccess("Password updated and all active sessions rotated cleanly.");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      setPwError(err instanceof Error ? err.message : "Failed to update password.");
    } finally {
      setPwSaving(false);
    }
  }

  const adminMeta = (
    <HeadTags
      meta={{
        title: `${title} — CLPS Admin Portal`,
        description: subtitle || "Authenticated CLPS Luna Browser operations workspace.",
        canonicalPath: location.pathname,
        robots: "noindex,nofollow",
        ogType: "website",
        breadcrumbs: [
          { name: "Home", path: "/" },
          { name: "Admin", path: "/admin" },
        ],
      }}
    />
  );

  if (meQuery.isLoading) {
    return (
      <div className="page-shell">
        {adminMeta}
        <div className="ambient-bg-layer" aria-hidden="true">
          <LunarMoonCanvas mode="ambient" sites={[]} />
          <div className="admin-ambient-scrim" />
        </div>
        <div className="page-content-layer">
          <SiteHeader />
          <main id="main-content" className="container" style={{ paddingTop: "3rem" }}>
            <div className="glass-panel-strong" style={{ padding: "2rem", textAlign: "center" }}>
              <p className="eyebrow" style={{ marginTop: 0 }}>
                Session Verification
              </p>
              <h1 style={{ fontSize: "1.4rem", margin: 0 }}>Checking authenticated session...</h1>
            </div>
          </main>
        </div>
      </div>
    );
  }

  if (meQuery.isError || !meQuery.data) {
    const err = meQuery.error;
    const isUnauth = err instanceof ApiClientError ? err.status === 401 || err.status === 403 : true;
    if (isUnauth) {
      return (
        <Navigate
          to="/admin/login"
          replace
          state={{ from: `${location.pathname}${location.search}` }}
        />
      );
    }
    return (
      <div className="page-shell">
        {adminMeta}
        <div className="page-content-layer">
          <SiteHeader />
          <main id="main-content" className="container">
            <div className="notice-banner error">
              <span>Unable to verify administrator session: {String(err)}</span>
            </div>
          </main>
        </div>
      </div>
    );
  }

  const admin = meQuery.data;
  const roles = admin.roles ?? [];
  const authorized = requireSuperAdmin
    ? isSuperAdmin(roles)
    : !requiredRoles || hasAnyRole(roles, ...requiredRoles);

  return (
    <div className="page-shell">
      {adminMeta}
      <div className="ambient-bg-layer" aria-hidden="true">
        <LunarMoonCanvas mode="ambient" sites={[]} />
        <div className="admin-ambient-scrim" />
      </div>

      <div className="page-content-layer">
        <SiteHeader />

        <main id="main-content" className="container admin-portal-main">
        <section
          className="glass-panel-strong admin-topbar"
          aria-label="Admin Portal navigation and session status"
        >
          <div className="admin-topbar-header">
            <div>
              <p className="eyebrow" style={{ margin: 0 }}>
                CLPS Admin Console
              </p>
              <h1 style={{ margin: "0.2rem 0 0", fontSize: "1.45rem" }}>{title}</h1>
              {subtitle && (
                <p
                  style={{
                    margin: "0.25rem 0 0",
                    color: "var(--text-secondary)",
                    fontSize: "0.88rem",
                  }}
                >
                  {subtitle}
                </p>
              )}
            </div>

            <div className="admin-session-controls">
              <span className="pill-badge ok" title={`Roles: ${roles.join(", ")}`}>
                <span className="status-dot" />
                <span>
                  {admin.username} ({roles[0] || "viewer"})
                </span>
              </span>
              <button
                type="button"
                className="btn"
                onClick={() => {
                  setPwError(null);
                  setPwSuccess(null);
                  setPasswordModalOpen(true);
                }}
              >
                Password
              </button>
              <button type="button" className="btn" onClick={handleSignOut}>
                Sign Out
              </button>
            </div>
          </div>

          <nav className="admin-subnav" aria-label="Admin sections">
            {ADMIN_NAV_ITEMS.filter((item) => item.visible(roles)).map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) => `admin-subnav-link${isActive ? " active" : ""}`}
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </section>

        {admin.password_must_rotate && (
          <div className="notice-banner warn" style={{ marginTop: "0.9rem" }}>
            <div>
              <strong>Password Rotation Required:</strong> Your administrator password was reset and
              should be changed now.
            </div>
            <button
              type="button"
              className="btn btn-amber"
              onClick={() => setPasswordModalOpen(true)}
            >
              Change Password
            </button>
          </div>
        )}

        {!authorized ? (
          <section
            className="glass-panel-strong"
            style={{ marginTop: "1rem", padding: "1.5rem" }}
            role="alert"
          >
            <p className="eyebrow" style={{ marginTop: 0 }}>
              403 Forbidden
            </p>
            <h2 style={{ marginTop: "0.25rem" }}>Insufficient Role Permissions</h2>
            <p style={{ color: "var(--text-secondary)" }}>
              Signed in as <code>{admin.username}</code> with role(s){" "}
              <code>{roles.join(", ") || "none"}</code>. Access to <strong>{title}</strong>{" "}
              requires{" "}
              <code>
                {requireSuperAdmin ? "super_admin" : requiredRoles?.join(" or ") || "authorized role"}
              </code>
              .
            </p>
          </section>
        ) : (
          <div style={{ marginTop: "1rem" }}>{children(admin)}</div>
        )}
        </main>
      </div>

      {passwordModalOpen && (
        <div className="modal-backdrop" role="presentation" onClick={() => setPasswordModalOpen(false)}>
          <div
            className="glass-panel-strong"
            role="dialog"
            aria-modal="true"
            aria-label="Change Administrator Password"
            style={{ width: "min(460px, 100%)", padding: "1.35rem" }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 style={{ marginTop: 0, fontSize: "1.2rem" }}>Change Password</h2>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>
              Minimum 12 characters with uppercase, lowercase, digit, and special character. Updating
              rotates your active session cookie and revokes older tokens.
            </p>
            {pwError && (
              <div className="notice-banner error" style={{ marginBottom: "0.75rem" }}>
                <span>{pwError}</span>
              </div>
            )}
            {pwSuccess && (
              <div className="notice-banner cyan" style={{ marginBottom: "0.75rem" }}>
                <span>{pwSuccess}</span>
              </div>
            )}
            <form onSubmit={handlePasswordSubmit} style={{ display: "grid", gap: "0.85rem" }}>
              <div>
                <label className="field-label" htmlFor="pw-current">
                  Current Password
                </label>
                <input
                  id="pw-current"
                  type="password"
                  required
                  className="input"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                />
              </div>
              <div>
                <label className="field-label" htmlFor="pw-new">
                  New Password
                </label>
                <input
                  id="pw-new"
                  type="password"
                  required
                  minLength={12}
                  className="input"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                />
              </div>
              <div>
                <label className="field-label" htmlFor="pw-confirm">
                  Confirm New Password
                </label>
                <input
                  id="pw-confirm"
                  type="password"
                  required
                  minLength={12}
                  className="input"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                />
              </div>
              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.6rem" }}>
                <button
                  type="button"
                  className="btn"
                  onClick={() => setPasswordModalOpen(false)}
                >
                  Close
                </button>
                <button type="submit" className="btn btn-primary" disabled={pwSaving}>
                  {pwSaving ? "Updating..." : "Update Password"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
