import { lazy, Suspense, useEffect, useState } from "react";
import { useTheme } from "../app/ThemeContext";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { detectWebGLSupport } from "./coordinates";
import type { LunarMoonCanvasClientProps } from "./LunarMoonCanvasClient";
import { MoonFallbackView } from "./MoonFallbackView";

const LazyLunarMoonClient = lazy(() => import("./LunarMoonCanvasClient"));

export function LunarMoonCanvas(props: LunarMoonCanvasClientProps) {
  const { reducedMotion } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [webglOk, setWebglOk] = useState(false);

  useEffect(() => {
    setMounted(true);
    setWebglOk(detectWebGLSupport());
  }, []);

  const dimmed = props.mode === "ambient";

  if (!mounted || !webglOk) {
    return (
      <MoonFallbackView
        dimmed={dimmed}
        compact={props.mode === "site-focus"}
        label="Lunar globe preview rendered using NASA SVS CGI Moon Kit surface imagery"
      />
    );
  }

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        opacity: dimmed ? 0.34 : 1,
        transition: "opacity 220ms ease",
      }}
    >
      <ErrorBoundary
        fallbackTitle="3D Lunar View Fallback"
        fallbackMessage="WebGL rendering is unavailable on this browser context."
      >
        <Suspense
          fallback={
            <MoonFallbackView
              dimmed={dimmed}
              compact={props.mode === "site-focus"}
            />
          }
        >
          <LazyLunarMoonClient
            {...props}
            reducedMotion={props.reducedMotion ?? reducedMotion}
          />
        </Suspense>
      </ErrorBoundary>
    </div>
  );
}

