import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { AdminLayout } from "../../admin/AdminLayout";
import { hasAnyRole } from "../../admin/rbac";
import {
  adminQueryKeys,
  archiveAdminSite,
  createAdminSite,
  deleteAdminSite,
  fetchAdminRegions,
  fetchAdminSites,
} from "../../api/adminEndpoints";
import type { AdminProfileOut } from "../../api/endpoints";

function SitesManager({ admin }: { admin: AdminProfileOut }) {
  const queryClient = useQueryClient();
  const canEdit = hasAnyRole(admin.roles, "site_editor", "research_admin");
  const canDelete = hasAnyRole(admin.roles, "system_admin");

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [regionFilter, setRegionFilter] = useState<string>("");
  const [sortBy, setSortBy] = useState<string>("updated_at");
  const [page, setPage] = useState(1);

  const [createOpen, setCreateOpen] = useState(false);
  const [siteCode, setSiteCode] = useState("");
  const [siteName, setSiteName] = useState("");
  const [siteSlug, setSiteSlug] = useState("");
  const [regionId, setRegionId] = useState<string>("");
  const [lat, setLat] = useState("-85.0");
  const [lon, setLon] = useState("0.0");
  const [elevation, setElevation] = useState("");
  const [terrainType, setTerrainType] = useState("");
  const [overviewSummary, setOverviewSummary] = useState("");
  const [catalogueStatus, setCatalogueStatus] = useState("draft");

  const [notice, setNotice] = useState<{ kind: "cyan" | "error"; text: string } | null>(null);

  const regionsQuery = useQuery({
    queryKey: adminQueryKeys.regions,
    queryFn: () => fetchAdminRegions(),
  });

  const queryParams = {
    page,
    page_size: 25,
    catalogue_status: statusFilter || undefined,
    region_id: regionFilter ? Number(regionFilter) : undefined,
    search: search.trim() || undefined,
    sort_by: sortBy,
  };

  const sitesQuery = useQuery({
    queryKey: adminQueryKeys.sites(queryParams),
    queryFn: () => fetchAdminSites(queryParams),
  });

  const createMutation = useMutation({
    mutationFn: () =>
      createAdminSite({
        site_code: siteCode.trim(),
        site_name: siteName.trim(),
        site_slug: siteSlug.trim() || null,
        region_id: regionId ? Number(regionId) : null,
        latitude_deg: Number(lat),
        longitude_deg: Number(lon),
        elevation_m: elevation.trim() ? Number(elevation) : null,
        terrain_type: terrainType.trim() || null,
        overview_summary: overviewSummary.trim() || null,
        catalogue_status: catalogueStatus,
        coordinate_reference: "MOON_ME (IAU/NAIF Mean Earth/Polar Axis)",
      }),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ["admin", "sites"] });
      queryClient.invalidateQueries({ queryKey: adminQueryKeys.overview });
      queryClient.invalidateQueries({ queryKey: ["sites"] });
      setNotice({
        kind: "cyan",
        text: `Created landing site "${created.site_name}" (${created.site_code}) in status "${created.catalogue_status}".`,
      });
      setCreateOpen(false);
      setSiteCode("");
      setSiteName("");
      setSiteSlug("");
      setOverviewSummary("");
    },
    onError: (err) => {
      setNotice({
        kind: "error",
        text: err instanceof Error ? err.message : "Failed to create landing site.",
      });
    },
  });

  const archiveMutation = useMutation({
    mutationFn: (id: number) => archiveAdminSite(id),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ["admin", "sites"] });
      queryClient.invalidateQueries({ queryKey: adminQueryKeys.overview });
      queryClient.invalidateQueries({ queryKey: ["sites"] });
      queryClient.invalidateQueries({ queryKey: ["site"] });
      setNotice({ kind: "cyan", text: `Archived "${updated.site_name}".` });
    },
    onError: (err) => {
      setNotice({
        kind: "error",
        text: err instanceof Error ? err.message : "Failed to archive site.",
      });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteAdminSite(id),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ["admin", "sites"] });
      queryClient.invalidateQueries({ queryKey: adminQueryKeys.overview });
      queryClient.invalidateQueries({ queryKey: ["sites"] });
      queryClient.invalidateQueries({ queryKey: ["site"] });
      setNotice({ kind: "cyan", text: `Deleted site #${res.site_id}.` });
    },
    onError: (err) => {
      setNotice({
        kind: "error",
        text: err instanceof Error ? err.message : "Unable to delete site.",
      });
    },
  });

  const items = sitesQuery.data?.items ?? [];

  return (
    <div style={{ display: "grid", gap: "1rem" }}>
      {notice && (
        <div className={`notice-banner ${notice.kind}`} role="status">
          <span>{notice.text}</span>
        </div>
      )}

      <section className="glass-panel-strong" style={{ padding: "1.1rem" }}>
        <div className="admin-toolbar">
          <input
            type="search"
            className="input"
            aria-label="Search landing sites"
            placeholder="Filter by site name, code, or summary..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            style={{ flex: "1 1 220px" }}
          />
          <select
            className="input"
            aria-label="Filter by status"
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
            style={{ width: "auto", minWidth: "145px" }}
          >
            <option value="">All Statuses</option>
            <option value="published">published</option>
            <option value="verified">verified</option>
            <option value="draft">draft</option>
            <option value="archived">archived</option>
          </select>
          <select
            className="input"
            aria-label="Filter by region"
            value={regionFilter}
            onChange={(e) => {
              setRegionFilter(e.target.value);
              setPage(1);
            }}
            style={{ width: "auto", minWidth: "165px" }}
          >
            <option value="">All NASA Regions</option>
            {(regionsQuery.data ?? []).map((reg) => (
              <option key={reg.region_id} value={reg.region_id}>
                {reg.region_name}
              </option>
            ))}
          </select>
          <select
            className="input"
            aria-label="Sort sites"
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            style={{ width: "auto", minWidth: "155px" }}
          >
            <option value="updated_at">Sort: Recently Updated</option>
            <option value="name">Sort: Name (A–Z)</option>
            <option value="elevation_desc">Sort: Highest Elevation</option>
            <option value="elevation_asc">Sort: Lowest Elevation</option>
          </select>
          {canEdit && (
            <button type="button" className="btn btn-primary" onClick={() => setCreateOpen(true)}>
              + New Site
            </button>
          )}
        </div>

        <div className="admin-table-wrap" style={{ marginTop: "0.9rem" }}>
          <table className="admin-table">
            <thead>
              <tr>
                <th>Code</th>
                <th>Site Name</th>
                <th>Region</th>
                <th>Coordinates (MOON_ME)</th>
                <th>Elevation</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {sitesQuery.isLoading ? (
                <tr>
                  <td colSpan={7}>Loading catalogue entries...</td>
                </tr>
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan={7}>No landing sites match the selected filters.</td>
                </tr>
              ) : (
                items.map((site) => (
                  <tr key={site.site_id}>
                    <td>
                      <code>{site.site_code}</code>
                    </td>
                    <td>
                      <strong>{site.site_name}</strong>
                      <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                        /{site.site_slug}
                      </div>
                    </td>
                    <td>{site.region_name ?? "Unassigned"}</td>
                    <td>
                      {site.latitude_deg.toFixed(3)} deg, {site.longitude_deg.toFixed(3)} deg
                    </td>
                    <td>
                      {site.elevation_m !== null && site.elevation_m !== undefined
                        ? `${site.elevation_m.toFixed(0)} m`
                        : "—"}
                    </td>
                    <td>
                      <span
                        className={`pill-badge ${
                          site.catalogue_status === "published"
                            ? "ok"
                            : site.catalogue_status === "archived"
                              ? "danger"
                              : "warn"
                        }`}
                      >
                        {site.catalogue_status}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
                        <Link className="btn btn-cyan" to={`/admin/sites/${site.site_id}`}>
                          Edit
                        </Link>
                        {site.catalogue_status === "published" && (
                          <Link className="btn" to={`/sites/${site.site_slug}`}>
                            Public
                          </Link>
                        )}
                        {canEdit && site.catalogue_status !== "archived" && (
                          <button
                            type="button"
                            className="btn"
                            disabled={archiveMutation.isPending}
                            onClick={() => archiveMutation.mutate(site.site_id)}
                          >
                            Archive
                          </button>
                        )}
                        {canDelete && site.catalogue_status !== "published" && (
                          <button
                            type="button"
                            className="btn btn-amber"
                            disabled={deleteMutation.isPending}
                            onClick={() => deleteMutation.mutate(site.site_id)}
                          >
                            Delete
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

        {sitesQuery.data && (
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginTop: "0.9rem",
              fontSize: "0.85rem",
              color: "var(--text-secondary)",
            }}
          >
            <span>
              Showing {items.length} of {sitesQuery.data.total} sites (page {page})
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
                disabled={!sitesQuery.data.has_more}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </button>
            </div>
          </div>
        )}
      </section>

      {createOpen && (
        <div className="modal-backdrop" role="presentation" onClick={() => setCreateOpen(false)}>
          <div
            className="glass-panel-strong"
            role="dialog"
            aria-modal="true"
            aria-label="Create Landing Site"
            style={{ width: "min(620px, 100%)", padding: "1.35rem", maxHeight: "90vh", overflowY: "auto" }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 style={{ marginTop: 0 }}>Create Candidate Landing Site</h2>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                createMutation.mutate();
              }}
              style={{ display: "grid", gap: "0.8rem" }}
            >
              <div className="admin-form-grid-2">
                <div>
                  <label className="field-label" htmlFor="new-site-code">
                    Site Code
                  </label>
                  <input
                    id="new-site-code"
                    required
                    className="input"
                    placeholder="ART3-NEW-01"
                    value={siteCode}
                    onChange={(e) => setSiteCode(e.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="new-site-name">
                    Site Name
                  </label>
                  <input
                    id="new-site-name"
                    required
                    className="input"
                    placeholder="Malapert Massif Bench"
                    value={siteName}
                    onChange={(e) => setSiteName(e.target.value)}
                  />
                </div>
              </div>

              <div className="admin-form-grid-2">
                <div>
                  <label className="field-label" htmlFor="new-site-slug">
                    URL Slug (optional)
                  </label>
                  <input
                    id="new-site-slug"
                    className="input"
                    placeholder="malapert-massif-bench"
                    value={siteSlug}
                    onChange={(e) => setSiteSlug(e.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="new-site-region">
                    NASA Exploration Region
                  </label>
                  <select
                    id="new-site-region"
                    className="input"
                    value={regionId}
                    onChange={(e) => setRegionId(e.target.value)}
                  >
                    <option value="">Unassigned</option>
                    {(regionsQuery.data ?? []).map((reg) => (
                      <option key={reg.region_id} value={reg.region_id}>
                        {reg.region_name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="admin-form-grid-3">
                <div>
                  <label className="field-label" htmlFor="new-site-lat">
                    Latitude (deg)
                  </label>
                  <input
                    id="new-site-lat"
                    type="number"
                    step="0.0001"
                    min={-90}
                    max={90}
                    required
                    className="input"
                    value={lat}
                    onChange={(e) => setLat(e.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="new-site-lon">
                    Longitude (deg)
                  </label>
                  <input
                    id="new-site-lon"
                    type="number"
                    step="0.0001"
                    min={-180}
                    max={180}
                    required
                    className="input"
                    value={lon}
                    onChange={(e) => setLon(e.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="new-site-elev">
                    Elevation (m)
                  </label>
                  <input
                    id="new-site-elev"
                    type="number"
                    step="1"
                    className="input"
                    value={elevation}
                    onChange={(e) => setElevation(e.target.value)}
                  />
                </div>
              </div>

              <div className="admin-form-grid-2">
                <div>
                  <label className="field-label" htmlFor="new-site-terrain">
                    Terrain Type
                  </label>
                  <input
                    id="new-site-terrain"
                    className="input"
                    value={terrainType}
                    onChange={(e) => setTerrainType(e.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="new-site-status">
                    Catalogue Status
                  </label>
                  <select
                    id="new-site-status"
                    className="input"
                    value={catalogueStatus}
                    onChange={(e) => setCatalogueStatus(e.target.value)}
                  >
                    <option value="draft">draft</option>
                    <option value="verified">verified</option>
                    <option value="published">published</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="field-label" htmlFor="new-site-summary">
                  Overview Summary
                </label>
                <textarea
                  id="new-site-summary"
                  rows={3}
                  className="input"
                  value={overviewSummary}
                  onChange={(e) => setOverviewSummary(e.target.value)}
                />
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.6rem" }}>
                <button type="button" className="btn" onClick={() => setCreateOpen(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={createMutation.isPending}>
                  {createMutation.isPending ? "Creating..." : "Create Landing Site"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export function AdminSitesPage() {
  return (
    <AdminLayout
      title="Landing Sites Catalogue"
      subtitle="Browse draft, verified, published, and archived lunar candidate landing sites."
      requiredRoles={["site_editor", "research_admin", "system_admin", "viewer"]}
    >
      {(admin) => <SitesManager admin={admin} />}
    </AdminLayout>
  );
}
