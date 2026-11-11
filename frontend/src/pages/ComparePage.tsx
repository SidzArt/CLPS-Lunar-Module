import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  fetchCompareProfiles,
  fetchSites,
  postCompareSites,
  type ComparisonResultOut,
  type ParameterComparisonOut,
} from "../api/endpoints";
import { queryKeys } from "../api/queryKeys";
import { CopyButton } from "../components/CopyButton";
import { SiteHeader } from "../components/SiteHeader";
import { UtilitiesFooter } from "../components/UtilitiesFooter";
import { HeadTags } from "../seo/HeadTags";
import { LunarMoonCanvas } from "../three/LunarMoonCanvas";
import { formatNumber } from "../utils/formatting";

function formatParamValue(
  numVal: number | null | undefined,
  textVal: string | null | undefined,
  unit: string | null | undefined,
): string {
  if (numVal !== null && numVal !== undefined && !Number.isNaN(numVal)) {
    return `${formatNumber(numVal, 2)}${unit ? ` ${unit}` : ""}`;
  }
  if (textVal && textVal.trim().length > 0) {
    return textVal;
  }
  return "Missing / No Data";
}

function formatParameterWinner(
  row: ParameterComparisonOut,
  nameA: string,
  nameB: string,
): string {
  switch (row.winner_key) {
    case "site_a":
      return nameA;
    case "site_b":
      return nameB;
    case "tie":
      return "Tie";
    case "neutral":
      return "Descriptive / Neutral";
    case "incompatible":
      return "Incompatible Metadata";
    default:
      return "Insufficient Data";
  }
}

