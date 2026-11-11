function cleanBaseUrl(rawUrl) {
  return (rawUrl || "http://127.0.0.1:3000").replace(/\/+$/, "");
}

function escapeXml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

export function buildRobotsTxt(publicBaseUrl) {
  const base = cleanBaseUrl(publicBaseUrl);
  return [
    "User-agent: *",
    "Allow: /",
    "Allow: /browser",
    "Allow: /sites/",
    "Allow: /contact",
    "Allow: /privacy",
    "Allow: /terms",
    "Disallow: /compare",
    "Disallow: /ai-assist",
    "Disallow: /simulation",
    "Disallow: /codex",
    "Disallow: /admin",
    "Disallow: /api/",
    `Sitemap: ${base}/sitemap.xml`,
    "",
  ].join("\n");
}

export async function buildSitemapXml(publicBaseUrl, backendOrigin) {
  const base = cleanBaseUrl(publicBaseUrl);
  const backend = cleanBaseUrl(backendOrigin || "http://127.0.0.1:8000");

  const staticEntries = [
    { loc: `${base}/`, changefreq: "weekly", priority: "1.0" },
    { loc: `${base}/browser`, changefreq: "weekly", priority: "0.9" },
    { loc: `${base}/contact`, changefreq: "monthly", priority: "0.4" },
    { loc: `${base}/privacy`, changefreq: "yearly", priority: "0.3" },
    { loc: `${base}/terms`, changefreq: "yearly", priority: "0.3" },
  ];

  const siteEntries = [];
  try {
    let page = 1;
    while (page <= 10) {
      const resp = await fetch(
        `${backend}/api/v1/sites?status=published&page=${page}&page_size=100`,
        { headers: { Accept: "application/json" } },
      );
      if (!resp.ok) {
        break;
      }
      const payload = await resp.json();
      const items = Array.isArray(payload.items) ? payload.items : [];
      for (const s of items) {
        if (s.catalogue_status === "published" && s.site_slug) {
          siteEntries.push({
            loc: `${base}/sites/${encodeURIComponent(s.site_slug)}`,
            lastmod:
              typeof s.updated_at === "string" ? s.updated_at.slice(0, 10) : undefined,
            changefreq: "weekly",
            priority: "0.8",
          });
        }
      }
      if (items.length < 100 || siteEntries.length >= Number(payload.total || 0)) {
        break;
      }
      page += 1;
    }
  } catch {
    // Emit valid base sitemap even if backend is transiently unreachable
  }

  const allUrls = [...staticEntries, ...siteEntries];
  const urlNodes = allUrls
    .map((entry) => {
      const parts = [
        "  <url>",
        `    <loc>${escapeXml(entry.loc)}</loc>`,
        entry.lastmod ? `    <lastmod>${escapeXml(entry.lastmod)}</lastmod>` : null,
        `    <changefreq>${escapeXml(entry.changefreq)}</changefreq>`,
        `    <priority>${escapeXml(entry.priority)}</priority>`,
        "  </url>",
      ].filter(Boolean);
      return parts.join("\n");
    })
    .join("\n");

  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    urlNodes,
    "</urlset>",
    "",
  ].join("\n");
}
