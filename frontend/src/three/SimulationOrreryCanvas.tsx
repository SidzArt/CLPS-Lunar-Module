import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { detectWebGLSupport } from "./coordinates";
import { MoonFallbackView } from "./MoonFallbackView";
import type { SimulationOrreryCanvasClientProps } from "./SimulationOrreryCanvasClient";
import {
  AU_KM,
  eclipJ2000ToThree,
  INSET_KM_TO_UNITS,
  INSET_VS_OVERVIEW_MAGNIFICATION,
  interpolateOrbitalState,
  OVERVIEW_KM_TO_UNITS,
  OVERVIEW_MOON_OFFSET_MAGNIFICATION,
} from "./simulationOrbitMath";

const SimulationOrreryCanvasClient = lazy(() => import("./SimulationOrreryCanvasClient"));

function SynchronizedOrbitalSvgFallback({
  series,
  trajectory,
  elapsedSeconds = 0,
  activeTimestampUtc,
}: SimulationOrreryCanvasClientProps) {
  const orbital = useMemo(() => {
    if (!trajectory || !trajectory.samples || trajectory.samples.length === 0) {
      return null;
    }
    return interpolateOrbitalState(trajectory, elapsedSeconds);
  }, [trajectory, elapsedSeconds]);

  if (!trajectory || !orbital) {
    return (
      <MoonFallbackView
        compact
        label={`NOT TO SCALE · Waiting for SPICE orbital trajectory (${series.site.site_name})`}
      />
    );
  }

  // Project Three.js XZ plane ([X, -Z] -> [x, -z] or [x, y_eclip]) onto SVG viewboxes
  const ovCx = 140;
  const ovCy = 110;
  const ovScale = 8.4; // 1 AU (10 units) -> 84px
  const toOvX = (x: number) => ovCx + x * ovScale;
  const toOvY = (z: number) => ovCy + z * ovScale;

  const earthPathPts = trajectory.samples
    .filter((_, i) => i % Math.max(1, Math.floor(trajectory.samples.length / 120)) === 0)
    .map((s) => {
      const p = eclipJ2000ToThree(s.earth_wrt_sun_eclipj2000_km, OVERVIEW_KM_TO_UNITS);
      return `${toOvX(p[0]).toFixed(1)},${toOvY(p[2]).toFixed(1)}`;
    })
    .join(" ");

  const moonCombinedPts = trajectory.samples
    .filter((_, i) => i % Math.max(1, Math.floor(trajectory.samples.length / 180)) === 0)
    .map((s) => {
      const ep = eclipJ2000ToThree(s.earth_wrt_sun_eclipj2000_km, OVERVIEW_KM_TO_UNITS);
      const mp = eclipJ2000ToThree(
        s.moon_wrt_earth_eclipj2000_km,
        OVERVIEW_KM_TO_UNITS * OVERVIEW_MOON_OFFSET_MAGNIFICATION,
      );
      return `${toOvX(ep[0] + mp[0]).toFixed(1)},${toOvY(ep[2] + mp[2]).toFixed(1)}`;
    })
    .join(" ");

  const inCx = 140;
  const inCy = 110;
  const inScale = 22; // 3.6 units -> ~79px
  const toInX = (x: number) => inCx + x * inScale;
  const toInY = (z: number) => inCy + z * inScale;

  const moonInsetPts = trajectory.samples
    .filter((_, i) => i % Math.max(1, Math.floor(trajectory.samples.length / 160)) === 0)
    .map((s) => {
      const p = eclipJ2000ToThree(s.moon_wrt_earth_eclipj2000_km, INSET_KM_TO_UNITS);
      return `${toInX(p[0]).toFixed(1)},${toInY(p[2]).toFixed(1)}`;
    })
    .join(" ");

  const eX = toOvX(orbital.overviewEarthPos[0]);
  const eY = toOvY(orbital.overviewEarthPos[2]);
  const mOvX = toOvX(orbital.overviewMoonPos[0]);
  const mOvY = toOvY(orbital.overviewMoonPos[2]);
  const mInX = toInX(orbital.insetMoonPos[0]);
  const mInY = toInY(orbital.insetMoonPos[2]);

  return (
    <div className="sim-dual-viewport-grid" data-testid="orbital-fallback-views">
      <div className="sim-viewport-pane">
        <div className="sim-viewport-header">
          <span className="sim-viewport-title">
            Main Overview: Sun -&gt; Earth -&gt; Moon (ECLIPJ2000)
          </span>
          <span className="sim-viewport-mag mono">
            NOT TO SCALE · Moon offset {OVERVIEW_MOON_OFFSET_MAGNIFICATION}x
          </span>
        </div>
        <div className="sim-fallback-svg-wrap">
          <svg
            viewBox="0 0 280 220"
            style={{ width: "100%", height: "auto", display: "block" }}
            role="img"
            aria-label="Heliocentric Sun Earth Moon orbital trajectory schematic"
          >
            {earthPathPts && (
              <polyline fill="none" stroke="#5ad2e6" strokeWidth="1.5" points={earthPathPts} />
            )}
            {moonCombinedPts && (
              <polyline
                fill="none"
                stroke="#cbd5e1"
                strokeWidth="1"
                strokeOpacity="0.65"
                points={moonCombinedPts}
              />
            )}
            <line x1={ovCx} y1={ovCy} x2={eX} y2={eY} stroke="#f5b83d" strokeDasharray="3 3" strokeOpacity="0.5" />
            <line x1={eX} y1={eY} x2={mOvX} y2={mOvY} stroke="#5ad2e6" strokeOpacity="0.8" />
            <circle cx={ovCx} cy={ovCy} r={8} fill="#f5b83d" data-testid="svg-sun" />
            <circle cx={eX} cy={eY} r={5} fill="#3d8fd6" data-testid="svg-overview-earth" />
            <circle cx={mOvX} cy={mOvY} r={3} fill="#edf2f7" data-testid="svg-overview-moon" />
          </svg>
        </div>
        <div className="sim-viewport-footer mono">
          <span>
            Earth-Sun: {(orbital.earthSunDistanceKm / AU_KM).toFixed(4)} AU
          </span>
          <span>UTC: {activeTimestampUtc || orbital.timestampUtc}</span>
        </div>
      </div>

      <div className="sim-viewport-pane">
        <div className="sim-viewport-header">
          <span className="sim-viewport-title">
            Magnified Earth-Moon System (3D Inclination &amp; Tidal Lock)
          </span>
          <span className="sim-viewport-mag mono">
            NOT TO SCALE · Distance {INSET_VS_OVERVIEW_MAGNIFICATION}x vs Overview
          </span>
        </div>
        <div className="sim-fallback-svg-wrap">
          <svg
            viewBox="0 0 280 220"
            style={{ width: "100%", height: "auto", display: "block" }}
            role="img"
            aria-label="Magnified Earth Moon inclined orbit schematic"
          >
            {moonInsetPts && (
              <polyline fill="none" stroke="#5ad2e6" strokeWidth="1.5" points={moonInsetPts} />
            )}
            <line x1={inCx} y1={inCy} x2={mInX} y2={mInY} stroke="#5ad2e6" strokeOpacity="0.7" />
            <circle cx={inCx} cy={inCy} r={7} fill="#3d8fd6" data-testid="svg-inset-earth" />
            <circle cx={mInX} cy={mInY} r={4.5} fill="#edf2f7" data-testid="svg-inset-moon" />
          </svg>
        </div>
        <div className="sim-viewport-footer mono">
          <span>Earth-Moon: {Math.round(orbital.moonEarthDistanceKm).toLocaleString()} km</span>
          <span>Inclination Z-lat: {orbital.moonWrtEarthElevationDeg.toFixed(2)} deg</span>
        </div>
      </div>
    </div>
  );
}

