import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import express from "express";
import { buildRobotsTxt, buildSitemapXml } from "./seo-routes.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, "..");

const isProd = process.env.NODE_ENV === "production";
const port = Number(process.env.PORT || 3000);
const backendOrigin = (process.env.BACKEND_ORIGIN || "http://127.0.0.1:8000").replace(
  /\/+$/,
  "",
);

const trustProxy = process.env.TRUST_PROXY === "true";
const allowedHosts = new Set(
  (process.env.ALLOWED_HOSTS || "127.0.0.1,localhost,[::1]")
    .split(",")
    .map((h) => h.trim().toLowerCase())
    .filter(Boolean),
);

function resolveRequestBaseUrl(req) {
  if (process.env.PUBLIC_BASE_URL && process.env.PUBLIC_BASE_URL.trim().length > 0) {
    return process.env.PUBLIC_BASE_URL.trim().replace(/\/+$/, "");
  }
  const rawProto = String(
    (trustProxy && req.headers["x-forwarded-proto"]) || req.protocol || "http",
  )
    .split(",")[0]
    .trim()
    .toLowerCase();
  const proto = rawProto === "https" ? "https" : "http";
  const rawHost = String(
    (trustProxy && req.headers["x-forwarded-host"]) || req.get("host") || `127.0.0.1:${port}`,
  )
    .split(",")[0]
    .trim();
  const hostMatch = /^(\[::1\]|[a-zA-Z0-9.-]+)(?::(\d{1,5}))?$/.exec(rawHost);
  const hostOnly = hostMatch ? hostMatch[1].toLowerCase() : "";
  const safeHost = hostMatch && allowedHosts.has(hostOnly) ? rawHost : `127.0.0.1:${port}`;
  return `${proto}://${safeHost}`;
}

async function readRawBody(req) {
  const chunks = [];
  for await (const chunk of req) {
    chunks.push(typeof chunk === "string" ? Buffer.from(chunk) : chunk);
  }
  return chunks.length > 0 ? Buffer.concat(chunks) : undefined;
}

async function proxyToBackend(req, res) {
  const targetUrl = `${backendOrigin}${req.originalUrl}`;
  const headers = new Headers();

  for (const [k, v] of Object.entries(req.headers)) {
    if (v === undefined) continue;
    const lower = k.toLowerCase();
    if (lower === "host" || lower === "connection" || lower === "content-length") {
      continue;
    }
    if (Array.isArray(v)) {
      headers.set(k, v.join(", "));
    } else {
      headers.set(k, v);
    }
  }
  if (!headers.has("x-forwarded-host") && req.get("host")) {
    headers.set("x-forwarded-host", req.get("host"));
  }
  if (!headers.has("x-forwarded-proto") && req.protocol) {
    headers.set("x-forwarded-proto", req.protocol);
  }

  const hasBody = !["GET", "HEAD"].includes(req.method.toUpperCase());
  const body = hasBody ? await readRawBody(req) : undefined;

  try {
    const upstream = await fetch(targetUrl, {
      method: req.method,
      headers,
      body,
      redirect: "manual",
    });

    res.status(upstream.status);
    upstream.headers.forEach((value, key) => {
      const lower = key.toLowerCase();
      if (lower === "transfer-encoding" || lower === "content-encoding" || lower === "set-cookie") {
        return;
      }
      res.setHeader(key, value);
    });
    const setCookies =
      typeof upstream.headers.getSetCookie === "function"
        ? upstream.headers.getSetCookie()
        : upstream.headers.get("set-cookie")
          ? [upstream.headers.get("set-cookie")]
          : [];
    for (const cookieHeader of setCookies) {
      if (cookieHeader) {
        res.appendHeader("Set-Cookie", cookieHeader);
      }
    }

    const buf = Buffer.from(await upstream.arrayBuffer());
    res.send(buf);
  } catch (err) {
    res.status(502).json({
      code: "BACKEND_UNAVAILABLE",
      message:
        err instanceof Error
          ? `Failed to reach FastAPI backend at ${backendOrigin}: ${err.message}`
          : "Failed to reach FastAPI backend.",
    });
  }
}

