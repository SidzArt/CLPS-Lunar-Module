import {
  dehydrate,
  HydrationBoundary,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { renderToString } from "react-dom/server";
import { StaticRouter } from "react-router-dom";
import { ApiClientError } from "./api/client";
import {
  fetchCodexStatus,
  fetchCompareProfiles,
  fetchSiteBySlug,
  fetchSiteHistory,
  fetchSiteMedia,
  fetchSiteMetrics,
  fetchSiteProsCons,
  fetchSiteSections,
  fetchSites,
} from "./api/endpoints";
import { queryKeys } from "./api/queryKeys";
import { AppRoutes, KNOWN_EXACT_PATHS, isKnownDynamicRoute } from "./app/AppRoutes";
import { ThemeProvider } from "./app/ThemeContext";
import {
  HeadCollectorProvider,
  renderHeadHtml,
  type HeadCollector,
} from "./seo/HeadTags";
import "./styles/tokens.css";
import "./styles/global.css";
import "./styles/print.css";

export interface RenderOptions {
  url: string;
  backendOrigin?: string;
  publicBaseUrl?: string;
  cspNonce?: string;
}

export interface RenderResult {
  appHtml: string;
  headHtml: string;
  dehydratedStateScript: string;
  statusCode: number;
}

function normalizePathname(rawUrl: string): string {
  const pathOnly = rawUrl.split("?")[0]?.split("#")[0] || "/";
  if (pathOnly.length > 1 && pathOnly.endsWith("/")) {
    return pathOnly.slice(0, -1);
  }
  return pathOnly;
}

export async function renderPage(options: RenderOptions): Promise<RenderResult> {
  const {
    url,
    backendOrigin = "http://127.0.0.1:8000",
    publicBaseUrl,
  } = options;
  const pathname = normalizePathname(url);
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 30_000,
      },
    },
  });

  let statusCode = 200;

  await Promise.allSettled([
    queryClient.prefetchQuery({
      queryKey: queryKeys.sites({ status: "published", page_size: 50 }),
      queryFn: () =>
        fetchSites({ status: "published", page_size: 50 }, { baseUrl: backendOrigin }),
    }),
    queryClient.prefetchQuery({
      queryKey: queryKeys.codexStatus(),
      queryFn: () => fetchCodexStatus({ baseUrl: backendOrigin }),
    }),
  ]);

  if (pathname === "/compare") {
    await Promise.allSettled([
      queryClient.prefetchQuery({
        queryKey: queryKeys.compareProfiles(),
        queryFn: () => fetchCompareProfiles({ baseUrl: backendOrigin }),
      }),
    ]);
  } else if (pathname.startsWith("/sites/")) {
    const rawSlug = pathname.slice("/sites/".length);
    const siteSlug = decodeURIComponent(rawSlug);
    if (!siteSlug || siteSlug.includes("/")) {
      statusCode = 404;
    } else {
      try {
        const detail = await fetchSiteBySlug(siteSlug, { baseUrl: backendOrigin });
        queryClient.setQueryData(queryKeys.siteDetail(siteSlug), detail);
        await Promise.allSettled([
          queryClient.prefetchQuery({
            queryKey: queryKeys.siteSections(siteSlug),
            queryFn: () => fetchSiteSections(siteSlug, { baseUrl: backendOrigin }),
          }),
          queryClient.prefetchQuery({
            queryKey: queryKeys.siteProsCons(siteSlug),
            queryFn: () => fetchSiteProsCons(siteSlug, { baseUrl: backendOrigin }),
          }),
          queryClient.prefetchQuery({
            queryKey: queryKeys.siteMetrics(siteSlug),
            queryFn: () => fetchSiteMetrics(siteSlug, { baseUrl: backendOrigin }),
          }),
          queryClient.prefetchQuery({
            queryKey: queryKeys.siteMedia(siteSlug),
            queryFn: () => fetchSiteMedia(siteSlug, { baseUrl: backendOrigin }),
          }),
          queryClient.prefetchQuery({
            queryKey: queryKeys.siteHistory(siteSlug),
            queryFn: () => fetchSiteHistory(siteSlug, { baseUrl: backendOrigin }),
          }),
        ]);
      } catch (err) {
        if (err instanceof ApiClientError && err.status === 404) {
          statusCode = 404;
        }
      }
    }
  } else if (
    !KNOWN_EXACT_PATHS.has(pathname) &&
    !isKnownDynamicRoute(pathname)
  ) {
    statusCode = 404;
  }

  const collector: HeadCollector = {};
  const dehydratedState = dehydrate(queryClient);

  const appHtml = renderToString(
    <HeadCollectorProvider collector={collector}>
      <QueryClientProvider client={queryClient}>
        <HydrationBoundary state={dehydratedState}>
          <ThemeProvider>
            <StaticRouter location={url}>
              <AppRoutes />
            </StaticRouter>
          </ThemeProvider>
        </HydrationBoundary>
      </QueryClientProvider>
    </HeadCollectorProvider>,
  );

  const headHtml = renderHeadHtml(collector.meta, publicBaseUrl);
  const safeJson = JSON.stringify(dehydratedState).replace(/</g, "\\u003c");
  const nonceAttr = options.cspNonce ? ` nonce="${options.cspNonce}"` : "";
  const dehydratedStateScript = `<script${nonceAttr}>window.__INITIAL_QUERY_STATE__ = ${safeJson};</script>`;

  queryClient.clear();

  return {
    appHtml,
    headHtml,
    dehydratedStateScript,
    statusCode,
  };
}
