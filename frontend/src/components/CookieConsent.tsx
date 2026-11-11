import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

const CONSENT_STORAGE_KEY = "clps_luna_analytics_consent";

type ConsentChoice = "pending" | "accepted" | "declined" | "hidden";

function injectGa4Script(measurementId: string): void {
  if (typeof document === "undefined" || !measurementId) {
    return;
  }
  const existing = document.getElementById("clps-ga4-script");
  if (existing) {
    return;
  }
  const script = document.createElement("script");
  script.id = "clps-ga4-script";
  script.async = true;
  script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(measurementId)}`;
  document.head.appendChild(script);
}

export function CookieConsent() {
  const [choice, setChoice] = useState<ConsentChoice>("hidden");
  const ga4Id = import.meta.env.VITE_GA4_MEASUREMENT_ID as string | undefined;

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(CONSENT_STORAGE_KEY);
      if (saved === "accepted") {
        setChoice("accepted");
        if (ga4Id && ga4Id.trim().length > 0) {
          injectGa4Script(ga4Id.trim());
        }
      } else if (saved === "declined") {
        setChoice("declined");
      } else {
        setChoice("pending");
      }
    } catch {
      setChoice("pending");
    }
  }, [ga4Id]);

  function handleSelect(next: "accepted" | "declined") {
    setChoice(next);
    try {
      window.localStorage.setItem(CONSENT_STORAGE_KEY, next);
    } catch {
      // Ignore storage error
    }
    if (next === "accepted" && ga4Id && ga4Id.trim().length > 0) {
      injectGa4Script(ga4Id.trim());
    }
  }

  if (choice !== "pending") {
    return null;
  }

  return (
    <aside
      className="cookie-consent-bar no-print"
      aria-label="Analytics privacy consent"
    >
      <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--text-secondary)" }}>
        Essential session cookies are used only for authenticated operator routes. Optional
        analytics remain disabled unless you consent (
        <Link to="/privacy" style={{ color: "var(--accent-amber)", textDecoration: "underline" }}>
          Privacy Notice
        </Link>
        ).
      </p>
      <div style={{ display: "flex", gap: "0.45rem", flexShrink: 0, flexWrap: "wrap" }}>
        <button
          type="button"
          className="btn"
          style={{ padding: "0.3rem 0.7rem", fontSize: "0.78rem" }}
          onClick={() => handleSelect("declined")}
        >
          Decline
        </button>
        <button
          type="button"
          className="btn btn-primary"
          style={{ padding: "0.3rem 0.7rem", fontSize: "0.78rem" }}
          onClick={() => handleSelect("accepted")}
        >
          Accept Analytics
        </button>
      </div>
    </aside>
  );
}
