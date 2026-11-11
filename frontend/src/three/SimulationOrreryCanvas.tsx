import { lazy, Suspense, useEffect, useState } from "react";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { detectWebGLSupport } from "./coordinates";
import { MoonFallbackView } from "./MoonFallbackView";
import type { SimulationOrreryCanvasClientProps } from "./SimulationOrreryCanvasClient";

const LazyOrreryClient = lazy(() => import("./SimulationOrreryCanvasClient"));

export function SimulationOrreryCanvas(props: SimulationOrreryCanvasClientProps) {
  const [mounted, setMounted] = useState(false);
  const [webglOk, setWebglOk] = useState(false);

  useEffect(() => {
    setMounted(true);
    setWebglOk(detectWebGLSupport());
  }, []);

  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        height: "440px",
        borderRadius: "var(--radius-md)",
        overflow: "hidden",
        border: "1px solid var(--border-subtle)",
        background: "#05070b",
      }}
    >
      <div
        className="pill-badge cyan"
        style={{
          position: "absolute",
          top: "0.75rem",
          left: "0.75rem",
          zIndex: 5,
          fontSize: "0.72rem",
          pointerEvents: "none",
        }}
      >
        Schematic Scale: Body radii &amp; orbital radii compressed for visual legibility; readouts are exact SPICE telemetry
      </div>

      {!mounted || !webglOk ? (
        <MoonFallbackView
          compact
          label="Schematic orbital fallback (WebGL unavailable)"
        />
      ) : (
        <ErrorBoundary fallbackTitle="Orrery Canvas Unavailable">
          <Suspense fallback={<MoonFallbackView compact />}>
            <LazyOrreryClient {...props} />
          </Suspense>
        </ErrorBoundary>
      )}
    </div>
  );
}

