import { apiFetch, type ApiFetchOptions } from "./client";
import type {
  AdminAuthOut,
  CodexRunPrepareOut,
  PaginatedSitesOut,
  Schema,
  SiteDetailOut,
  SiteHistoryOut,
  SiteMediaOut,
  SiteMetricOut,
  SiteProConOut,
  SiteSectionOut,
} from "./endpoints";

export type AdminOverviewOut = Schema["AdminOverviewOut"];
export type RoleOut = Schema["RoleOut"];
export type AdminUserOut = Schema["AdminUserOut"];
export type AdminUserCreateIn = Schema["AdminUserCreateIn"];
export type AdminUserUpdateIn = Schema["AdminUserUpdateIn"];
export type AdminResetPasswordIn = Schema["AdminResetPasswordIn"];
export type AdminSessionRevokeOut = Schema["AdminSessionRevokeOut"];
export type AdminChangePasswordIn = Schema["AdminChangePasswordIn"];
export type CsrfTokenOut = Schema["CsrfTokenOut"];

export type AuditLogEntryOut = Schema["AuditLogEntryOut"];
export type AuditLogPageOut = Schema["AuditLogPageOut"];
export type SystemComponentHealthOut = Schema["SystemComponentHealthOut"];
export type SystemHealthSummaryOut = Schema["SystemHealthSummaryOut"];

export type DataSourceOut = Schema["DataSourceOut"];
export type DataSourceCreateIn = Schema["DataSourceCreateIn"];
export type DataSourceUpdateIn = Schema["DataSourceUpdateIn"];
export type ParameterDefinitionAdminOut = Schema["ParameterDefinitionAdminOut"];
export type LunarRegionOut = Schema["LunarRegionOut"];

export type SiteCreateIn = Schema["SiteCreateIn"];
export type SiteUpdateIn = Schema["SiteUpdateIn"];
export type SectionCreateIn = Schema["SectionCreateIn"];
export type SectionUpdateIn = Schema["SectionUpdateIn"];
export type ProConCreateIn = Schema["ProConCreateIn"];
export type ProConUpdateIn = Schema["ProConUpdateIn"];
export type SiteHistoryCreateIn = Schema["SiteHistoryCreateIn"];
export type SiteHistoryUpdateIn = Schema["SiteHistoryUpdateIn"];
export type SiteMetricUpsertItem = Schema["SiteMetricUpsertItem"];
export type SiteMetricsBulkUpsertIn = Schema["SiteMetricsBulkUpsertIn"];

export type MediaUpdateIn = Schema["MediaUpdateIn"];
export type OrphanMediaFileOut = Schema["OrphanMediaFileOut"];
export type AdminMediaListOut = Schema["AdminMediaListOut"];

export type ImportSummaryOut = Schema["ImportSummaryOut"];
export type ImportListOut = Schema["ImportListOut"];
export type ImportPreviewOut = Schema["ImportPreviewOut"];
export type ImportCommitOut = Schema["ImportCommitOut"];
export type ImportRollbackOut = Schema["ImportRollbackOut"];

export type AdminDevicesListOut = Schema["AdminDevicesListOut"];
export type AdminHardwareDeviceOut = Schema["AdminHardwareDeviceOut"];
export type DeviceHeartbeatIn = Schema["DeviceHeartbeatIn"];
export type CalibrationCreateIn = Schema["CalibrationCreateIn"];
export type CalibrationUpdateIn = Schema["CalibrationUpdateIn"];
export type CalibrationProfileOut = Schema["CalibrationProfileOut"];
export type MoonLedRegionOut = Schema["MoonLedRegionOut"];
export type MoonLedRegionUpsertIn = Schema["MoonLedRegionUpsertIn"];
export type HardwareConfigurationOut = Schema["HardwareConfigurationOut"];
export type HardwareRunAdminSummaryOut = Schema["HardwareRunAdminSummaryOut"];

