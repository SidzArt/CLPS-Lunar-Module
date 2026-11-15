import { useState } from "react";
import { Link } from "react-router-dom";

export interface LunarSouthPoleSite {
  id: string;
  siteCode: string;
  name: string;
  primaryCoord: string;
  altCoord?: string;
  isDetailed: boolean;
  latitude: string;
  longitude: string;
}

export interface SiteGalleryImage {
  src: string;
  thumbSrc: string;
  title: string;
  caption: string;
  credit: string;
  imageType: string;
  sourceUrl: string;
}

export const ALL_NINE_SOUTH_POLE_SITES: LunarSouthPoleSite[] = [
  {
    id: "peak-near-cabeus-b",
    siteCode: "1",
    name: "Peak near Cabeus B",
    latitude: "83.6°S",
    longitude: "68.8°W (291.2°E)",
    primaryCoord: "83.6°S, 68.8°W (291.2°E)",
    isDetailed: true,
  },
  {
    id: "haworth",
    siteCode: "2",
    name: "Haworth",
    latitude: "86.9°S",
    longitude: "4.0°W",
    primaryCoord: "86.9°S, 4.0°W",
    altCoord: "87.45°S, 5.2°W (Alternative gazetteer coordinates)",
    isDetailed: true,
  },
  {
    id: "malapert-massif",
    siteCode: "3",
    name: "Malapert Massif",
    latitude: "~86.4°S",
    longitude: "1.3°E",
    primaryCoord: "~86.4°S, 1.3°E",
    isDetailed: false,
  },
  {
    id: "mons-mouton-plateau",
    siteCode: "4",
    name: "Mons Mouton Plateau",
    latitude: "84.6°S",
    longitude: "31.0°E",
    primaryCoord: "84.6°S, 31.0°E",
    isDetailed: false,
  },
  {
    id: "nobile-rim-2",
    siteCode: "5",
    name: "Nobile Rim 2",
    latitude: "84.20°S",
    longitude: "60.70°E",
    primaryCoord: "84.20°S, 60.70°E",
    isDetailed: false,
  },
  {
    id: "connecting-ridge",
    siteCode: "6",
    name: "Connecting Ridge",
    latitude: "~89.6°S",
    longitude: "172.7°W (187.3°E)",
    primaryCoord: "~89.6°S, 172.7°W (187.3°E)",
    isDetailed: false,
  },
  {
    id: "connecting-ridge-extension",
    siteCode: "7",
    name: "Connecting Ridge Extension",
    latitude: "~89.2°S",
    longitude: "86.0°W (274.0°E)",
    primaryCoord: "~89.2°S, 86.0°W (274.0°E)",
    isDetailed: false,
  },
  {
    id: "leibnitz-beta-plateau",
    siteCode: "8",
    name: "Leibnitz Beta Plateau",
    latitude: "~85.2°S",
    longitude: "33.8°E",
    primaryCoord: "~85.2°S, 33.8°E",
    isDetailed: false,
  },
  {
    id: "amundsen-rim",
    siteCode: "9",
    name: "Amundsen Rim",
    latitude: "~84.2°S",
    longitude: "66.9°E",
    primaryCoord: "~84.2°S, 66.9°E",
    isDetailed: false,
  },
];

const CABEUS_B_IMAGES: SiteGalleryImage[] = [
  {
    src: "/storage/media/cabeus_b_orbital_lroc.webp",
    thumbSrc: "/storage/media/cabeus_b_orbital_lroc_thumb.webp",
    title: "Orbital Reconnaissance Mosaic",
    caption: "High-resolution orbital reconnaissance of Peak near Cabeus B candidate landing zone.",
    credit: "NASA / GSFC / Arizona State University (LRO/LROC)",
    imageType: "Orbital Imagery",
    sourceUrl: "https://pds-geosciences.wustl.edu/missions/lro/",
  },
  {
    src: "/storage/media/cabeus_b_terrain_lola.webp",
    thumbSrc: "/storage/media/cabeus_b_terrain_lola_thumb.webp",
    title: "LOLA Shaded Relief & Slopes",
    caption: "Topographic 6 km relief and slope roughness across Cabeus B elevated ridge.",
    credit: "NASA / Goddard Space Flight Center (LOLA Science Team)",
    imageType: "Elevation & Slope Map",
    sourceUrl: "https://imbrium.mit.edu/DATA/LOLA_GDR/",
  },
  {
    src: "/storage/media/cabeus_b_psr_illumination.webp",
    thumbSrc: "/storage/media/cabeus_b_psr_illumination_thumb.webp",
    title: "Volatiles & PSR Illumination Model",
    caption: "Permanently shadowed regions and solar illumination availability model.",
    credit: "NASA Artemis Science Team / LRO LAMP / Diviner",
    imageType: "Scientific Visualization",
    sourceUrl: "https://www.nasa.gov/news-release/nasa-identifies-candidate-regions-for-landing-next-americans-on-moon/",
  },
];

