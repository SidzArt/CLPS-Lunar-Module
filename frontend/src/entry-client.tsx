import {
  HydrationBoundary,
  QueryClient,
  QueryClientProvider,
  type DehydratedState,
} from "@tanstack/react-query";
import { StrictMode } from "react";
import { hydrateRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { AppRoutes } from "./app/AppRoutes";
import { ThemeProvider } from "./app/ThemeContext";
import "./styles/tokens.css";
import "./styles/global.css";
import "./styles/print.css";

interface WindowWithHydrationState extends Window {
  __INITIAL_QUERY_STATE__?: DehydratedState;
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});

const dehydratedState = (window as WindowWithHydrationState).__INITIAL_QUERY_STATE__;

const rootEl = document.getElementById("root");
if (rootEl) {
  hydrateRoot(
    rootEl,
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <HydrationBoundary state={dehydratedState}>
          <ThemeProvider>
            <BrowserRouter>
              <AppRoutes />
            </BrowserRouter>
          </ThemeProvider>
        </HydrationBoundary>
      </QueryClientProvider>
    </StrictMode>,
  );
}
