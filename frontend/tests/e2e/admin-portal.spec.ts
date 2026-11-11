import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

const SCREENSHOT_DIR =
  process.env.PHASE7_SCREENSHOT_DIR ||
  "/Users/siddharthwaikar/.gemini/antigravity/brain/652c902a-6cab-4688-b4b9-d5bc9cd0fa05/screenshots/phase7";

const E2E_USERNAME = process.env.E2E_ADMIN_USER || "e2e_p7_super";
const E2E_PASSWORD = process.env.E2E_ADMIN_PASS || "Phase7!Super#2026";

function ensureDir(dir: string) {
  fs.mkdirSync(dir, { recursive: true });
}

function trackBrowserErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (err) => {
    errors.push(`pageerror: ${err.message}`);
  });
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      const txt = msg.text();
      if (!txt.includes("401 (Unauthorized)")) {
        errors.push(`console.error: ${txt}`);
      }
    }
    if (msg.text().toLowerCase().includes("hydration")) {
      errors.push(`hydration-warning: ${msg.text()}`);
    }
  });
  return errors;
}

async function assertNoHorizontalOverflow(page: Page, contextLabel: string) {
  const overflow = await page.evaluate(() => {
    return document.documentElement.scrollWidth - window.innerWidth;
  });
  expect(
    overflow,
    `Horizontal overflow detected on ${contextLabel}: ${overflow}px`,
  ).toBeLessThanOrEqual(2);
}