const HAWORTH_IMAGES: SiteGalleryImage[] = [
  {
    src: "/storage/media/haworth_crater_orbital_lroc.webp",
    thumbSrc: "/storage/media/haworth_crater_orbital_lroc_thumb.webp",
    title: "Haworth Crater Polar Mosaic",
    caption: "LROC Wide Angle Camera polar mosaic showing the 51 km diameter Haworth impact crater.",
    credit: "NASA / GSFC / Arizona State University (LRO/LROC)",
    imageType: "Orbital Imagery",
    sourceUrl: "https://pds-geosciences.wustl.edu/missions/lro/",
  },
  {
    src: "/storage/media/haworth_lola_elevation_profile.webp",
    thumbSrc: "/storage/media/haworth_lola_elevation_profile_thumb.webp",
    title: "LOLA Topographic Profile",
    caption: "Topographic depression, interior floor gradient, and surrounding crater rim slopes.",
    credit: "NASA / Goddard Space Flight Center (LOLA Science Team)",
    imageType: "Elevation Profile",
    sourceUrl: "https://imbrium.mit.edu/DATA/LOLA_GDR/",
  },
  {
    src: "/storage/media/haworth_psr_frost_map.webp",
    thumbSrc: "/storage/media/haworth_psr_frost_map_thumb.webp",
    title: "Cryogenic PSR & Frost Distribution",
    caption: "Permanently shadowed regions thermal profile (<40 K) and surface frost signatures.",
    credit: "NASA / UCLA / SwRI (LRO Science Teams)",
    imageType: "Thermal & Frost Chart",
    sourceUrl: "https://pds-geosciences.wustl.edu/missions/lro/",
  },
];

