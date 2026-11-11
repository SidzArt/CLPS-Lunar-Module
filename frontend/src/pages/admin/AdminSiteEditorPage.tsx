import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AdminLayout } from "../../admin/AdminLayout";
import { hasAnyRole } from "../../admin/rbac";
import {
  adminQueryKeys,
  archiveAdminSite,
  createAdminHistory,
  createAdminProCon,
  createAdminSection,
  deleteAdminHistory,
  deleteAdminMedia,
  deleteAdminProCon,
  deleteAdminSection,
  deleteAdminSite,
  fetchAdminDataSources,
  fetchAdminParameters,
  fetchAdminRegions,
  fetchAdminSiteDetail,
  fetchAdminSiteHistory,
  fetchAdminSiteMedia,
  fetchAdminSiteMetrics,
  fetchAdminSiteProsCons,
  fetchAdminSiteSections,
  setAdminMediaPrimary,
  updateAdminHistory,
  updateAdminProCon,
  updateAdminSection,
  updateAdminSite,
  uploadAdminMedia,
  upsertAdminSiteMetricsBulk,
  type SiteMetricUpsertItem,
} from "../../api/adminEndpoints";
import type { AdminProfileOut, SiteHistoryOut, SiteProConOut, SiteSectionOut } from "../../api/endpoints";

type EditorTab = "metadata" | "sections" | "pros-cons" | "history" | "metrics" | "media";

interface MetricDraftRow {
  parameter_id: number;
  parameter_key: string;
  display_name: string;
  unit: string | null;
  value_type: string;
  validation_min: number | null;
  validation_max: number | null;
  numeric_value: string;
  text_value: string;
  uncertainty_value: string;
  methodology: string;
  source_id: string;
  data_quality_status: "verified" | "estimated" | "unverified" | "pending";
  dataset_version: string;
}

