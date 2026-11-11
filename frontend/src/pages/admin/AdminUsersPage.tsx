import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AdminLayout } from "../../admin/AdminLayout";
import {
  adminQueryKeys,
  createAdminUser,
  fetchAdminRoles,
  fetchAdminUsers,
  resetAdminUserPassword,
  revokeAdminUserSessions,
  updateAdminUser,
  type AdminUserOut,
} from "../../api/adminEndpoints";
import type { AdminProfileOut } from "../../api/endpoints";

function UsersWorkbench({ admin }: { admin: AdminProfileOut }) {
  const queryClient = useQueryClient();
  const [notice, setNotice] = useState<{ kind: "cyan" | "error"; text: string } | null>(null);

  // Create user modal
  const [createOpen, setCreateOpen] = useState(false);
  const [newUsername, setNewUsername] = useState("");
  const [newDisplay, setNewDisplay] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRoles, setNewRoles] = useState<string[]>(["viewer"]);
  const [newMustRotate, setNewMustRotate] = useState(true);

  // Edit user modal
  const [editing, setEditing] = useState<AdminUserOut | null>(null);
  const [editDisplay, setEditDisplay] = useState("");
  const [editActive, setEditActive] = useState(true);
  const [editRoles, setEditRoles] = useState<string[]>([]);
  const [editUnlock, setEditUnlock] = useState(false);

  // Reset password modal
  const [resetTarget, setResetTarget] = useState<AdminUserOut | null>(null);
  const [resetPw, setResetPw] = useState("");
  const [resetRotate, setResetRotate] = useState(true);

  const rolesQuery = useQuery({
    queryKey: adminQueryKeys.roles,
    queryFn: () => fetchAdminRoles(),
  });
  const usersQuery = useQuery({
    queryKey: adminQueryKeys.users,
    queryFn: () => fetchAdminUsers(),
  });

  const createMutation = useMutation({
    mutationFn: () =>
      createAdminUser({
        username: newUsername.trim(),
        password: newPassword,
        display_name: newDisplay.trim() || null,
        is_active: true,
        password_must_rotate: newMustRotate,
        role_keys: newRoles,
      }),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: adminQueryKeys.users });
      setCreateOpen(false);
      setNewUsername("");
      setNewDisplay("");
      setNewPassword("");
      setNewRoles(["viewer"]);
      setNotice({ kind: "cyan", text: `Provisioned operator "${created.username}".` });
    },
    onError: (err) =>
      setNotice({ kind: "error", text: err instanceof Error ? err.message : "Create failed." }),
  });

  const updateMutation = useMutation({
    mutationFn: () => {
      if (!editing) throw new Error("No user selected.");
      return updateAdminUser(editing.admin_id, {
        display_name: editDisplay.trim() || null,
        is_active: editActive,
        role_keys: editRoles,
        unlock_account: editUnlock,
      });
    },
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: adminQueryKeys.users });
      setEditing(null);
      setNotice({ kind: "cyan", text: `Updated roles & account state for "${updated.username}".` });
    },
    onError: (err) =>
      setNotice({ kind: "error", text: err instanceof Error ? err.message : "Update failed." }),
  });

  const resetMutation = useMutation({
    mutationFn: () => {
      if (!resetTarget) throw new Error("No user selected.");
      return resetAdminUserPassword(resetTarget.admin_id, {
        new_password: resetPw,
        password_must_rotate: resetRotate,
      });
    },
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: adminQueryKeys.users });
      setResetTarget(null);
      setResetPw("");
      setNotice({
        kind: "cyan",
        text: `Reset password and rotated sessions for "${updated.username}".`,
      });
    },
    onError: (err) =>
      setNotice({ kind: "error", text: err instanceof Error ? err.message : "Reset failed." }),
  });

  function toggleRole(list: string[], setList: (next: string[]) => void, key: string) {
    if (list.includes(key)) {
      if (list.length > 1) setList(list.filter((r) => r !== key));
    } else {
      setList([...list, key]);
    }
  }

  return (
    <div style={{ display: "grid", gap: "1rem" }}>
      {notice && (
        <div className={`notice-banner ${notice.kind}`} role="status">
          <span>{notice.text}</span>
        </div>
      )}

      <section className="glass-panel-strong" style={{ padding: "1.1rem" }}>
        <div className="admin-toolbar" style={{ marginBottom: "0.9rem" }}>
          <div style={{ marginRight: "auto" }}>
            <h2 style={{ margin: 0, fontSize: "1.14rem" }}>Administrator Accounts &amp; RBAC Matrix</h2>
            <p style={{ margin: "0.2rem 0 0", fontSize: "0.84rem", color: "var(--text-secondary)" }}>
              Signed in as <code>{admin.username}</code>. Self-demotion, self-deactivation, and
              removing the final <code>super_admin</code> are blocked at the API boundary.
            </p>
          </div>
          <button type="button" className="btn btn-primary" onClick={() => setCreateOpen(true)}>
            + Provision Admin User
          </button>
        </div>

        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Username</th>
                <th>Roles</th>
                <th>Status</th>
                <th>Active Sessions</th>
                <th>Failed Logins</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {(usersQuery.data ?? []).map((u) => {
                const locked = u.locked_until && new Date(u.locked_until).getTime() > Date.now();
                return (
                  <tr key={u.admin_id}>
                    <td>
                      <strong>{u.username}</strong>
                      {u.display_name && (
                        <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                          {u.display_name}
                        </div>
                      )}
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: "0.3rem", flexWrap: "wrap" }}>
                        {(u.roles ?? []).map((r) => (
                          <span key={r} className="pill-badge">
                            {r}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td>
                      <span className={`pill-badge ${u.is_active && !locked ? "ok" : "warn"}`}>
                        {locked ? "Locked" : u.is_active ? "Active" : "Disabled"}
                      </span>
                    </td>
                    <td>{u.active_sessions_count}</td>
                    <td>{u.failed_login_count}</td>
                    <td>
                      <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap" }}>
                        <button
                          type="button"
                          className="btn btn-cyan"
                          onClick={() => {
                            setEditing(u);
                            setEditDisplay(u.display_name ?? "");
                            setEditActive(u.is_active);
                            setEditRoles([...(u.roles ?? ["viewer"])]);
                            setEditUnlock(Boolean(locked));
                          }}
                        >
                          Edit Roles
                        </button>
                        <button
                          type="button"
                          className="btn"
                          onClick={() => {
                            setResetTarget(u);
                            setResetPw("");
                            setResetRotate(true);
                          }}
                        >
                          Reset PW
                        </button>
                        <button
                          type="button"
                          className="btn btn-amber"
                          onClick={async () => {
                            try {
                              const res = await revokeAdminUserSessions(u.admin_id);
                              queryClient.invalidateQueries({ queryKey: adminQueryKeys.users });
                              setNotice({
                                kind: "cyan",
                                text: `Revoked ${res.revoked_sessions_count} session(s) for "${u.username}".`,
                              });
                            } catch (err) {
                              setNotice({ kind: "error", text: String(err) });
                            }
                          }}
                        >
                          Revoke Sessions
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {createOpen && (
        <div className="modal-backdrop" role="presentation" onClick={() => setCreateOpen(false)}>
          <div
            className="glass-panel-strong"
            role="dialog"
            aria-modal="true"
            aria-label="Provision Admin User"
            style={{ width: "min(520px, 100%)", padding: "1.25rem" }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ marginTop: 0 }}>Provision Administrator</h3>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                createMutation.mutate();
              }}
              style={{ display: "grid", gap: "0.75rem" }}
            >
              <div className="admin-form-grid-2">
                <div>
                  <label className="field-label" htmlFor="nu-name">
                    Username
                  </label>
                  <input
                    id="nu-name"
                    required
                    minLength={3}
                    className="input"
                    value={newUsername}
                    onChange={(e) => setNewUsername(e.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="nu-disp">
                    Display Name
                  </label>
                  <input
                    id="nu-disp"
                    className="input"
                    value={newDisplay}
                    onChange={(e) => setNewDisplay(e.target.value)}
                  />
                </div>
              </div>
              <div>
                <label className="field-label" htmlFor="nu-pw">
                  Initial Password (&ge; 12 chars, upper/lower/digit/symbol)
                </label>
                <input
                  id="nu-pw"
                  type="password"
                  required
                  minLength={12}
                  className="input"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                />
              </div>
              <div>
                <span className="field-label">Assigned Roles</span>
                <div style={{ display: "flex", gap: "0.65rem", flexWrap: "wrap", marginTop: "0.35rem" }}>
                  {(rolesQuery.data ?? []).map((r) => (
                    <label key={r.role_id} style={{ display: "flex", gap: "0.35rem", fontSize: "0.85rem" }}>
                      <input
                        type="checkbox"
                        checked={newRoles.includes(r.role_key)}
                        onChange={() => toggleRole(newRoles, setNewRoles, r.role_key)}
                      />
                      {r.role_key}
                    </label>
                  ))}
                </div>
              </div>
              <label style={{ display: "flex", gap: "0.45rem", fontSize: "0.85rem" }}>
                <input
                  type="checkbox"
                  checked={newMustRotate}
                  onChange={(e) => setNewMustRotate(e.target.checked)}
                />
                Require password change on first sign-in
              </label>
              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem" }}>
                <button type="button" className="btn" onClick={() => setCreateOpen(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={createMutation.isPending}>
                  Create User
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {editing && (
        <div className="modal-backdrop" role="presentation" onClick={() => setEditing(null)}>
          <div
            className="glass-panel-strong"
            role="dialog"
            aria-modal="true"
            aria-label="Edit User Roles"
            style={{ width: "min(500px, 100%)", padding: "1.25rem" }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ marginTop: 0 }}>Edit {editing.username}</h3>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                updateMutation.mutate();
              }}
              style={{ display: "grid", gap: "0.75rem" }}
            >
              <div>
                <label className="field-label" htmlFor="eu-disp">
                  Display Name
                </label>
                <input
                  id="eu-disp"
                  className="input"
                  value={editDisplay}
                  onChange={(e) => setEditDisplay(e.target.value)}
                />
              </div>
              <div>
                <span className="field-label">RBAC Roles</span>
                <div style={{ display: "flex", gap: "0.65rem", flexWrap: "wrap", marginTop: "0.35rem" }}>
                  {(rolesQuery.data ?? []).map((r) => (
                    <label key={r.role_id} style={{ display: "flex", gap: "0.35rem", fontSize: "0.85rem" }}>
                      <input
                        type="checkbox"
                        checked={editRoles.includes(r.role_key)}
                        onChange={() => toggleRole(editRoles, setEditRoles, r.role_key)}
                      />
                      {r.role_key}
                    </label>
                  ))}
                </div>
              </div>
              <label style={{ display: "flex", gap: "0.45rem", fontSize: "0.85rem" }}>
                <input
                  type="checkbox"
                  checked={editActive}
                  onChange={(e) => setEditActive(e.target.checked)}
                />
                Account active
              </label>
              <label style={{ display: "flex", gap: "0.45rem", fontSize: "0.85rem" }}>
                <input
                  type="checkbox"
                  checked={editUnlock}
                  onChange={(e) => setEditUnlock(e.target.checked)}
                />
                Clear lockout counter
              </label>
              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem" }}>
                <button type="button" className="btn" onClick={() => setEditing(null)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={updateMutation.isPending}>
                  Save Changes
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {resetTarget && (
        <div className="modal-backdrop" role="presentation" onClick={() => setResetTarget(null)}>
          <div
            className="glass-panel-strong"
            role="dialog"
            aria-modal="true"
            aria-label="Reset Administrator Password"
            style={{ width: "min(460px, 100%)", padding: "1.25rem" }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ marginTop: 0 }}>Reset Password for {resetTarget.username}</h3>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                resetMutation.mutate();
              }}
              style={{ display: "grid", gap: "0.75rem" }}
            >
              <div>
                <label className="field-label" htmlFor="rp-pw">
                  New Password (&ge; 12 chars + upper/lower/digit/symbol)
                </label>
                <input
                  id="rp-pw"
                  type="password"
                  required
                  minLength={12}
                  className="input"
                  value={resetPw}
                  onChange={(e) => setResetPw(e.target.value)}
                />
              </div>
              <label style={{ display: "flex", gap: "0.45rem", fontSize: "0.85rem" }}>
                <input
                  type="checkbox"
                  checked={resetRotate}
                  onChange={(e) => setResetRotate(e.target.checked)}
                />
                Force password rotation on next login
              </label>
              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem" }}>
                <button type="button" className="btn" onClick={() => setResetTarget(null)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={resetMutation.isPending}>
                  Reset &amp; Revoke Sessions
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export function AdminUsersPage() {
  return (
    <AdminLayout
      title="Users & RBAC Roles"
      subtitle="Provision operators, assign least-privilege RBAC roles, clear failed-login lockouts, and revoke sessions."
      requireSuperAdmin
    >
      {(admin) => <UsersWorkbench admin={admin} />}
    </AdminLayout>
  );
}
