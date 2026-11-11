import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  fetchSiteBySlug,
  fetchSiteHistory,
  fetchSiteMedia,
  fetchSiteMetrics,
  fetchSiteProsCons,
  fetchSites,
  fetchSiteSections,
  type SiteMediaOut,
} from "../api/endpoints";
import { queryKeys } from "../api/queryKeys";
import { CopyButton } from "../components/CopyButton";
import { CloseIcon } from "../components/Icons";
import { SiteHeader } from "../components/SiteHeader";
import { UtilitiesFooter } from "../components/UtilitiesFooter";
import { HeadTags } from "../seo/HeadTags";
import { LunarMoonCanvas } from "../three/LunarMoonCanvas";
import {
  formatElevation,
  formatLatLon,
  formatNumber,
  formatUtcTimestamp,
} from "../utils/formatting";

type BlockKey =
  | "overview"
  | "history"
  | "pros_cons"
  | "statistics"
  | "gallery"
  | "research";

const BLOCK_ITEMS: Array<{ key: BlockKey; title: string; subtitle: string }> = [
  { key: "overview", title: "Overview", subtitle: "Site profile & coordinates" },
  { key: "history", title: "History", subtitle: "Mission milestones" },
  { key: "pros_cons", title: "Pros & Cons", subtitle: "Evidence & caveats" },
  { key: "statistics", title: "Statistics", subtitle: "Cited parameters" },
  { key: "gallery", title: "Gallery", subtitle: "Media & attribution" },
  { key: "research", title: "Research & References", subtitle: "Sources & citations" },
];

