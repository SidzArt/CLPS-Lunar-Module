import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AdminLayout } from "../../admin/AdminLayout";
import { hasAnyRole } from "../../admin/rbac";
import {
  adminQueryKeys,
  deleteAdminMedia,
  fetchAdminMediaList,
  fetchAdminSites,
  setAdminMediaPrimary,
  updateAdminMediaMetadata,
  uploadAdminMedia,
} from "../../api/adminEndpoints";
import type { AdminProfileOut, SiteMediaOut } from "../../api/endpoints";

function MediaManager({ admin }: { admin: AdminProfileOut }) {
  const queryClient = useQueryClient();
  const canEdit = hasAnyRole(admin.roles, "site_editor");

  const [filterSiteId, setFilterSiteId] = useState<string>("");
  const [uploadSiteId, setUploadSiteId] = useState<string>("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadAlt, setUploadAlt] = useState("");
  const [uploadCaption, setUploadCaption] = useState("");
  const [uploadCredit, setUploadCredit] = useState("");
  const [uploadPrimary, setUploadPrimary] = useState(false);

  const [editing, setEditing] = useState<SiteMediaOut | null>(null);
  const [editCaption, setEditCaption] = useState("");
  const [editCredit, setEditCredit] = useState("");
  const [editAlt, setEditAlt] = useState("");
  const [editOrder, setEditOrder] = useState("0");

  const [notice, setNotice] = useState<{ kind: "cyan" | "error"; text: string } | null>(null);

  const sitesQuery = useQuery({
    queryKey: adminQueryKeys.sites({ page_size: 100 }),
    queryFn: () => fetchAdminSites({ page_size: 100 }),
  });

  const mediaQuery = useQuery({
    queryKey: adminQueryKeys.mediaList(filterSiteId ? Number(filterSiteId) : null),
    queryFn: () => fetchAdminMediaList(filterSiteId ? Number(filterSiteId) : null),
  });

  const uploadMutation = useMutation({
    mutationFn: () => {
      if (!uploadSiteId) throw new Error("Choose a landing site for the upload.");
      if (!uploadFile) throw new Error("Choose an image file to upload.");
      const fd = new FormData();
      fd.append("site_id", uploadSiteId);
      fd.append("file", uploadFile);
      fd.append("alt_text", uploadAlt.trim() || "Lunar site imagery");
      if (uploadCaption.trim()) fd.append("caption", uploadCaption.trim());
      if (uploadCredit.trim()) fd.append("credit", uploadCredit.trim());
      fd.append("is_primary", String(uploadPrimary));
      return uploadAdminMedia(fd);
    },
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ["admin", "media"] });
      queryClient.invalidateQueries({ queryKey: ["sites"] });
      queryClient.invalidateQueries({ queryKey: ["site"] });
      setUploadFile(null);
      setUploadAlt("");
      setUploadCaption("");
      setNotice({ kind: "cyan", text: `Uploaded media #${created.media_id} (${created.mime_type}).` });
    },
    onError: (err) =>
      setNotice({ kind: "error", text: err instanceof Error ? err.message : "Upload failed." }),
  });

  const patchMutation = useMutation({
    mutationFn: () => {
      if (!editing) throw new Error("No media asset selected.");
      return updateAdminMediaMetadata(editing.media_id, {
        caption: editCaption.trim() || null,
        credit: editCredit.trim() || null,
        alt_text: editAlt.trim() || editing.alt_text,
        display_order: Number(editOrder) || 0,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "media"] });
      queryClient.invalidateQueries({ queryKey: ["sites"] });
      queryClient.invalidateQueries({ queryKey: ["site"] });
      setEditing(null);
      setNotice({ kind: "cyan", text: "Updated media attribution & metadata." });
    },
    onError: (err) =>
      setNotice({ kind: "error", text: err instanceof Error ? err.message : "Metadata update failed." }),
  });

  const mediaItems = (mediaQuery.data?.items ?? []) as unknown as SiteMediaOut[];
  const orphans = mediaQuery.data?.orphan_files ?? [];
  const siteNameById = new Map(
    (sitesQuery.data?.items ?? []).map((s) => [s.site_id, `${s.site_name} (${s.site_code})`]),
  );

  return (
    <div style={{ display: "grid", gap: "1rem" }}>
      {notice && (
        <div className={`notice-banner ${notice.kind}`} role="status">
          <span>{notice.text}</span>
        </div>
      )}

      {canEdit && (
        <section className="glass-panel-strong" style={{ padding: "1.1rem" }}>
          <h2 style={{ marginTop: 0, fontSize: "1.12rem" }}>Upload New Media Asset (WebP Pipeline)</h2>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              uploadMutation.mutate();
            }}
            style={{ display: "grid", gap: "0.75rem" }}
          >
            <div className="admin-form-grid-3">
              <div>
                <label className="field-label" htmlFor="media-site">
                  Target Site
                </label>
                <select
                  id="media-site"
                  className="input"
                  required
                  value={uploadSiteId}
                  onChange={(e) => setUploadSiteId(e.target.value)}
                >
                  <option value="">Select Landing Site...</option>
                  {(sitesQuery.data?.items ?? []).map((s) => (
                    <option key={s.site_id} value={s.site_id}>
                      {s.site_name} ({s.site_code})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="field-label" htmlFor="media-file">
                  Image File
                </label>
                <input
                  id="media-file"
                  type="file"
                  accept="image/*"
                  required
                  className="input"
                  onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)}
                />
              </div>
              <div>
                <label className="field-label" htmlFor="media-alt">
                  Alt Text
                </label>
                <input
                  id="media-alt"
                  className="input"
                  required
                  value={uploadAlt}
                  onChange={(e) => setUploadAlt(e.target.value)}
                />
              </div>
            </div>
            <div className="admin-form-grid-2">
              <div>
                <label className="field-label" htmlFor="media-caption">
                  Caption
                </label>
                <input
                  id="media-caption"
                  className="input"
                  value={uploadCaption}
                  onChange={(e) => setUploadCaption(e.target.value)}
                />
              </div>
              <div>
                <label className="field-label" htmlFor="media-credit">
                  Credit / Agency
                </label>
                <input
                  id="media-credit"
                  className="input"
                  value={uploadCredit}
                  onChange={(e) => setUploadCredit(e.target.value)}
                />
              </div>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.6rem" }}>
              <label style={{ display: "flex", alignItems: "center", gap: "0.45rem", fontSize: "0.86rem" }}>
                <input
                  type="checkbox"
                  checked={uploadPrimary}
                  onChange={(e) => setUploadPrimary(e.target.checked)}
                />
                Mark as primary site thumbnail
              </label>
              <button type="submit" className="btn btn-primary" disabled={uploadMutation.isPending}>
                {uploadMutation.isPending ? "Converting & Storing..." : "Upload Media"}
              </button>
            </div>
          </form>
        </section>
      )}

      <section className="glass-panel-strong" style={{ padding: "1.1rem" }}>
        <div className="admin-toolbar" style={{ marginBottom: "0.9rem" }}>
          <h2 style={{ margin: 0, fontSize: "1.12rem", marginRight: "auto" }}>
            Media Gallery ({mediaQuery.data?.total ?? mediaItems.length})
          </h2>
          <select
            className="input"
            aria-label="Filter media by site"
            value={filterSiteId}
            onChange={(e) => setFilterSiteId(e.target.value)}
            style={{ width: "auto", minWidth: "220px" }}
          >
            <option value="">All Landing Sites</option>
            {(sitesQuery.data?.items ?? []).map((s) => (
              <option key={s.site_id} value={s.site_id}>
                {s.site_name}
              </option>
            ))}
          </select>
        </div>

        <div className="admin-media-grid">
          {mediaItems.map((m) => (
            <article key={m.media_id} className="glass-panel" style={{ padding: "0.8rem", display: "grid", gap: "0.5rem" }}>
              <img
                src={m.thumbnail_url || m.image_url}
                alt={m.alt_text}
                style={{ width: "100%", height: "145px", objectFit: "cover", borderRadius: "8px" }}
              />
              <div style={{ fontSize: "0.84rem" }}>
                <strong>{m.caption || m.original_filename || `Asset #${m.media_id}`}</strong>
                <div style={{ color: "var(--text-muted)", fontSize: "0.76rem" }}>
                  {siteNameById.get(m.site_id) ?? `Site #${m.site_id}`} · {m.is_primary ? "Primary" : "Secondary"}
                </div>
              </div>
              {canEdit && (
                <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap" }}>
                  <button
                    type="button"
                    className="btn"
                    onClick={() => {
                      setEditing(m);
                      setEditCaption(m.caption ?? "");
                      setEditCredit(m.credit ?? "");
                      setEditAlt(m.alt_text);
                      setEditOrder(String(m.display_order));
                    }}
                  >
                    Metadata
                  </button>
                  {!m.is_primary && (
                    <button
                      type="button"
                      className="btn btn-cyan"
                      onClick={async () => {
                        await setAdminMediaPrimary(m.media_id);
                        queryClient.invalidateQueries({ queryKey: ["admin", "media"] });
                        queryClient.invalidateQueries({ queryKey: ["sites"] });
                        queryClient.invalidateQueries({ queryKey: ["site"] });
                      }}
                    >
                      Primary
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn btn-amber"
                    onClick={async () => {
                      await deleteAdminMedia(m.media_id);
                      queryClient.invalidateQueries({ queryKey: ["admin", "media"] });
                      queryClient.invalidateQueries({ queryKey: ["sites"] });
                      queryClient.invalidateQueries({ queryKey: ["site"] });
                    }}
                  >
                    Delete
                  </button>
                </div>
              )}
            </article>
          ))}
        </div>
      </section>

      <section className="glass-panel-strong" style={{ padding: "1.1rem" }}>
        <h2 style={{ marginTop: 0, fontSize: "1.08rem" }}>
          Storage Orphan Diagnostics ({orphans.length})
        </h2>
        <p style={{ marginTop: 0, fontSize: "0.85rem", color: "var(--text-secondary)" }}>
          Files detected on backend media storage without matching <code>site_media</code> rows.
        </p>
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Relative Storage Path</th>
                <th>Size (bytes)</th>
              </tr>
            </thead>
            <tbody>
              {orphans.length === 0 ? (
                <tr>
                  <td colSpan={2}>Zero unreferenced orphan media files detected.</td>
                </tr>
              ) : (
                orphans.map((o) => (
                  <tr key={o.relative_path}>
                    <td>
                      <code>{o.relative_path}</code>
                    </td>
                    <td>{o.size_bytes.toLocaleString()}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {editing && (
        <div className="modal-backdrop" role="presentation" onClick={() => setEditing(null)}>
          <div
            className="glass-panel-strong"
            role="dialog"
            aria-modal="true"
            aria-label="Edit Media Metadata"
            style={{ width: "min(480px, 100%)", padding: "1.25rem" }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ marginTop: 0 }}>Edit Media #{editing.media_id} Metadata</h3>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                patchMutation.mutate();
              }}
              style={{ display: "grid", gap: "0.75rem" }}
            >
              <div>
                <label className="field-label" htmlFor="ed-m-alt">
                  Alt Text
                </label>
                <input
                  id="ed-m-alt"
                  className="input"
                  value={editAlt}
                  onChange={(e) => setEditAlt(e.target.value)}
                />
              </div>
              <div>
                <label className="field-label" htmlFor="ed-m-cap">
                  Caption
                </label>
                <input
                  id="ed-m-cap"
                  className="input"
                  value={editCaption}
                  onChange={(e) => setEditCaption(e.target.value)}
                />
              </div>
              <div className="admin-form-grid-2">
                <div>
                  <label className="field-label" htmlFor="ed-m-cred">
                    Credit
                  </label>
                  <input
                    id="ed-m-cred"
                    className="input"
                    value={editCredit}
                    onChange={(e) => setEditCredit(e.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="ed-m-ord">
                    Display Order
                  </label>
                  <input
                    id="ed-m-ord"
                    type="number"
                    className="input"
                    value={editOrder}
                    onChange={(e) => setEditOrder(e.target.value)}
                  />
                </div>
              </div>
              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem" }}>
                <button type="button" className="btn" onClick={() => setEditing(null)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={patchMutation.isPending}>
                  Save Metadata
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export function AdminMediaPage() {
  return (
    <AdminLayout
      title="Media Asset Library"
      subtitle="Upload normalized WebP media assets, assign primary thumbnails, update attributions, and audit orphan files."
      requiredRoles={["site_editor", "research_admin", "system_admin", "viewer"]}
    >
      {(admin) => <MediaManager admin={admin} />}
    </AdminLayout>
  );
}