export type CodeVersionOut = Schema["CodeVersionOut"];
export type CodeVersionDetailOut = Schema["CodeVersionDetailOut"];
export type CodeVersionCreateIn = Schema["CodeVersionCreateIn"];
export type CodeVersionDiffOut = Schema["CodeVersionDiffOut"];
export type CodeVersionSyntaxValidationOut = Schema["CodeVersionSyntaxValidationOut"];
export type CodeVersionRenderIn = Schema["CodeVersionRenderIn"];
export type PlaceholderSpecIn = Schema["PlaceholderSpecIn"];
export type HardwareVariableRefOut = Schema["HardwareVariableRefOut"];

export interface CodeVersionRenderOut {
  code_version_id: string;
  controller_key: string;
  version_label: string;
  source_checksum_sha256: string;
  rendered_checksum_sha256: string;
  substituted_keys: string[];
  warnings: string[];
  rendered_source: string;
}

export const adminQueryKeys = {
  me: ["admin", "me"] as const,
  overview: ["admin", "overview"] as const,
  regions: ["admin", "regions"] as const,
  sites: (params: Record<string, unknown>) => ["admin", "sites", params] as const,
  siteDetail: (siteId: number) => ["admin", "siteDetail", siteId] as const,
  siteSections: (siteId: number) => ["admin", "siteSections", siteId] as const,
  siteProsCons: (siteId: number) => ["admin", "siteProsCons", siteId] as const,
  siteHistory: (siteId: number) => ["admin", "siteHistory", siteId] as const,
  siteMetrics: (siteId: number) => ["admin", "siteMetrics", siteId] as const,
  siteMedia: (siteId: number) => ["admin", "siteMedia", siteId] as const,
  mediaList: (siteId?: number | null) => ["admin", "media", siteId ?? "all"] as const,
  imports: (statusFilter?: string) => ["admin", "imports", statusFilter ?? "all"] as const,
  sources: ["admin", "sources"] as const,
  parameters: ["admin", "parameters"] as const,
  roles: ["admin", "roles"] as const,
  users: ["admin", "users"] as const,
  auditLogs: (params: Record<string, unknown>) => ["admin", "auditLogs", params] as const,
  systemHealth: ["admin", "systemHealth"] as const,
  codexDevices: ["admin", "codexDevices"] as const,
  calibrations: (motorKey?: string) => ["admin", "calibrations", motorKey ?? "all"] as const,
  ledMapping: ["admin", "ledMapping"] as const,
  configs: (controllerKey?: string) => ["admin", "configs", controllerKey ?? "all"] as const,
  runs: (statusFilter?: string) => ["admin", "runs", statusFilter ?? "all"] as const,
  codeVersions: (controllerKey?: string) =>
    ["admin", "codeVersions", controllerKey ?? "all"] as const,
  codeVersionDetail: (versionId: string) => ["admin", "codeVersion", versionId] as const,
  hardwareVariables: ["admin", "hardwareVariables"] as const,
  prepareRunPreview: (id: string) => ["admin", "prepareRun", id] as const,
};

export function fetchCsrfToken(options?: ApiFetchOptions): Promise<CsrfTokenOut> {
  return apiFetch<CsrfTokenOut>("/api/v1/auth/csrf", options);
}