export function SiteInfoPage() {
  const { siteSlug = "" } = useParams();
  const [activeBlock, setActiveBlock] = useState<BlockKey>("overview");
  const [lightboxItem, setLightboxItem] = useState<SiteMediaOut | null>(null);

  const siteQuery = useQuery({
    queryKey: queryKeys.siteDetail(siteSlug),
    queryFn: () => fetchSiteBySlug(siteSlug),
    enabled: siteSlug.length > 0,
    retry: false,
  });

  const sectionsQuery = useQuery({
    queryKey: queryKeys.siteSections(siteSlug),
    queryFn: () => fetchSiteSections(siteSlug),
    enabled: Boolean(siteQuery.data),
  });

  const prosConsQuery = useQuery({
    queryKey: queryKeys.siteProsCons(siteSlug),
    queryFn: () => fetchSiteProsCons(siteSlug),
    enabled: Boolean(siteQuery.data),
  });

  const metricsQuery = useQuery({
    queryKey: queryKeys.siteMetrics(siteSlug),
    queryFn: () => fetchSiteMetrics(siteSlug),
    enabled: Boolean(siteQuery.data),
  });

  const mediaQuery = useQuery({
    queryKey: queryKeys.siteMedia(siteSlug),
    queryFn: () => fetchSiteMedia(siteSlug),
    enabled: Boolean(siteQuery.data),
  });

  const historyQuery = useQuery({
    queryKey: queryKeys.siteHistory(siteSlug),
    queryFn: () => fetchSiteHistory(siteSlug),
    enabled: Boolean(siteQuery.data),
  });

  const catalogueQuery = useQuery({
    queryKey: queryKeys.sites({ status: "published", page_size: 50 }),
    queryFn: () => fetchSites({ status: "published", page_size: 50 }),
    staleTime: 60_000,
  });

  const site = siteQuery.data;
  const sections = sectionsQuery.data ?? [];
  const prosCons = prosConsQuery.data ?? [];
  const metrics = metricsQuery.data ?? [];
  const media = mediaQuery.data ?? [];
  const history = historyQuery.data ?? [];

  const uniqueSources = useMemo(() => {
    const map = new Map<
      string,
      { title: string; citation?: string | null; url?: string | null }
    >();
    for (const m of metrics) {
      const key = m.source_citation || m.source_title || "";
      if (key || m.source_url) {
        map.set(key || String(m.source_url), {
          title: m.source_title || "Scientific Data Source",
          citation: m.source_citation,
          url: m.source_url,
        });
      }
    }
    return Array.from(map.values());
  }, [metrics]);

  if (siteQuery.isLoading) {
    return (
      <div className="page-shell">
        <SiteHeader subtitle="Loading landing site..." />
        <main id="main-content" className="container">
          <div className="glass-panel" style={{ padding: "1.5rem" }}>
            Loading landing-site dossier...
          </div>
        </main>
      </div>
    );
  }

  if (siteQuery.isError || !site) {
    return (
      <div className="page-shell">
        <HeadTags
          meta={{
            title: "Landing Site Not Found — CLPS Luna Browser",
            description: "The requested lunar landing site does not exist or is unpublished.",
            canonicalPath: `/sites/${encodeURIComponent(siteSlug)}`,
            robots: "noindex,nofollow",
            ogType: "website",
            breadcrumbs: [
              { name: "Home", path: "/" },
              { name: "Browser", path: "/browser" },
              { name: "Not Found", path: `/sites/${encodeURIComponent(siteSlug)}` },
            ],
          }}
        />
        <SiteHeader subtitle="Site Not Found" />
        <main id="main-content" className="container">
          <div className="glass-panel notice-banner error" role="alert">
            <div>
              <h1 style={{ margin: "0 0 0.35rem", fontSize: "1.3rem" }}>
                Landing Site Not Found
              </h1>
              <p style={{ margin: 0, color: "var(--text-secondary)" }}>
                No published site matches slug `{siteSlug}`.
              </p>
            </div>
            <Link to="/browser" className="btn btn-primary">
              Return to Browser
            </Link>
          </div>
        </main>
      </div>
    );
  }

  const coordsText = `${site.latitude_deg.toFixed(4)}, ${site.longitude_deg.toFixed(4)} (${site.coordinate_reference})`;

  return (
    <div className="page-shell">
      <HeadTags
        meta={{
          title: site.seo_title || `${site.site_name} (${site.site_code}) — CLPS Luna Browser`,
          description:
            site.seo_meta_description ||
            site.overview_summary ||
            `Scientific landing-site profile and ephemeris simulation tools for ${site.site_name}.`,
          canonicalPath: `/sites/${encodeURIComponent(site.site_slug)}`,
          robots: "index,follow",
          ogType: "article",
          ogImage: site.og_image_url || site.primary_image_url || undefined,
          breadcrumbs: [
            { name: "Home", path: "/" },
            { name: "Browser", path: "/browser" },
            { name: site.site_name, path: `/sites/${encodeURIComponent(site.site_slug)}` },
          ],
        }}
      />

      <div className="ambient-bg-layer" aria-hidden="true">
        <LunarMoonCanvas
          mode="site-focus"
          sites={catalogueQuery.data?.items ?? []}
          selectedSiteSlug={site.site_slug}
          focusLatDeg={site.latitude_deg}
          focusLonDeg={site.longitude_deg}
        />
      </div>

      <SiteHeader
        subtitle={site.site_name}
        rightActions={
          <>
            <Link
              to={`/simulation?siteId=${site.site_id}&slug=${encodeURIComponent(site.site_slug)}`}
              className="btn btn-cyan"
            >
              Simulate
            </Link>
            <Link
              to={`/codex?siteId=${site.site_id}&slug=${encodeURIComponent(site.site_slug)}`}
              className="btn btn-primary"
            >
              Run CODEX
            </Link>
          </>
        }
      />

      <main id="main-content" className="page-content-layer container">
        {/* Compact Header Strip */}
        <section
          className="glass-panel-strong"
          style={{
            padding: "1.1rem 1.25rem",
            marginBottom: "1.15rem",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            flexWrap: "wrap",
            gap: "0.85rem",
          }}
        >
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.55rem", flexWrap: "wrap" }}>
              <Link to="/browser" style={{ fontSize: "0.84rem", color: "var(--accent-amber)" }}>
                &lt;- Browser
              </Link>
              <span className="pill-badge cyan mono">{site.site_code}</span>
              {site.region_name && <span className="pill-badge">{site.region_name}</span>}
            </div>
            <h1 style={{ margin: "0.35rem 0 0.2rem", fontSize: "1.7rem" }}>
              {site.site_name}
            </h1>
            <div
              className="mono"
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: "1rem",
                fontSize: "0.82rem",
                color: "var(--text-secondary)",
              }}
            >
              <span>{formatLatLon(site.latitude_deg, site.longitude_deg)}</span>
              <span>Elev: {formatElevation(site.elevation_m)}</span>
              {site.terrain_type && <span>Terrain: {site.terrain_type}</span>}
              <span>Frame: {site.coordinate_reference}</span>
            </div>
          </div>

          <div className="no-print" style={{ display: "flex", gap: "0.55rem", flexWrap: "wrap" }}>
            <CopyButton text={coordsText} label="Copy Coords" />
            <Link to={`/compare?siteA=${site.site_id}`} className="btn">
              Compare Site
            </Link>
            <button type="button" className="btn" onClick={() => window.print()}>
              Print
            </button>
          </div>
        </section>

        {/* 6-Block Workspace matching Approved Reference */}
        <div className="site-workspace-grid">
          <div
            className="block-selector-grid no-print"
            role="tablist"
            aria-label="Landing site information blocks"
          >
            {BLOCK_ITEMS.map((item) => {
              const selected = activeBlock === item.key;
              return (
                <button
                  key={item.key}
                  type="button"
                  role="tab"
                  aria-selected={selected}
                  id={`tab-${item.key}`}
                  aria-controls={`panel-${item.key}`}
                  className="block-tile"
                  onClick={() => setActiveBlock(item.key)}
                >
                  <strong
                    style={{
                      fontSize: "0.95rem",
                      color: selected ? "var(--accent-amber)" : "var(--text-primary)",
                    }}
                  >
                    {item.title}
                  </strong>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                    {item.subtitle}
                  </span>
                </button>
              );
            })}
          </div>

          <section
            id={`panel-${activeBlock}`}
            role="tabpanel"
            aria-labelledby={`tab-${activeBlock}`}
            className="glass-panel-strong"
            style={{ padding: "1.25rem", minHeight: "360px" }}
          >
            {activeBlock === "overview" && (
              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                <div>
                  <p className="eyebrow" style={{ margin: "0 0 0.35rem", color: "var(--accent-amber)" }}>
                    About the Site
                  </p>
                  <h2 style={{ margin: "0 0 0.65rem", fontSize: "1.28rem" }}>
                    Site Overview
                  </h2>
                  <p style={{ margin: 0, lineHeight: 1.65, color: "var(--text-secondary)" }}>
                    {site.overview_summary ||
                      "No narrative overview summary has been recorded for this site."}
                  </p>
                </div>

                {sections.map((sec) => (
                  <article
                    key={sec.content_id}
                    style={{
                      borderTop: "1px solid var(--border-subtle)",
                      paddingTop: "0.9rem",
                    }}
                  >
                    <h3 style={{ margin: "0 0 0.45rem", fontSize: "1.06rem" }}>
                      {sec.title || sec.section_key}
                    </h3>
                    <p
                      style={{
                        margin: 0,
                        whiteSpace: "pre-line",
                        color: "var(--text-secondary)",
                      }}
                    >
                      {sec.body}
                    </p>
                  </article>
                ))}

                <div
                  className="glass-panel"
                  style={{
                    padding: "0.9rem",
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))",
                    gap: "0.75rem",
                    fontSize: "0.84rem",
                  }}
                >
                  <div>
                    <span className="eyebrow">Catalogue Status</span>
                    <div className="mono">{site.catalogue_status}</div>
                  </div>
                  <div>
                    <span className="eyebrow">Latitude (deg)</span>
                    <div className="mono">{site.latitude_deg.toFixed(4)}</div>
                  </div>
                  <div>
                    <span className="eyebrow">Longitude (deg E)</span>
                    <div className="mono">{site.longitude_deg.toFixed(4)}</div>
                  </div>
                  <div>
                    <span className="eyebrow">Updated At</span>
                    <div className="mono">{formatUtcTimestamp(site.updated_at)}</div>
                  </div>
                </div>
              </div>
            )}

            {activeBlock === "history" && (
              <div>
                <h2 style={{ margin: "0 0 0.75rem", fontSize: "1.28rem" }}>
                  Mission History &amp; Milestones
                </h2>
                {history.length === 0 ? (
                  <div className="notice-banner">
                    <span>
                      No historical timeline milestones have been ingested into PostgreSQL for{" "}
                      {site.site_name} yet.
                    </span>
                  </div>
                ) : (
                  <ol
                    style={{
                      margin: 0,
                      paddingLeft: "1.2rem",
                      display: "flex",
                      flexDirection: "column",
                      gap: "0.85rem",
                    }}
                  >
                    {history.map((item) => (
                      <li key={item.history_id}>
                        <div style={{ display: "flex", gap: "0.6rem", alignItems: "baseline", flexWrap: "wrap" }}>
                          <strong>{item.title}</strong>
                          {item.event_date && (
                            <span className="pill-badge mono">{item.event_date}</span>
                          )}
                        </div>
                        <p style={{ margin: "0.3rem 0 0", color: "var(--text-secondary)" }}>
                          {item.description}
                        </p>
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            )}

            {activeBlock === "pros_cons" && (
              <div>
                <h2 style={{ margin: "0 0 0.75rem", fontSize: "1.28rem" }}>
                  Mission Pros &amp; Cons
                </h2>
                {prosCons.length === 0 ? (
                  <div className="notice-banner">
                    <span>
                      No qualitative pros or cons entries have been authored for {site.site_name} yet.
                      Use the Statistics tab and Compare workspace for quantitative evaluation.
                    </span>
                  </div>
                ) : (
                  <div className="responsive-grid-2">
                    <div className="glass-panel" style={{ padding: "0.95rem" }}>
                      <h3 style={{ margin: "0 0 0.6rem", color: "var(--status-ok)" }}>
                        Advantages
                      </h3>
                      <ul style={{ margin: 0, paddingLeft: "1.1rem" }}>
                        {prosCons
                          .filter((p) => p.point_type === "pro")
                          .map((p) => (
                            <li key={p.point_id} style={{ marginBottom: "0.5rem" }}>
                              <strong>{p.title || "Strength"}: </strong>
                              <span style={{ color: "var(--text-secondary)" }}>{p.body}</span>
                            </li>
                          ))}
                      </ul>
                    </div>
                    <div className="glass-panel" style={{ padding: "0.95rem" }}>
                      <h3 style={{ margin: "0 0 0.6rem", color: "var(--accent-amber)" }}>
                        Limitations &amp; Risks
                      </h3>
                      <ul style={{ margin: 0, paddingLeft: "1.1rem" }}>
                        {prosCons
                          .filter((p) => p.point_type !== "pro")
                          .map((p) => (
                            <li key={p.point_id} style={{ marginBottom: "0.5rem" }}>
                              <strong>{p.title || "Constraint"}: </strong>
                              <span style={{ color: "var(--text-secondary)" }}>{p.body}</span>
                            </li>
                          ))}
                      </ul>
                    </div>
                  </div>
                )}
              </div>
            )}

            {activeBlock === "statistics" && (
              <div>
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
                  <h2 style={{ margin: 0, fontSize: "1.28rem" }}>
                    Scientific &amp; Engineering Statistics
                  </h2>
                  {metrics.length > 0 && (
                    <CopyButton
                      text={JSON.stringify(metrics, null, 2)}
                      label="Copy Metrics JSON"
                    />
                  )}
                </div>

                {metrics.length === 0 ? (
                  <div className="notice-banner">
                    <span>No scientific parameters recorded in PostgreSQL for this site.</span>
                  </div>
                ) : (
                  <div className="data-table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Parameter</th>
                          <th>Value</th>
                          <th>Uncertainty</th>
                          <th>Quality</th>
                          <th>Validity Window</th>
                          <th>Source</th>
                        </tr>
                      </thead>
                      <tbody>
                        {metrics.map((m) => (
                          <tr key={m.site_metric_id}>
                            <td>
                              <strong>{m.display_name}</strong>
                              <div className="mono" style={{ fontSize: "0.74rem", color: "var(--text-muted)" }}>
                                {m.parameter_key}
                              </div>
                            </td>
                            <td className="mono">
                              {m.numeric_value !== null && m.numeric_value !== undefined
                                ? `${formatNumber(m.numeric_value, 2)}${m.unit ? ` ${m.unit}` : ""}`
                                : m.text_value || "—"}
                            </td>
                            <td className="mono">
                              {m.uncertainty_value !== null && m.uncertainty_value !== undefined
                                ? `±${formatNumber(m.uncertainty_value, 2)}`
                                : "—"}
                            </td>
                            <td>
                              <span
                                className={`pill-badge ${
                                  m.data_quality_status === "verified" ? "ok" : "amber"
                                }`}
                              >
                                {m.data_quality_status}
                              </span>
                            </td>
                            <td className="mono" style={{ fontSize: "0.76rem", color: "var(--text-secondary)" }}>
                              {m.valid_from || m.valid_to
                                ? `${m.valid_from ?? "?"} .. ${m.valid_to ?? "?"}`
                                : "Unspecified"}
                            </td>
                            <td style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                              <div>{m.source_title || m.source_citation || "Pending citation"}</div>
                              {m.source_url && (
                                <a
                                  href={m.source_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  style={{ color: "var(--accent-cyan)", textDecoration: "underline" }}
                                >
                                  Source Reference
                                </a>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            {activeBlock === "gallery" && (
              <div>
                <h2 style={{ margin: "0 0 0.75rem", fontSize: "1.28rem" }}>
                  Imagery Gallery &amp; Attribution
                </h2>
                {media.length === 0 ? (
                  <div className="notice-banner">
                    <span>
                      No site-specific photographs or DEM cutout images have been ingested for{" "}
                      {site.site_name} yet. The 3D globe displays NASA SVS CGI Moon Kit LROC
                      surface imagery as visual reference.
                    </span>
                  </div>
                ) : (
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                      gap: "0.85rem",
                    }}
                  >
                    {media.map((item) => (
                      <button
                        key={item.media_id}
                        type="button"
                        className="glass-panel"
                        onClick={() => setLightboxItem(item)}
                        style={{
                          padding: "0.6rem",
                          cursor: "pointer",
                          textAlign: "left",
                        }}
                      >
                        <img
                          src={item.thumbnail_url || item.image_url}
                          alt={item.alt_text}
                          style={{
                            width: "100%",
                            height: "150px",
                            objectFit: "cover",
                            borderRadius: "var(--radius-sm)",
                          }}
                        />
                        <div style={{ marginTop: "0.45rem", fontSize: "0.82rem" }}>
                          {item.caption || item.alt_text}
                        </div>
                        {item.credit && (
                          <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
                            Credit: {item.credit}
                          </div>
                        )}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {activeBlock === "research" && (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }}>
                <h2 style={{ margin: 0, fontSize: "1.28rem" }}>
                  Research &amp; References
                </h2>

                {uniqueSources.length > 0 ? (
                  <ul style={{ margin: 0, paddingLeft: "1.2rem", display: "flex", flexDirection: "column", gap: "0.6rem" }}>
                    {uniqueSources.map((src) => (
                      <li key={`${src.title}-${src.url ?? ""}`}>
                        <strong>{src.title}</strong>
                        {src.citation && (
                          <div style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
                            {src.citation}
                          </div>
                        )}
                        {src.url && (
                          <a
                            href={src.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ fontSize: "0.82rem", color: "var(--accent-cyan)", textDecoration: "underline" }}
                          >
                            {src.url}
                          </a>
                        )}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className="notice-banner">
                    <span>
                      Catalogue metrics for {site.site_name} currently carry quality status{" "}
                      <code>unverified</code> without linked bibliographic records yet.
                    </span>
                  </div>
                )}

                <div className="glass-panel" style={{ padding: "0.9rem", fontSize: "0.84rem" }}>
                  <strong>Surface Texture &amp; Cartography Attribution:</strong>{" "}
                  <span style={{ color: "var(--text-secondary)" }}>
                    NASA Goddard Space Flight Center Scientific Visualization Studio (SVS) CGI Moon
                    Kit #4720 (LROC Wide Angle Camera mosaic &amp; LOLA elevation data, Public
                    Domain), coordinate reference {site.coordinate_reference}.
                  </span>
                </div>
              </div>
            )}
          </section>
        </div>
      </main>

      {lightboxItem && (
        <div
          className="modal-backdrop no-print"
          role="dialog"
          aria-modal="true"
          aria-label={lightboxItem.alt_text}
          onClick={() => setLightboxItem(null)}
        >
          <div
            className="glass-panel-strong"
            style={{ maxWidth: "780px", width: "100%", padding: "1rem" }}
            onClick={(event) => event.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.65rem" }}>
              <strong>{lightboxItem.caption || lightboxItem.alt_text}</strong>
              <button
                type="button"
                className="btn"
                aria-label="Close lightbox"
                onClick={() => setLightboxItem(null)}
              >
                <CloseIcon />
              </button>
            </div>
            <img
              src={lightboxItem.image_url}
              alt={lightboxItem.alt_text}
              style={{
                width: "100%",
                maxHeight: "65vh",
                objectFit: "contain",
                borderRadius: "var(--radius-sm)",
              }}
            />
            {lightboxItem.credit && (
              <p style={{ margin: "0.5rem 0 0", fontSize: "0.8rem", color: "var(--text-muted)" }}>
                Credit: {lightboxItem.credit}
              </p>
            )}
          </div>
        </div>
      )}

      <UtilitiesFooter lastUpdated={site.updated_at.slice(0, 10)} />
    </div>
  );
}

