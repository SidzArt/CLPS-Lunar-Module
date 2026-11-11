export interface BreadcrumbItem {
  name: string;
  path: string;
}

export interface PageMetadata {
  title: string;
  description: string;
  canonicalPath: string;
  robots: string;
  ogType: "website" | "article";
  ogImage?: string;
  breadcrumbs: BreadcrumbItem[];
}

function resolvePublicBaseUrl(override?: string): string {
  const fromOverride = override?.trim();
  if (fromOverride) {
    return fromOverride.replace(/\/+$/, "");
  }
  if (typeof window !== "undefined" && window.location?.origin) {
    return window.location.origin.replace(/\/+$/, "");
  }
  const maybeProcess = (
    globalThis as { process?: { env?: Record<string, string | undefined> } }
  ).process;
  const envUrl = maybeProcess?.env?.PUBLIC_BASE_URL;
  return (envUrl && envUrl.trim().length > 0 ? envUrl : "http://127.0.0.1:3000").replace(
    /\/+$/,
    "",
  );
}

export function buildAbsoluteUrl(path: string, publicBaseUrl?: string): string {
  const base = resolvePublicBaseUrl(publicBaseUrl);
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  return `${base}${cleanPath}`;
}

export function buildOrganizationJsonLd(publicBaseUrl?: string): Record<string, unknown> {
  const base = resolvePublicBaseUrl(publicBaseUrl);
  return {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: "CLPS Luna Browser",
    url: base,
    description:
      "Independent educational and scientific mission planning platform for lunar landing-site exploration, comparison, and topocentric visibility simulation. Not endorsed by or affiliated with NASA.",
  };
}

export function buildBreadcrumbJsonLd(
  breadcrumbs: BreadcrumbItem[],
  publicBaseUrl?: string,
): Record<string, unknown> {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: breadcrumbs.map((crumb, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: crumb.name,
      item: buildAbsoluteUrl(crumb.path, publicBaseUrl),
    })),
  };
}
