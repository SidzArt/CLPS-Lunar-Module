import type { components } from "./generated/schema";
import { apiFetch, type ApiFetchOptions } from "./client";

export type Schema = components["schemas"];

export type SiteCardOut = Schema["SiteCardOut"];
export type PaginatedSitesOut = Schema["PaginatedResponse_SiteCardOut_"];
export type SiteDetailOut = Schema["SiteDetailOut"];
export type SiteSectionOut = Schema["SiteSectionOut"];
export type SiteProConOut = Schema["SiteProConOut"];
export type SiteMetricOut = Schema["SiteMetricOut"];
export type SiteMediaOut = Schema["SiteMediaOut"];
export type SiteHistoryOut = Schema["SiteHistoryOut"];
export type SearchResultOut = Schema["SearchResultOut"];

export type ComparisonProfileOut = Schema["ComparisonProfileOut"];
export type ComparisonRequestIn = Schema["ComparisonRequestIn"];
export type ComparisonResultOut = Schema["ComparisonResultOut"];
export type ParameterComparisonOut = Schema["ParameterComparisonOut"];

export type AIAssistRequestIn = Schema["AIAssistRequestIn"];
export type AIAssistResponseOut = Schema["AIAssistResponseOut"];
export type SiteRecommendationOut = Schema["SiteRecommendationOut"];

export type SimulationCreateIn = Schema["SimulationCreateIn"];
export type SimulationCreateOut = Schema["SimulationCreateOut"];
export type SimulationStatusOut = Schema["SimulationStatusOut"];
export type SimulationSeriesOut = Schema["SimulationSeriesOut"];
export type SimulationSampleOut = Schema["SimulationSampleOut"];
export type SimulationEventsOut = Schema["SimulationEventsOut"];
export type SimulationEventOut = Schema["SimulationEventOut"];
export type SimulationCancelOut = Schema["SimulationCancelOut"];
export type HorizonCurveOut = Schema["HorizonCurveOut"];
export type SiteSimulationSummaryOut = Schema["SiteSimulationSummaryOut"];

export interface OrbitalTrajectorySampleOut {
  timestamp_utc: string;
  ephemeris_time: number;
  elapsed_seconds: number;
  earth_wrt_sun_eclipj2000_km: [number, number, number];
  moon_wrt_earth_eclipj2000_km: [number, number, number];
  moon_wrt_sun_eclipj2000_km: [number, number, number];
  moon_me_to_eclipj2000: [
    [number, number, number],
    [number, number, number],
    [number, number, number],
  ];
}

export interface OrbitalTrajectoryOut {
  simulation_id: string;
  site: SiteSimulationSummaryOut;
  coordinate_frame: string;
  lunar_body_frame: string;
  distance_units: string;
  aberration_policy: string;
  ephemeris_source: string;
  ephemeris_version: string;
  start_time_utc: string;
  end_time_utc: string;
  duration_seconds: number;
  sample_count: number;
  coverage_start_utc: string;
  coverage_end_utc: string;
  samples: OrbitalTrajectorySampleOut[];
}

export type PublicCodexStatusOut = Schema["PublicCodexStatusOut"];
export type PublicControllerStatusOut = Schema["PublicControllerStatusOut"];
export type CodexRunPrepareIn = Schema["CodexRunPrepareIn"];
export type CodexRunPrepareOut = Schema["CodexRunPrepareOut"];

export type AdminLoginIn = Schema["AdminLoginIn"];
export type AdminAuthOut = Schema["AdminAuthOut"];
export type AdminProfileOut = Schema["AdminProfileOut"];

export type ContactSubmitIn = Schema["ContactSubmitIn"];
export type ContactSubmitOut = Schema["ContactSubmitOut"];
export type HealthStatus = Schema["HealthStatus"];

export interface ListSitesParams {
  page?: number;
  page_size?: number;
  region_id?: number;
  status?: "published" | "draft" | "archived";
  search?: string;
  sort?: "name" | "elevation_asc" | "elevation_desc" | "updated_at";
}

export function fetchSites(
  params: ListSitesParams = {},
  options?: ApiFetchOptions,
): Promise<PaginatedSitesOut> {
  const qs = new URLSearchParams();
  qs.set("page", String(params.page ?? 1));
  qs.set("page_size", String(params.page_size ?? 50));
  qs.set("status", params.status ?? "published");
  if (params.region_id !== undefined) {
    qs.set("region_id", String(params.region_id));
  }
  if (params.search && params.search.trim().length > 0) {
    qs.set("search", params.search.trim());
  }
  if (params.sort) {
    qs.set("sort", params.sort);
  }
  return apiFetch<PaginatedSitesOut>(`/api/v1/sites?${qs.toString()}`, options);
}