export function adminChangePassword(
  payload: AdminChangePasswordIn,
  options?: ApiFetchOptions,
): Promise<AdminAuthOut> {
  return apiFetch<AdminAuthOut>("/api/v1/auth/change-password", {
    ...options,
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchAdminOverview(options?: ApiFetchOptions): Promise<AdminOverviewOut> {
  return apiFetch<AdminOverviewOut>("/api/v1/admin/overview", options);
}

export function fetchAdminRegions(options?: ApiFetchOptions): Promise<LunarRegionOut[]> {
  return apiFetch<LunarRegionOut[]>("/api/v1/admin/regions", options);
}

export function fetchAdminSites(
  params: {
    page?: number;
    page_size?: number;
    region_id?: number;
    catalogue_status?: string;
    search?: string;
    sort_by?: string;
  } = {},
  options?: ApiFetchOptions,
): Promise<PaginatedSitesOut> {
  const qs = new URLSearchParams();
  if (params.page) qs.set("page", String(params.page));
  if (params.page_size) qs.set("page_size", String(params.page_size));
  if (params.region_id !== undefined) qs.set("region_id", String(params.region_id));
  if (params.catalogue_status) qs.set("catalogue_status", params.catalogue_status);
  if (params.search && params.search.trim()) qs.set("search", params.search.trim());
  if (params.sort_by) qs.set("sort_by", params.sort_by);
  const query = qs.toString();
  return apiFetch<PaginatedSitesOut>(`/api/v1/admin/sites${query ? `?${query}` : ""}`, options);
}

export function fetchAdminSiteDetail(
  siteId: number,
  options?: ApiFetchOptions,
): Promise<SiteDetailOut> {
  return apiFetch<SiteDetailOut>(`/api/v1/admin/sites/${siteId}`, options);
}

export function createAdminSite(
  payload: SiteCreateIn,
  options?: ApiFetchOptions,
): Promise<SiteDetailOut> {
  return apiFetch<SiteDetailOut>("/api/v1/admin/sites", {
    ...options,
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateAdminSite(
  siteId: number,
  payload: SiteUpdateIn,
  options?: ApiFetchOptions,
): Promise<SiteDetailOut> {
  return apiFetch<SiteDetailOut>(`/api/v1/admin/sites/${siteId}`, {
    ...options,
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function archiveAdminSite(
  siteId: number,
  options?: ApiFetchOptions,
): Promise<SiteDetailOut> {
  return apiFetch<SiteDetailOut>(`/api/v1/admin/sites/${siteId}/archive`, {
    ...options,
    method: "POST",
  });
}

export function deleteAdminSite(
  siteId: number,
  options?: ApiFetchOptions,
): Promise<{ status: string; site_id: number }> {
  return apiFetch<{ status: string; site_id: number }>(`/api/v1/admin/sites/${siteId}`, {
    ...options,
    method: "DELETE",
  });
}

export function fetchAdminSiteSections(siteId: number): Promise<SiteSectionOut[]> {
  return apiFetch<SiteSectionOut[]>(`/api/v1/admin/sites/${siteId}/sections`);
}

export function createAdminSection(
  siteId: number,
  payload: SectionCreateIn,
): Promise<SiteSectionOut> {
  return apiFetch<SiteSectionOut>(`/api/v1/admin/sites/${siteId}/sections`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateAdminSection(
  siteId: number,
  contentId: number,
  payload: SectionUpdateIn,
): Promise<SiteSectionOut> {
  return apiFetch<SiteSectionOut>(`/api/v1/admin/sites/${siteId}/sections/${contentId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteAdminSection(
  siteId: number,
  contentId: number,
): Promise<{ status: string; content_id: number }> {
  return apiFetch<{ status: string; content_id: number }>(
    `/api/v1/admin/sites/${siteId}/sections/${contentId}`,
    { method: "DELETE" },
  );
}

export function fetchAdminSiteProsCons(siteId: number): Promise<SiteProConOut[]> {
  return apiFetch<SiteProConOut[]>(`/api/v1/admin/sites/${siteId}/pros-cons`);
}

export function createAdminProCon(
  siteId: number,
  payload: ProConCreateIn,
): Promise<SiteProConOut> {
  return apiFetch<SiteProConOut>(`/api/v1/admin/sites/${siteId}/pros-cons`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateAdminProCon(
  siteId: number,
  pointId: number,
  payload: ProConUpdateIn,
): Promise<SiteProConOut> {
  return apiFetch<SiteProConOut>(`/api/v1/admin/sites/${siteId}/pros-cons/${pointId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteAdminProCon(
  siteId: number,
  pointId: number,
): Promise<{ status: string; point_id: number }> {
  return apiFetch<{ status: string; point_id: number }>(
    `/api/v1/admin/sites/${siteId}/pros-cons/${pointId}`,
    { method: "DELETE" },
  );
}

export function fetchAdminSiteHistory(siteId: number): Promise<SiteHistoryOut[]> {
  return apiFetch<SiteHistoryOut[]>(`/api/v1/admin/sites/${siteId}/history`);
}

export function createAdminHistory(
  siteId: number,
  payload: SiteHistoryCreateIn,
): Promise<SiteHistoryOut> {
  return apiFetch<SiteHistoryOut>(`/api/v1/admin/sites/${siteId}/history`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateAdminHistory(
  siteId: number,
  historyId: number,
  payload: SiteHistoryUpdateIn,
): Promise<SiteHistoryOut> {
  return apiFetch<SiteHistoryOut>(`/api/v1/admin/sites/${siteId}/history/${historyId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteAdminHistory(
  siteId: number,
  historyId: number,
): Promise<{ status: string; history_id: number }> {
  return apiFetch<{ status: string; history_id: number }>(
    `/api/v1/admin/sites/${siteId}/history/${historyId}`,
    { method: "DELETE" },
  );
}

export function fetchAdminSiteMetrics(siteId: number): Promise<SiteMetricOut[]> {
  return apiFetch<SiteMetricOut[]>(`/api/v1/admin/sites/${siteId}/metrics`);
}

export function upsertAdminSiteMetricsBulk(
  siteId: number,
  payload: SiteMetricsBulkUpsertIn,
): Promise<SiteMetricOut[]> {
  return apiFetch<SiteMetricOut[]>(`/api/v1/admin/sites/${siteId}/metrics`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function fetchAdminSiteMedia(siteId: number): Promise<SiteMediaOut[]> {
  return apiFetch<SiteMediaOut[]>(`/api/v1/admin/sites/${siteId}/media`);
}

export function fetchAdminMediaList(siteId?: number | null): Promise<AdminMediaListOut> {
  const qs = siteId ? `?site_id=${siteId}&page_size=100` : "?page_size=100";
  return apiFetch<AdminMediaListOut>(`/api/v1/admin/media${qs}`);
}

export function uploadAdminMedia(formData: FormData): Promise<SiteMediaOut> {
  return apiFetch<SiteMediaOut>("/api/v1/admin/media/upload", {
    method: "POST",
    body: formData,
  });
}

export function updateAdminMediaMetadata(
  mediaId: number,
  payload: MediaUpdateIn,
): Promise<SiteMediaOut> {
  return apiFetch<SiteMediaOut>(`/api/v1/admin/media/${mediaId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function setAdminMediaPrimary(mediaId: number): Promise<SiteMediaOut> {
  return apiFetch<SiteMediaOut>(`/api/v1/admin/media/${mediaId}/primary`, {
    method: "PATCH",
  });
}

export function deleteAdminMedia(
  mediaId: number,
): Promise<{ status: string; message: string }> {
  return apiFetch<{ status: string; message: string }>(`/api/v1/admin/media/${mediaId}`, {
    method: "DELETE",
  });
}

export function fetchAdminImports(statusFilter?: string): Promise<ImportListOut> {
  const qs = statusFilter ? `?status=${encodeURIComponent(statusFilter)}` : "";
  return apiFetch<ImportListOut>(`/api/v1/admin/imports${qs}`);
}

export function stageAdminImport(formData: FormData): Promise<ImportPreviewOut> {
  return apiFetch<ImportPreviewOut>("/api/v1/admin/imports", {
    method: "POST",
    body: formData,
  });
}

export function fetchAdminImportPreview(importId: number): Promise<ImportPreviewOut> {
  return apiFetch<ImportPreviewOut>(`/api/v1/admin/imports/${importId}/preview`);
}

export function commitAdminImport(importId: number): Promise<ImportCommitOut> {
  return apiFetch<ImportCommitOut>(`/api/v1/admin/imports/${importId}/commit`, {
    method: "POST",
  });
}

export function rollbackAdminImport(importId: number): Promise<ImportRollbackOut> {
  return apiFetch<ImportRollbackOut>(`/api/v1/admin/imports/${importId}/rollback`, {
    method: "POST",
  });
}

export function fetchAdminDataSources(): Promise<DataSourceOut[]> {
  return apiFetch<DataSourceOut[]>("/api/v1/admin/sources");
}

export function createAdminDataSource(payload: DataSourceCreateIn): Promise<DataSourceOut> {
  return apiFetch<DataSourceOut>("/api/v1/admin/sources", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateAdminDataSource(
  sourceId: number,
  payload: DataSourceUpdateIn,
): Promise<DataSourceOut> {
  return apiFetch<DataSourceOut>(`/api/v1/admin/sources/${sourceId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function fetchAdminParameters(): Promise<ParameterDefinitionAdminOut[]> {
  return apiFetch<ParameterDefinitionAdminOut[]>("/api/v1/admin/parameters");
}

export function fetchAdminRoles(): Promise<RoleOut[]> {
  return apiFetch<RoleOut[]>("/api/v1/admin/roles");
}

export function fetchAdminUsers(): Promise<AdminUserOut[]> {
  return apiFetch<AdminUserOut[]>("/api/v1/admin/users");
}

export function createAdminUser(payload: AdminUserCreateIn): Promise<AdminUserOut> {
  return apiFetch<AdminUserOut>("/api/v1/admin/users", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateAdminUser(
  adminId: string,
  payload: AdminUserUpdateIn,
): Promise<AdminUserOut> {
  return apiFetch<AdminUserOut>(`/api/v1/admin/users/${encodeURIComponent(adminId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function resetAdminUserPassword(
  adminId: string,
  payload: AdminResetPasswordIn,
): Promise<AdminUserOut> {
  return apiFetch<AdminUserOut>(
    `/api/v1/admin/users/${encodeURIComponent(adminId)}/reset-password`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function revokeAdminUserSessions(adminId: string): Promise<AdminSessionRevokeOut> {
  return apiFetch<AdminSessionRevokeOut>(
    `/api/v1/admin/users/${encodeURIComponent(adminId)}/revoke-sessions`,
    { method: "POST" },
  );
}

export function fetchAuditLogs(
  params: {
    action_key?: string;
    entity_type?: string;
    page?: number;
    page_size?: number;
  } = {},
): Promise<AuditLogPageOut> {
  const qs = new URLSearchParams();
  if (params.action_key && params.action_key.trim()) {
    qs.set("action_key", params.action_key.trim());
  }
  if (params.entity_type && params.entity_type.trim()) {
    qs.set("entity_type", params.entity_type.trim());
  }
  if (params.page) qs.set("page", String(params.page));
  if (params.page_size) qs.set("page_size", String(params.page_size));
  const query = qs.toString();
  return apiFetch<AuditLogPageOut>(`/api/v1/admin/audit-logs${query ? `?${query}` : ""}`);
}

export function fetchSystemHealth(): Promise<SystemHealthSummaryOut> {
  return apiFetch<SystemHealthSummaryOut>("/api/v1/admin/system/health");
}

export function fetchAdminCodexDevices(): Promise<AdminDevicesListOut> {
  return apiFetch<AdminDevicesListOut>("/api/v1/admin/codex/devices");
}

export function postDeviceHeartbeat(
  controllerKey: string,
  payload: DeviceHeartbeatIn,
): Promise<AdminDevicesListOut> {
  return apiFetch<AdminDevicesListOut>(
    `/api/v1/admin/codex/devices/${encodeURIComponent(controllerKey)}/heartbeat`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function upsertHardwareConfiguration(
  controllerKey: string,
  payload: {
    board_model: string;
    firmware_target: string;
    motor_type?: string | null;
    steps_per_revolution?: number | null;
    microstep_setting?: number | null;
    gear_ratio?: number | null;
    driver_model?: string | null;
    current_limit_setting?: number | null;
    led_count?: number | null;
    led_mapping_version?: string | null;
    config_json?: Record<string, unknown> | null;
  },
): Promise<{
  hardware_config_id: string;
  controller_key: string;
  board_model: string;
  firmware_target: string;
  is_active: boolean;
}> {
  return apiFetch(`/api/v1/admin/codex/configurations/${encodeURIComponent(controllerKey)}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function fetchAdminCalibrations(motorKey?: string): Promise<CalibrationProfileOut[]> {
  const qs = motorKey ? `?motor_key=${encodeURIComponent(motorKey)}` : "";
  return apiFetch<CalibrationProfileOut[]>(`/api/v1/admin/codex/calibrations${qs}`);
}

export function createCalibration(payload: CalibrationCreateIn): Promise<CalibrationProfileOut> {
  return apiFetch<CalibrationProfileOut>("/api/v1/admin/codex/calibrations", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateCalibration(payload: CalibrationUpdateIn): Promise<CalibrationProfileOut> {
  return apiFetch<CalibrationProfileOut>("/api/v1/admin/codex/calibrations", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function fetchAdminLedMapping(): Promise<MoonLedRegionOut[]> {
  return apiFetch<MoonLedRegionOut[]>("/api/v1/admin/codex/led-mapping");
}

export function upsertLedRegion(payload: MoonLedRegionUpsertIn): Promise<MoonLedRegionOut> {
  return apiFetch<MoonLedRegionOut>("/api/v1/admin/codex/led-mapping", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchAdminHardwareConfigurations(
  controllerKey?: string,
): Promise<HardwareConfigurationOut[]> {
  const qs = controllerKey ? `?controller_key=${encodeURIComponent(controllerKey)}` : "";
  return apiFetch<HardwareConfigurationOut[]>(`/api/v1/admin/codex/configurations${qs}`);
}

export function fetchAdminHardwareRuns(
  statusFilter?: string,
): Promise<HardwareRunAdminSummaryOut[]> {
  const qs = statusFilter ? `?status=${encodeURIComponent(statusFilter)}` : "";
  return apiFetch<HardwareRunAdminSummaryOut[]>(`/api/v1/admin/codex/runs${qs}`);
}

export function fetchCodeVersions(controllerKey?: string): Promise<CodeVersionOut[]> {
  const qs = controllerKey ? `?controller_key=${encodeURIComponent(controllerKey)}` : "";
  return apiFetch<CodeVersionOut[]>(`/api/v1/admin/hardware/code-versions${qs}`);
}

export function fetchCodeVersionDetail(versionId: string): Promise<CodeVersionDetailOut> {
  return apiFetch<CodeVersionDetailOut>(
    `/api/v1/admin/hardware/code-versions/${encodeURIComponent(versionId)}`,
  );
}

export function createCodeVersion(payload: CodeVersionCreateIn): Promise<CodeVersionDetailOut> {
  return apiFetch<CodeVersionDetailOut>("/api/v1/admin/hardware/code-versions", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function activateCodeVersion(versionId: string): Promise<CodeVersionDetailOut> {
  return apiFetch<CodeVersionDetailOut>(
    `/api/v1/admin/hardware/code-versions/${encodeURIComponent(versionId)}/activate`,
    { method: "POST" },
  );
}

export function diffCodeVersions(
  baseVersionId: string,
  targetVersionId: string,
): Promise<CodeVersionDiffOut> {
  return apiFetch<CodeVersionDiffOut>(
    `/api/v1/admin/hardware/code-versions/${encodeURIComponent(baseVersionId)}/diff/${encodeURIComponent(targetVersionId)}`,
  );
}

export function validateCodeVersionSyntax(
  versionId: string,
): Promise<CodeVersionSyntaxValidationOut> {
  return apiFetch<CodeVersionSyntaxValidationOut>(
    `/api/v1/admin/hardware/code-versions/${encodeURIComponent(versionId)}/validate-syntax`,
    { method: "POST" },
  );
}

export function renderCodeVersionPreview(
  versionId: string,
  payload: CodeVersionRenderIn,
): Promise<CodeVersionRenderOut> {
  return apiFetch<CodeVersionRenderOut>(
    `/api/v1/admin/hardware/code-versions/${encodeURIComponent(versionId)}/render-preview`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function fetchHardwareVariables(): Promise<HardwareVariableRefOut[]> {
  return apiFetch<HardwareVariableRefOut[]>("/api/v1/admin/hardware/variables");
}

export type PreparePreviewSummary = CodexRunPrepareOut;