test.describe("CLPS Luna Browser Phase 7 Admin Portal & Security E2E", () => {
  test.beforeAll(() => {
    ensureDir(SCREENSHOT_DIR);
  });

  test("enforces CSP nonces, security headers, cookie auth, and end-to-end admin workflows", async ({
    page,
  }) => {
    const errors = trackBrowserErrors(page);
    await page.setViewportSize({ width: 1440, height: 900 });

    // 1. Public Three.js CSP compliance & zero console errors
    const homeResp = await page.goto("/");
    expect(homeResp?.status()).toBe(200);
    const homeHeaders = homeResp?.headers() ?? {};
    expect(homeHeaders["content-security-policy"]).toMatch(/script-src 'self' 'nonce-[A-Za-z0-9+/=]+'/);
    expect(homeHeaders["x-content-type-options"]).toBe("nosniff");
    expect(homeHeaders["permissions-policy"]).toContain("camera=()");

    // 2. Unauthenticated /admin redirects to /admin/login with no-store Cache-Control
    const adminResp = await page.goto("/admin");
    expect(adminResp?.headers()["cache-control"]).toContain("no-store");
    await expect(page).toHaveURL(/\/admin\/login/);
    await expect(page.getByRole("heading", { name: /Administrator Sign-In/i })).toBeVisible();
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "desktop-1440-admin-login.png") });

    // 3. Sign in via cookie-only auth (zero localStorage/sessionStorage token persistence)
    await page.getByLabel(/Username/i).fill(E2E_USERNAME);
    await page.getByLabel(/Password/i).fill(E2E_PASSWORD);
    await page.getByRole("button", { name: /Sign In/i }).click();

    await expect(page).toHaveURL(/\/admin$/);
    await expect(page.getByRole("heading", { name: /Operations Overview/i })).toBeVisible();
    await expect(page.getByText(/Split-Pane Firmware Editor/i)).toBeVisible();

    const rowCount = await page.locator(".admin-dashboard-row").count();
    expect(rowCount).toBeLessThanOrEqual(2);

    const storageCounts = await page.evaluate(() => ({
      local: window.localStorage.length,
      session: window.sessionStorage.length,
    }));
    expect(storageCounts.local).toBe(0);
    expect(storageCounts.session).toBe(0);

    await page.waitForTimeout(450);
    await assertNoHorizontalOverflow(page, "desktop-1440 /admin");
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "desktop-1440-admin-dashboard.png") });

    // Light theme check on dashboard
    await page.getByRole("button", { name: /Switch to light color theme/i }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "desktop-1440-admin-dashboard-light.png"),
    });
    await page.getByRole("button", { name: /Switch to dark color theme/i }).click();

    // 4. Sites Catalogue -> Create ephemeral site -> Edit -> Archive & Delete cleanup
    await page.goto("/admin/sites");
    await expect(page.getByRole("heading", { name: /Landing Sites Catalogue/i })).toBeVisible();
    await page.getByRole("button", { name: /\+ New Site/i }).click();
    await page.getByLabel(/Site Code/i).fill("E2E-P7-SITE");
    await page.getByLabel(/Site Name/i).fill("Phase 7 E2E Ridge");
    await page.getByLabel(/URL Slug/i).fill("phase-7-e2e-ridge");
    await page.getByRole("button", { name: /Create Landing Site/i }).click();
    await expect(page.getByText(/Created landing site "Phase 7 E2E Ridge"/i)).toBeVisible();

    const editLink = page
      .locator("tr", { hasText: "E2E-P7-SITE" })
      .getByRole("link", { name: /^Edit$/i });
    await editLink.click();
    await expect(page).toHaveURL(/\/admin\/sites\/\d+/);
    await expect(page.getByText(/Phase 7 E2E Ridge/)).toBeVisible();

    await page.getByRole("tab", { name: /Sections/i }).click();
    await page.getByLabel(/Title/i).fill("E2E Geological Context");
    await page.getByLabel(/Full Content Body/i).fill("E2E section body verified under PostgreSQL.");
    await page.getByRole("button", { name: /Add Section/i }).click();
    await expect(page.getByText(/E2E Geological Context/)).toBeVisible();

    await page.getByRole("tab", { name: /Metrics/i }).click();
    await page.waitForTimeout(250);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "desktop-1440-admin-site-editor.png") });

    // Clean up ephemeral site via Metadata tab Delete button (draft site can be deleted)
    await page.getByRole("button", { name: /Delete Site/i }).click();
    await expect(page).toHaveURL(/\/admin\/sites$/);

    // 5. Media & Imports
    await page.goto("/admin/media");
    await expect(page.getByRole("heading", { name: /Media Asset Library/i })).toBeVisible();
    await expect(page.getByText(/Storage Orphan Diagnostics/i)).toBeVisible();

    await page.goto("/admin/imports");
    await expect(page.getByRole("heading", { name: /Dataset Imports/i })).toBeVisible();
    await expect(page.getByText(/Scientific Data Sources/i)).toBeVisible();

    // 6. CODEX Hardware + Split-Pane Firmware Editor
    await page.goto("/admin/codex");
    await expect(page.getByText(/Hardware Safety Boundary/i)).toBeVisible();
    await expect(page.getByText(/Three-Controller Bus Status/i)).toBeVisible();
    await page
      .locator("tr", { hasText: "motion_uno" })
      .getByRole("button", { name: /^Probe$/i })
      .click();
    await expect(page.getByText(/Transport probe completed cleanly/i)).toBeVisible();
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "desktop-1440-admin-codex.png") });

    await page.goto("/admin/codex/firmware");
    await expect(page.getByText(/No Auto-Flash Safety Policy/i)).toBeVisible();
    await expect(page.getByText(/Live Variable Reference/i)).toBeVisible();

    // Insert live backend variable & save two immutable snapshots to compare diff
    const stamp = Date.now().toString().slice(-6);
    await page.getByLabel(/New Snapshot Label/i).fill(`v1.0.${stamp}-a`);
    const editor = page.getByLabel(/Controller C\+\+ firmware source editor/i);
    await editor.fill("// Stepper rate placeholder\nvoid setup() {\n  // rate = ");
    await page.getByRole("button", { name: /^Insert$/i }).first().click();
    await editor.fill(`${await editor.inputValue()};\n}\nvoid loop() {}\n`);
    await page.getByRole("button", { name: /Save Immutable Version/i }).click();
    await expect(page.getByText(new RegExp(`Saved immutable firmware snapshot "v1\\.0\\.${stamp}-a"`))).toBeVisible();

    await page.getByRole("button", { name: /Validate Syntax/i }).click();
    await expect(page.getByText(/Static & Placeholder Validation/i)).toBeVisible();

    await page.getByLabel(/New Snapshot Label/i).fill(`v1.0.${stamp}-b`);
    const curVal = await editor.inputValue();
    await editor.fill(`${curVal}\n// Phase 7 E2E diff annotation\n`);
    await page.getByRole("button", { name: /Save Immutable Version/i }).click();
    await expect(page.getByText(new RegExp(`Saved immutable firmware snapshot "v1\\.0\\.${stamp}-b"`))).toBeVisible();

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "desktop-1440-admin-firmware-editor.png"),
    });

    await page.getByRole("button", { name: /Compare Diff/i }).click();
    const baseSelect = page.getByLabel(/Compare against base revision/i);
    const baseOpt = baseSelect.locator("option", { hasText: `v1.0.${stamp}-a` });
    const baseVal = await baseOpt.getAttribute("value");
    if (baseVal) {
      await baseSelect.selectOption(baseVal);
      await expect(page.getByText(/Phase 7 E2E diff annotation/i)).toBeVisible();
    }
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "desktop-1440-admin-firmware-diff.png"),
    });

    // 7. Audit & Health + Users & Roles
    await page.goto("/admin/audit");
    await expect(page.getByRole("heading", { name: /Live Subsystem Health Probes/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Redacted Audit Trail/i })).toBeVisible();
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "desktop-1440-admin-audit-health.png") });

    await page.goto("/admin/users");
    await expect(page.getByRole("heading", { name: /Administrator Accounts/i })).toBeVisible();
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "desktop-1440-admin-users.png") });

    // 8. Responsive viewports check (1024px, 768px, 390px) — zero horizontal overflow
    for (const vp of [
      { label: "laptop-1024", width: 1024, height: 768 },
      { label: "tablet-768", width: 768, height: 1024 },
      { label: "mobile-390", width: 390, height: 844 },
    ]) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto("/admin");
      await page.waitForTimeout(300);
      await assertNoHorizontalOverflow(page, `${vp.label} /admin`);
      await page.screenshot({ path: path.join(SCREENSHOT_DIR, `${vp.label}-admin-dashboard.png`) });

      await page.goto("/admin/codex/firmware");
      await page.waitForTimeout(300);
      await assertNoHorizontalOverflow(page, `${vp.label} /admin/codex/firmware`);
      await page.screenshot({ path: path.join(SCREENSHOT_DIR, `${vp.label}-admin-firmware.png`) });
    }

    expect(errors, `Browser console/page errors: ${errors.join(" | ")}`).toEqual([]);
  });
});
