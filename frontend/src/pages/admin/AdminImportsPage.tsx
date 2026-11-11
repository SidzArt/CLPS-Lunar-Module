import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AdminLayout } from "../../admin/AdminLayout";
import { hasAnyRole } from "../../admin/rbac";
import {
  adminQueryKeys,
  commitAdminImport,
  createAdminDataSource,
  fetchAdminDataSources,
  fetchAdminImportPreview,
  fetchAdminImports,
  rollbackAdminImport,
  stageAdminImport,
  updateAdminDataSource,
  type DataSourceOut,
  type ImportPreviewOut,
} from "../../api/adminEndpoints";
import type { AdminProfileOut } from "../../api/endpoints";

function ImportsAndSourcesWorkbench({ admin }: { admin: AdminProfileOut }) {
  const queryClient = useQueryClient();
  const canImport = hasAnyRole(admin.roles, "research_admin");
  const canEditSource = hasAnyRole(admin.roles, "research_admin", "site_editor");

  const [datasetFile, setDatasetFile] = useState<File | null>(null);
  const [stageSourceId, setStageSourceId] = useState("");
  const [preview, setPreview] = useState<ImportPreviewOut | null>(null);
  const [notice, setNotice] = useState<{ kind: "cyan" | "error"; text: string } | null>(null);

  // Source creation/edit
  const [editingSource, setEditingSource] = useState<DataSourceOut | null>(null);
  const [srcTitle, setSrcTitle] = useState("");
  const [srcAgency, setSrcAgency] = useState("");
  const [srcUrl, setSrcUrl] = useState("");
  const [srcVersion, setSrcVersion] = useState("");
  const [srcLicence, setSrcLicence] = useState("");
  const [srcCitation, setSrcCitation] = useState("");

  const importsQuery = useQuery({
    queryKey: adminQueryKeys.imports(),
    queryFn: () => fetchAdminImports(),
  });

  const sourcesQuery = useQuery({
    queryKey: adminQueryKeys.sources,
    queryFn: () => fetchAdminDataSources(),
  });

  const stageMutation = useMutation({
    mutationFn: () => {
      if (!datasetFile) throw new Error("Choose a CSV, XLSX, or GeoJSON dataset file to stage.");
      const fd = new FormData();
      fd.append("file", datasetFile);
      if (stageSourceId) fd.append("source_id", stageSourceId);
      return stageAdminImport(fd);
    },
    onSuccess: (res) => {
      setPreview(res);
      setDatasetFile(null);
      queryClient.invalidateQueries({ queryKey: ["admin", "imports"] });
      setNotice({
        kind: "cyan",
        text: `Staged "${res.filename}" (Import #${res.import_id}): ${res.valid_rows_count} valid, ${res.invalid_rows_count} invalid.`,
      });
    },
    onError: (err) =>
      setNotice({ kind: "error", text: err instanceof Error ? err.message : "Staging failed." }),
  });

  const commitMutation = useMutation({
    mutationFn: (importId: number) => commitAdminImport(importId),
    onSuccess: (res) => {
      setPreview(null);
      queryClient.invalidateQueries({ queryKey: ["admin", "imports"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "sites"] });
      queryClient.invalidateQueries({ queryKey: ["sites"] });
      queryClient.invalidateQueries({ queryKey: ["site"] });
      setNotice({ kind: "cyan", text: res.message });
    },
    onError: (err) =>
      setNotice({ kind: "error", text: err instanceof Error ? err.message : "Commit failed." }),
  });

  const rollbackMutation = useMutation({
    mutationFn: (importId: number) => rollbackAdminImport(importId),
    onSuccess: (res) => {
      setPreview(null);
      queryClient.invalidateQueries({ queryKey: ["admin", "imports"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "sites"] });
      queryClient.invalidateQueries({ queryKey: ["sites"] });
      queryClient.invalidateQueries({ queryKey: ["site"] });
      setNotice({ kind: "cyan", text: res.message });
    },
    onError: (err) =>
      setNotice({ kind: "error", text: err instanceof Error ? err.message : "Rollback failed." }),
  });

  const saveSourceMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        title: srcTitle.trim(),
        agency_name: srcAgency.trim() || null,
        source_url: srcUrl.trim() || null,
        dataset_version: srcVersion.trim() || null,
        licence: srcLicence.trim() || null,
        citation_text: srcCitation.trim() || null,
      };
      if (editingSource) {
        return updateAdminDataSource(editingSource.source_id, payload);
      }
      return createAdminDataSource(payload);
    },
    onSuccess: (saved) => {
      queryClient.invalidateQueries({ queryKey: adminQueryKeys.sources });
      setEditingSource(null);
      setSrcTitle("");
      setSrcAgency("");
      setSrcUrl("");
      setSrcVersion("");
      setSrcLicence("");
      setSrcCitation("");
      setNotice({ kind: "cyan", text: `Saved Data Source #${saved.source_id}: "${saved.title}".` });
    },
    onError: (err) =>
      setNotice({ kind: "error", text: err instanceof Error ? err.message : "Source save failed." }),
  });

  return (
    <div style={{ display: "grid", gap: "1rem" }}>
      {notice && (
        <div className={`notice-banner ${notice.kind}`} role="status">
          <span>{notice.text}</span>
        </div>
      )}

      {canImport && (
        <section className="glass-panel-strong" style={{ padding: "1.1rem" }}>
          <h2 style={{ marginTop: 0, fontSize: "1.12rem" }}>Stage Dataset Import (CSV / XLSX / GeoJSON)</h2>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              stageMutation.mutate();
            }}
            className="admin-toolbar"
          >
            <input
              type="file"
              accept=".csv,.xlsx,.geojson,.json"
              className="input"
              aria-label="Dataset file"
              onChange={(e) => setDatasetFile(e.target.files?.[0] ?? null)}
              style={{ flex: "1 1 240px" }}
            />
            <select
              className="input"
              aria-label="Provenance data source"
              value={stageSourceId}
              onChange={(e) => setStageSourceId(e.target.value)}
              style={{ width: "auto", minWidth: "220px" }}
            >
              <option value="">Optional Data Source...</option>
              {(sourcesQuery.data ?? []).map((s) => (
                <option key={s.source_id} value={s.source_id}>
                  #{s.source_id}: {s.title}
                </option>
              ))}
            </select>
            <button type="submit" className="btn btn-primary" disabled={stageMutation.isPending}>
              {stageMutation.isPending ? "Staging..." : "Stage & Validate"}
            </button>
          </form>
        </section>
      )}

      {preview && (
        <section className="glass-panel-strong" style={{ padding: "1.1rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.75rem" }}>
            <div>
              <h2 style={{ margin: 0, fontSize: "1.1rem" }}>
                Validation Preview: {preview.filename} (#{preview.import_id})
              </h2>
              <p style={{ margin: "0.2rem 0 0", fontSize: "0.85rem", color: "var(--text-secondary)" }}>
                Valid: {preview.valid_rows_count} · Invalid: {preview.invalid_rows_count} · New:{" "}
                {preview.new_sites_count} · Updates: {preview.updated_sites_count}
              </p>
            </div>
            {canImport && (
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={commitMutation.isPending || preview.valid_rows_count === 0}
                  onClick={() => commitMutation.mutate(preview.import_id)}
                >
                  Commit Valid Rows
                </button>
                <button
                  type="button"
                  className="btn btn-amber"
                  disabled={rollbackMutation.isPending}
                  onClick={() => rollbackMutation.mutate(preview.import_id)}
                >
                  Rollback Stage
                </button>
              </div>
            )}
          </div>
          <div className="admin-table-wrap" style={{ marginTop: "0.75rem" }}>
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Row</th>
                  <th>Status</th>
                  <th>Action</th>
                  <th>Site Code</th>
                  <th>Site Name</th>
                  <th>Errors</th>
                </tr>
              </thead>
              <tbody>
                {(preview.rows ?? []).slice(0, 25).map((r) => (
                  <tr key={r.row_id}>
                    <td>{r.row_id}</td>
                    <td>
                      <span className={`pill-badge ${r.row_status === "valid" ? "ok" : "danger"}`}>
                        {r.row_status}
                      </span>
                    </td>
                    <td>{r.action_type}</td>
                    <td>
                      <code>{r.site_code ?? "—"}</code>
                    </td>
                    <td>{r.site_name ?? "—"}</td>
                    <td>{r.validation_errors ? JSON.stringify(r.validation_errors) : "None"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="glass-panel-strong" style={{ padding: "1.1rem" }}>
        <h2 style={{ marginTop: 0, fontSize: "1.12rem" }}>Dataset Import History</h2>
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Filename</th>
                <th>Status</th>
                <th>Row Counts</th>
                <th>Started</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {(importsQuery.data?.items ?? []).length === 0 ? (
                <tr>
                  <td colSpan={6}>No dataset imports recorded.</td>
                </tr>
              ) : (
                (importsQuery.data?.items ?? []).map((imp) => (
                  <tr key={imp.import_id}>
                    <td>#{imp.import_id}</td>
                    <td>{imp.filename}</td>
                    <td>
                      <span className="pill-badge">{imp.status}</span>
                    </td>
                    <td>
                      <code>{imp.row_counts ? JSON.stringify(imp.row_counts) : "—"}</code>
                    </td>
                    <td>{new Date(imp.started_at).toLocaleString()}</td>
                    <td>
                      <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
                        {canImport && (
                          <button
                            type="button"
                            className="btn"
                            onClick={async () => {
                              try {
                                const pv = await fetchAdminImportPreview(imp.import_id);
                                setPreview(pv);
                              } catch (err) {
                                setNotice({ kind: "error", text: String(err) });
                              }
                            }}
                          >
                            Preview
                          </button>
                        )}
                        {canImport && imp.status === "staged" && (
                          <button
                            type="button"
                            className="btn btn-primary"
                            onClick={() => commitMutation.mutate(imp.import_id)}
                          >
                            Commit
                          </button>
                        )}
                        {canImport && imp.status !== "rolled_back" && (
                          <button
                            type="button"
                            className="btn btn-amber"
                            onClick={() => rollbackMutation.mutate(imp.import_id)}
                          >
                            Rollback
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="glass-panel-strong" style={{ padding: "1.1rem", display: "grid", gap: "1rem" }}>
        <h2 style={{ margin: 0, fontSize: "1.12rem" }}>Scientific Data Sources &amp; Provenance</h2>
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Title</th>
                <th>Agency</th>
                <th>Version</th>
                <th>Licence</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {(sourcesQuery.data ?? []).map((src) => (
                <tr key={src.source_id}>
                  <td>#{src.source_id}</td>
                  <td>
                    <strong>{src.title}</strong>
                    {src.source_url && (
                      <div style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>
                        {src.source_url}
                      </div>
                    )}
                  </td>
                  <td>{src.agency_name ?? "—"}</td>
                  <td>{src.dataset_version ?? "—"}</td>
                  <td>{src.licence ?? "—"}</td>
                  <td>
                    {canEditSource && (
                      <button
                        type="button"
                        className="btn"
                        onClick={() => {
                          setEditingSource(src);
                          setSrcTitle(src.title);
                          setSrcAgency(src.agency_name ?? "");
                          setSrcUrl(src.source_url ?? "");
                          setSrcVersion(src.dataset_version ?? "");
                          setSrcLicence(src.licence ?? "");
                          setSrcCitation(src.citation_text ?? "");
                        }}
                      >
                        Edit
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {canEditSource && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              saveSourceMutation.mutate();
            }}
            className="glass-panel"
            style={{ padding: "1rem", display: "grid", gap: "0.75rem" }}
          >
            <h3 style={{ margin: 0 }}>
              {editingSource ? `Edit Source #${editingSource.source_id}` : "Add Curated Data Source"}
            </h3>
            <div className="admin-form-grid-2">
              <div>
                <label className="field-label" htmlFor="src-title">
                  Source Title
                </label>
                <input
                  id="src-title"
                  required
                  className="input"
                  value={srcTitle}
                  onChange={(e) => setSrcTitle(e.target.value)}
                />
              </div>
              <div>
                <label className="field-label" htmlFor="src-agency">
                  Agency / Institution
                </label>
                <input
                  id="src-agency"
                  className="input"
                  value={srcAgency}
                  onChange={(e) => setSrcAgency(e.target.value)}
                />
              </div>
            </div>
            <div className="admin-form-grid-3">
              <div>
                <label className="field-label" htmlFor="src-url">
                  Reference URL
                </label>
                <input
                  id="src-url"
                  className="input"
                  value={srcUrl}
                  onChange={(e) => setSrcUrl(e.target.value)}
                />
              </div>
              <div>
                <label className="field-label" htmlFor="src-ver">
                  Dataset Version
                </label>
                <input
                  id="src-ver"
                  className="input"
                  value={srcVersion}
                  onChange={(e) => setSrcVersion(e.target.value)}
                />
              </div>
              <div>
                <label className="field-label" htmlFor="src-lic">
                  Licence
                </label>
                <input
                  id="src-lic"
                  className="input"
                  value={srcLicence}
                  onChange={(e) => setSrcLicence(e.target.value)}
                />
              </div>
            </div>
            <div>
              <label className="field-label" htmlFor="src-cite">
                Citation Text
              </label>
              <input
                id="src-cite"
                className="input"
                value={srcCitation}
                onChange={(e) => setSrcCitation(e.target.value)}
              />
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem" }}>
              {editingSource && (
                <button
                  type="button"
                  className="btn"
                  onClick={() => {
                    setEditingSource(null);
                    setSrcTitle("");
                    setSrcAgency("");
                    setSrcUrl("");
                    setSrcVersion("");
                    setSrcLicence("");
                    setSrcCitation("");
                  }}
                >
                  Cancel Edit
                </button>
              )}
              <button type="submit" className="btn btn-primary" disabled={saveSourceMutation.isPending}>
                {editingSource ? "Update Data Source" : "Create Data Source"}
              </button>
            </div>
          </form>
        )}
      </section>
    </div>
  );
}

export function AdminImportsPage() {
  return (
    <AdminLayout
      title="Dataset Imports & Data Sources"
      subtitle="Stage tabular/GeoJSON imports with validation previews, commit/rollback transactions, and curate authoritative NASA/LRO sources."
      requiredRoles={["research_admin", "site_editor", "system_admin"]}
    >
      {(admin) => <ImportsAndSourcesWorkbench admin={admin} />}
    </AdminLayout>
  );
}