export function LunarSouthPoleSitesSection() {
  const [activeDetailedSite, setActiveDetailedSite] = useState<"all" | "cabeus-b" | "haworth">("all");
  const [selectedImage, setSelectedImage] = useState<SiteGalleryImage | null>(null);

  return (
    <section
      id="lunar-south-pole-landing-sites"
      className="container"
      aria-labelledby="south-pole-section-heading"
      style={{
        paddingTop: "1.5rem",
        paddingBottom: "1.5rem",
        display: "flex",
        flexDirection: "column",
        gap: "1.5rem",
      }}
    >
      {/* Header Banner */}
      <div
        className="glass-panel"
        style={{
          padding: "1.5rem",
          borderLeft: "4px solid var(--accent-cyan)",
          display: "flex",
          flexDirection: "column",
          gap: "0.5rem",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.6rem" }}>
          <p className="eyebrow" style={{ margin: 0, color: "var(--accent-cyan)" }}>
            NASA Artemis Candidate Landing Regions · Lunar South Pole
          </p>
          <span className="pill-badge cyan">9 Database Records</span>
        </div>
        <h2
          id="south-pole-section-heading"
          style={{ margin: 0, fontSize: "1.55rem", letterSpacing: "-0.01em" }}
        >
          Lunar South Pole Landing Sites
        </h2>
        <p
          style={{
            margin: 0,
            color: "var(--text-secondary)",
            fontSize: "0.95rem",
            maxWidth: "78ch",
            lineHeight: 1.55,
          }}
        >
          Artemis candidate landing regions across selenographic latitudes 83°S to 90°S.
          All nine candidate sites are ingested into the live database. Complete scientific dossiers,
          authentic three-image galleries, and active SPICE simulation workflows are provided for{" "}
          <strong>Site Code 1 (Peak near Cabeus B)</strong> and <strong>Site Code 2 (Haworth)</strong>.
          Sites 3 through 9 are maintained strictly as compact name-and-coordinate records.
        </p>
      </div>

      {/* Overview Grid + Polar Projection Map */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
          gap: "1.25rem",
        }}
      >
        {/* Left: Complete 9-Site Catalogue Table / Grid */}
        <div className="glass-panel" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "0.9rem" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.5rem" }}>
            <h3 style={{ margin: 0, fontSize: "1.1rem" }}>
              Landing Sites Overview (9 Locations)
            </h3>
            <span className="mono" style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
              All 9 Ingested into Database
            </span>
          </div>

          <p style={{ margin: 0, fontSize: "0.86rem", color: "var(--text-secondary)" }}>
            Sites 1 &amp; 2 feature complete scientific dossiers and simulation hooks. Sites 3–9 are recorded strictly with name and coordinates.
          </p>

          <div
            style={{
              display: "grid",
              gap: "0.55rem",
              marginTop: "0.3rem",
            }}
          >
            {ALL_NINE_SOUTH_POLE_SITES.map((site) => {
              const isMajor = site.isDetailed;
              return (
                <div
                  key={site.id}
                  className={`glass-panel ${isMajor ? "glass-panel-strong" : ""}`}
                  style={{
                    padding: isMajor ? "0.85rem 1rem" : "0.65rem 0.9rem",
                    border: isMajor
                      ? site.siteCode === "1"
                        ? "1px solid var(--accent-amber-border)"
                        : "1px solid var(--accent-cyan-border)"
                      : "1px solid var(--border-subtle)",
                    backgroundColor: isMajor
                      ? "var(--bg-glass-strong)"
                      : "var(--bg-glass-subtle)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: "0.75rem",
                    transition: "border-color 0.15s ease",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", minWidth: 0 }}>
                    <div
                      className="mono"
                      style={{
                        fontSize: "0.78rem",
                        color: isMajor ? "var(--text-primary)" : "var(--text-muted)",
                        fontWeight: 700,
                        backgroundColor: isMajor
                          ? site.siteCode === "1" ? "var(--accent-amber-soft)" : "var(--accent-cyan-soft)"
                          : "rgba(255,255,255,0.05)",
                        padding: "0.2rem 0.5rem",
                        borderRadius: "var(--radius-sm)",
                        border: isMajor ? "1px solid var(--border-subtle)" : undefined,
                      }}
                    >
                      CODE {site.siteCode}
                    </div>

                    <div style={{ minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.45rem", flexWrap: "wrap" }}>
                        <span
                          style={{
                            fontWeight: isMajor ? 700 : 500,
                            fontSize: isMajor ? "0.95rem" : "0.88rem",
                            color: isMajor ? "var(--text-primary)" : "var(--text-secondary)",
                          }}
                        >
                          {site.name}
                        </span>
                        {isMajor && (
                          <span
                            className={`pill-badge ${site.siteCode === "1" ? "amber" : "cyan"}`}
                            style={{ padding: "0.1rem 0.4rem", fontSize: "0.68rem" }}
                          >
                            Full Dossier
                          </span>
                        )}
                      </div>

                      <div
                        className="mono"
                        style={{
                          fontSize: "0.82rem",
                          color: isMajor ? "var(--accent-amber)" : "var(--text-secondary)",
                          marginTop: "0.15rem",
                        }}
                      >
                        Latitude: {site.latitude} · Longitude: {site.longitude}
                        {site.altCoord && (
                          <span
                            style={{
                              display: "block",
                              fontSize: "0.74rem",
                              color: "var(--text-muted)",
                              marginTop: "0.1rem",
                            }}
                          >
                            Alt. Gazetteer: {site.altCoord}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {isMajor && (
                    <a
                      href={`#${site.id}-dossier`}
                      className="btn"
                      style={{
                        padding: "0.3rem 0.65rem",
                        fontSize: "0.76rem",
                        whiteSpace: "nowrap",
                      }}
                      onClick={() => {
                        if (site.id === "haworth") setActiveDetailedSite("haworth");
                        if (site.id === "peak-near-cabeus-b") setActiveDetailedSite("cabeus-b");
                      }}
                    >
                      View Dossier &darr;
                    </a>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Right: Polar Stereographic Map Visualization */}
        <div className="glass-panel" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <h3 style={{ margin: 0, fontSize: "1.1rem" }}>
              Lunar South Pole Spatial Projection
            </h3>
            <span className="mono" style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>
              80°S – 90°S Polar Grid
            </span>
          </div>

          <p style={{ margin: 0, fontSize: "0.84rem", color: "var(--text-secondary)" }}>
            Polar coordinate radar showing spatial distribution for all 9 candidate sites relative to 83°S, 86°S, and the lunar south pole (90°S).
          </p>

          <div
            style={{
              position: "relative",
              width: "100%",
              maxWidth: "380px",
              margin: "0.5rem auto",
              aspectRatio: "1 / 1",
            }}
          >
            <svg
              viewBox="0 0 340 340"
              style={{
                width: "100%",
                height: "100%",
                background: "radial-gradient(circle at center, #0b1422 0%, #05080e 75%)",
                borderRadius: "var(--radius-lg)",
                border: "1px solid var(--border-subtle)",
              }}
              aria-label="Lunar South Pole Polar Projection Diagram"
            >
              <circle cx="170" cy="170" r="150" fill="none" stroke="rgba(255, 255, 255, 0.08)" strokeDasharray="3 3" />
              <circle cx="170" cy="170" r="110" fill="none" stroke="rgba(255, 255, 255, 0.12)" strokeDasharray="4 4" />
              <circle cx="170" cy="170" r="65" fill="none" stroke="rgba(255, 255, 255, 0.18)" strokeDasharray="4 4" />
              <circle cx="170" cy="170" r="20" fill="none" stroke="rgba(90, 210, 230, 0.3)" />

              <line x1="170" y1="20" x2="170" y2="320" stroke="rgba(255, 255, 255, 0.08)" />
              <line x1="20" y1="170" x2="320" y2="170" stroke="rgba(255, 255, 255, 0.08)" />

              <text x="175" y="32" fill="var(--text-muted)" fontSize="9" fontFamily="monospace">0° (Prime Meridian)</text>
              <text x="175" y="315" fill="var(--text-muted)" fontSize="9" fontFamily="monospace">180° (Far Side)</text>
              <text x="25" y="165" fill="var(--text-muted)" fontSize="9" fontFamily="monospace">90°W</text>
              <text x="270" y="165" fill="var(--text-muted)" fontSize="9" fontFamily="monospace">90°E</text>

              <text x="175" y="165" fill="var(--accent-amber)" fontSize="9" fontFamily="monospace" fontWeight="bold">90°S</text>
              <text x="175" y="115" fill="var(--text-muted)" fontSize="8" fontFamily="monospace">86°S</text>
              <text x="175" y="70" fill="var(--text-muted)" fontSize="8" fontFamily="monospace">83°S</text>

              {/* Site 1: Peak near Cabeus B (83.6°S, 68.8°W) */}
              <g transform="translate(74, 96)">
                <circle r="7" fill="rgba(245, 184, 61, 0.25)" />
                <circle r="3.5" fill="#f5b83d" stroke="#fff" strokeWidth="1" />
                <text x="9" y="4" fill="#f5b83d" fontSize="9" fontWeight="bold" fontFamily="sans-serif">1. Peak nr Cabeus B</text>
              </g>

              {/* Site 2: Haworth (86.9°S, 4°W) */}
              <g transform="translate(164, 114)">
                <circle r="7" fill="rgba(90, 210, 230, 0.25)" />
                <circle r="3.5" fill="#5ad2e6" stroke="#fff" strokeWidth="1" />
                <text x="9" y="4" fill="#5ad2e6" fontSize="9" fontWeight="bold" fontFamily="sans-serif">2. Haworth</text>
              </g>

              {/* Sites 3-9: Compact */}
              <g transform="translate(175, 118)">
                <circle r="2.5" fill="#a8b3c7" />
                <text x="6" y="2" fill="#7c899e" fontSize="8" fontFamily="sans-serif">3. Malapert</text>
              </g>
              <g transform="translate(216, 122)">
                <circle r="2.5" fill="#a8b3c7" />
                <text x="6" y="2" fill="#7c899e" fontSize="8" fontFamily="sans-serif">4. Mons Mouton</text>
              </g>
              <g transform="translate(250, 142)">
                <circle r="2.5" fill="#a8b3c7" />
                <text x="6" y="2" fill="#7c899e" fontSize="8" fontFamily="sans-serif">5. Nobile Rim 2</text>
              </g>
              <g transform="translate(168, 178)">
                <circle r="2.5" fill="#a8b3c7" />
                <text x="6" y="10" fill="#7c899e" fontSize="8" fontFamily="sans-serif">6. Conn. Ridge</text>
              </g>
              <g transform="translate(156, 172)">
                <circle r="2.5" fill="#a8b3c7" />
                <text x="-75" y="2" fill="#7c899e" fontSize="8" fontFamily="sans-serif">7. Conn. Ridge Ext</text>
              </g>
              <g transform="translate(210, 136)">
                <circle r="2.5" fill="#a8b3c7" />
                <text x="6" y="10" fill="#7c899e" fontSize="8" fontFamily="sans-serif">8. Leibnitz Beta</text>
              </g>
              <g transform="translate(256, 154)">
                <circle r="2.5" fill="#a8b3c7" />
                <text x="6" y="10" fill="#7c899e" fontSize="8" fontFamily="sans-serif">9. Amundsen</text>
              </g>
            </svg>
          </div>

          <div
            style={{
              display: "flex",
              justifyContent: "center",
              gap: "1.25rem",
              fontSize: "0.78rem",
              color: "var(--text-secondary)",
              flexWrap: "wrap",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
              <span style={{ width: "8px", height: "8px", borderRadius: "50%", backgroundColor: "#f5b83d" }} />
              <span>Site 1: Peak near Cabeus B</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
              <span style={{ width: "8px", height: "8px", borderRadius: "50%", backgroundColor: "#5ad2e6" }} />
              <span>Site 2: Haworth</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
              <span style={{ width: "6px", height: "6px", borderRadius: "50%", backgroundColor: "#a8b3c7" }} />
              <span>Compact Sites 3–9</span>
            </div>
          </div>
        </div>
      </div>

      {/* Filter Tabs for Detailed Dossiers */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.5rem",
          flexWrap: "wrap",
          borderBottom: "1px solid var(--border-subtle)",
          paddingBottom: "0.75rem",
        }}
      >
        <span style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginRight: "0.25rem" }}>
          Major Site Dossiers:
        </span>
        <button
          type="button"
          className={`btn ${activeDetailedSite === "all" ? "btn-primary" : ""}`}
          onClick={() => setActiveDetailedSite("all")}
          style={{ fontSize: "0.82rem", padding: "0.35rem 0.8rem" }}
        >
          Both Major Sites (1 &amp; 2)
        </button>
        <button
          type="button"
          className={`btn ${activeDetailedSite === "cabeus-b" ? "btn-primary" : ""}`}
          onClick={() => setActiveDetailedSite("cabeus-b")}
          style={{ fontSize: "0.82rem", padding: "0.35rem 0.8rem" }}
        >
          Site Code 1: Peak near Cabeus B
        </button>
        <button
          type="button"
          className={`btn ${activeDetailedSite === "haworth" ? "btn-primary" : ""}`}
          onClick={() => setActiveDetailedSite("haworth")}
          style={{ fontSize: "0.82rem", padding: "0.35rem 0.8rem" }}
        >
          Site Code 2: Haworth
        </button>
      </div>

      {/* DETAILED DOSSIER 1: PEAK NEAR CABEUS B */}
      {(activeDetailedSite === "all" || activeDetailedSite === "cabeus-b") && (
        <article
          id="peak-near-cabeus-b-dossier"
          className="glass-panel-strong"
          style={{
            padding: "1.75rem",
            border: "1px solid var(--accent-amber-border)",
            borderRadius: "var(--radius-lg)",
            display: "flex",
            flexDirection: "column",
            gap: "1.25rem",
          }}
        >
          {/* Header */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "0.75rem" }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.25rem" }}>
                <span className="pill-badge amber">Site Code: 1</span>
                <span className="mono" style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                  MAJOR SITE · FULL DOSSIER
                </span>
              </div>
              <h3 style={{ margin: "0.2rem 0 0.35rem", fontSize: "1.45rem", color: "var(--text-primary)" }}>
                Peak near Cabeus B
              </h3>
              <p className="mono" style={{ margin: 0, fontSize: "0.95rem", color: "var(--accent-amber)" }}>
                Coordinates: Latitude: 83.6°S · Longitude: 68.8°W (East longitude equivalent: 291.2°E)
              </p>
            </div>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <Link to="/simulation" className="btn btn-primary" style={{ padding: "0.4rem 0.85rem", fontSize: "0.82rem" }}>
                Run SPICE Simulation &rarr;
              </Link>
            </div>
          </div>

          <hr style={{ border: "none", borderTop: "1px solid var(--border-subtle)", margin: "0.25rem 0" }} />

          {/* Section A: Overview */}
          <div className="glass-panel" style={{ padding: "1.25rem" }}>
            <h4 style={{ margin: "0 0 0.5rem", fontSize: "1.05rem", color: "var(--text-primary)" }}>
              A. Overview &amp; Scientific Significance
            </h4>
            <p style={{ margin: 0, fontSize: "0.92rem", color: "var(--text-secondary)", lineHeight: 1.6 }}>
              Peak near Cabeus B is an elevated prominence near the lunar south pole, located next to Cabeus B crater and Cabeus crater.
              Its geographical location provides a strategic vantage over surrounding permanently shadowed regions (PSRs) that hold significant
              potential for water ice volatiles. It was officially added to NASA's Artemis III candidate list in the October 2024 update as a
              primary candidate for lunar resource research and lunar geological investigation.
            </p>
          </div>

          {/* Section E: Three-Image Gallery */}
          <div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.75rem" }}>
              <h4 style={{ margin: 0, fontSize: "1.05rem", color: "var(--text-primary)" }}>
                E. Scientific Gallery (3 Authenticated Images)
              </h4>
              <span className="mono" style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                NASA PDS / LRO / LOLA Sources
              </span>
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
                gap: "1rem",
              }}
            >
              {CABEUS_B_IMAGES.map((img, idx) => (
                <div
                  key={idx}
                  className="glass-panel"
                  style={{
                    overflow: "hidden",
                    display: "flex",
                    flexDirection: "column",
                    border: "1px solid var(--border-subtle)",
                    cursor: "pointer",
                  }}
                  onClick={() => setSelectedImage(img)}
                >
                  <div style={{ position: "relative", width: "100%", height: "180px", background: "#05070b" }}>
                    <img
                      src={img.thumbSrc}
                      alt={img.caption}
                      style={{ width: "100%", height: "100%", objectFit: "cover" }}
                      loading="lazy"
                    />
                    <span
                      className="pill-badge"
                      style={{
                        position: "absolute",
                        top: "8px",
                        left: "8px",
                        fontSize: "0.68rem",
                        backgroundColor: "rgba(0,0,0,0.75)",
                        border: "1px solid rgba(255,255,255,0.2)",
                      }}
                    >
                      {img.imageType}
                    </span>
                  </div>

                  <div style={{ padding: "0.85rem", display: "flex", flexDirection: "column", gap: "0.35rem", flex: 1 }}>
                    <strong style={{ fontSize: "0.88rem", color: "var(--text-primary)" }}>{img.title}</strong>
                    <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--text-secondary)", lineHeight: 1.4, flex: 1 }}>
                      {img.caption}
                    </p>
                    <span className="mono" style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                      Credit: {img.credit}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Section B & C: Advantages & Disadvantages Side-by-Side */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(290px, 1fr))",
              gap: "1.25rem",
            }}
          >
            {/* Advantages */}
            <div
              className="glass-panel"
              style={{
                padding: "1.25rem",
                borderLeft: "3px solid var(--status-ok)",
                backgroundColor: "rgba(70, 209, 138, 0.04)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.75rem" }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--status-ok)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                  <polyline points="22 4 12 14.01 9 11.01" />
                </svg>
                <h4 style={{ margin: 0, fontSize: "1.05rem", color: "var(--status-ok)" }}>
                  B. Advantages
                </h4>
              </div>

              <ul style={{ margin: 0, paddingLeft: "1.2rem", display: "flex", flexDirection: "column", gap: "0.55rem", fontSize: "0.9rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                <li>Located near the Cabeus crater, an area of significant scientific interest because of permanently shadowed regions.</li>
                <li>Provides an opportunity to investigate water ice and other potentially useful lunar resources.</li>
                <li>Elevated terrain provides access to surrounding crater structures and geological formations.</li>
                <li>Can contribute information about the Moon's geological history.</li>
              </ul>
            </div>

            {/* Disadvantages */}
            <div
              className="glass-panel"
              style={{
                padding: "1.25rem",
                borderLeft: "3px solid var(--status-warn)",
                backgroundColor: "rgba(245, 184, 61, 0.04)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.75rem" }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--status-warn)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                  <line x1="12" y1="9" x2="12" y2="13" />
                  <line x1="12" y1="17" x2="12.01" y2="17" />
                </svg>
                <h4 style={{ margin: 0, fontSize: "1.05rem", color: "var(--status-warn)" }}>
                  C. Disadvantages
                </h4>
              </div>

              <ul style={{ margin: 0, paddingLeft: "1.2rem", display: "flex", flexDirection: "column", gap: "0.55rem", fontSize: "0.9rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                <li>Very limited safe landing area, with approximately 2.1 km² meeting the specified landing-slope requirements.</li>
                <li>Surrounding terrain presents challenges for astronaut and rover movement.</li>
                <li>Permanently shadowed regions may limit sunlight availability and complicate solar power generation.</li>
                <li>Limited suitable terrain reduces flexibility when choosing the exact touchdown location.</li>
              </ul>
            </div>
          </div>

          {/* Section D: History and Background */}
          <div
            className="glass-panel"
            style={{
              padding: "1.25rem",
              borderLeft: "3px solid var(--accent-cyan)",
              backgroundColor: "rgba(90, 210, 230, 0.04)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.75rem" }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--accent-cyan)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <circle cx="12" cy="12" r="10" />
                <polyline points="12 6 12 12 16 14" />
              </svg>
              <h4 style={{ margin: 0, fontSize: "1.05rem", color: "var(--accent-cyan)" }}>
                D. History and Background
              </h4>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "0.65rem", fontSize: "0.91rem", color: "var(--text-secondary)", lineHeight: 1.6 }}>
              <p style={{ margin: 0 }}>
                Peak near Cabeus B is not a formally named lunar feature. It was added to NASA's Artemis III candidate list in the October 2024 update.
                It is located near Cabeus B crater, next to Cabeus crater, with its centre at approximately 83.6°S, 291.2°E (68.8°W).
              </p>
              <p style={{ margin: 0 }}>
                The terrain rises approximately 6 km over a 30 km span, from roughly 2,900 m below to 3,850 m above mean lunar level.
              </p>
              <p style={{ margin: 0 }}>
                The region is close to the LCROSS impact location in Cabeus crater. NASA's LCROSS probe deliberately impacted Cabeus crater on 9 October 2009.
                The impact plume contained water ice, making the region scientifically important for lunar resource research.
              </p>
            </div>
          </div>
        </article>
      )}

      {/* DETAILED DOSSIER 2: HAWORTH */}
      {(activeDetailedSite === "all" || activeDetailedSite === "haworth") && (
        <article
          id="haworth-dossier"
          className="glass-panel-strong"
          style={{
            padding: "1.75rem",
            border: "1px solid var(--accent-cyan-border)",
            borderRadius: "var(--radius-lg)",
            display: "flex",
            flexDirection: "column",
            gap: "1.25rem",
          }}
        >
          {/* Header */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "0.75rem" }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.25rem" }}>
                <span className="pill-badge cyan">Site Code: 2</span>
                <span className="mono" style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                  MAJOR SITE · FULL DOSSIER
                </span>
              </div>
              <h3 style={{ margin: "0.2rem 0 0.35rem", fontSize: "1.45rem", color: "var(--text-primary)" }}>
                Haworth
              </h3>
              <p className="mono" style={{ margin: 0, fontSize: "0.95rem", color: "var(--accent-cyan)" }}>
                Coordinates: Primary: Latitude: 86.9°S · Longitude: 4.0°W
              </p>
              <p className="mono" style={{ margin: "0.15rem 0 0", fontSize: "0.82rem", color: "var(--text-muted)" }}>
                Alternative gazetteer coordinates: 87.45°S, 5.2°W
              </p>
            </div>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <Link to="/simulation" className="btn btn-primary" style={{ padding: "0.4rem 0.85rem", fontSize: "0.82rem" }}>
                Run SPICE Simulation &rarr;
              </Link>
            </div>
          </div>

          <hr style={{ border: "none", borderTop: "1px solid var(--border-subtle)", margin: "0.25rem 0" }} />

          {/* Section A: Overview */}
          <div className="glass-panel" style={{ padding: "1.25rem" }}>
            <h4 style={{ margin: "0 0 0.5rem", fontSize: "1.05rem", color: "var(--text-primary)" }}>
              A. Overview &amp; Crater Context
            </h4>
            <p style={{ margin: 0, fontSize: "0.92rem", color: "var(--text-secondary)", lineHeight: 1.6 }}>
              Haworth is an ancient Pre-Nectarian impact crater located near the lunar south pole, spanning approximately 51 km across.
              Its geographical context features deep permanently shadowed regions (PSRs) that never receive direct sunlight and maintain
              temperatures near 40 K, preserving surface frost and volatiles, alongside gentle terrain zones evaluated for crewed surface exploration.
            </p>
          </div>

          {/* Section E: Three-Image Gallery */}
          <div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.75rem" }}>
              <h4 style={{ margin: 0, fontSize: "1.05rem", color: "var(--text-primary)" }}>
                E. Scientific Gallery (3 Authenticated Images)
              </h4>
              <span className="mono" style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                NASA LRO / LOLA / Diviner Sources
              </span>
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
                gap: "1rem",
              }}
            >
              {HAWORTH_IMAGES.map((img, idx) => (
                <div
                  key={idx}
                  className="glass-panel"
                  style={{
                    overflow: "hidden",
                    display: "flex",
                    flexDirection: "column",
                    border: "1px solid var(--border-subtle)",
                    cursor: "pointer",
                  }}
                  onClick={() => setSelectedImage(img)}
                >
                  <div style={{ position: "relative", width: "100%", height: "180px", background: "#05070b" }}>
                    <img
                      src={img.thumbSrc}
                      alt={img.caption}
                      style={{ width: "100%", height: "100%", objectFit: "cover" }}
                      loading="lazy"
                    />
                    <span
                      className="pill-badge"
                      style={{
                        position: "absolute",
                        top: "8px",
                        left: "8px",
                        fontSize: "0.68rem",
                        backgroundColor: "rgba(0,0,0,0.75)",
                        border: "1px solid rgba(255,255,255,0.2)",
                      }}
                    >
                      {img.imageType}
                    </span>
                  </div>

                  <div style={{ padding: "0.85rem", display: "flex", flexDirection: "column", gap: "0.35rem", flex: 1 }}>
                    <strong style={{ fontSize: "0.88rem", color: "var(--text-primary)" }}>{img.title}</strong>
                    <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--text-secondary)", lineHeight: 1.4, flex: 1 }}>
                      {img.caption}
                    </p>
                    <span className="mono" style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                      Credit: {img.credit}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Section B & C: Advantages & Disadvantages Side-by-Side */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(290px, 1fr))",
              gap: "1.25rem",
            }}
          >
            {/* Advantages */}
            <div
              className="glass-panel"
              style={{
                padding: "1.25rem",
                borderLeft: "3px solid var(--status-ok)",
                backgroundColor: "rgba(70, 209, 138, 0.04)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.75rem" }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--status-ok)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                  <polyline points="22 4 12 14.01 9 11.01" />
                </svg>
                <h4 style={{ margin: 0, fontSize: "1.05rem", color: "var(--status-ok)" }}>
                  B. Advantages
                </h4>
              </div>

              <ul style={{ margin: 0, paddingLeft: "1.2rem", display: "flex", flexDirection: "column", gap: "0.55rem", fontSize: "0.9rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                <li>Relatively extensive areas of gentle slopes suitable for landing and surface exploration.</li>
                <li>Access to permanently shadowed regions that may contain water ice and other volatile materials.</li>
                <li>Opportunities to study ancient lunar geological formations.</li>
                <li>Several areas have relatively low surface roughness, supporting astronaut and rover mobility.</li>
              </ul>
            </div>

            {/* Disadvantages */}
            <div
              className="glass-panel"
              style={{
                padding: "1.25rem",
                borderLeft: "3px solid var(--status-warn)",
                backgroundColor: "rgba(245, 184, 61, 0.04)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.75rem" }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--status-warn)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                  <line x1="12" y1="9" x2="12" y2="13" />
                  <line x1="12" y1="17" x2="12.01" y2="17" />
                </svg>
                <h4 style={{ margin: 0, fontSize: "1.05rem", color: "var(--status-warn)" }}>
                  C. Disadvantages
                </h4>
              </div>

              <ul style={{ margin: 0, paddingLeft: "1.2rem", display: "flex", flexDirection: "column", gap: "0.55rem", fontSize: "0.9rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                <li>Steep slopes around crater rims can restrict movement and exploration.</li>
                <li>Permanently shadowed areas receive little or no direct sunlight, complicating scientific access and operations.</li>
                <li>Sunlight and Earth visibility vary across the region, potentially affecting power generation and communication.</li>
                <li>Rugged surroundings increase navigation complexity.</li>
              </ul>
            </div>
          </div>

          {/* Section D: History and Background */}
          <div
            className="glass-panel"
            style={{
              padding: "1.25rem",
              borderLeft: "3px solid var(--accent-cyan)",
              backgroundColor: "rgba(90, 210, 230, 0.04)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.75rem" }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--accent-cyan)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <circle cx="12" cy="12" r="10" />
                <polyline points="12 6 12 12 16 14" />
              </svg>
              <h4 style={{ margin: 0, fontSize: "1.05rem", color: "var(--accent-cyan)" }}>
                D. History and Background
              </h4>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "0.65rem", fontSize: "0.91rem", color: "var(--text-secondary)", lineHeight: 1.6 }}>
              <p style={{ margin: 0 }}>
                Haworth is a Pre-Nectarian impact crater estimated to be over 3.9 billion years old, approximately 51 km across, located near the lunar south pole.
                Its centre is approximately 86.9°S, 4°W, with alternative gazetteer coordinates of approximately 87.45°S, 5.2°W.
              </p>
              <p style={{ margin: 0 }}>
                Named after Walter Haworth, the British chemist who won the 1937 Nobel Prize in Chemistry for work on vitamin C, with the name officially approved in October 2008.
              </p>
              <p style={{ margin: 0 }}>
                Because the crater lies in near-permanent shadow, it is rarely visible in photographs and was known mainly through Earth-based radar observations.
                Much of its interior is permanently shadowed and extremely cold, possibly never exceeding approximately 40 K. Surrounding low-lying areas also contain frost.
              </p>
              <p style={{ margin: 0 }}>
                Haworth was one of NASA's 13 Artemis III candidate landing regions announced in 2022 and remained among the nine shortlisted regions announced in October 2024.
              </p>
            </div>
          </div>
        </article>
      )}

      {/* Lightbox Modal for Gallery Images */}
      {selectedImage && (
        <div
          className="drawer-backdrop"
          style={{ zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center", padding: "1.5rem" }}
          onClick={() => setSelectedImage(null)}
        >
          <div
            className="glass-panel-strong"
            style={{
              maxWidth: "850px",
              width: "100%",
              maxHeight: "90vh",
              overflowY: "auto",
              padding: "1.5rem",
              borderRadius: "var(--radius-lg)",
              border: "1px solid var(--border-strong)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
              <div>
                <span className="pill-badge cyan" style={{ marginBottom: "0.25rem" }}>{selectedImage.imageType}</span>
                <h3 style={{ margin: 0, fontSize: "1.2rem" }}>{selectedImage.title}</h3>
              </div>
              <button type="button" className="btn" onClick={() => setSelectedImage(null)}>
                Close &times;
              </button>
            </div>

            <img
              src={selectedImage.src}
              alt={selectedImage.caption}
              style={{ width: "100%", borderRadius: "var(--radius-md)", border: "1px solid var(--border-subtle)", marginBottom: "1rem" }}
            />

            <p style={{ margin: "0 0 0.5rem", fontSize: "0.92rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
              {selectedImage.caption}
            </p>
            <div className="mono" style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
              Source Credit: {selectedImage.credit} | Reference: {selectedImage.sourceUrl}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
