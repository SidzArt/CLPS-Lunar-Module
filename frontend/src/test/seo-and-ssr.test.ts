import { afterEach, describe, expect, it, vi } from "vitest";
import { buildRobotsTxt, buildSitemapXml } from "../../server/seo-routes.mjs";
import { renderPage } from "../entry-server";

const MOCK_SITES = {
  items: [
    {
      site_id: 102,
      site_slug: "lunokhod-1",
      site_code: "LUNA-17-LUNOKHOD-1",
      site_name: "Lunokhod 1",
      region_id: 15,
      region_name: "Mare Imbrium",
      latitude_deg: 38.315,
      longitude_deg: -35.008,
      elevation_m: -2600,
      terrain_type: "Mare Basaltic Plain",
      overview_summary: "Soviet Luna 17 / Lunokhod 1 landing site in Mare Imbrium.",
      catalogue_status: "published",
      primary_thumbnail: null,
      updated_at: "2026-11-11T00:00:00Z",
    },
  ],
  total: 1,
  page: 1,
  page_size: 50,
};

const MOCK_SITE_DETAIL = {
  site_id: 102,
  site_slug: "lunokhod-1",
  site_code: "LUNA-17-LUNOKHOD-1",
  site_name: "Lunokhod 1",
  alternate_names: [],
  region_id: 15,
  region_name: "Mare Imbrium",
  region_code: "MARE-IMBRIUM",
  latitude_deg: 38.315,
  longitude_deg: -35.008,
  elevation_m: -2600,
  terrain_type: "Mare Basaltic Plain",
  overview_summary: "Soviet Luna 17 / Lunokhod 1 landing site in Mare Imbrium.",
  catalogue_status: "published",
  coordinate_reference: "MOON_ME (IAU/NAIF Mean Earth/Polar Axis)",
  seo_title: null,
  seo_meta_description: null,
  og_image_url: null,
  primary_image_url: null,
  available_sections: [],
  created_at: "2026-11-11T00:00:00Z",
  updated_at: "2026-11-11T00:00:00Z",
};

const MOCK_METRICS = [
  {
    site_metric_id: 1,
    site_id: 102,
    parameter_id: 10,
    parameter_key: "solar_illumination_pct",
    display_name: "Solar Illumination",
    numeric_value: 54.0,
    text_value: null,
    unit: "%",
    uncertainty_value: null,
    methodology: null,
    source_id: null,
    source_title: null,
    source_citation: null,
    source_url: null,
    data_quality_status: "unverified",
    dataset_version: null,
    valid_from: null,
    valid_to: null,
    calculated_at: null,
  },
];

const MOCK_CODEX_STATUS = {
  transport_mode: "mock",
  require_verified_bench: true,
  overall_status: "unverified",
  motors_ready: false,
  led_ready: false,
  estop_latched: false,
  calibration_verified: false,
  led_mapping_verified: false,
  blockers: ["Phase 5 physical bench calibration required."],
  controllers: [
    {
      controller_key: "wifi_bridge",
      device_role: "wifi_uart_bridge",
      board_model: "ESP32-WROOM-32D",
      health_state: "unverified",
      verification_status: "unverified",
      heartbeat_fresh: false,
      uart_ok: false,
      driver_config_ok: false,
      led_controller_ok: false,
      estop_latched: false,
      battery_voltage_available: false,
      battery_voltage_v: null,
      last_heartbeat_at: null,
    },
  ],
  checked_at: "2026-11-11T00:00:00Z",
};

function installFetchMock() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.includes("/api/v1/sites?")) {
        return new Response(JSON.stringify(MOCK_SITES), { status: 200 });
      }
      if (url.endsWith("/api/v1/codex/status")) {
        return new Response(JSON.stringify(MOCK_CODEX_STATUS), { status: 200 });
      }
      if (url.includes("/api/v1/sites/lunokhod-1/metrics")) {
        return new Response(JSON.stringify(MOCK_METRICS), { status: 200 });
      }
      if (url.match(/\/api\/v1\/sites\/lunokhod-1\/(sections|pros-cons|media|history)/)) {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      if (url.endsWith("/api/v1/sites/lunokhod-1")) {
        return new Response(JSON.stringify(MOCK_SITE_DETAIL), { status: 200 });
      }
      if (url.includes("/api/v1/sites/missing-site")) {
        return new Response(
          JSON.stringify({ code: "NOT_FOUND", message: "Site not found" }),
          { status: 404 },
        );
      }
      if (url.includes("/api/v1/compare/profiles")) {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      return new Response(JSON.stringify({}), { status: 200 });
    }),
  );
}

describe("SSR renderPage and SEO endpoints", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders intro route with index,follow, Support & Assist heading, and dehydrated data", async () => {
    installFetchMock();
    const res = await renderPage({ url: "/", backendOrigin: "http://127.0.0.1:8000" });
    expect(res.statusCode).toBe(200);
    expect(res.appHtml).toContain("CLPS");
    expect(res.appHtml).toContain("Luna Browser");
    expect(res.appHtml).toContain("Support &amp; Assist");
    expect(res.headHtml).toContain('name="robots" content="index,follow"');
    expect(res.headHtml).toContain("application/ld+json");
    expect(res.dehydratedStateScript).toContain("__INITIAL_QUERY_STATE__");
  });

  it("renders site detail SSR HTML with PostgreSQL metrics and returns 404 for unknown slug", async () => {
    installFetchMock();
    const ok = await renderPage({
      url: "/sites/lunokhod-1",
      backendOrigin: "http://127.0.0.1:8000",
    });
    expect(ok.statusCode).toBe(200);
    expect(ok.appHtml).toContain("Lunokhod 1");
    expect(ok.appHtml).toContain("LUNA-17-LUNOKHOD-1");
    expect(ok.headHtml).toContain('name="robots" content="index,follow"');

    const missing = await renderPage({
      url: "/sites/missing-site",
      backendOrigin: "http://127.0.0.1:8000",
    });
    expect(missing.statusCode).toBe(404);
  });

  it("marks tool and admin routes noindex,nofollow and unknown paths 404", async () => {
    installFetchMock();
    for (const route of ["/compare", "/ai-assist", "/simulation", "/codex", "/admin"]) {
      const rendered = await renderPage({
        url: route,
        backendOrigin: "http://127.0.0.1:8000",
      });
      expect(rendered.statusCode).toBe(200);
      expect(rendered.headHtml).toContain('name="robots" content="noindex,nofollow"');
    }

    const notFound = await renderPage({
      url: "/completely-unknown-path",
      backendOrigin: "http://127.0.0.1:8000",
    });
    expect(notFound.statusCode).toBe(404);
  });

  it("generates accurate robots.txt and dynamic sitemap.xml from published sites", async () => {
    installFetchMock();
    const robots = buildRobotsTxt("https://clps.example.org");
    expect(robots).toContain("Disallow: /admin");
    expect(robots).toContain("Disallow: /compare");
    expect(robots).toContain("Disallow: /codex");
    expect(robots).toContain("Sitemap: https://clps.example.org/sitemap.xml");

    const sitemap = await buildSitemapXml(
      "https://clps.example.org",
      "http://127.0.0.1:8000",
    );
    expect(sitemap).toContain("<loc>https://clps.example.org/</loc>");
    expect(sitemap).toContain("<loc>https://clps.example.org/browser</loc>");
    expect(sitemap).toContain("<loc>https://clps.example.org/sites/lunokhod-1</loc>");
    expect(sitemap).not.toContain("/admin");
  });
});

