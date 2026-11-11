import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { fetchSites } from "../api/endpoints";
import { queryKeys } from "../api/queryKeys";
import { useTheme } from "../app/ThemeContext";
import { SiteHeader } from "../components/SiteHeader";
import { UtilitiesFooter } from "../components/UtilitiesFooter";
import { HeadTags } from "../seo/HeadTags";
import { LunarMoonCanvas } from "../three/LunarMoonCanvas";

export function IntroPage() {
  const { reducedMotion } = useTheme();
  const scrollProgressRef = useRef(0);

  const sitesQuery = useQuery({
    queryKey: queryKeys.sites({ status: "published", page_size: 50 }),
    queryFn: () => fetchSites({ status: "published", page_size: 50 }),
    staleTime: 60_000,
  });

  const sites = sitesQuery.data?.items ?? [];

  useEffect(() => {
    if (reducedMotion) {
      scrollProgressRef.current = 0;
      return;
    }
    const doc = document.documentElement;
    let maxScroll = Math.max(1, doc.scrollHeight - doc.clientHeight);

    function updateMaxScroll() {
      maxScroll = Math.max(1, doc.scrollHeight - doc.clientHeight);
    }

    function handleScroll() {
      const pct = Math.min(1, Math.max(0, window.scrollY / maxScroll));
      scrollProgressRef.current = pct;
    }

    const resizeObserver =
      typeof ResizeObserver !== "undefined" ? new ResizeObserver(updateMaxScroll) : null;
    resizeObserver?.observe(doc);
    window.addEventListener("resize", updateMaxScroll, { passive: true });
    window.addEventListener("scroll", handleScroll, { passive: true });
    handleScroll();

    return () => {
      resizeObserver?.disconnect();
      window.removeEventListener("resize", updateMaxScroll);
      window.removeEventListener("scroll", handleScroll);
    };
  }, [reducedMotion]);

  const latestUpdate =
    sites.length > 0
      ? sites
          .map((s) => s.updated_at.slice(0, 10))
          .sort()
          .slice(-1)[0]
      : undefined;

  return (
    <div className="page-shell">
      <HeadTags
        meta={{
          title: "CLPS Luna Browser — Lunar Landing-Site Analysis & Simulation",
          description:
            "Interactive 3D lunar landing-site explorer, scientific deterministic comparator, local AI mission assist, and topocentric Sun/Earth visibility simulator.",
          canonicalPath: "/",
          robots: "index,follow",
          ogType: "website",
          breadcrumbs: [{ name: "Home", path: "/" }],
        }}
      />

      <SiteHeader showSearch />

      <main id="main-content" className="page-content-layer">
        {/* Three-sector approved intro layout */}
        <section className="intro-hero" aria-label="CLPS Luna Browser overview">
          <div className="intro-left-rail">
            <Link
              to="/admin"
              className="btn glass-panel"
              aria-label="Open Admin Portal login"
              style={{ width: "fit-content" }}
            >
              ADMIN
            </Link>
          </div>

          <div className="glass-panel intro-center-col">
            <p className="eyebrow" style={{ margin: "0 0 0.5rem", color: "var(--accent-amber)" }}>
              Lunar Mission Planning Platform
            </p>
            <h1
              style={{
                margin: "0 0 0.9rem",
                fontSize: "clamp(2rem, 3.6vw, 3rem)",
                lineHeight: 1.08,
                letterSpacing: "-0.02em",
              }}
            >
              <span style={{ color: "var(--accent-amber)" }}>CLPS</span> Luna Browser
            </h1>
            <p
              style={{
                margin: "0 0 1.4rem",
                color: "var(--text-secondary)",
                fontSize: "1rem",
                maxWidth: "46ch",
              }}
            >
              Inspect candidate lunar landing sites with cited engineering metrics, run
              deterministic multi-criteria site comparisons, generate mission-matched
              shortlists with local AI assist, and simulate Sun and Earth topocentric
              visibility across selenographic coordinates.
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem", alignItems: "center" }}>
              <Link to="/browser" className="btn btn-primary" style={{ padding: "0.75rem 1.35rem", fontSize: "0.98rem" }}>
                Luna Browser -&gt;
              </Link>
              <span className="pill-badge cyan">
                {sitesQuery.isLoading
                  ? "Loading catalogue..."
                  : `${sites.length} Published Sites`}
              </span>
            </div>
          </div>

          <div className="intro-moon-stage">
            <LunarMoonCanvas
              mode="intro"
              sites={sites}
              scrollProgressRef={scrollProgressRef}
              reducedMotion={reducedMotion}
            />
          </div>

          <a
            href="#platform-capabilities"
            className="scroll-indicator"
            aria-label="Scroll to platform capabilities"
          >
            <span>Scroll</span>
            <span aria-hidden="true">v</span>
          </a>
        </section>

        {/* Ordered factual reveal sections */}
        <section
          id="platform-capabilities"
          className="container"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
            gap: "1.1rem",
            paddingTop: "1rem",
          }}
        >
          <article className="glass-panel" style={{ padding: "1.25rem" }}>
            <p className="eyebrow" style={{ margin: "0 0 0.4rem", color: "var(--accent-amber)" }}>
              01 · Interactive Catalogue
            </p>
            <h2 style={{ margin: "0 0 0.6rem", fontSize: "1.15rem" }}>
              MOON_ME Landing-Site Dossiers
            </h2>
            <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "0.92rem" }}>
              Every site entry displays recorded selenographic latitude, longitude, elevation,
              parameter provenance, quality status badges, and explicit warnings wherever
              historical or photographic records remain uningested.
            </p>
          </article>

          <article className="glass-panel" style={{ padding: "1.25rem" }}>
            <p className="eyebrow" style={{ margin: "0 0 0.4rem", color: "var(--accent-cyan)" }}>
              02 · Deterministic Analysis
            </p>
            <h2 style={{ margin: "0 0 0.6rem", fontSize: "1.15rem" }}>
              Purpose-Driven Comparison &amp; AI Assist
            </h2>
            <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "0.92rem" }}>
              Side-by-side comparison avoids arbitrary universal scores by weighting parameters
              strictly against mission purpose. Natural-language AI assist falls back openly to
              deterministic keyword scoring when Ollama is unavailable.
            </p>
          </article>

          <article className="glass-panel" style={{ padding: "1.25rem" }}>
            <p className="eyebrow" style={{ margin: "0 0 0.4rem", color: "var(--accent-amber)" }}>
              03 · Ephemeris &amp; CODEX Boundary
            </p>
            <h2 style={{ margin: "0 0 0.6rem", fontSize: "1.15rem" }}>
              SPICE + LOLA Horizon &amp; Mock Hardware Preview
            </h2>
            <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "0.92rem" }}>
              Topocentric Sun/Earth visibility simulations clearly report geometric-only vs
              terrain-aware quality states. CODEX operates in non-actuating Mock/Demonstration mode
              while Phase 5 physical bench verification awaits hardware sign-off.
            </p>
          </article>
        </section>

        {/* Required Support & Assist section with exact heading */}
        <section
          className="container"
          aria-labelledby="support-assist-heading"
          style={{ paddingTop: "0.5rem" }}
        >
          <div className="glass-panel" style={{ padding: "1.5rem" }}>
            <h2
              id="support-assist-heading"
              style={{ margin: "0 0 0.6rem", fontSize: "1.35rem" }}
            >
              Support &amp; Assist
            </h2>
            <p style={{ margin: "0 0 1rem", color: "var(--text-secondary)", maxWidth: "68ch" }}>
              Inspect surface provenance, report scientific dataset discrepancies, or contact the
              mission software team. Planetary globe textures are adapted from NASA SVS CGI Moon Kit
              public-domain LROC and LOLA elevation data; CLPS Luna Browser is an independent
              tool and is not endorsed by NASA.
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem" }}>
              <Link to="/browser" className="btn btn-primary">
                Open Lunar Browser -&gt;
              </Link>
              <Link to="/compare" className="btn">
                Compare Two Sites
              </Link>
              <Link to="/ai-assist" className="btn">
                AI Assist
              </Link>
              <Link to="/contact" className="btn">
                Contact Support
              </Link>
            </div>
          </div>
        </section>
      </main>

      <UtilitiesFooter lastUpdated={latestUpdate} />
    </div>
  );
}