export async function createSsrServer() {
  const app = express();
  app.disable("x-powered-by");

  app.use((_req, res, next) => {
    res.setHeader("X-Content-Type-Options", "nosniff");
    res.setHeader("X-Frame-Options", "SAMEORIGIN");
    res.setHeader("Referrer-Policy", "strict-origin-when-cross-origin");
    res.setHeader(
      "Permissions-Policy",
      "accelerometer=(), autoplay=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()",
    );
    next();
  });

  // Reverse proxy API and stored media assets to FastAPI backend
  app.use("/api", proxyToBackend);
  app.use("/storage", proxyToBackend);

  // SEO endpoints
  app.get("/robots.txt", (req, res) => {
    res.type("text/plain; charset=utf-8");
    res.send(buildRobotsTxt(resolveRequestBaseUrl(req)));
  });

  app.get("/sitemap.xml", async (req, res) => {
    res.type("application/xml; charset=utf-8");
    const xml = await buildSitemapXml(resolveRequestBaseUrl(req), backendOrigin);
    res.send(xml);
  });

  // Legacy/convenience 301 canonical redirects
  app.get("/sites", (_req, res) => {
    res.redirect(301, "/browser");
  });
  app.get("/site/:slug", (req, res) => {
    res.redirect(301, `/sites/${encodeURIComponent(req.params.slug)}`);
  });

  let vite;
  let templateHtml = "";
  let prodRenderPage = null;

  if (!isProd) {
    const { createServer } = await import("vite");
    vite = await createServer({
      root: rootDir,
      server: { middlewareMode: true },
      appType: "custom",
    });
    app.use(vite.middlewares);
  } else {
    const clientDir = path.resolve(rootDir, "dist/client");
    templateHtml = await fs.readFile(path.join(clientDir, "index.html"), "utf-8");
    const serverEntry = await import(
      path.resolve(rootDir, "dist/server/entry-server.js")
    );
    prodRenderPage = serverEntry.renderPage;
    app.use(
      express.static(clientDir, {
        index: false,
        maxAge: "7d",
      }),
    );
  }

  // Catch-all SSR handler (Express 5 safe without bare * path syntax)
  app.use(async (req, res, next) => {
    if (req.method !== "GET" && req.method !== "HEAD") {
      next();
      return;
    }

    const url = req.originalUrl;
    try {
      let template;
      let render;

      if (!isProd && vite) {
        const rawTemplate = await fs.readFile(
          path.resolve(rootDir, "index.html"),
          "utf-8",
        );
        template = await vite.transformIndexHtml(url, rawTemplate);
        const mod = await vite.ssrLoadModule("/src/entry-server.tsx");
        render = mod.renderPage;
      } else {
        template = templateHtml;
        render = prodRenderPage;
      }

      const cspNonce = crypto.randomBytes(16).toString("base64");
      const rendered = await render({
        url,
        backendOrigin,
        publicBaseUrl: resolveRequestBaseUrl(req),
        cspNonce,
      });

      const noncedTemplate = template.replace(
        /<script(?![^>]*\bnonce=)(?![^>]*application\/ld\+json)([^>]*)>/g,
        `<script nonce="${cspNonce}"$1>`,
      );

      const html = noncedTemplate
        .replace("<!--app-head-->", rendered.headHtml)
        .replace("<!--app-html-->", rendered.appHtml)
        .replace("<!--app-state-->", rendered.dehydratedStateScript);

      const connectSrc = isProd
        ? "connect-src 'self'"
        : "connect-src 'self' ws://127.0.0.1:* ws://localhost:*";
      res.setHeader(
        "Content-Security-Policy",
        [
          "default-src 'self'",
          `script-src 'self' 'nonce-${cspNonce}'`,
          "style-src 'self' 'unsafe-inline'",
          "img-src 'self' data: blob:",
          "font-src 'self' data:",
          "worker-src 'self' blob:",
          connectSrc,
          "object-src 'none'",
          "base-uri 'self'",
          "form-action 'self'",
          "frame-ancestors 'self'",
        ].join("; "),
      );
      if (url.startsWith("/admin")) {
        res.setHeader("Cache-Control", "no-store, max-age=0");
      }

      res.status(rendered.statusCode).setHeader("Content-Type", "text/html; charset=utf-8");
      res.end(html);
    } catch (err) {
      if (vite && err instanceof Error) {
        vite.ssrFixStacktrace(err);
      }
      next(err);
    }
  });

  return app;
}

if (
  import.meta.url === `file://${process.argv[1]}` ||
  process.argv[1]?.endsWith("ssr-server.mjs")
) {
  const app = await createSsrServer();
  app.listen(port, "127.0.0.1", () => {
    console.log(
      `CLPS Luna Browser SSR server listening on http://127.0.0.1:${port} (mode=${isProd ? "production" : "development"}, backend=${backendOrigin})`,
    );
  });
}
