import { useMutation, useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  fetchSites,
  postAiAssistRecommend,
  type AIAssistResponseOut,
} from "../api/endpoints";
import { queryKeys } from "../api/queryKeys";
import { SiteHeader } from "../components/SiteHeader";
import { UtilitiesFooter } from "../components/UtilitiesFooter";
import { HeadTags } from "../seo/HeadTags";
import { LunarMoonCanvas } from "../three/LunarMoonCanvas";
import { formatElevation, formatLatLon, formatNumber } from "../utils/formatting";

const EXAMPLE_PROMPTS = [
  "Need a site with high solar illumination, reliable direct Earth communication visibility, and slope under 10 degrees.",
  "Recommend south polar sites suited for low-angle illumination research with moderate slope stability.",
  "Basalt mare plains suitable for geological traverse and surface sample characterisation.",
];

export function AiAssistPage() {
  const sitesQuery = useQuery({
    queryKey: queryKeys.sites({ status: "published", page_size: 50 }),
    queryFn: () => fetchSites({ status: "published", page_size: 50 }),
    staleTime: 60_000,
  });

  const sites = sitesQuery.data?.items ?? [];

  const [missionPrompt, setMissionPrompt] = useState(EXAMPLE_PROMPTS[0]);
  const [maxRecommendations, setMaxRecommendations] = useState(5);
  const [minScoreThreshold, setMinScoreThreshold] = useState(0);
  const [result, setResult] = useState<AIAssistResponseOut | null>(null);
  const [validationErr, setValidationErr] = useState<string | null>(null);

  const aiMutation = useMutation({
    mutationFn: (payload: Parameters<typeof postAiAssistRecommend>[0]) =>
      postAiAssistRecommend(payload),
    onSuccess: (data) => {
      setResult(data);
      setValidationErr(null);
    },
  });

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setValidationErr(null);
    if (missionPrompt.trim().length < 8) {
      setValidationErr("Describe your mission requirements in at least 8 characters.");
      return;
    }
    aiMutation.mutate({
      mission_request: missionPrompt.trim(),
      max_recommendations: maxRecommendations,
      min_score_threshold: minScoreThreshold,
    });
  }

  return (
    <div className="page-shell">
      <HeadTags
        meta={{
          title: "AI Assist — CLPS Luna Browser",
          description:
            "Natural-language mission constraint extraction and evidence-grounded landing-site recommendation powered by local Ollama with deterministic fallback.",
          canonicalPath: "/ai-assist",
          robots: "noindex,nofollow",
          ogType: "website",
          breadcrumbs: [
            { name: "Home", path: "/" },
            { name: "AI Assist", path: "/ai-assist" },
          ],
        }}
      />

      <div className="ambient-bg-layer" aria-hidden="true">
        <LunarMoonCanvas mode="ambient" sites={sites} />
      </div>

      <SiteHeader subtitle="Local AI-Assisted Site Selection" />

      <main id="main-content" className="page-content-layer container">
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "0.75rem",
            marginBottom: "1rem",
          }}
        >
          <div>
            <h1 style={{ margin: 0, fontSize: "1.65rem" }}>AI Assist</h1>
            <p style={{ margin: "0.2rem 0 0", color: "var(--text-secondary)", fontSize: "0.92rem" }}>
              Describe your mission constraints to extract structured parameters and rank
              candidate sites deterministically from catalogue metrics.
            </p>
          </div>
          <div className="no-print" style={{ display: "flex", gap: "0.55rem" }}>
            <Link to="/browser" className="btn">
              &lt;- Browser
            </Link>
            <Link to="/compare" className="btn">
              Compare -&gt;
            </Link>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="glass-panel" style={{ padding: "1.15rem", marginBottom: "1.25rem" }}>
          <label htmlFor="ai-assist-prompt" className="field-label">
            Describe mission requirements and engineering constraints
          </label>
          <textarea
            id="ai-assist-prompt"
            className="textarea"
            value={missionPrompt}
            onChange={(event) => setMissionPrompt(event.target.value)}
            rows={3}
            placeholder="e.g. Need high solar illumination, Earth line-of-sight communication, and terrain slope under 12 degrees."
            required
          />

          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "0.5rem",
              marginTop: "0.65rem",
              alignItems: "center",
            }}
          >
            <span className="eyebrow">Quick Prompts:</span>
            {EXAMPLE_PROMPTS.map((preset, idx) => (
              <button
                key={preset}
                type="button"
                className="btn"
                style={{ padding: "0.3rem 0.65rem", fontSize: "0.76rem" }}
                onClick={() => setMissionPrompt(preset)}
              >
                Preset {idx + 1}
              </button>
            ))}
          </div>

          <div
            className="responsive-grid-3"
            style={{ marginTop: "0.9rem", alignItems: "end" }}
          >
            <div>
              <label htmlFor="ai-max-recs" className="field-label">
                Max Recommendations
              </label>
              <select
                id="ai-max-recs"
                className="select"
                value={maxRecommendations}
                onChange={(event) => setMaxRecommendations(Number(event.target.value))}
              >
                <option value={3}>Top 3</option>
                <option value={5}>Top 5</option>
                <option value={10}>Top 10</option>
              </select>
            </div>

            <div>
              <label htmlFor="ai-min-score" className="field-label">
                Min Score Threshold (0.0 - 1.0)
              </label>
              <input
                id="ai-min-score"
                type="number"
                className="input"
                min={0}
                max={1}
                step={0.05}
                value={minScoreThreshold}
                onChange={(event) => setMinScoreThreshold(Number(event.target.value))}
              />
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              disabled={aiMutation.isPending}
              style={{ height: "40px" }}
            >
              {aiMutation.isPending ? "Analysing..." : "Recommend Sites ->"}
            </button>
          </div>

          {validationErr && (
            <div className="notice-banner error" role="alert" style={{ marginTop: "0.8rem" }}>
              <span>{validationErr}</span>
            </div>
          )}

          {aiMutation.isError && (
            <div className="notice-banner error" role="alert" style={{ marginTop: "0.8rem" }}>
              <span>{aiMutation.error.message}</span>
            </div>
          )}
        </form>

        {result && (
          <section aria-label="AI recommendation results" style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div
              className={`notice-banner ${result.fallback_used ? "warn" : "cyan"}`}
              role="status"
            >
              <div>
                <strong style={{ display: "block", marginBottom: "0.2rem" }}>
                  {result.fallback_used
                    ? "Deterministic Keyword Fallback Active"
                    : `Local LLM Extraction (${result.model_used})`}
                </strong>
                <span style={{ fontSize: "0.84rem", color: "var(--text-secondary)" }}>
                  {result.fallback_used
                    ? `Local Ollama did not supply structured extraction (model field: ${result.model_used}); parameters were parsed deterministically and scored strictly against stored site metrics.`
                    : `Constraints extracted by ${result.model_used} in ${result.execution_time_ms.toFixed(0)} ms and scored deterministically against PostgreSQL metrics.`}
                </span>
              </div>
              <span className="pill-badge mono">{result.execution_time_ms.toFixed(0)} ms</span>
            </div>

            {result.clarification_message && (
              <div className="notice-banner warn">
                <span>
                  <strong>Clarification Needed:</strong> {result.clarification_message}
                </span>
              </div>
            )}

            <div className="glass-panel" style={{ padding: "1rem 1.15rem" }}>
              <span className="eyebrow">Mission Summary &amp; Extracted Parameters</span>
              <p style={{ margin: "0.3rem 0 0.7rem", fontSize: "0.95rem" }}>
                {result.mission_summary}
              </p>

              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.45rem" }}>
                {(result.extracted_requirements.required_parameters ?? []).map((p) => (
                  <span key={`req-${p}`} className="pill-badge amber mono">
                    Required: {p}
                  </span>
                ))}
                {(result.extracted_requirements.preferred_parameters ?? []).map((p) => (
                  <span key={`pref-${p}`} className="pill-badge cyan mono">
                    Preferred: {p}
                  </span>
                ))}
                {(result.extracted_requirements.constraints ?? []).map((c, idx) => (
                  <span
                    key={`con-${c.parameter_key}-${idx}`}
                    className="pill-badge mono"
                  >
                    {c.parameter_key} {c.operator} {c.value}
                  </span>
                ))}
              </div>

              {result.limitations && result.limitations.length > 0 && (
                <ul
                  style={{
                    margin: "0.75rem 0 0",
                    paddingLeft: "1.15rem",
                    fontSize: "0.82rem",
                    color: "var(--text-muted)",
                  }}
                >
                  {result.limitations.map((lim) => (
                    <li key={lim}>{lim}</li>
                  ))}
                </ul>
              )}
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(290px, 1fr))",
                gap: "1rem",
              }}
            >
              {result.recommendations.map((rec) => (
                <article
                  key={rec.site_id}
                  className="glass-panel-strong"
                  style={{
                    padding: "1.05rem",
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "space-between",
                    gap: "0.7rem",
                  }}
                >
                  <div>
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "flex-start",
                        gap: "0.5rem",
                      }}
                    >
                      <div>
                        <span className="eyebrow" style={{ color: "var(--accent-amber)" }}>
                          Rank #{rec.rank} · {rec.site_code}
                        </span>
                        <h2 style={{ margin: "0.15rem 0 0", fontSize: "1.12rem" }}>
                          {rec.site_name}
                        </h2>
                      </div>
                      <span
                        className={`pill-badge ${
                          rec.data_quality_status === "verified" ? "ok" : "amber"
                        }`}
                      >
                        Score {formatNumber(rec.score, 2)} ({rec.data_quality_status})
                      </span>
                    </div>

                    <div
                      className="mono"
                      style={{ fontSize: "0.76rem", color: "var(--text-secondary)", marginTop: "0.35rem" }}
                    >
                      {formatLatLon(rec.latitude_deg, rec.longitude_deg)} · Elev{" "}
                      {formatElevation(rec.elevation_m)}
                    </div>

                    <p style={{ margin: "0.65rem 0 0", fontSize: "0.86rem", color: "var(--text-secondary)" }}>
                      {rec.rationale}
                    </p>

                    {rec.matched_parameters &&
                      Object.keys(rec.matched_parameters).length > 0 && (
                        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem", marginTop: "0.65rem" }}>
                          {Object.entries(rec.matched_parameters).map(([k, v]) => (
                            <span key={k} className="pill-badge cyan mono" style={{ fontSize: "0.72rem" }}>
                              {k}: {v === null ? "N/A" : formatNumber(v, 2)}
                            </span>
                          ))}
                        </div>
                      )}

                    {rec.missing_parameters && rec.missing_parameters.length > 0 && (
                      <div style={{ marginTop: "0.55rem", fontSize: "0.76rem", color: "var(--accent-amber)" }}>
                        Missing data: {rec.missing_parameters.join(", ")}
                      </div>
                    )}
                  </div>

                  <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                    <Link
                      to={`/sites/${encodeURIComponent(rec.site_slug)}`}
                      className="btn btn-primary"
                      style={{ flex: 1 }}
                    >
                      View Site -&gt;
                    </Link>
                    <Link
                      to={`/compare?siteA=${rec.site_id}`}
                      className="btn"
                    >
                      Compare
                    </Link>
                  </div>
                </article>
              ))}
            </div>
          </section>
        )}
      </main>

      <UtilitiesFooter />
    </div>
  );
}