export function fetchSiteBySlug(
  siteSlug: string,
  options?: ApiFetchOptions,
): Promise<SiteDetailOut> {
  return apiFetch<SiteDetailOut>(
    `/api/v1/sites/${encodeURIComponent(siteSlug)}`,
    options,
  );
}

export function fetchSiteSections(
  siteSlug: string,
  options?: ApiFetchOptions,
): Promise<SiteSectionOut[]> {
  return apiFetch<SiteSectionOut[]>(
    `/api/v1/sites/${encodeURIComponent(siteSlug)}/sections`,
    options,
  );
}

export function fetchSiteProsCons(
  siteSlug: string,
  options?: ApiFetchOptions,
): Promise<SiteProConOut[]> {
  return apiFetch<SiteProConOut[]>(
    `/api/v1/sites/${encodeURIComponent(siteSlug)}/pros-cons`,
    options,
  );
}

export function fetchSiteMetrics(
  siteSlug: string,
  options?: ApiFetchOptions,
): Promise<SiteMetricOut[]> {
  return apiFetch<SiteMetricOut[]>(
    `/api/v1/sites/${encodeURIComponent(siteSlug)}/metrics`,
    options,
  );
}

export function fetchSiteMedia(
  siteSlug: string,
  options?: ApiFetchOptions,
): Promise<SiteMediaOut[]> {
  return apiFetch<SiteMediaOut[]>(
    `/api/v1/sites/${encodeURIComponent(siteSlug)}/media`,
    options,
  );
}

export function fetchSiteHistory(
  siteSlug: string,
  options?: ApiFetchOptions,
): Promise<SiteHistoryOut[]> {
  return apiFetch<SiteHistoryOut[]>(
    `/api/v1/sites/${encodeURIComponent(siteSlug)}/history`,
    options,
  );
}

export function searchLandingSites(
  q: string,
  limit = 12,
  options?: ApiFetchOptions,
): Promise<SearchResultOut[]> {
  const qs = new URLSearchParams({ q: q.trim(), limit: String(limit) });
  return apiFetch<SearchResultOut[]>(`/api/v1/search?${qs.toString()}`, options);
}

export function fetchCompareProfiles(
  options?: ApiFetchOptions,
): Promise<ComparisonProfileOut[]> {
  return apiFetch<ComparisonProfileOut[]>("/api/v1/compare/profiles", options);
}

