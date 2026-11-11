import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { fetchSites, type SiteCardOut } from "../api/endpoints";
import { queryKeys } from "../api/queryKeys";
import { CompareIcon, PauseIcon, PlayIcon, SparkCpuIcon } from "../components/Icons";
import { SiteHeader } from "../components/SiteHeader";
import { HeadTags } from "../seo/HeadTags";
import { LunarMoonCanvas } from "../three/LunarMoonCanvas";
import { formatElevation, formatLatLon } from "../utils/formatting";

export function BrowserPage() {
  const [filterText, setFilterText] = useState("");
  const [regionFilter, setRegionFilter] = useState<string>("all");
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [rotationPaused, setRotationPaused] = useState(false);
  const [resetTrigger, setResetTrigger] = useState(0);
  const [mobileListCollapsed, setMobileListCollapsed] = useState(true);

  const sitesQuery = useQuery({
    queryKey: queryKeys.sites({ status: "published", page_size: 50 }),
    queryFn: () => fetchSites({ status: "published", page_size: 50 }),
    staleTime: 60_000,
  });

  const allSites = sitesQuery.data?.items ?? [];

  const regions = useMemo(() => {
    const names = new Set<string>();
    for (const s of allSites) {
      if (s.region_name) {
        names.add(s.region_name);
      }
    }
    return Array.from(names).sort();
  }, [allSites]);

  const filteredSites = useMemo(() => {
    const q = filterText.trim().toLowerCase();
    return allSites.filter((site) => {
      if (regionFilter !== "all" && site.region_name !== regionFilter) {
        return false;
      }
      if (!q) {
        return true;
      }
      return (
        site.site_name.toLowerCase().includes(q) ||
        site.site_code.toLowerCase().includes(q) ||
        site.site_slug.toLowerCase().includes(q) ||
        (site.region_name ?? "").toLowerCase().includes(q) ||
        (site.terrain_type ?? "").toLowerCase().includes(q)
      );
    });
  }, [allSites, filterText, regionFilter]);

  const activeSite: SiteCardOut | undefined = useMemo(() => {
    if (!selectedSlug) {
      return allSites[0];
    }
    return allSites.find((s) => s.site_slug === selectedSlug) ?? allSites[0];
  }, [allSites, selectedSlug]);

  function handleSelectSite(site: SiteCardOut) {
    setSelectedSlug(site.site_slug);
  }

  return (
    <div className="page-shell">
      <HeadTags
        meta={{
          title: "Interactive Lunar Browser — CLPS Luna Browser",
          description:
            "Explore published CLPS candidate lunar landing sites on an interactive 3D lunar globe with region filters and orbital controls.",
          canonicalPath: "/browser",
          robots: "index,follow",
          ogType: "website",
          breadcrumbs: [
            { name: "Home", path: "/" },
            { name: "Browser", path: "/browser" },
          ],
        }}
      />

      {/* Minimal top header matching approved spec: title left + search/theme/CODEX pill right, zero top nav row */}
      <SiteHeader showSearch />

      <main id="main-content" className="browser-workspace" aria-label="Interactive Lunar Browser">
        <div className="browser-globe-layer">
          <LunarMoonCanvas
            mode="browser"
            sites={filteredSites.length > 0 ? filteredSites : allSites}
            selectedSiteSlug={activeSite?.site_slug ?? null}
            onSelectSite={handleSelectSite}
            rotationPaused={rotationPaused}
            resetTrigger={resetTrigger}
          />
        </div>

        {/* Left Landing Sites Panel */}
        <aside
          className="glass-panel-strong browser-left-panel"
          data-mobile-collapsed={mobileListCollapsed ? "true" : "false"}
          aria-label="Published landing sites directory"
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: "0.5rem",
              marginBottom: "0.7rem",
            }}
          >
            <h1 style={{ margin: 0, fontSize: "1.1rem" }}>Landing Sites</h1>
            <span className="pill-badge amber">{filteredSites.length}</span>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginBottom: "0.75rem" }}>
            <label htmlFor="browser-site-filter" className="sr-only">
              Filter landing sites
            </label>
            <input
              id="browser-site-filter"
              type="search"
              className="input"
              placeholder="Filter name, code, terrain..."
              value={filterText}
              onChange={(event) => setFilterText(event.target.value)}
            />

            {regions.length > 0 && (
              <>
                <label htmlFor="browser-region-filter" className="sr-only">
                  Filter by lunar region
                </label>
                <select
                  id="browser-region-filter"
                  className="select"
                  value={regionFilter}
                  onChange={(event) => setRegionFilter(event.target.value)}
                >
                  <option value="all">All Lunar Regions</option>
                  {regions.map((reg) => (
                    <option key={reg} value={reg}>
                      {reg}
                    </option>
                  ))}
                </select>
              </>
            )}
          </div>

          {sitesQuery.isLoading && (
            <p style={{ color: "var(--text-secondary)", fontSize: "0.86rem" }}>
              Loading published landing sites...
            </p>
          )}

          {sitesQuery.isError && (
            <div className="notice-banner error" role="alert">
              <span>Failed to load catalogue sites.</span>
            </div>
          )}

          <ul
            style={{
              listStyle: "none",
              margin: 0,
              padding: 0,
              overflowY: "auto",
              flex: 1,
              display: "flex",
              flexDirection: "column",
              gap: "0.45rem",
            }}
          >
            {filteredSites.map((site) => {
              const isActive = activeSite?.site_slug === site.site_slug;
              return (
                <li key={site.site_slug}>
                  <button
                    type="button"
                    onClick={() => handleSelectSite(site)}
                    aria-current={isActive ? "true" : undefined}
                    style={{
                      width: "100%",
                      textAlign: "left",
                      padding: "0.68rem 0.78rem",
                      borderRadius: "var(--radius-md)",
                      border: `1px solid ${
                        isActive ? "var(--accent-amber-border)" : "var(--border-subtle)"
                      }`,
                      background: isActive ? "var(--accent-amber-soft)" : "rgba(8, 12, 20, 0.55)",
                      cursor: "pointer",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        gap: "0.45rem",
                      }}
                    >
                      <strong style={{ fontSize: "0.92rem", color: isActive ? "var(--accent-amber)" : "var(--text-primary)" }}>
                        {site.site_name}
                      </strong>
                      <span className="mono" style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
                        {site.site_code}
                      </span>
                    </div>
                    <div
                      className="mono"
                      style={{
                        fontSize: "0.74rem",
                        color: "var(--text-secondary)",
                        marginTop: "0.2rem",
                      }}
                    >
                      {formatLatLon(site.latitude_deg, site.longitude_deg)}
                    </div>
                    {site.region_name && (
                      <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.15rem" }}>
                        {site.region_name}
                      </div>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </aside>

        {/* Active Site Inspection Card */}
        {activeSite && (
          <section
            className="glass-panel-strong browser-selected-card"
            aria-label={`Selected site: ${activeSite.site_name}`}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem" }}>
              <div>
                <span className="eyebrow" style={{ color: "var(--accent-amber)" }}>
                  {activeSite.site_code}
                </span>
                <h2 style={{ margin: "0.15rem 0 0", fontSize: "1.15rem" }}>
                  {activeSite.site_name}
                </h2>
              </div>
              <span className="pill-badge cyan">Published</span>
            </div>

            <div
              className="mono"
              style={{ fontSize: "0.78rem", color: "var(--text-secondary)", marginTop: "0.5rem" }}
            >
              <div>Coords: {formatLatLon(activeSite.latitude_deg, activeSite.longitude_deg)}</div>
              <div>Elevation: {formatElevation(activeSite.elevation_m)}</div>
              {activeSite.terrain_type && <div>Terrain: {activeSite.terrain_type}</div>}
              {activeSite.region_name && <div>Region: {activeSite.region_name}</div>}
            </div>

            {activeSite.overview_summary && (
              <p
                style={{
                  margin: "0.65rem 0 0.85rem",
                  fontSize: "0.84rem",
                  color: "var(--text-secondary)",
                  display: "-webkit-box",
                  WebkitLineClamp: 3,
                  WebkitBoxOrient: "vertical",
                  overflow: "hidden",
                }}
              >
                {activeSite.overview_summary}
              </p>
            )}

            <div style={{ display: "flex", gap: "0.55rem", flexWrap: "wrap", marginTop: "0.7rem" }}>
              <Link
                to={`/sites/${encodeURIComponent(activeSite.site_slug)}`}
                className="btn btn-primary"
                style={{ flex: 1 }}
              >
                Site Dossier -&gt;
              </Link>
              <Link
                to={`/simulation?siteId=${activeSite.site_id}&slug=${encodeURIComponent(activeSite.site_slug)}`}
                className="btn btn-cyan"
              >
                Simulate
              </Link>
            </div>
          </section>
        )}

        {/* Bottom-right actions + Globe controls + Mobile drawer toggle */}
        <div className="browser-bottom-actions">
          <button
            type="button"
            className="btn browser-mobile-toggle"
            onClick={() => setMobileListCollapsed((prev) => !prev)}
          >
            {mobileListCollapsed ? `Sites (${filteredSites.length})` : "Hide List"}
          </button>

          <button
            type="button"
            className="btn"
            onClick={() => setRotationPaused((p) => !p)}
            aria-label={rotationPaused ? "Resume globe rotation" : "Pause globe rotation"}
            title={rotationPaused ? "Resume globe rotation" : "Pause globe rotation"}
          >
            {rotationPaused ? <PlayIcon /> : <PauseIcon />}
            <span>{rotationPaused ? "Resume" : "Pause"}</span>
          </button>

          <button
            type="button"
            className="btn"
            onClick={() => {
              setSelectedSlug(null);
              setResetTrigger((n) => n + 1);
            }}
          >
            Reset View
          </button>

          <Link to="/compare" className="btn">
            <CompareIcon size={15} />
            <span>Compare</span>
          </Link>

          <Link to="/ai-assist" className="btn btn-primary">
            <SparkCpuIcon size={15} />
            <span>AI Assist</span>
          </Link>
        </div>
      </main>
    </div>
  );
}

