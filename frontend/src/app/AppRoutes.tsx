import { Route, Routes } from "react-router-dom";
import { CookieConsent } from "../components/CookieConsent";
import { AiAssistPage } from "../pages/AiAssistPage";
import { AdminAuditHealthPage } from "../pages/admin/AdminAuditHealthPage";
import { AdminCodexPage } from "../pages/admin/AdminCodexPage";
import { AdminDashboardPage } from "../pages/admin/AdminDashboardPage";
import { AdminFirmwareEditorPage } from "../pages/admin/AdminFirmwareEditorPage";
import { AdminImportsPage } from "../pages/admin/AdminImportsPage";
import { AdminLoginPage } from "../pages/admin/AdminLoginPage";
import { AdminMediaPage } from "../pages/admin/AdminMediaPage";
import { AdminSiteEditorPage } from "../pages/admin/AdminSiteEditorPage";
import { AdminSitesPage } from "../pages/admin/AdminSitesPage";
import { AdminUsersPage } from "../pages/admin/AdminUsersPage";
import { BrowserPage } from "../pages/BrowserPage";
import { CodexPage } from "../pages/CodexPage";
import { ComparePage } from "../pages/ComparePage";
import { ContactPage } from "../pages/ContactPage";
import { IntroPage } from "../pages/IntroPage";
import { PrivacyPage, TermsPage } from "../pages/LegalPages";
import { NotFoundPage } from "../pages/NotFoundPage";
import { SimulationPage } from "../pages/SimulationPage";
import { SiteInfoPage } from "../pages/SiteInfoPage";

export const KNOWN_EXACT_PATHS = new Set<string>([
  "/",
  "/browser",
  "/compare",
  "/ai-assist",
  "/simulation",
  "/codex",
  "/admin",
  "/admin/login",
  "/admin/sites",
  "/admin/media",
  "/admin/imports",
  "/admin/users",
  "/admin/audit",
  "/admin/codex",
  "/admin/codex/devices",
  "/admin/codex/calibration",
  "/admin/codex/led-mapping",
  "/admin/codex/firmware",
  "/contact",
  "/privacy",
  "/terms",
]);

export function isKnownDynamicRoute(pathname: string): boolean {
  if (pathname.startsWith("/simulation/")) return true;
  if (/^\/admin\/sites\/\d+$/.test(pathname)) return true;
  if (/^\/admin\/codex\/firmware\/[^/]+$/.test(pathname)) return true;
  return false;
}

export function AppRoutes() {
  return (
    <>
      <a href="#main-content" className="skip-link">
        Skip to main content
      </a>
      <Routes>
        <Route path="/" element={<IntroPage />} />
        <Route path="/browser" element={<BrowserPage />} />
        <Route path="/compare" element={<ComparePage />} />
        <Route path="/ai-assist" element={<AiAssistPage />} />
        <Route path="/sites/:siteSlug" element={<SiteInfoPage />} />
        <Route path="/simulation" element={<SimulationPage />} />
        <Route path="/simulation/:simulationId" element={<SimulationPage />} />
        <Route path="/codex" element={<CodexPage />} />

        {/* Authenticated Admin Portal */}
        <Route path="/admin/login" element={<AdminLoginPage />} />
        <Route path="/admin" element={<AdminDashboardPage />} />
        <Route path="/admin/sites" element={<AdminSitesPage />} />
        <Route path="/admin/sites/:siteId" element={<AdminSiteEditorPage />} />
        <Route path="/admin/media" element={<AdminMediaPage />} />
        <Route path="/admin/imports" element={<AdminImportsPage />} />
        <Route path="/admin/users" element={<AdminUsersPage />} />
        <Route path="/admin/audit" element={<AdminAuditHealthPage />} />
        <Route path="/admin/codex" element={<AdminCodexPage />} />
        <Route path="/admin/codex/devices" element={<AdminCodexPage />} />
        <Route path="/admin/codex/calibration" element={<AdminCodexPage />} />
        <Route path="/admin/codex/led-mapping" element={<AdminCodexPage />} />
        <Route path="/admin/codex/firmware" element={<AdminFirmwareEditorPage />} />
        <Route path="/admin/codex/firmware/:versionId" element={<AdminFirmwareEditorPage />} />

        <Route path="/contact" element={<ContactPage />} />
        <Route path="/privacy" element={<PrivacyPage />} />
        <Route path="/terms" element={<TermsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
      <CookieConsent />
    </>
  );
}
