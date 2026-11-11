import { Link } from "react-router-dom";
import { SiteHeader } from "../components/SiteHeader";
import { UtilitiesFooter } from "../components/UtilitiesFooter";
import { HeadTags } from "../seo/HeadTags";

export function NotFoundPage() {
  return (
    <div className="page-shell">
      <HeadTags
        meta={{
          title: "Page Not Found (404) — CLPS Luna Browser",
          description: "The requested CLPS Luna Browser page could not be found.",
          canonicalPath: "/404",
          robots: "noindex,nofollow",
          ogType: "website",
          breadcrumbs: [
            { name: "Home", path: "/" },
            { name: "Not Found", path: "/404" },
          ],
        }}
      />
      <SiteHeader subtitle="404 Not Found" />
      <main id="main-content" className="page-content-layer container" style={{ maxWidth: "620px" }}>
        <section className="glass-panel-strong" style={{ padding: "1.6rem" }}>
          <p className="eyebrow" style={{ color: "var(--accent-amber)", margin: "0 0 0.35rem" }}>
            HTTP 404
          </p>
          <h1 style={{ margin: "0 0 0.55rem", fontSize: "1.6rem" }}>Route Not Found</h1>
          <p style={{ margin: "0 0 1.2rem", color: "var(--text-secondary)" }}>
            The requested path does not exist in CLPS Luna Browser.
          </p>
          <div style={{ display: "flex", gap: "0.65rem", flexWrap: "wrap" }}>
            <Link to="/" className="btn">
              Home
            </Link>
            <Link to="/browser" className="btn btn-primary">
              Open Lunar Browser -&gt;
            </Link>
          </div>
        </section>
      </main>
      <UtilitiesFooter />
    </div>
  );
}

