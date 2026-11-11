import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { adminQueryKeys, fetchCsrfToken } from "../../api/adminEndpoints";
import { ApiClientError } from "../../api/client";
import { adminLogin, fetchAdminProfile } from "../../api/endpoints";
import { SiteHeader } from "../../components/SiteHeader";
import { HeadTags } from "../../seo/HeadTags";
import { LunarMoonCanvas } from "../../three/LunarMoonCanvas";

interface LocationState {
  from?: string;
}

export function AdminLoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const state = (location.state as LocationState | null) ?? null;
  const redirectTo =
    state?.from && state.from.startsWith("/admin") && state.from !== "/admin/login"
      ? state.from
      : "/admin";

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [errorSeverity, setErrorSeverity] = useState<"error" | "warn">("error");

  useEffect(() => {
    let active = true;
    fetchCsrfToken().catch(() => {
      // Login form submission will still function if backend sets initial CSRF cookie on login
    });
    fetchAdminProfile()
      .then((profile) => {
        if (!active) return;
        queryClient.setQueryData(adminQueryKeys.me, profile);
        navigate(redirectTo, { replace: true });
      })
      .catch(() => {
        // Expected when unauthenticated
      });
    return () => {
      active = false;
    };
  }, [navigate, queryClient, redirectTo]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setErrorMessage(null);
    setErrorSeverity("error");
    setSubmitting(true);
    try {
      const auth = await adminLogin({
        username: username.trim(),
        password,
      });
      queryClient.setQueryData(adminQueryKeys.me, auth.admin);
      await queryClient.invalidateQueries({ queryKey: ["admin"] });
      navigate(redirectTo, { replace: true });
    } catch (err) {
      if (err instanceof ApiClientError) {
        if (err.status === 423) {
          setErrorSeverity("warn");
          setErrorMessage(
            err.message ||
              "Administrator account is temporarily locked due to repeated failed sign-in attempts.",
          );
        } else if (err.status === 429) {
          setErrorSeverity("warn");
          setErrorMessage(
            err.message || "Too many login attempts from this address. Wait before retrying.",
          );
        } else {
          setErrorMessage(err.message || "Invalid administrator username or password.");
        }
      } else {
        setErrorMessage(err instanceof Error ? err.message : "Authentication request failed.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page-shell">
      <HeadTags
        meta={{
          title: "Administrator Sign-In — CLPS Luna Browser",
          description: "Authenticated CLPS Luna Browser operations portal sign-in.",
          canonicalPath: "/admin/login",
          robots: "noindex,nofollow",
          ogType: "website",
          breadcrumbs: [
            { name: "Home", path: "/" },
            { name: "Admin Sign-In", path: "/admin/login" },
          ],
        }}
      />
      <div className="ambient-bg-layer" aria-hidden="true">
        <LunarMoonCanvas mode="ambient" sites={[]} />
        <div className="admin-ambient-scrim" />
      </div>

      <div className="page-content-layer">
        <SiteHeader />

        <main id="main-content" className="container admin-login-main">
        <section
          className="glass-panel-strong admin-login-card"
          aria-labelledby="admin-login-heading"
        >
          <p className="eyebrow" style={{ marginTop: 0 }}>
            Authenticated Operations Portal
          </p>
          <h1 id="admin-login-heading" style={{ margin: "0.25rem 0 0.5rem", fontSize: "1.65rem" }}>
            Administrator Sign-In
          </h1>
          <p style={{ marginTop: 0, color: "var(--text-secondary)", fontSize: "0.9rem" }}>
            Sessions use hardened <code>HttpOnly</code> cookies and HMAC double-submit CSRF tokens.
            No tokens are persisted in browser storage.
          </p>

          {errorMessage && (
            <div className={`notice-banner ${errorSeverity}`} role="alert" style={{ marginBottom: "1rem" }}>
              <span>{errorMessage}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="admin-login-form">
            <div>
              <label className="field-label" htmlFor="admin-username">
                Username
              </label>
              <input
                id="admin-username"
                name="username"
                type="text"
                required
                autoComplete="username"
                minLength={3}
                maxLength={100}
                className="input"
                placeholder="operator_username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>

            <div>
              <label className="field-label" htmlFor="admin-password">
                Password
              </label>
              <input
                id="admin-password"
                name="password"
                type="password"
                required
                autoComplete="current-password"
                minLength={8}
                maxLength={256}
                className="input"
                placeholder="Enter password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            <div className="admin-login-actions">
              <Link to="/browser" className="btn">
                Return to Public Browser
              </Link>
              <button type="submit" className="btn btn-primary" disabled={submitting}>
                {submitting ? "Signing In..." : "Sign In"}
              </button>
            </div>
          </form>
        </section>
        </main>
      </div>
    </div>
  );
}