function SiteEditorWorkbench({ admin, siteId }: { admin: AdminProfileOut; siteId: number }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const canEdit = hasAnyRole(admin.roles, "site_editor", "research_admin");
  const canEditMetrics = hasAnyRole(admin.roles, "research_admin", "site_editor");
  const canDeleteSite = hasAnyRole(admin.roles, "system_admin");

  const [tab, setTab] = useState<EditorTab>("metadata");
  const [notice, setNotice] = useState<{ kind: "cyan" | "error"; text: string } | null>(null);

  const siteQuery = useQuery({
    queryKey: adminQueryKeys.siteDetail(siteId),
    queryFn: () => fetchAdminSiteDetail(siteId),
  });
  const regionsQuery = useQuery({
    queryKey: adminQueryKeys.regions,
    queryFn: () => fetchAdminRegions(),
  });
  const sourcesQuery = useQuery({
    queryKey: adminQueryKeys.sources,
    queryFn: () => fetchAdminDataSources(),
  });
  const paramsQuery = useQuery({
    queryKey: adminQueryKeys.parameters,
    queryFn: () => fetchAdminParameters(),
  });

  const sectionsQuery = useQuery({
    queryKey: adminQueryKeys.siteSections(siteId),
    queryFn: () => fetchAdminSiteSections(siteId),
  });
  const prosConsQuery = useQuery({
    queryKey: adminQueryKeys.siteProsCons(siteId),
    queryFn: () => fetchAdminSiteProsCons(siteId),
  });
  const historyQuery = useQuery({
    queryKey: adminQueryKeys.siteHistory(siteId),
    queryFn: () => fetchAdminSiteHistory(siteId),
  });
  const metricsQuery = useQuery({
    queryKey: adminQueryKeys.siteMetrics(siteId),
    queryFn: () => fetchAdminSiteMetrics(siteId),
  });
  const mediaQuery = useQuery({
    queryKey: adminQueryKeys.siteMedia(siteId),
    queryFn: () => fetchAdminSiteMedia(siteId),
  });

  // Metadata state
  const [siteName, setSiteName] = useState("");
  const [regionId, setRegionId] = useState("");
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [elevation, setElevation] = useState("");
  const [terrainType, setTerrainType] = useState("");
  const [catalogueStatus, setCatalogueStatus] = useState("draft");
  const [overviewSummary, setOverviewSummary] = useState("");
  const [seoTitle, setSeoTitle] = useState("");
  const [seoDesc, setSeoDesc] = useState("");

  useEffect(() => {
    const s = siteQuery.data;
    if (!s) return;
    setSiteName(s.site_name);
    setRegionId(s.region_id !== null && s.region_id !== undefined ? String(s.region_id) : "");
    setLat(String(s.latitude_deg));
    setLon(String(s.longitude_deg));
    setElevation(s.elevation_m !== null && s.elevation_m !== undefined ? String(s.elevation_m) : "");
    setTerrainType(s.terrain_type ?? "");
    setCatalogueStatus(s.catalogue_status);
    setOverviewSummary(s.overview_summary ?? "");
    setSeoTitle(s.seo_title ?? "");
    setSeoDesc(s.seo_meta_description ?? "");
  }, [siteQuery.data]);

  const updateMetaMutation = useMutation({
    mutationFn: () =>
      updateAdminSite(siteId, {
        site_name: siteName.trim(),
        region_id: regionId ? Number(regionId) : null,
        latitude_deg: Number(lat),
        longitude_deg: Number(lon),
        elevation_m: elevation.trim() ? Number(elevation) : null,
        terrain_type: terrainType.trim() || null,
        catalogue_status: catalogueStatus,
        overview_summary: overviewSummary.trim() || null,
        seo_title: seoTitle.trim() || null,
        seo_meta_description: seoDesc.trim() || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminQueryKeys.siteDetail(siteId) });
      queryClient.invalidateQueries({ queryKey: ["admin", "sites"] });
      queryClient.invalidateQueries({ queryKey: ["sites"] });
      queryClient.invalidateQueries({ queryKey: ["site"] });
      setNotice({ kind: "cyan", text: "Landing site metadata saved." });
    },
    onError: (err) =>
      setNotice({ kind: "error", text: err instanceof Error ? err.message : "Save failed." }),
  });

  // Section editor state
  const [editingSectionId, setEditingSectionId] = useState<number | null>(null);
  const [secKey, setSecKey] = useState("overview");
  const [secTitle, setSecTitle] = useState("");
  const [secBody, setSecBody] = useState("");
  const [secOrder, setSecOrder] = useState("0");

  function startEditSection(sec: SiteSectionOut) {
    setEditingSectionId(sec.content_id);
    setSecKey(sec.section_key);
    setSecTitle(sec.title ?? "");
    setSecBody(sec.body);
    setSecOrder(String(sec.display_order));
  }

  function resetSectionForm() {
    setEditingSectionId(null);
    setSecKey("overview");
    setSecTitle("");
    setSecBody("");
    setSecOrder("0");
  }

  const saveSectionMutation = useMutation({
    mutationFn: async () => {
      if (editingSectionId !== null) {
        return updateAdminSection(siteId, editingSectionId, {
          section_key: secKey,
          title: secTitle.trim() || null,
          body: secBody,
          display_order: Number(secOrder) || 0,
        });
      }
      return createAdminSection(siteId, {
        section_key: secKey,
        title: secTitle.trim() || null,
        body: secBody,
        display_order: Number(secOrder) || 0,
        language_code: "en",
        source_status: "verified",
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminQueryKeys.siteSections(siteId) });
      queryClient.invalidateQueries({ queryKey: ["site"] });
      resetSectionForm();
      setNotice({ kind: "cyan", text: "Narrative section saved cleanly." });
    },
    onError: (err) =>
      setNotice({ kind: "error", text: err instanceof Error ? err.message : "Section save failed." }),
  });

  // Pro/Con state
  const [editingPointId, setEditingPointId] = useState<number | null>(null);
  const [pointType, setPointType] = useState<"PRO" | "CON">("PRO");
  const [pointTitle, setPointTitle] = useState("");
  const [pointBody, setPointBody] = useState("");
  const [pointNote, setPointNote] = useState("");
  const [pointSourceId, setPointSourceId] = useState("");

  function startEditPoint(pt: SiteProConOut) {
    setEditingPointId(pt.point_id);
    setPointType(pt.point_type === "CON" ? "CON" : "PRO");
    setPointTitle(pt.title ?? "");
    setPointBody(pt.body);
    setPointNote(pt.evidence_note ?? "");
    setPointSourceId(pt.source_id ? String(pt.source_id) : "");
  }

  function resetPointForm() {
    setEditingPointId(null);
    setPointType("PRO");
    setPointTitle("");
    setPointBody("");
    setPointNote("");
    setPointSourceId("");
  }

  const saveProConMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        point_type: pointType,
        title: pointTitle.trim() || null,
        body: pointBody,
        evidence_note: pointNote.trim() || null,
        source_id: pointSourceId ? Number(pointSourceId) : null,
        display_order: 0,
      };
      if (editingPointId !== null) {
        return updateAdminProCon(siteId, editingPointId, payload);
      }
      return createAdminProCon(siteId, payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminQueryKeys.siteProsCons(siteId) });
      queryClient.invalidateQueries({ queryKey: ["site"] });
      resetPointForm();
      setNotice({ kind: "cyan", text: "Advantage/limitation item saved." });
    },
    onError: (err) =>
      setNotice({ kind: "error", text: err instanceof Error ? err.message : "Save failed." }),
  });

  // History state
  const [editingHistoryId, setEditingHistoryId] = useState<number | null>(null);
  const [histDate, setHistDate] = useState("");
  const [histTitle, setHistTitle] = useState("");
  const [histDesc, setHistDesc] = useState("");
  const [histSourceId, setHistSourceId] = useState("");

  function startEditHistory(item: SiteHistoryOut) {
    setEditingHistoryId(item.history_id);
    setHistDate(item.event_date ?? "");
    setHistTitle(item.title);
    setHistDesc(item.description);
    setHistSourceId(item.source_id ? String(item.source_id) : "");
  }

  function resetHistoryForm() {
    setEditingHistoryId(null);
    setHistDate("");
    setHistTitle("");
    setHistDesc("");
    setHistSourceId("");
  }

  const saveHistoryMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        event_date: histDate || null,
        title: histTitle.trim(),
        description: histDesc.trim(),
        source_id: histSourceId ? Number(histSourceId) : null,
        display_order: 0,
      };
      if (editingHistoryId !== null) {
        return updateAdminHistory(siteId, editingHistoryId, payload);
      }
      return createAdminHistory(siteId, payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminQueryKeys.siteHistory(siteId) });
      queryClient.invalidateQueries({ queryKey: ["site"] });
      resetHistoryForm();
      setNotice({ kind: "cyan", text: "History milestone saved." });
    },
    onError: (err) =>
      setNotice({ kind: "error", text: err instanceof Error ? err.message : "History save failed." }),
  });

  // Metrics state
  const [metricRows, setMetricRows] = useState<MetricDraftRow[]>([]);

  useEffect(() => {
    const params = paramsQuery.data;
    const existing = metricsQuery.data;
    if (!params || !existing) return;
    const byParam = new Map(existing.map((m) => [m.parameter_id, m]));
    setMetricRows(
      params.map((p) => {
        const cur = byParam.get(p.parameter_id);
        return {
          parameter_id: p.parameter_id,
          parameter_key: p.parameter_key,
          display_name: p.display_name,
          unit: p.unit ?? null,
          value_type: p.value_type,
          validation_min: p.validation_min ?? null,
          validation_max: p.validation_max ?? null,
          numeric_value:
            cur && cur.numeric_value !== null && cur.numeric_value !== undefined
              ? String(cur.numeric_value)
              : "",
          text_value: cur?.text_value ?? "",
          uncertainty_value:
            cur && cur.uncertainty_value !== null && cur.uncertainty_value !== undefined
              ? String(cur.uncertainty_value)
              : "",
          methodology: cur?.methodology ?? "",
          source_id: cur?.source_id ? String(cur.source_id) : "",
          data_quality_status: (cur?.data_quality_status as MetricDraftRow["data_quality_status"]) ?? "unverified",
          dataset_version: cur?.dataset_version ?? "",
        };
      }),
    );
  }, [paramsQuery.data, metricsQuery.data]);

  const saveMetricsMutation = useMutation({
    mutationFn: async () => {
      const payloadItems: SiteMetricUpsertItem[] = [];
      for (const row of metricRows) {
        const hasVal = row.numeric_value.trim() !== "" || row.text_value.trim() !== "";
        if (!hasVal) continue;
        if (row.data_quality_status === "verified" && !row.source_id) {
          throw new Error(
            `Verified metric "${row.display_name}" requires an authoritative provenance Data Source.`,
          );
        }
        payloadItems.push({
          parameter_id: row.parameter_id,
          numeric_value: row.numeric_value.trim() ? Number(row.numeric_value) : null,
          text_value: row.text_value.trim() || null,
          uncertainty_value: row.uncertainty_value.trim() ? Number(row.uncertainty_value) : null,
          methodology: row.methodology.trim() || null,
          source_id: row.source_id ? Number(row.source_id) : null,
          data_quality_status: row.data_quality_status,
          dataset_version: row.dataset_version.trim() || null,
        });
      }
      if (payloadItems.length === 0) {
        throw new Error("Enter at least one metric value before submitting.");
      }
      return upsertAdminSiteMetricsBulk(siteId, { metrics: payloadItems });
    },
    onSuccess: (saved) => {
      queryClient.invalidateQueries({ queryKey: adminQueryKeys.siteMetrics(siteId) });
      queryClient.invalidateQueries({ queryKey: ["site"] });
      setNotice({ kind: "cyan", text: `Saved ${saved.length} scientific metrics with provenance checks.` });
    },
    onError: (err) =>
      setNotice({ kind: "error", text: err instanceof Error ? err.message : "Metric update failed." }),
  });

  // Media upload inside site editor
  const [mediaFile, setMediaFile] = useState<File | null>(null);
  const [mediaAlt, setMediaAlt] = useState("");
  const [mediaCaption, setMediaCaption] = useState("");
  const [mediaCredit, setMediaCredit] = useState("");
  const [mediaPrimary, setMediaPrimary] = useState(false);

  const uploadMediaMutation = useMutation({
    mutationFn: () => {
      if (!mediaFile) throw new Error("Choose an image file to upload.");
      const fd = new FormData();
      fd.append("site_id", String(siteId));
      fd.append("file", mediaFile);
      fd.append("alt_text", mediaAlt.trim() || `${siteQuery.data?.site_name ?? "Lunar site"} image`);
      if (mediaCaption.trim()) fd.append("caption", mediaCaption.trim());
      if (mediaCredit.trim()) fd.append("credit", mediaCredit.trim());
      fd.append("is_primary", String(mediaPrimary));
      return uploadAdminMedia(fd);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminQueryKeys.siteMedia(siteId) });
      queryClient.invalidateQueries({ queryKey: ["admin", "media"] });
      queryClient.invalidateQueries({ queryKey: ["sites"] });
      queryClient.invalidateQueries({ queryKey: ["site"] });
      setMediaFile(null);
      setMediaAlt("");
      setMediaCaption("");
      setNotice({ kind: "cyan", text: "Uploaded and converted WebP site media." });
    },
    onError: (err) =>
      setNotice({ kind: "error", text: err instanceof Error ? err.message : "Media upload failed." }),
  });

  if (siteQuery.isLoading) {
    return (
      <section className="glass-panel-strong" style={{ padding: "1.5rem" }}>
        Loading site editor...
      </section>
    );
  }

  if (siteQuery.isError || !siteQuery.data) {
    return (
      <div className="notice-banner error">
        <span>Unable to load site #{siteId}.</span>
      </div>
    );
  }

  const site = siteQuery.data;

  return (
    <div style={{ display: "grid", gap: "1rem" }}>
      {notice && (
        <div className={`notice-banner ${notice.kind}`} role="status">
          <span>{notice.text}</span>
        </div>
      )}

      <section className="glass-panel-strong" style={{ padding: "1rem 1.2rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.75rem" }}>
          <div>
            <Link to="/admin/sites" style={{ fontSize: "0.84rem", color: "var(--accent-cyan)" }}>
              &larr; Back to Sites Catalogue
            </Link>
            <h2 style={{ margin: "0.2rem 0 0", fontSize: "1.3rem" }}>
              {site.site_name} <code>({site.site_code})</code>
            </h2>
          </div>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <span className="pill-badge ok">{site.catalogue_status}</span>
            {canEdit && site.catalogue_status !== "archived" && (
              <button
                type="button"
                className="btn"
                onClick={async () => {
                  try {
                    await archiveAdminSite(siteId);
                    queryClient.invalidateQueries({ queryKey: adminQueryKeys.siteDetail(siteId) });
                    queryClient.invalidateQueries({ queryKey: ["admin", "sites"] });
                    queryClient.invalidateQueries({ queryKey: ["sites"] });
                    queryClient.invalidateQueries({ queryKey: ["site"] });
                    setNotice({ kind: "cyan", text: "Site archived." });
                  } catch (err) {
                    setNotice({ kind: "error", text: String(err) });
                  }
                }}
              >
                Archive Site
              </button>
            )}
            {canDeleteSite && site.catalogue_status !== "published" && (
              <button
                type="button"
                className="btn btn-amber"
                onClick={async () => {
                  try {
                    await deleteAdminSite(siteId);
                    navigate("/admin/sites", { replace: true });
                  } catch (err) {
                    setNotice({ kind: "error", text: String(err) });
                  }
                }}
              >
                Delete Site
              </button>
            )}
          </div>
        </div>

        <div className="admin-tab-strip" role="tablist" aria-label="Site editor tabs">
          {(
            [
              ["metadata", "Metadata"],
              ["sections", `Sections (${sectionsQuery.data?.length ?? 0})`],
              ["pros-cons", `Pros & Cons (${prosConsQuery.data?.length ?? 0})`],
              ["history", `History (${historyQuery.data?.length ?? 0})`],
              ["metrics", `Metrics (${metricsQuery.data?.length ?? 0})`],
              ["media", `Media (${mediaQuery.data?.length ?? 0})`],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={tab === key}
              className={`admin-tab-btn${tab === key ? " active" : ""}`}
              onClick={() => setTab(key)}
            >
              {label}
            </button>
          ))}
        </div>
      </section>

      {tab === "metadata" && (
        <section className="glass-panel-strong" style={{ padding: "1.25rem" }}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              updateMetaMutation.mutate();
            }}
            style={{ display: "grid", gap: "0.9rem" }}
          >
            <div className="admin-form-grid-2">
              <div>
                <label className="field-label" htmlFor="ed-name">
                  Site Name
                </label>
                <input
                  id="ed-name"
                  className="input"
                  value={siteName}
                  onChange={(e) => setSiteName(e.target.value)}
                  disabled={!canEdit}
                />
              </div>
              <div>
                <label className="field-label" htmlFor="ed-region">
                  Region
                </label>
                <select
                  id="ed-region"
                  className="input"
                  value={regionId}
                  onChange={(e) => setRegionId(e.target.value)}
                  disabled={!canEdit}
                >
                  <option value="">Unassigned</option>
                  {(regionsQuery.data ?? []).map((r) => (
                    <option key={r.region_id} value={r.region_id}>
                      {r.region_name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="admin-form-grid-3">
              <div>
                <label className="field-label" htmlFor="ed-lat">
                  Latitude (deg)
                </label>
                <input
                  id="ed-lat"
                  type="number"
                  step="0.0001"
                  className="input"
                  value={lat}
                  onChange={(e) => setLat(e.target.value)}
                  disabled={!canEdit}
                />
              </div>
              <div>
                <label className="field-label" htmlFor="ed-lon">
                  Longitude (deg)
                </label>
                <input
                  id="ed-lon"
                  type="number"
                  step="0.0001"
                  className="input"
                  value={lon}
                  onChange={(e) => setLon(e.target.value)}
                  disabled={!canEdit}
                />
              </div>
              <div>
                <label className="field-label" htmlFor="ed-elev">
                  Elevation (m)
                </label>
                <input
                  id="ed-elev"
                  type="number"
                  step="1"
                  className="input"
                  value={elevation}
                  onChange={(e) => setElevation(e.target.value)}
                  disabled={!canEdit}
                />
              </div>
            </div>

            <div className="admin-form-grid-2">
              <div>
                <label className="field-label" htmlFor="ed-terrain">
                  Terrain Classification
                </label>
                <input
                  id="ed-terrain"
                  className="input"
                  value={terrainType}
                  onChange={(e) => setTerrainType(e.target.value)}
                  disabled={!canEdit}
                />
              </div>
              <div>
                <label className="field-label" htmlFor="ed-status">
                  Catalogue Status
                </label>
                <select
                  id="ed-status"
                  className="input"
                  value={catalogueStatus}
                  onChange={(e) => setCatalogueStatus(e.target.value)}
                  disabled={!canEdit}
                >
                  <option value="draft">draft</option>
                  <option value="verified">verified</option>
                  <option value="published">published</option>
                  <option value="archived">archived</option>
                </select>
              </div>
            </div>

            <div>
              <label className="field-label" htmlFor="ed-summary">
                Overview Summary
              </label>
              <textarea
                id="ed-summary"
                rows={4}
                className="input"
                value={overviewSummary}
                onChange={(e) => setOverviewSummary(e.target.value)}
                disabled={!canEdit}
              />
            </div>

            <div className="admin-form-grid-2">
              <div>
                <label className="field-label" htmlFor="ed-seo-title">
                  SEO Title
                </label>
                <input
                  id="ed-seo-title"
                  className="input"
                  value={seoTitle}
                  onChange={(e) => setSeoTitle(e.target.value)}
                  disabled={!canEdit}
                />
              </div>
              <div>
                <label className="field-label" htmlFor="ed-seo-desc">
                  SEO Meta Description
                </label>
                <input
                  id="ed-seo-desc"
                  className="input"
                  value={seoDesc}
                  onChange={(e) => setSeoDesc(e.target.value)}
                  disabled={!canEdit}
                />
              </div>
            </div>

            {canEdit && (
              <div style={{ display: "flex", justifyContent: "flex-end" }}>
                <button type="submit" className="btn btn-primary" disabled={updateMetaMutation.isPending}>
                  {updateMetaMutation.isPending ? "Saving..." : "Save Metadata"}
                </button>
              </div>
            )}
          </form>
        </section>
      )}

      {tab === "sections" && (
        <section className="glass-panel-strong" style={{ padding: "1.25rem", display: "grid", gap: "1rem" }}>
          <div style={{ display: "grid", gap: "0.75rem" }}>
            {(sectionsQuery.data ?? []).map((sec) => (
              <article key={sec.content_id} className="glass-panel" style={{ padding: "0.95rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.6rem" }}>
                  <div>
                    <span className="pill-badge">{sec.section_key}</span>{" "}
                    <strong>{sec.title || "(Untitled Section)"}</strong>{" "}
                    <span style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>
                      order {sec.display_order}
                    </span>
                  </div>
                  {canEdit && (
                    <div style={{ display: "flex", gap: "0.4rem" }}>
                      <button type="button" className="btn" onClick={() => startEditSection(sec)}>
                        Edit
                      </button>
                      <button
                        type="button"
                        className="btn btn-amber"
                        onClick={async () => {
                          await deleteAdminSection(siteId, sec.content_id);
                          queryClient.invalidateQueries({ queryKey: adminQueryKeys.siteSections(siteId) });
                          queryClient.invalidateQueries({ queryKey: ["site"] });
                        }}
                      >
                        Delete
                      </button>
                    </div>
                  )}
                </div>
                <p style={{ margin: "0.55rem 0 0", color: "var(--text-secondary)", fontSize: "0.9rem" }}>
                  {sec.body.slice(0, 260)}
                  {sec.body.length > 260 ? "..." : ""}
                </p>
              </article>
            ))}
          </div>

          {canEdit && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                saveSectionMutation.mutate();
              }}
              className="glass-panel"
              style={{ padding: "1rem", display: "grid", gap: "0.75rem" }}
            >
              <h3 style={{ margin: 0 }}>
                {editingSectionId !== null ? `Edit Section #${editingSectionId}` : "Add Narrative Section"}
              </h3>
              <div className="admin-form-grid-3">
                <div>
                  <label className="field-label" htmlFor="sec-key">
                    Section Key
                  </label>
                  <select
                    id="sec-key"
                    className="input"
                    value={secKey}
                    onChange={(e) => setSecKey(e.target.value)}
                  >
                    <option value="overview">overview</option>
                    <option value="history">history</option>
                    <option value="geology">geology</option>
                    <option value="research">research</option>
                    <option value="mission_relevance">mission_relevance</option>
                    <option value="limitations">limitations</option>
                    <option value="other">other</option>
                  </select>
                </div>
                <div>
                  <label className="field-label" htmlFor="sec-title">
                    Title
                  </label>
                  <input
                    id="sec-title"
                    className="input"
                    value={secTitle}
                    onChange={(e) => setSecTitle(e.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="sec-order">
                    Display Order
                  </label>
                  <input
                    id="sec-order"
                    type="number"
                    className="input"
                    value={secOrder}
                    onChange={(e) => setSecOrder(e.target.value)}
                  />
                </div>
              </div>
              <div>
                <label className="field-label" htmlFor="sec-body">
                  Full Content Body
                </label>
                <textarea
                  id="sec-body"
                  required
                  rows={5}
                  className="input"
                  value={secBody}
                  onChange={(e) => setSecBody(e.target.value)}
                />
              </div>
              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem" }}>
                {editingSectionId !== null && (
                  <button type="button" className="btn" onClick={resetSectionForm}>
                    Cancel Edit
                  </button>
                )}
                <button type="submit" className="btn btn-primary" disabled={saveSectionMutation.isPending}>
                  {editingSectionId !== null ? "Update Section" : "Add Section"}
                </button>
              </div>
            </form>
          )}
        </section>
      )}

      {tab === "pros-cons" && (
        <section className="glass-panel-strong" style={{ padding: "1.25rem", display: "grid", gap: "1rem" }}>
          <div style={{ display: "grid", gap: "0.7rem" }}>
            {(prosConsQuery.data ?? []).map((pt) => (
              <article key={pt.point_id} className="glass-panel" style={{ padding: "0.9rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.6rem" }}>
                  <div>
                    <span className={`pill-badge ${pt.point_type === "PRO" ? "ok" : "warn"}`}>
                      {pt.point_type}
                    </span>{" "}
                    <strong>{pt.title || pt.point_type}</strong>
                    {pt.source_title && (
                      <span style={{ marginLeft: "0.5rem", fontSize: "0.8rem", color: "var(--text-muted)" }}>
                        Source: {pt.source_title}
                      </span>
                    )}
                  </div>
                  {canEdit && (
                    <div style={{ display: "flex", gap: "0.4rem" }}>
                      <button type="button" className="btn" onClick={() => startEditPoint(pt)}>
                        Edit
                      </button>
                      <button
                        type="button"
                        className="btn btn-amber"
                        onClick={async () => {
                          await deleteAdminProCon(siteId, pt.point_id);
                          queryClient.invalidateQueries({ queryKey: adminQueryKeys.siteProsCons(siteId) });
                          queryClient.invalidateQueries({ queryKey: ["site"] });
                        }}
                      >
                        Delete
                      </button>
                    </div>
                  )}
                </div>
                <p style={{ margin: "0.5rem 0 0", color: "var(--text-secondary)", fontSize: "0.9rem" }}>
                  {pt.body}
                </p>
              </article>
            ))}
          </div>

          {canEdit && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                saveProConMutation.mutate();
              }}
              className="glass-panel"
              style={{ padding: "1rem", display: "grid", gap: "0.75rem" }}
            >
              <h3 style={{ margin: 0 }}>
                {editingPointId !== null ? `Edit Entry #${editingPointId}` : "Add Pro / Con Point"}
              </h3>
              <div className="admin-form-grid-3">
                <div>
                  <label className="field-label" htmlFor="pc-type">
                    Type
                  </label>
                  <select
                    id="pc-type"
                    className="input"
                    value={pointType}
                    onChange={(e) => setPointType(e.target.value === "CON" ? "CON" : "PRO")}
                  >
                    <option value="PRO">PRO</option>
                    <option value="CON">CON</option>
                  </select>
                </div>
                <div>
                  <label className="field-label" htmlFor="pc-title">
                    Title
                  </label>
                  <input
                    id="pc-title"
                    className="input"
                    value={pointTitle}
                    onChange={(e) => setPointTitle(e.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="pc-src">
                    Provenance Source
                  </label>
                  <select
                    id="pc-src"
                    className="input"
                    value={pointSourceId}
                    onChange={(e) => setPointSourceId(e.target.value)}
                  >
                    <option value="">None specified</option>
                    {(sourcesQuery.data ?? []).map((src) => (
                      <option key={src.source_id} value={src.source_id}>
                        {src.title}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <div>
                <label className="field-label" htmlFor="pc-body">
                  Description
                </label>
                <textarea
                  id="pc-body"
                  required
                  rows={3}
                  className="input"
                  value={pointBody}
                  onChange={(e) => setPointBody(e.target.value)}
                />
              </div>
              <div>
                <label className="field-label" htmlFor="pc-note">
                  Evidence Note
                </label>
                <input
                  id="pc-note"
                  className="input"
                  value={pointNote}
                  onChange={(e) => setPointNote(e.target.value)}
                />
              </div>
              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem" }}>
                {editingPointId !== null && (
                  <button type="button" className="btn" onClick={resetPointForm}>
                    Cancel Edit
                  </button>
                )}
                <button type="submit" className="btn btn-primary" disabled={saveProConMutation.isPending}>
                  {editingPointId !== null ? "Update Entry" : "Add Entry"}
                </button>
              </div>
            </form>
          )}
        </section>
      )}

      {tab === "history" && (
        <section className="glass-panel-strong" style={{ padding: "1.25rem", display: "grid", gap: "1rem" }}>
          <div style={{ display: "grid", gap: "0.7rem" }}>
            {(historyQuery.data ?? []).map((h) => (
              <article key={h.history_id} className="glass-panel" style={{ padding: "0.9rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.6rem" }}>
                  <div>
                    <span className="pill-badge">{h.event_date || "Undated"}</span>{" "}
                    <strong>{h.title}</strong>
                  </div>
                  {canEdit && (
                    <div style={{ display: "flex", gap: "0.4rem" }}>
                      <button type="button" className="btn" onClick={() => startEditHistory(h)}>
                        Edit
                      </button>
                      <button
                        type="button"
                        className="btn btn-amber"
                        onClick={async () => {
                          await deleteAdminHistory(siteId, h.history_id);
                          queryClient.invalidateQueries({ queryKey: adminQueryKeys.siteHistory(siteId) });
                          queryClient.invalidateQueries({ queryKey: ["site"] });
                        }}
                      >
                        Delete
                      </button>
                    </div>
                  )}
                </div>
                <p style={{ margin: "0.45rem 0 0", color: "var(--text-secondary)", fontSize: "0.9rem" }}>
                  {h.description}
                </p>
              </article>
            ))}
          </div>

          {canEdit && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                saveHistoryMutation.mutate();
              }}
              className="glass-panel"
              style={{ padding: "1rem", display: "grid", gap: "0.75rem" }}
            >
              <h3 style={{ margin: 0 }}>
                {editingHistoryId !== null ? `Edit Milestone #${editingHistoryId}` : "Add History Milestone"}
              </h3>
              <div className="admin-form-grid-3">
                <div>
                  <label className="field-label" htmlFor="hist-date">
                    Event Date
                  </label>
                  <input
                    id="hist-date"
                    type="date"
                    className="input"
                    value={histDate}
                    onChange={(e) => setHistDate(e.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="hist-title">
                    Milestone Title
                  </label>
                  <input
                    id="hist-title"
                    required
                    className="input"
                    value={histTitle}
                    onChange={(e) => setHistTitle(e.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="hist-src">
                    Source Citation
                  </label>
                  <select
                    id="hist-src"
                    className="input"
                    value={histSourceId}
                    onChange={(e) => setHistSourceId(e.target.value)}
                  >
                    <option value="">None</option>
                    {(sourcesQuery.data ?? []).map((src) => (
                      <option key={src.source_id} value={src.source_id}>
                        {src.title}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <div>
                <label className="field-label" htmlFor="hist-desc">
                  Description
                </label>
                <textarea
                  id="hist-desc"
                  required
                  rows={3}
                  className="input"
                  value={histDesc}
                  onChange={(e) => setHistDesc(e.target.value)}
                />
              </div>
              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem" }}>
                {editingHistoryId !== null && (
                  <button type="button" className="btn" onClick={resetHistoryForm}>
                    Cancel Edit
                  </button>
                )}
                <button type="submit" className="btn btn-primary" disabled={saveHistoryMutation.isPending}>
                  {editingHistoryId !== null ? "Update Milestone" : "Add Milestone"}
                </button>
              </div>
            </form>
          )}
        </section>
      )}

      {tab === "metrics" && (
        <section className="glass-panel-strong" style={{ padding: "1.25rem" }}>
          <p style={{ marginTop: 0, color: "var(--text-secondary)", fontSize: "0.88rem" }}>
            Metrics marked <strong>verified</strong> require an authoritative provenance Data Source
            (enforced server-side with HTTP 422). Parameter validation bounds are displayed per row.
          </p>
          <div className="admin-table-wrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Parameter</th>
                  <th>Numeric Value</th>
                  <th>Uncertainty (+/-)</th>
                  <th>Quality Status</th>
                  <th>Provenance Source</th>
                </tr>
              </thead>
              <tbody>
                {metricRows.map((row, idx) => (
                  <tr key={row.parameter_id}>
                    <td>
                      <strong>{row.display_name}</strong>
                      <div style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>
                        <code>{row.parameter_key}</code>
                        {row.unit ? ` (${row.unit})` : ""}
                        {row.validation_min !== null || row.validation_max !== null
                          ? ` · bounds [${row.validation_min ?? "-inf"}, ${row.validation_max ?? "+inf"}]`
                          : ""}
                      </div>
                    </td>
                    <td>
                      <input
                        type="number"
                        step="any"
                        className="input"
                        aria-label={`${row.display_name} numeric value`}
                        value={row.numeric_value}
                        disabled={!canEditMetrics}
                        onChange={(e) => {
                          const val = e.target.value;
                          setMetricRows((prev) =>
                            prev.map((r, i) => (i === idx ? { ...r, numeric_value: val } : r)),
                          );
                        }}
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        step="any"
                        className="input"
                        aria-label={`${row.display_name} uncertainty`}
                        value={row.uncertainty_value}
                        disabled={!canEditMetrics}
                        onChange={(e) => {
                          const val = e.target.value;
                          setMetricRows((prev) =>
                            prev.map((r, i) => (i === idx ? { ...r, uncertainty_value: val } : r)),
                          );
                        }}
                      />
                    </td>
                    <td>
                      <select
                        className="input"
                        aria-label={`${row.display_name} quality status`}
                        value={row.data_quality_status}
                        disabled={!canEditMetrics}
                        onChange={(e) => {
                          const val = e.target.value as MetricDraftRow["data_quality_status"];
                          setMetricRows((prev) =>
                            prev.map((r, i) => (i === idx ? { ...r, data_quality_status: val } : r)),
                          );
                        }}
                      >
                        <option value="verified">verified</option>
                        <option value="estimated">estimated</option>
                        <option value="unverified">unverified</option>
                        <option value="pending">pending</option>
                      </select>
                    </td>
                    <td>
                      <select
                        className="input"
                        aria-label={`${row.display_name} source`}
                        value={row.source_id}
                        disabled={!canEditMetrics}
                        onChange={(e) => {
                          const val = e.target.value;
                          setMetricRows((prev) =>
                            prev.map((r, i) => (i === idx ? { ...r, source_id: val } : r)),
                          );
                        }}
                      >
                        <option value="">Select Source...</option>
                        {(sourcesQuery.data ?? []).map((src) => (
                          <option key={src.source_id} value={src.source_id}>
                            #{src.source_id}: {src.title.slice(0, 48)}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {canEditMetrics && (
            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "1rem" }}>
              <button
                type="button"
                className="btn btn-primary"
                disabled={saveMetricsMutation.isPending}
                onClick={() => saveMetricsMutation.mutate()}
              >
                {saveMetricsMutation.isPending ? "Validating & Saving..." : "Save Provenance Metrics"}
              </button>
            </div>
          )}
        </section>
      )}

      {tab === "media" && (
        <section className="glass-panel-strong" style={{ padding: "1.25rem", display: "grid", gap: "1rem" }}>
          <div className="admin-media-grid">
            {(mediaQuery.data ?? []).map((m) => (
              <article key={m.media_id} className="glass-panel" style={{ padding: "0.75rem", display: "grid", gap: "0.5rem" }}>
                <img
                  src={m.thumbnail_url || m.image_url}
                  alt={m.alt_text}
                  style={{ width: "100%", height: "145px", objectFit: "cover", borderRadius: "8px" }}
                />
                <div style={{ fontSize: "0.84rem" }}>
                  <strong>{m.caption || m.original_filename || `Media #${m.media_id}`}</strong>
                  <div style={{ color: "var(--text-muted)", fontSize: "0.76rem" }}>
                    {m.is_primary ? "Primary image" : "Gallery asset"} · {m.width_px ?? "?"}x
                    {m.height_px ?? "?"}
                  </div>
                </div>
                {canEdit && (
                  <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
                    {!m.is_primary && (
                      <button
                        type="button"
                        className="btn btn-cyan"
                        onClick={async () => {
                          await setAdminMediaPrimary(m.media_id);
                          queryClient.invalidateQueries({ queryKey: adminQueryKeys.siteMedia(siteId) });
                          queryClient.invalidateQueries({ queryKey: ["sites"] });
                          queryClient.invalidateQueries({ queryKey: ["site"] });
                        }}
                      >
                        Set Primary
                      </button>
                    )}
                    <button
                      type="button"
                      className="btn btn-amber"
                      onClick={async () => {
                        await deleteAdminMedia(m.media_id);
                        queryClient.invalidateQueries({ queryKey: adminQueryKeys.siteMedia(siteId) });
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

          {canEdit && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                uploadMediaMutation.mutate();
              }}
              className="glass-panel"
              style={{ padding: "1rem", display: "grid", gap: "0.75rem" }}
            >
              <h3 style={{ margin: 0 }}>Upload Site Media</h3>
              <div className="admin-form-grid-2">
                <div>
                  <label className="field-label" htmlFor="site-media-file">
                    Image File (JPEG/PNG/WebP/TIFF)
                  </label>
                  <input
                    id="site-media-file"
                    type="file"
                    accept="image/*"
                    className="input"
                    onChange={(e) => setMediaFile(e.target.files?.[0] ?? null)}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="site-media-alt">
                    Alt Text
                  </label>
                  <input
                    id="site-media-alt"
                    className="input"
                    required
                    value={mediaAlt}
                    onChange={(e) => setMediaAlt(e.target.value)}
                  />
                </div>
              </div>
              <div className="admin-form-grid-2">
                <div>
                  <label className="field-label" htmlFor="site-media-caption">
                    Caption
                  </label>
                  <input
                    id="site-media-caption"
                    className="input"
                    value={mediaCaption}
                    onChange={(e) => setMediaCaption(e.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="site-media-credit">
                    Credit / Attribution
                  </label>
                  <input
                    id="site-media-credit"
                    className="input"
                    value={mediaCredit}
                    onChange={(e) => setMediaCredit(e.target.value)}
                  />
                </div>
              </div>
              <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.88rem" }}>
                <input
                  type="checkbox"
                  checked={mediaPrimary}
                  onChange={(e) => setMediaPrimary(e.target.checked)}
                />
                Set as primary thumbnail immediately
              </label>
              <div style={{ display: "flex", justifyContent: "flex-end" }}>
                <button type="submit" className="btn btn-primary" disabled={uploadMediaMutation.isPending}>
                  {uploadMediaMutation.isPending ? "Uploading..." : "Upload Media"}
                </button>
              </div>
            </form>
          )}
        </section>
      )}
    </div>
  );
}

export function AdminSiteEditorPage() {
  const { siteId } = useParams<{ siteId: string }>();
  const numericId = Number(siteId);

  return (
    <AdminLayout
      title={`Landing Site Editor${Number.isFinite(numericId) ? ` #${numericId}` : ""}`}
      subtitle="Edit site metadata, structured narrative sections, advantages/limitations, history, provenance metrics, and media."
      requiredRoles={["site_editor", "research_admin", "system_admin", "viewer"]}
    >
      {(admin) =>
        Number.isFinite(numericId) && numericId > 0 ? (
          <SiteEditorWorkbench admin={admin} siteId={numericId} />
        ) : (
          <div className="notice-banner error">
            <span>Invalid landing site identifier.</span>
          </div>
        )
      }
    </AdminLayout>
  );
}