export function postCompareSites(
  payload: ComparisonRequestIn,
  options?: ApiFetchOptions,
): Promise<ComparisonResultOut> {
  return apiFetch<ComparisonResultOut>("/api/v1/compare", {
    ...options,
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function postAiAssistRecommend(
  payload: AIAssistRequestIn,
  options?: ApiFetchOptions,
): Promise<AIAssistResponseOut> {
  return apiFetch<AIAssistResponseOut>("/api/v1/ai-assist/recommend", {
    ...options,
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function createSimulation(
  payload: SimulationCreateIn,
  options?: ApiFetchOptions,
): Promise<SimulationCreateOut> {
  return apiFetch<SimulationCreateOut>("/api/v1/simulations", {
    ...options,
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchSimulationStatus(
  simulationId: string,
  options?: ApiFetchOptions,
): Promise<SimulationStatusOut> {
  return apiFetch<SimulationStatusOut>(
    `/api/v1/simulations/${encodeURIComponent(simulationId)}`,
    options,
  );
}

export function fetchSimulationSeries(
  simulationId: string,
  params: { offset?: number; limit?: number; downsample?: number; include_horizon?: boolean } = {},
  options?: ApiFetchOptions,
): Promise<SimulationSeriesOut> {
  const qs = new URLSearchParams();
  qs.set("offset", String(params.offset ?? 0));
  qs.set("limit", String(params.limit ?? 1000));
  qs.set("downsample", String(params.downsample ?? 1));
  qs.set("include_horizon", String(params.include_horizon ?? true));
  return apiFetch<SimulationSeriesOut>(
    `/api/v1/simulations/${encodeURIComponent(simulationId)}/series?${qs.toString()}`,
    options,
  );
}

/**
 * Fetch the complete simulation time-series without silent truncation across long spans.
 * Preserves first sample, last sample, and event-refined transition points via pagination,
 * falling back to bounded stride downsampling + endpoint anchoring only for huge runs.
 */
export async function fetchCompleteSimulationSeries(
  simulationId: string,
  options?: ApiFetchOptions,
): Promise<SimulationSeriesOut> {
  const pageLimit = 2000;
  const fullPaginationCap = 24000;
  const firstPage = await fetchSimulationSeries(
    simulationId,
    { offset: 0, limit: pageLimit, downsample: 1, include_horizon: true },
    options,
  );

  const firstSamples = firstPage.samples ?? [];
  const totalAvailable = firstPage.total_samples_available ?? firstSamples.length;
  if (firstSamples.length === 0 || firstSamples.length >= totalAvailable) {
    return firstPage;
  }

  const byIndex = new Map<number, SimulationSampleOut>();
  for (const s of firstSamples) {
    byIndex.set(s.sample_index, s);
  }

  let effectiveDownsample = 1;

  if (totalAvailable <= fullPaginationCap) {
    let offset = firstSamples.length;
    while (offset < totalAvailable) {
      const page = await fetchSimulationSeries(
        simulationId,
        { offset, limit: pageLimit, downsample: 1, include_horizon: false },
        options,
      );
      const batch = page.samples ?? [];
      if (batch.length === 0) {
        break;
      }
      for (const s of batch) {
        byIndex.set(s.sample_index, s);
      }
      offset += batch.length;
    }
  } else {
    effectiveDownsample = Math.min(100, Math.max(2, Math.ceil(totalAvailable / 4000)));
    let dsOffset = 0;
    while (true) {
      const page = await fetchSimulationSeries(
        simulationId,
        { offset: dsOffset, limit: pageLimit, downsample: effectiveDownsample, include_horizon: false },
        options,
      );
      const batch = page.samples ?? [];
      if (batch.length === 0) {
        break;
      }
      for (const s of batch) {
        byIndex.set(s.sample_index, s);
      }
      if (batch.length < pageLimit) {
        break;
      }
      dsOffset += batch.length;
    }
    const lastPage = await fetchSimulationSeries(
      simulationId,
      {
        offset: Math.max(0, totalAvailable - 1),
        limit: 1,
        downsample: 1,
        include_horizon: false,
      },
      options,
    );
    for (const s of lastPage.samples ?? []) {
      byIndex.set(s.sample_index, s);
    }
  }

  const merged = Array.from(byIndex.values()).sort((a, b) => a.sample_index - b.sample_index);
  return {
    ...firstPage,
    returned_samples: merged.length,
    limit: merged.length,
    downsample_step: effectiveDownsample,
    samples: merged,
  };
}

export function fetchSimulationOrbitalTrajectory(
  simulationId: string,
  params: { samples?: number } = {},
  options?: ApiFetchOptions,
): Promise<OrbitalTrajectoryOut> {
  const qs = new URLSearchParams();
  if (params.samples !== undefined) {
    qs.set("samples", String(params.samples));
  }
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return apiFetch<OrbitalTrajectoryOut>(
    `/api/v1/simulations/${encodeURIComponent(simulationId)}/orbital-trajectory${suffix}`,
    options,
  );
}

export function fetchSimulationEvents(
  simulationId: string,
  options?: ApiFetchOptions,
): Promise<SimulationEventsOut> {
  return apiFetch<SimulationEventsOut>(
    `/api/v1/simulations/${encodeURIComponent(simulationId)}/events`,
    options,
  );
}

export function cancelSimulation(
  simulationId: string,
  options?: ApiFetchOptions,
): Promise<SimulationCancelOut> {
  return apiFetch<SimulationCancelOut>(
    `/api/v1/simulations/${encodeURIComponent(simulationId)}/cancel`,
    {
      ...options,
      method: "POST",
    },
  );
}

export function fetchCodexStatus(
  options?: ApiFetchOptions,
): Promise<PublicCodexStatusOut> {
  return apiFetch<PublicCodexStatusOut>("/api/v1/codex/status", options);
}

export function prepareCodexRun(
  payload: CodexRunPrepareIn,
  options?: ApiFetchOptions,
): Promise<CodexRunPrepareOut> {
  return apiFetch<CodexRunPrepareOut>("/api/v1/codex/runs/prepare", {
    ...options,
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function adminLogin(
  payload: AdminLoginIn,
  options?: ApiFetchOptions,
): Promise<AdminAuthOut> {
  return apiFetch<AdminAuthOut>("/api/v1/auth/login", {
    ...options,
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function adminLogout(options?: ApiFetchOptions): Promise<{ status: string }> {
  return apiFetch<{ status: string }>("/api/v1/auth/logout", {
    ...options,
    method: "POST",
  });
}

export function fetchAdminProfile(
  options?: ApiFetchOptions,
): Promise<AdminProfileOut> {
  return apiFetch<AdminProfileOut>("/api/v1/auth/me", options);
}

export function submitContactForm(
  payload: ContactSubmitIn,
  options?: ApiFetchOptions,
): Promise<ContactSubmitOut> {
  return apiFetch<ContactSubmitOut>("/api/v1/contact", {
    ...options,
    method: "POST",
    body: JSON.stringify(payload),
  });
}
