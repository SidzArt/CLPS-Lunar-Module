import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

const SCREENSHOT_DIR =
  process.env.SCREENSHOT_DIR ||
  "/Users/siddharthwaikar/.gemini/antigravity/brain/652c902a-6cab-4688-b4b9-d5bc9cd0fa05/screenshots/phase6";

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
      // Ignore expected 401 probes on /api/v1/auth/me before admin sign-in
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

test.describe("CLPS Luna Browser Phase 6 Live End-to-End & Visual Verification", () => {
  test.beforeAll(() => {
    ensureDir(SCREENSHOT_DIR);
  });

  test("verifies SSR HTML, SEO endpoints, 301 redirects, and 404 HTTP status", async ({
    request,
  }) => {
    const homeResp = await request.get("/");
    expect(homeResp.status()).toBe(200);
    const homeHtml = await homeResp.text();
    expect(homeHtml).toContain("CLPS");
    expect(homeHtml).toContain("Support &amp; Assist");
    expect(homeHtml).toContain('name="robots" content="index,follow"');
    expect(homeHtml).toContain("application/ld+json");

    const siteResp = await request.get("/sites/lunokhod-1");
    expect(siteResp.status()).toBe(200);
    const siteHtml = await siteResp.text();
    expect(siteHtml).toContain("Lunokhod 1");
    expect(siteHtml).toContain('name="robots" content="index,follow"');

    const compareResp = await request.get("/compare");
    expect(compareResp.status()).toBe(200);
    expect(await compareResp.text()).toContain('name="robots" content="noindex,nofollow"');

    const robotsResp = await request.get("/robots.txt");
    expect(robotsResp.status()).toBe(200);
    const robotsTxt = await robotsResp.text();
    expect(robotsTxt).toContain("Disallow: /admin");
    expect(robotsTxt).toContain("Sitemap:");

    const sitemapResp = await request.get("/sitemap.xml");
    expect(sitemapResp.status()).toBe(200);
    const sitemapXml = await sitemapResp.text();
    expect(sitemapXml).toContain("/sites/lunokhod-1");
    expect(sitemapXml).toContain("/sites/mons-mouton");

    const redirResp = await request.get("/site/lunokhod-1", { maxRedirects: 0 });
    expect(redirResp.status()).toBe(301);
    expect(redirResp.headers().location).toBe("/sites/lunokhod-1");

    const notFoundResp = await request.get("/nonexistent-route-check");
    expect(notFoundResp.status()).toBe(404);
  });

  test("validates full user journeys across live FastAPI, PostgreSQL, and simulation worker", async ({
    page,
  }) => {
    const errors = trackBrowserErrors(page);
    await page.setViewportSize({ width: 1440, height: 900 });

    // 1. Intro page
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Luna Browser");
    await expect(page.getByRole("heading", { name: "Support & Assist" })).toBeVisible();
    // Wait briefly for Moon WebGL / texture settle
    await page.waitForTimeout(900);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "desktop-1440-intro.png"),
    });

    // Navigate via CTA -> /browser
    await page.getByRole("link", { name: /Luna Browser ->/i }).first().click();
    await expect(page).toHaveURL(/\/browser$/);
    await expect(page.getByRole("heading", { name: "Landing Sites" })).toBeVisible();
    await page.waitForTimeout(900);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "desktop-1440-browser.png"),
    });

    // Check Search drawer
    await page.getByRole("button", { name: /Open landing site search/i }).click();
    await page.getByPlaceholder(/e\.g\. Lunokhod/i).fill("Mouton");
    await expect(page.getByRole("dialog").getByText("Mons Mouton")).toBeVisible();
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "desktop-1440-search-drawer.png"),
    });
    await page.keyboard.press("Escape");

    // Check CODEX drawer from Browser header
    await page.getByRole("button", { name: /Inspect CODEX hardware status/i }).click();
    await expect(page.getByText(/MOCK \/ DEMONSTRATION MODE ACTIVE/i)).toBeVisible();
    await expect(page.getByRole("dialog").getByText("Arduino Uno R3")).toBeVisible();
    await expect(page.getByRole("dialog").getByText("ESP32-S3")).toBeVisible();
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "desktop-1440-codex-drawer.png"),
    });
    await page.keyboard.press("Escape");

    // 2. Site Dossier + 6-block tabs (/sites/lunokhod-1)
    await page.goto("/sites/lunokhod-1");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Lunokhod 1");
    await page.waitForTimeout(700);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "desktop-1440-site-overview.png"),
    });

    await page.getByRole("tab", { name: /Statistics/i }).click();
    await expect(page.getByText(/Annual Average Illumination/i)).toBeVisible();
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "desktop-1440-site-statistics.png"),
    });

    await page.getByRole("tab", { name: /History/i }).click();
    await expect(page.getByText(/No historical timeline milestones/i)).toBeVisible();
    await page.getByRole("tab", { name: /Pros & Cons/i }).click();
    await expect(page.getByText(/No qualitative pros or cons entries/i)).toBeVisible();
    await page.getByRole("tab", { name: /Gallery/i }).click();
    await expect(page.getByText(/No site-specific photographs/i)).toBeVisible();
    await page.getByRole("tab", { name: /Research & References/i }).click();
    await expect(page.getByText(/NASA Goddard Space Flight Center/i)).toBeVisible();

    // 3. Compare Workflow (/compare)
    await page.goto("/compare");
    await page.getByRole("button", { name: /Compare ->/i }).click();
    await expect(page.getByText(/Evaluation Summary/i)).toBeVisible();
    await page.waitForTimeout(500);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "desktop-1440-compare.png"),
    });

    // 4. AI Assist (/ai-assist)
    await page.goto("/ai-assist");
    await page.getByRole("button", { name: /Recommend Sites ->/i }).click();
    await expect(page.getByText(/Mission Summary & Extracted Parameters/i)).toBeVisible({
      timeout: 20_000,
    });
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "desktop-1440-ai-assist.png"),
    });

    // 5. Simulation Live Run & Orrery (/simulation)
    await page.goto("/simulation");
    await page.getByRole("button", { name: /Run Simulation ->/i }).click();
    await expect(page).toHaveURL(/\/simulation\/[0-9a-f-]+$/i);
    // Wait for background worker to finish computing the simulation series
    await expect(page.getByText(/Azimuth vs Elevation & Horizon Profile/i)).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByText(/GEOMETRIC ONLY/i)).toBeVisible();
    await page.waitForTimeout(900);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "desktop-1440-simulation.png"),
    });

    // Test Step +1 timeline scrubber updates elapsed readout cleanly
    await page.getByRole("button", { name: /Step \+1/i }).click();
    await expect(page.getByText(/Sample 2 \//i)).toBeVisible();

    // 6. CODEX page & Admin Login Redirect & Contact
    await page.goto("/codex");
    await expect(page.getByText(/REAL HARDWARE MODE — BLOCKED/i)).toBeVisible();
    await page.waitForTimeout(500);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "desktop-1440-codex-page.png"),
    });

    await page.goto("/admin");
    await expect(page).toHaveURL(/\/admin\/login/);
    await expect(page.getByRole("heading", { name: /Administrator Sign-In/i })).toBeVisible();
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "desktop-1440-admin-login.png"),
    });

    await page.goto("/contact");
    await page.getByLabel("Your Name").fill("Phase Six E2E Inspector");
    await page.getByLabel("Email Address").fill("inspector@example.org");
    await page.getByLabel("Subject").fill("Automated Playwright Verification");
    await page
      .getByLabel("Message")
      .fill("Confirming live contact submission storage through Express SSR proxy to FastAPI.");
    await page.getByRole("button", { name: /Send Message ->/i }).click();
    await expect(page.getByText(/Message Received/i)).toBeVisible();
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "desktop-1440-contact.png"),
    });

    // Test Light Accessibility Theme Toggle cleanly
    await page.getByRole("button", { name: /Switch to light color theme/i }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    await page.getByRole("button", { name: /Switch to dark color theme/i }).click();

    expect(errors, `Browser console/page errors: ${errors.join(" | ")}`).toEqual([]);
  });

  test("verifies multi-viewport responsive layouts (1024px, 768px, 390px) with zero horizontal overflow", async ({
    page,
  }) => {
    const errors = trackBrowserErrors(page);

    const viewports = [
      { label: "laptop-1024", width: 1024, height: 768 },
      { label: "tablet-768", width: 768, height: 1024 },
      { label: "mobile-390", width: 390, height: 844 },
    ];

    for (const vp of viewports) {
      await page.setViewportSize({ width: vp.width, height: vp.height });

      await page.goto("/");
      await page.waitForTimeout(500);
      await assertNoHorizontalOverflow(page, `${vp.label} /`);
      await page.screenshot({
        path: path.join(SCREENSHOT_DIR, `${vp.label}-intro.png`),
      });

      await page.goto("/browser");
      await page.waitForTimeout(500);
      await assertNoHorizontalOverflow(page, `${vp.label} /browser`);
      await page.screenshot({
        path: path.join(SCREENSHOT_DIR, `${vp.label}-browser.png`),
      });

      await page.goto("/sites/lunokhod-1");
      await page.waitForTimeout(400);
      await assertNoHorizontalOverflow(page, `${vp.label} /sites/lunokhod-1`);
      await page.screenshot({
        path: path.join(SCREENSHOT_DIR, `${vp.label}-site-info.png`),
      });

      await page.goto("/compare");
      await page.waitForTimeout(300);
      await assertNoHorizontalOverflow(page, `${vp.label} /compare`);
    }

    expect(errors, `Responsive check errors: ${errors.join(" | ")}`).toEqual([]);
  });

  test("verifies smooth Intro scroll animation forward/reverse, Compare selection, and reduced-motion", async ({
    page,
  }) => {
    const errors = trackBrowserErrors(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Luna Browser");
    await expect(page.locator("canvas")).toBeVisible();
    await page.waitForTimeout(700);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "phase8-intro-scroll-top.png"),
    });

    // Scroll to mid-page and bottom cleanly without React DOM instability or overflow
    const maxScroll = await page.evaluate(() =>
      Math.max(1, document.documentElement.scrollHeight - document.documentElement.clientHeight),
    );
    await page.evaluate((y) => window.scrollTo({ top: y, behavior: "instant" }), Math.round(maxScroll * 0.5));
    await page.waitForTimeout(550);
    await assertNoHorizontalOverflow(page, "intro scroll mid");
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "phase8-intro-scroll-mid.png"),
    });

    await page.evaluate((y) => window.scrollTo({ top: y, behavior: "instant" }), maxScroll);
    await page.waitForTimeout(550);
    await expect(page.getByRole("heading", { name: "Support & Assist" })).toBeVisible();
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "phase8-intro-scroll-bottom.png"),
    });

    // Scroll back up smoothly to top
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
    await page.waitForTimeout(450);

    // Reduced-motion check
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Luna Browser");
    await page.waitForTimeout(400);

    // Compare dropdown distinct-selection regression check
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await page.goto("/compare");
    const siteA = page.getByLabel("Site A", { exact: true });
    const siteB = page.getByLabel("Site B", { exact: true });
    const initialA = await siteA.inputValue();
    const initialB = await siteB.inputValue();
    expect(initialA).not.toBe(initialB);
    await siteA.selectOption(initialB);
    expect(await siteA.inputValue()).toBe(initialB);
    await siteB.selectOption(initialA);
    expect(await siteB.inputValue()).toBe(initialA);
    await page.getByRole("button", { name: /Compare ->/i }).click();
    await expect(page.getByText(/Evaluation Summary/i)).toBeVisible();

    expect(errors, `Scroll & Compare E2E errors: ${errors.join(" | ")}`).toEqual([]);
  });
});
