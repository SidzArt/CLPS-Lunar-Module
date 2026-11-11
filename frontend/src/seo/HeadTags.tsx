import { createContext, useContext, useEffect, type ReactNode } from "react";
import {
  buildAbsoluteUrl,
  buildBreadcrumbJsonLd,
  buildOrganizationJsonLd,
  type PageMetadata,
} from "./metadata";

export interface HeadCollector {
  meta?: PageMetadata;
}

const HeadCollectorContext = createContext<HeadCollector | null>(null);

export function HeadCollectorProvider({
  collector,
  children,
}: {
  collector: HeadCollector;
  children: ReactNode;
}) {
  return (
    <HeadCollectorContext.Provider value={collector}>
      {children}
    </HeadCollectorContext.Provider>
  );
}

function escapeHtmlAttr(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function escapeHtmlText(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function escapeJsonLd(obj: Record<string, unknown>): string {
  return JSON.stringify(obj).replace(/</g, "\\u003c");
}

export function renderHeadHtml(
  meta: PageMetadata | undefined,
  publicBaseUrl?: string,
): string {
  if (!meta) {
    return "";
  }
  const canonicalUrl = buildAbsoluteUrl(meta.canonicalPath, publicBaseUrl);
  const ogImageUrl = buildAbsoluteUrl(
    meta.ogImage || "/assets/moon/moon_albedo_2k.webp",
    publicBaseUrl,
  );
  const orgJsonLd = escapeJsonLd(buildOrganizationJsonLd(publicBaseUrl));
  const breadcrumbJsonLd = escapeJsonLd(
    buildBreadcrumbJsonLd(meta.breadcrumbs, publicBaseUrl),
  );

  return [
    `<title>${escapeHtmlText(meta.title)}</title>`,
    `<meta name="description" content="${escapeHtmlAttr(meta.description)}" />`,
    `<meta name="robots" content="${escapeHtmlAttr(meta.robots)}" />`,
    `<link rel="canonical" href="${escapeHtmlAttr(canonicalUrl)}" />`,
    `<meta property="og:title" content="${escapeHtmlAttr(meta.title)}" />`,
    `<meta property="og:description" content="${escapeHtmlAttr(meta.description)}" />`,
    `<meta property="og:type" content="${escapeHtmlAttr(meta.ogType)}" />`,
    `<meta property="og:url" content="${escapeHtmlAttr(canonicalUrl)}" />`,
    `<meta property="og:image" content="${escapeHtmlAttr(ogImageUrl)}" />`,
    `<meta name="twitter:card" content="summary_large_image" />`,
    `<meta name="twitter:title" content="${escapeHtmlAttr(meta.title)}" />`,
    `<meta name="twitter:description" content="${escapeHtmlAttr(meta.description)}" />`,
    `<script type="application/ld+json">${orgJsonLd}</script>`,
    `<script type="application/ld+json">${breadcrumbJsonLd}</script>`,
  ].join("\n    ");
}

function upsertMetaTag(attrName: "name" | "property", key: string, content: string): void {
  let el = document.head.querySelector(`meta[${attrName}="${key}"]`);
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute(attrName, key);
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}

function upsertCanonical(href: string): void {
  let el = document.head.querySelector('link[rel="canonical"]');
  if (!el) {
    el = document.createElement("link");
    el.setAttribute("rel", "canonical");
    document.head.appendChild(el);
  }
  el.setAttribute("href", href);
}

export interface HeadTagsProps {
  meta: PageMetadata;
  publicBaseUrl?: string;
}

export function HeadTags({ meta, publicBaseUrl }: HeadTagsProps) {
  const collector = useContext(HeadCollectorContext);
  if (collector) {
    collector.meta = meta;
  }

  useEffect(() => {
    if (typeof document === "undefined") {
      return;
    }
    const canonicalUrl = buildAbsoluteUrl(meta.canonicalPath, publicBaseUrl);
    const ogImageUrl = buildAbsoluteUrl(
      meta.ogImage || "/assets/moon/moon_albedo_2k.webp",
      publicBaseUrl,
    );

    document.title = meta.title;
    upsertMetaTag("name", "description", meta.description);
    upsertMetaTag("name", "robots", meta.robots);
    upsertCanonical(canonicalUrl);
    upsertMetaTag("property", "og:title", meta.title);
    upsertMetaTag("property", "og:description", meta.description);
    upsertMetaTag("property", "og:type", meta.ogType);
    upsertMetaTag("property", "og:url", canonicalUrl);
    upsertMetaTag("property", "og:image", ogImageUrl);
    upsertMetaTag("name", "twitter:card", "summary_large_image");
    upsertMetaTag("name", "twitter:title", meta.title);
    upsertMetaTag("name", "twitter:description", meta.description);
  }, [meta, publicBaseUrl]);

  return null;
}
