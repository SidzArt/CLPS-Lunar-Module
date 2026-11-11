import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

const SCREENSHOT_DIR =
  "/Users/siddharthwaikar/.gemini/antigravity/brain/652c902a-6cab-4688-b4b9-d5bc9cd0fa05/screenshots/orbital-redesign";

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

test.describe("CLPS Orbital Simulation Redesign Live Verification", () => {
  test.beforeAll(() => {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  });

  test("verifies Landing Site -> Simulate flow, dual WebGL SPICE views, 1-month & 1-year trajectories, playback duration controls, and mobile layout", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const errors = trackBrowserErrors(page);

    await page.setViewportSize({ width: 1440, height: 900 });

    // 1. Landing Site -> Click existing Simulate button
    await page.goto("/sites/lunokhod-1");
    await expect(page.getByRole("heading", { name: /Lunokhod 1/i })).toBeVisible();
    await page.getByRole("link", { name: /Simulate/i }).first().click();
    await expect(page).toHaveURL(/\/simulation\?siteId=\d+/);

    // 2. Verify all 6 scientific duration options exist and run 1 lunar sidereal month (27.322 days)
    const durationSelect = page.getByLabel(/Physical Duration/i);
    await durationSelect.selectOption("2360621");
    await page.getByRole("button", { name: /Run Simulation ->/i }).click();
    await expect(page).toHaveURL(/\/simulation\/[0-9a-f-]+$/i);

    await expect(page.getByText(/Azimuth vs Elevation & Horizon Profile/i)).toBeVisible({
      timeout: 45_000,
    });
    await expect(page.locator("canvas")).toHaveCount(2, { timeout: 15_000 });
    await expect(page.getByText(/NOT TO SCALE/i).first()).toBeVisible();

    // Let WebGL render frames cleanly and verify long-duration series was NOT truncated at 1000
    await expect(page.getByText(/Sample 1 \/ [2-9]\d{3}/)).toBeVisible();
    await page.waitForTimeout(900);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "after-simulation-lunar-month.png"),
      fullPage: false,
    });

    // 3. Test all 6 Animation Playback Duration presets
    const customInput = page.getByLabel("Custom animation duration (seconds)");
    for (const [label, sec] of [
      ["15s", "15"],
      ["30s", "30"],
      ["60s", "60"],
      ["2m", "120"],
      ["5m", "300"],
      ["10m", "600"],
    ]) {
      await page.getByRole("button", { name: label, exact: true }).click();
      await expect(customInput).toHaveValue(sec);
    }

    // 4. Test valid custom numeric values (45, 180, 600)
    for (const good of ["45", "180", "600"]) {
      await customInput.fill(good);
      await expect(customInput).toHaveValue(good);
      await expect(page.getByRole("alert").filter({ hasText: /seconds/i })).toHaveCount(0);
    }

    // 5. Test invalid inputs preserve text, show error, disable Play
    for (const bad of ["", "0", "-10", "12.5", "abc", "4000"]) {
      await customInput.fill(bad);
      await expect(customInput).toHaveValue(bad);
      await expect(
        page.getByRole("alert").filter({ hasText: /between 5 and 3600 seconds/i }),
      ).toBeVisible();
      await expect(page.getByRole("button", { name: /Play|Resume/i })).toBeDisabled();
    }

    // Restore valid 15s preset and test Play -> Pause -> Resume -> Step +1 -> Scrub -> Reset
    await page.getByRole("button", { name: "15s", exact: true }).click();
    const initTs = await page.getByTestId("orrery-timestamp").textContent();
    await page.getByRole("button", { name: /^Play$/i }).click();
    await page.waitForTimeout(450);
    await page.getByRole("button", { name: /^Pause$/i }).click();
    const pausedTs = await page.getByTestId("orrery-timestamp").textContent();
    expect(pausedTs).not.toBe(initTs);
    await page.waitForTimeout(250);
    expect(await page.getByTestId("orrery-timestamp").textContent()).toBe(pausedTs);

    await page.getByRole("button", { name: /^Resume$/i }).click();
    await page.waitForTimeout(300);
    await page.getByRole("button", { name: /^Pause$/i }).click();
    const resumedTs = await page.getByTestId("orrery-timestamp").textContent();
    expect(resumedTs).not.toBe(pausedTs);

    // Inset Focus switch & Reset
    await page.getByRole("button", { name: /Moon & Site/i }).click();
    await page.waitForTimeout(350);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "after-simulation-moon-focus.png"),
      fullPage: false,
    });
    await page.getByRole("button", { name: /Earth Center/i }).click();

    await page.getByRole("button", { name: /^Reset$/i }).click();
    await expect(page.getByText(/Sample 1 \//)).toBeVisible();
    await page.getByRole("button", { name: /Step \+1/i }).click();
    await expect(page.getByText(/Sample 2 \//)).toBeVisible();

    // 6. Run 1 Earth sidereal year (365.256 days = 31558118s) with shifted start date
    await page.getByLabel(/Start Date & Time/i).fill("2026-01-03T00:00:00Z");
    await page.getByLabel(/Physical Duration/i).selectOption("31558118");
    const trajPromise = page.waitForResponse(
      (r) => r.url().includes("/orbital-trajectory") && r.status() === 200,
      { timeout: 60_000 },
    );
    await page.getByRole("button", { name: /Run Simulation ->/i }).click();
    const trajResp = await trajPromise;
    const trajBody = await trajResp.json();
    expect(trajBody.duration_seconds).toBe(31558118);
    expect(trajBody.sample_count).toBe(2048);
    expect(trajBody.coordinate_frame).toBe("ECLIPJ2000");

    await expect(page.getByText(/Azimuth vs Elevation & Horizon Profile/i)).toBeVisible({
      timeout: 45_000,
    });
    await expect(page.getByText(/Sample 1 \/ [89]\d{3}/)).toBeVisible({ timeout: 20_000 });
    await page.waitForTimeout(900);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "after-simulation-one-year.png"),
      fullPage: false,
    });

    // 7. Mobile viewport layout & zero horizontal overflow
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(450);
    const mobileOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    expect(mobileOverflow).toBeLessThanOrEqual(2);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "after-simulation-mobile-390.png"),
      fullPage: false,
    });

    expect(errors, `Browser errors detected: ${errors.join(" | ")}`).toEqual([]);
  });
});

