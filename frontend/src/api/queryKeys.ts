export const queryKeys = {
  sites: (params?: Record<string, unknown>) => ["sites", params ?? {}] as const,
  siteDetail: (slug: string) => ["site", slug] as const,
  siteSections: (slug: string) => ["site", slug, "sections"] as const,
  siteProsCons: (slug: string) => ["site", slug, "pros-cons"] as const,
  siteMetrics: (slug: string) => ["site", slug, "metrics"] as const,
  siteMedia: (slug: string) => ["site", slug, "media"] as const,
  siteHistory: (slug: string) => ["site", slug, "history"] as const,
  search: (q: string) => ["search", q] as const,
  compareProfiles: () => ["compare", "profiles"] as const,
  simulationStatus: (id: string) => ["simulation", id, "status"] as const,
  simulationSeries: (id: string) => ["simulation", id, "series"] as const,
  simulationOrbitalTrajectory: (id: string, samples = 1024) =>
    ["simulation", id, "orbital-trajectory", samples] as const,
  simulationEvents: (id: string) => ["simulation", id, "events"] as const,
  codexStatus: () => ["codex", "status"] as const,
  adminMe: () => ["admin", "me"] as const,
};

