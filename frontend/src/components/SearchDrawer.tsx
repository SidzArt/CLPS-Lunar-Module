import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { searchLandingSites, type SearchResultOut } from "../api/endpoints";
import { formatLatLon } from "../utils/formatting";
import { CloseIcon, SearchIcon } from "./Icons";

export interface SearchDrawerProps {
  open: boolean;
  onClose: () => void;
}

export function SearchDrawer({ open, onClose }: SearchDrawerProps) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResultOut[]>([]);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setResults([]);
      setErrorMsg(null);
      return;
    }
    const timer = window.setTimeout(async () => {
      setLoading(true);
      setErrorMsg(null);
      try {
        const hits = await searchLandingSites(trimmed, 12);
        setResults(hits);
      } catch (err) {
        setErrorMsg(err instanceof Error ? err.message : "Search failed.");
      } finally {
        setLoading(false);
      }
    }, 220);

    return () => window.clearTimeout(timer);
  }, [query, open]);

  if (!open) {
    return null;
  }

  return (
    <div
      className="drawer-backdrop no-print"
      role="presentation"
      onClick={onClose}
    >
      <div
        className="glass-panel-strong drawer-panel"
        role="dialog"
        aria-modal="true"
        aria-label="Global landing site search"
        onClick={(event) => event.stopPropagation()}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: "1rem",
          }}
        >
          <div>
            <p className="eyebrow" style={{ margin: 0 }}>
              Catalogue Index
            </p>
            <h2 style={{ margin: "0.15rem 0 0", fontSize: "1.15rem" }}>
              Search Landing Sites
            </h2>
          </div>
          <button
            type="button"
            className="btn"
            aria-label="Close search drawer"
            onClick={onClose}
          >
            <CloseIcon />
          </button>
        </div>

        <label className="field-label" htmlFor="global-site-search-input">
          Site name, code, region, or narrative keyword
        </label>
        <div style={{ position: "relative", marginBottom: "1rem" }}>
          <input
            id="global-site-search-input"
            type="search"
            className="input"
            placeholder="e.g. Lunokhod, Imbrium, Mons Mouton..."
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            autoFocus
            style={{ paddingLeft: "2.1rem" }}
          />
          <span
            style={{
              position: "absolute",
              left: "0.7rem",
              top: "50%",
              transform: "translateY(-50%)",
              color: "var(--text-muted)",
              pointerEvents: "none",
            }}
          >
            <SearchIcon size={15} />
          </span>
        </div>

        {query.trim().length < 2 && (
          <p style={{ color: "var(--text-secondary)", fontSize: "0.86rem" }}>
            Enter at least 2 characters to search verified catalogue records.
          </p>
        )}

        {loading && (
          <p style={{ color: "var(--text-secondary)", fontSize: "0.86rem" }}>
            Searching landing sites...
          </p>
        )}

        {errorMsg && (
          <div className="notice-banner error" role="alert">
            <span>{errorMsg}</span>
          </div>
        )}

        {!loading && !errorMsg && query.trim().length >= 2 && results.length === 0 && (
          <p style={{ color: "var(--text-secondary)", fontSize: "0.86rem" }}>
            No matching landing sites found for "{query.trim()}".
          </p>
        )}

        <ul
          style={{
            listStyle: "none",
            padding: 0,
            margin: 0,
            display: "flex",
            flexDirection: "column",
            gap: "0.6rem",
          }}
        >
          {results.map((hit) => (
            <li key={hit.site_id}>
              <button
                type="button"
                className="glass-panel"
                onClick={() => {
                  onClose();
                  navigate(`/sites/${encodeURIComponent(hit.site_slug)}`);
                }}
                style={{
                  width: "100%",
                  textAlign: "left",
                  padding: "0.8rem 0.9rem",
                  cursor: "pointer",
                  borderColor: "var(--border-subtle)",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    gap: "0.5rem",
                  }}
                >
                  <strong style={{ fontSize: "0.96rem" }}>{hit.site_name}</strong>
                  <span className="pill-badge cyan mono">{hit.site_code}</span>
                </div>
                <div
                  className="mono"
                  style={{
                    fontSize: "0.76rem",
                    color: "var(--text-secondary)",
                    marginTop: "0.25rem",
                  }}
                >
                  {formatLatLon(hit.latitude_deg, hit.longitude_deg)}
                  {hit.region_name ? ` · ${hit.region_name}` : ""}
                </div>
                {hit.match_snippet && (
                  <p
                    style={{
                      margin: "0.4rem 0 0",
                      fontSize: "0.8rem",
                      color: "var(--text-muted)",
                    }}
                  >
                    Match ({hit.match_field}): {hit.match_snippet}
                  </p>
                )}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