export function SimulationOrreryCanvas(props: SimulationOrreryCanvasClientProps) {
  const [webglSupported, setWebglSupported] = useState(false);
  const [insetFocus, setInsetFocus] = useState<"earth" | "moon">("earth");

  useEffect(() => {
    setWebglSupported(detectWebGLSupport());
  }, []);

  const tsDisplay = props.activeTimestampUtc
    ? props.activeTimestampUtc.replace("T", " ").replace("Z", " UTC")
    : undefined;

  return (
    <div className="glass-panel sim-orrery-card" style={{ position: "relative" }}>
      <div className="sim-orrery-hud">
        <div style={{ display: "flex", gap: "0.45rem", flexWrap: "wrap", alignItems: "center" }}>
          <span className="sim-scale-warning mono">
            NOT TO SCALE · Overview Moon {OVERVIEW_MOON_OFFSET_MAGNIFICATION}x · Inset{" "}
            {INSET_VS_OVERVIEW_MAGNIFICATION}x
          </span>
          {tsDisplay && (
            <span className="sim-timestamp-pill mono" data-testid="orrery-timestamp">
              {tsDisplay}
            </span>
          )}
        </div>

        {webglSupported && (
          <div style={{ display: "flex", gap: "0.35rem", alignItems: "center" }}>
            <span className="eyebrow">Inset Focus:</span>
            <button
              type="button"
              className={`btn ${insetFocus === "earth" ? "btn-cyan" : ""}`}
              style={{ padding: "0.24rem 0.55rem", fontSize: "0.73rem" }}
              onClick={() => setInsetFocus("earth")}
            >
              Earth Center
            </button>
            <button
              type="button"
              className={`btn ${insetFocus === "moon" ? "btn-cyan" : ""}`}
              style={{ padding: "0.24rem 0.55rem", fontSize: "0.73rem" }}
              onClick={() => setInsetFocus("moon")}
            >
              Moon &amp; Site
            </button>
          </div>
        )}
      </div>

      {webglSupported ? (
        <Suspense
          fallback={
            <MoonFallbackView
              compact
              label="Loading WebGL Sun-Earth-Moon orbital simulation..."
            />
          }
        >
          <SimulationOrreryCanvasClient {...props} insetFocus={insetFocus} />
        </Suspense>
      ) : (
        <SynchronizedOrbitalSvgFallback {...props} />
      )}
    </div>
  );
}
