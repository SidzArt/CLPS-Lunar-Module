import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { fetchCodexStatus } from "../api/endpoints";
import { queryKeys } from "../api/queryKeys";
import { useTheme } from "../app/ThemeContext";
import { CodexDrawer } from "./CodexDrawer";
import { CrescentLogoIcon, SearchIcon, SunThemeIcon } from "./Icons";
import { SearchDrawer } from "./SearchDrawer";

export interface SiteHeaderProps {
  subtitle?: string;
  showSearch?: boolean;
  rightActions?: ReactNode;
  hideCodexPill?: boolean;
}

export function SiteHeader({
  subtitle,
  showSearch = true,
  rightActions,
  hideCodexPill = false,
}: SiteHeaderProps) {
  const { theme, toggleTheme } = useTheme();
  const [searchOpen, setSearchOpen] = useState(false);
  const [codexOpen, setCodexOpen] = useState(false);

  const codexQuery = useQuery({
    queryKey: queryKeys.codexStatus(),
    queryFn: () => fetchCodexStatus(),
    staleTime: 25_000,
    retry: false,
  });

  const statusData = codexQuery.data;
  const isMock = !statusData || statusData.transport_mode === "mock";
  const hardwareReady =
    Boolean(statusData?.motors_ready) &&
    Boolean(statusData?.calibration_verified) &&
    Boolean(statusData?.led_mapping_verified) &&
    !statusData?.estop_latched &&
    !isMock;

  const codexLabel = codexQuery.isLoading
    ? "CODEX"
    : codexQuery.isError
      ? "CODEX · Unavailable"
      : hardwareReady
        ? "CODEX · Bench Ready"
        : isMock
          ? "CODEX · Mock / Blocked"
          : "CODEX · Blocked";

  return (
    <>
      <header className="site-header no-print">
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", minWidth: 0 }}>
          <Link to="/" className="brand-link" aria-label="CLPS Luna Browser home">
            <CrescentLogoIcon size={22} />
            <span>
              <span className="brand-accent">CLPS</span> Luna Browser
            </span>
          </Link>
          {subtitle && (
            <span
              style={{
                color: "var(--text-muted)",
                fontSize: "0.86rem",
                borderLeft: "1px solid var(--border-subtle)",
                paddingLeft: "0.75rem",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {subtitle}
            </span>
          )}
        </div>

        <div className="header-actions">
          {rightActions}

          {showSearch && (
            <button
              type="button"
              className="btn"
              onClick={() => setSearchOpen(true)}
              aria-label="Open landing site search"
              title="Search landing sites"
            >
              <SearchIcon size={15} />
              <span className="sr-only">Search</span>
            </button>
          )}

          <button
            type="button"
            className="btn"
            onClick={toggleTheme}
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} color theme`}
            title={`Switch to ${theme === "dark" ? "light" : "dark"} color theme`}
          >
            <SunThemeIcon size={15} />
          </button>

          {!hideCodexPill && (
            <button
              type="button"
              className={`pill-badge ${hardwareReady ? "ok" : "amber"}`}
              onClick={() => setCodexOpen(true)}
              style={{ cursor: "pointer", padding: "0.42rem 0.8rem" }}
              aria-label="Inspect CODEX hardware status"
            >
              <span className="status-dot" />
              <span>{codexLabel}</span>
            </button>
          )}
        </div>
      </header>

      <SearchDrawer open={searchOpen} onClose={() => setSearchOpen(false)} />
      <CodexDrawer
        open={codexOpen}
        onClose={() => setCodexOpen(false)}
        status={statusData}
        isLoading={codexQuery.isLoading}
        error={codexQuery.error}
      />
    </>
  );
}