export function ComparePage() {
  const [searchParams] = useSearchParams();
  const initialSiteA = Number(searchParams.get("siteA") ?? 0) || undefined;

  const sitesQuery = useQuery({
    queryKey: queryKeys.sites({ status: "published", page_size: 50 }),
    queryFn: () => fetchSites({ status: "published", page_size: 50 }),
    staleTime: 60_000,
  });

  const profilesQuery = useQuery({
    queryKey: queryKeys.compareProfiles(),
    queryFn: () => fetchCompareProfiles(),
    staleTime: 60_000,
  });

  const sites = sitesQuery.data?.items ?? [];
  const profiles = profilesQuery.data ?? [];

  const [siteAId, setSiteAId] = useState<number>(initialSiteA ?? 0);
  const [siteBId, setSiteBId] = useState<number>(0);
  const [missionPurpose, setMissionPurpose] = useState(
    "Evaluate solar power illumination, Earth communication visibility, and terrain landing slope.",
  );
  const [profileKey, setProfileKey] = useState<string>("");
  const [validationErr, setValidationErr] = useState<string | null>(null);
  const [result, setResult] = useState<ComparisonResultOut | null>(null);

  useEffect(() => {
    if (sites.length >= 2) {
      const initialA = siteAId > 0 ? siteAId : sites[0].site_id;
      if (siteAId === 0) {
        setSiteAId(initialA);
      }
      if (siteBId === 0) {
        const fallbackB = sites.find((s) => s.site_id !== initialA)?.site_id ?? sites[1].site_id;
        setSiteBId(fallbackB);
      }
    }
  }, [sites, siteAId, siteBId]);

  const compareMutation = useMutation({
    mutationFn: (payload: Parameters<typeof postCompareSites>[0]) =>
      postCompareSites(payload),
    onSuccess: (data) => {
      setResult(data);
      setValidationErr(null);
    },
  });

  function handleSwap() {
    setSiteAId(siteBId);
    setSiteBId(siteAId);
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setValidationErr(null);

    if (!siteAId || !siteBId) {
      setValidationErr("Select two landing sites to compare.");
      return;
    }
    if (siteAId === siteBId) {
      setValidationErr("Site A and Site B must be two different landing sites.");
      return;
    }
    if (missionPurpose.trim().length < 5) {
      setValidationErr("Enter a specific scientific or mission purpose (at least 5 characters).");
      return;
    }

    compareMutation.mutate({
      site_a_id: siteAId,
      site_b_id: siteBId,
      mission_purpose: missionPurpose.trim(),
      profile_key: profileKey || null,
    });
  }

  const summaryCopyText = result
    ? [
        `Comparison: ${result.site_a_name} vs ${result.site_b_name}`,
        `Mission Purpose: ${result.mission_purpose}`,
        `Data Coverage: ${result.data_coverage}`,
        `Overall Winner: ${result.overall_winner === "undetermined" ? "Undetermined" : result.winner_site_name ?? result.overall_winner}`,
        `Conclusion: ${result.scientific_conclusion}`,
      ].join("\n")
    : "";

  return (
    <div className="page-shell">
      <HeadTags
        meta={{
          title: "Compare Landing Sites — CLPS Luna Browser",
          description:
            "Mission-purpose-driven deterministic side-by-side comparison of two candidate lunar landing sites with parameter provenance and quality badges.",
          canonicalPath: "/compare",
          robots: "noindex,nofollow",
          ogType: "website",
          breadcrumbs: [
            { name: "Home", path: "/" },
            { name: "Compare", path: "/compare" },
          ],
        }}
      />

      <div className="ambient-bg-layer" aria-hidden="true">
        <LunarMoonCanvas mode="ambient" sites={sites} />
      </div>

      <SiteHeader subtitle="Deterministic Comparison Engine" />

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
            <h1 style={{ margin: 0, fontSize: "1.65rem" }}>Compare Landing Sites</h1>
            <p style={{ margin: "0.2rem 0 0", color: "var(--text-secondary)", fontSize: "0.92rem" }}>
              Select two sites and state your mission purpose. No arbitrary universal score is
              computed without mission intent.
            </p>
          </div>
          <div className="no-print" style={{ display: "flex", gap: "0.55rem" }}>
            <Link to="/browser" className="btn">
              &lt;- Browser
            </Link>
            <Link to="/ai-assist" className="btn btn-cyan">
              AI Assist -&gt;
            </Link>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="glass-panel no-print" style={{ padding: "1.15rem", marginBottom: "1.25rem" }}>
          <div className="compare-row-sites" style={{ marginBottom: "0.9rem" }}>
            <div>
              <label htmlFor="compare-site-a" className="field-label">
                Site A
              </label>
              <select
                id="compare-site-a"
                className="select"
                value={siteAId}
                onChange={(event) => setSiteAId(Number(event.target.value))}
              >
                {sites.map((s) => (
                  <option key={s.site_id} value={s.site_id}>
                    {s.site_name} ({s.site_code})
                  </option>
                ))}
              </select>
            </div>

            <button
              type="button"
              className="btn"
              onClick={handleSwap}
              aria-label="Swap Site A and Site B"
              title="Swap sites"
            >
              &lt;-&gt;
            </button>

            <div>
              <label htmlFor="compare-site-b" className="field-label">
                Site B
              </label>
              <select
                id="compare-site-b"
                className="select"
                value={siteBId}
                onChange={(event) => setSiteBId(Number(event.target.value))}
              >
                {sites.map((s) => (
                  <option key={s.site_id} value={s.site_id}>
                    {s.site_name} ({s.site_code})
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="compare-row-purpose">
            <div>
              <label htmlFor="compare-purpose" className="field-label">
                Mission Purpose (Required)
              </label>
              <input
                id="compare-purpose"
                type="text"
                className="input"
                value={missionPurpose}
                onChange={(event) => setMissionPurpose(event.target.value)}
                required
                minLength={5}
              />
            </div>

            <div>
              <label htmlFor="compare-profile" className="field-label">
                Scoring Profile (Optional)
              </label>
              <select
                id="compare-profile"
                className="select"
                value={profileKey}
                onChange={(event) => setProfileKey(event.target.value)}
              >
                <option value="">Equal Weights / Purpose Default</option>
                {profiles.map((p) => (
                  <option key={p.profile_key} value={p.profile_key}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              disabled={compareMutation.isPending || sites.length < 2}
            >
              {compareMutation.isPending ? "Comparing..." : "Compare ->"}
            </button>
          </div>

          {validationErr && (
            <div className="notice-banner error" role="alert" style={{ marginTop: "0.8rem" }}>
              <span>{validationErr}</span>
            </div>
          )}

          {compareMutation.isError && (
            <div className="notice-banner error" role="alert" style={{ marginTop: "0.8rem" }}>
              <span>{compareMutation.error.message}</span>
            </div>
          )}
        </form>

        {result && (
          <section aria-label="Comparison evaluation results" style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div className="glass-panel-strong" style={{ padding: "1.15rem" }}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "flex-start",
                  flexWrap: "wrap",
                  gap: "0.8rem",
                }}
              >
                <div>
                  <span className="eyebrow">Evaluation Summary · {result.algorithm_version}</span>
                  <h2 style={{ margin: "0.2rem 0 0", fontSize: "1.25rem" }}>
                    {result.site_a_name} vs {result.site_b_name}
                  </h2>
                  <p style={{ margin: "0.35rem 0 0", color: "var(--text-secondary)", fontSize: "0.9rem" }}>
                    <strong>Basis:</strong> {result.mission_purpose}
                  </p>
                </div>

                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", alignItems: "center" }}>
                  <span className="pill-badge cyan">Coverage: {result.data_coverage}</span>
                  {result.overall_winner === "undetermined" ? (
                    <span className="pill-badge amber">
                      Undetermined — Insufficient Data or Tie
                    </span>
                  ) : (
                    <span className="pill-badge ok">
                      Favoured: {result.winner_site_name ?? result.overall_winner}
                    </span>
                  )}
                  <CopyButton text={summaryCopyText} label="Copy Summary" />
                  <button
                    type="button"
                    className="btn no-print"
                    onClick={() => window.print()}
                  >
                    Print
                  </button>
                </div>
              </div>

              {(result.overall_score_a !== null && result.overall_score_a !== undefined) ||
              (result.overall_score_b !== null && result.overall_score_b !== undefined) ? (
                <div
                  className="mono"
                  style={{
                    display: "flex",
                    gap: "1.5rem",
                    flexWrap: "wrap",
                    marginTop: "0.75rem",
                    fontSize: "0.86rem",
                    color: "var(--text-secondary)",
                  }}
                >
                  <span>
                    {result.site_a_name} Weighted Score: {formatNumber(result.overall_score_a, 3)}
                  </span>
                  <span>
                    {result.site_b_name} Weighted Score: {formatNumber(result.overall_score_b, 3)}
                  </span>
                </div>
              ) : null}

              <p style={{ margin: "0.8rem 0 0", fontSize: "0.94rem" }}>
                {result.scientific_conclusion}
              </p>

              {result.limitations_and_caveats.length > 0 && (
                <div className="notice-banner warn" style={{ marginTop: "0.85rem" }}>
                  <div>
                    <strong style={{ display: "block", marginBottom: "0.25rem" }}>
                      Limitations &amp; Caveats
                    </strong>
                    <ul style={{ margin: 0, paddingLeft: "1.15rem", fontSize: "0.84rem" }}>
                      {result.limitations_and_caveats.map((cav) => (
                        <li key={cav}>{cav}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}

              <div className="no-print" style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap", marginTop: "0.9rem" }}>
                <Link
                  to={`/sites/${encodeURIComponent(result.site_a_slug)}`}
                  className="btn"
                >
                  View {result.site_a_name} -&gt;
                </Link>
                <Link
                  to={`/sites/${encodeURIComponent(result.site_b_slug)}`}
                  className="btn"
                >
                  View {result.site_b_name} -&gt;
                </Link>
              </div>
            </div>

            <div className="glass-panel data-table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Parameter</th>
                    <th>Direction</th>
                    <th>{result.site_a_name}</th>
                    <th>{result.site_b_name}</th>
                    <th>Diff</th>
                    <th>Normalised</th>
                    <th>Quality</th>
                    <th>Row Outcome</th>
                    <th>Provenance &amp; Note</th>
                  </tr>
                </thead>
                <tbody>
                  {result.parameters.map((row) => (
                    <tr key={row.parameter_key}>
                      <td>
                        <strong>{row.display_name}</strong>
                        <div className="mono" style={{ fontSize: "0.74rem", color: "var(--text-muted)" }}>
                          {row.parameter_key}
                          {row.required ? " · required" : ""}
                        </div>
                      </td>
                      <td className="mono" style={{ fontSize: "0.78rem" }}>
                        {row.comparison_direction}
                      </td>
                      <td className="mono">
                        {formatParamValue(row.value_a, row.text_value_a, row.unit)}
                      </td>
                      <td className="mono">
                        {formatParamValue(row.value_b, row.text_value_b, row.unit)}
                      </td>
                      <td className="mono" style={{ fontSize: "0.8rem" }}>
                        {row.absolute_difference !== null && row.absolute_difference !== undefined
                          ? formatNumber(row.absolute_difference, 2)
                          : "—"}
                        {row.relative_difference_percent !== null &&
                        row.relative_difference_percent !== undefined
                          ? ` (${formatNumber(row.relative_difference_percent, 1)}%)`
                          : ""}
                      </td>
                      <td className="mono" style={{ fontSize: "0.8rem" }}>
                        {formatNumber(row.normalised_a, 2)} / {formatNumber(row.normalised_b, 2)}
                      </td>
                      <td>
                        <span
                          className={`pill-badge ${
                            row.data_quality_status === "verified" ? "ok" : "amber"
                          }`}
                        >
                          {row.data_quality_status}
                        </span>
                      </td>
                      <td style={{ fontWeight: 600 }}>
                        {formatParameterWinner(row, result.site_a_name, result.site_b_name)}
                      </td>
                      <td style={{ maxWidth: "300px", fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                        <div>{row.explanation}</div>
                        {row.compatibility_note && (
                          <div style={{ color: "var(--accent-amber)", marginTop: "0.2rem" }}>
                            {row.compatibility_note}
                          </div>
                        )}
                        {row.source_reference && (
                          <div style={{ color: "var(--text-muted)", marginTop: "0.2rem" }}>
                            Source: {row.source_reference}
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </main>

      <UtilitiesFooter />
    </div>
  );
}
