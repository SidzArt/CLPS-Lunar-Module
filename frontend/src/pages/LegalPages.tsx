import { useState } from "react";
import { Link } from "react-router-dom";
import { SiteHeader } from "../components/SiteHeader";
import { UtilitiesFooter } from "../components/UtilitiesFooter";
import { HeadTags } from "../seo/HeadTags";

const CONSENT_STORAGE_KEY = "clps_luna_analytics_consent";

export function PrivacyPage() {
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  function updateConsent(value: "accepted" | "declined") {
    try {
      window.localStorage.setItem(CONSENT_STORAGE_KEY, value);
      setStatusMsg(`Optional analytics preference saved as "${value}".`);
    } catch {
      setStatusMsg("Unable to access browser local storage.");
    }
  }

  return (
    <div className="page-shell">
      <HeadTags
        meta={{
          title: "Privacy Notice — CLPS Luna Browser",
          description:
            "Cookie policy, optional analytics opt-in disclosure, and operator session storage policy for CLPS Luna Browser.",
          canonicalPath: "/privacy",
          robots: "index,follow",
          ogType: "website",
          breadcrumbs: [
            { name: "Home", path: "/" },
            { name: "Privacy", path: "/privacy" },
          ],
        }}
      />
      <SiteHeader subtitle="Privacy Notice" />
      <main id="main-content" className="page-content-layer container" style={{ maxWidth: "820px" }}>
        <article className="glass-panel-strong" style={{ padding: "1.5rem" }}>
          <h1 style={{ margin: "0 0 0.75rem", fontSize: "1.6rem" }}>Privacy Notice</h1>
          <p style={{ color: "var(--text-secondary)" }}>
            CLPS Luna Browser does not require user accounts or tracking cookies for public
            catalogue browsing, comparison, AI assist, or simulation views.
          </p>
          <ul>
            <li>
              <strong>Essential Operator Session Cookie:</strong> Used exclusively when an
              authorised operator explicitly signs in at <Link to="/admin">/admin</Link>.
            </li>
            <li>
              <strong>Optional Analytics:</strong> Google Analytics is never loaded without
              explicit opt-in consent and only when configured via environment variable.
            </li>
            <li>
              <strong>Contact Submissions:</strong> Messages submitted via{" "}
              <Link to="/contact">/contact</Link> store sender name, email, subject, message text,
              and abuse-prevention hashes in PostgreSQL solely for support follow-up.
            </li>
          </ul>
          <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap", marginTop: "1rem" }}>
            <button
              type="button"
              className="btn"
              onClick={() => updateConsent("declined")}
            >
              Disable Optional Analytics
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => updateConsent("accepted")}
            >
              Enable Optional Analytics
            </button>
          </div>
          {statusMsg && (
            <p style={{ marginTop: "0.65rem", color: "var(--accent-cyan)", fontSize: "0.86rem" }}>
              {statusMsg}
            </p>
          )}
        </article>
      </main>
      <UtilitiesFooter />
    </div>
  );
}

export function TermsPage() {
  return (
    <div className="page-shell">
      <HeadTags
        meta={{
          title: "Terms & Scientific Attribution — CLPS Luna Browser",
          description:
            "Scientific methodology disclaimers, NASA SVS CGI Moon Kit attribution, and hardware demonstration notices.",
          canonicalPath: "/terms",
          robots: "index,follow",
          ogType: "website",
          breadcrumbs: [
            { name: "Home", path: "/" },
            { name: "Terms", path: "/terms" },
          ],
        }}
      />
      <SiteHeader subtitle="Terms & Attribution" />
      <main id="main-content" className="page-content-layer container" style={{ maxWidth: "820px" }}>
        <article className="glass-panel-strong" style={{ padding: "1.5rem" }}>
          <h1 style={{ margin: "0 0 0.75rem", fontSize: "1.6rem" }}>
            Terms, Scientific Disclaimers &amp; Attribution
          </h1>
          <ul>
            <li>
              <strong>Non-Endorsement:</strong> CLPS Luna Browser is an independent mission-planning
              and educational visualization platform and is not endorsed by or affiliated with NASA.
            </li>
            <li>
              <strong>Lunar Surface Textures:</strong> Global albedo and displacement imagery is
              derived from the NASA Goddard Space Flight Center Scientific Visualization Studio CGI
              Moon Kit (#4720, public domain LROC &amp; LOLA elevation datasets).
            </li>
            <li>
              <strong>Data Quality Transparency:</strong> Catalogue site metrics explicitly carry
              verified/unverified flags and quality states (`geometric_only` vs DEM terrain-aware
              visibility) so preliminary estimates are never mistaken for flight-certified mission
              data.
            </li>
            <li>
              <strong>CODEX Hardware Safety:</strong> Physical actuation remains blocked until Phase
              5 motor calibration and bench wiring verification are explicitly approved.
            </li>
          </ul>
        </article>
      </main>
      <UtilitiesFooter />
    </div>
  );
}

