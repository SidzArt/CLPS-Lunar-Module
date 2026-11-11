import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

export interface UtilitiesFooterProps {
  lastUpdated?: string;
}

export function UtilitiesFooter({ lastUpdated }: UtilitiesFooterProps) {
  const [scrollPct, setScrollPct] = useState(0);

  useEffect(() => {
    function onScroll() {
      const doc = document.documentElement;
      const total = doc.scrollHeight - doc.clientHeight;
      if (total <= 0) {
        setScrollPct(0);
      } else {
        setScrollPct(Math.min(100, Math.max(0, (window.scrollY / total) * 100)));
      }
    }
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <>
      <div
        className="scroll-progress-bar no-print"
        style={{ width: `${scrollPct.toFixed(1)}%` }}
        aria-hidden="true"
      />
      <footer className="utilities-footer no-print">
        <div className="utilities-footer-inner">
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.9rem", alignItems: "center" }}>
            <span>
              CLPS Luna Browser · Independent educational &amp; mission-planning platform
              (not endorsed by NASA).
            </span>
            {lastUpdated && (
              <span className="mono" style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>
                Catalogue updated: {lastUpdated}
              </span>
            )}
          </div>

          <nav aria-label="Footer support links" style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
            <Link to="/browser">Browser</Link>
            <Link to="/compare">Compare</Link>
            <Link to="/ai-assist">AI Assist</Link>
            <Link to="/simulation">Simulation</Link>
            <Link to="/contact">Contact</Link>
            <Link to="/privacy">Privacy</Link>
            <Link to="/terms">Terms</Link>
            <button
              type="button"
              className="btn btn-ghost"
              style={{ padding: "0.15rem 0.5rem", fontSize: "0.8rem" }}
              onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
            >
              Top
            </button>
          </nav>
        </div>
      </footer>
    </>
  );
}

