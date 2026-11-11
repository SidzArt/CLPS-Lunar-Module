import { Html, Line, OrbitControls, Stars, useTexture } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { memo, Suspense, useEffect, useMemo, useState } from "react";
import * as THREE from "three";
import type { SimulationSampleOut, SimulationSeriesOut } from "../api/endpoints";
import { MoonFallbackView } from "./MoonFallbackView";
import {
  latLonToThreeVector,
  lerpDirectionUnit,
  spiceMoonMeToThree,
  topocentricAzElToThree,
} from "./coordinates";

export interface SimulationOrreryCanvasClientProps {
  series: SimulationSeriesOut;
  sampleIndex: number;
  interpolationAlpha?: number;
}

const EARTH_ORBIT_R = 3.1;
const SUN_ORBIT_R = 4.6;

function scaleVec(
  dir: readonly [number, number, number],
  dist: number,
): [number, number, number] {
  return [dir[0] * dist, dir[1] * dist, dir[2] * dist];
}

function TexturedMoonMesh() {
  const [albedoMap, bumpMap] = useTexture([
    "/assets/moon/moon_albedo_2k.webp",
    "/assets/moon/moon_bump_2k.webp",
  ]);
  useEffect(() => {
    albedoMap.colorSpace = THREE.SRGBColorSpace;
    albedoMap.anisotropy = 4;
    albedoMap.needsUpdate = true;
  }, [albedoMap]);
  return (
    <mesh>
      <sphereGeometry args={[1, 64, 64]} />
      <meshStandardMaterial
        map={albedoMap}
        bumpMap={bumpMap}
        bumpScale={0.015}
        roughness={0.92}
      />
    </mesh>
  );
}

const StaticOrreryEnvironment = memo(function StaticOrreryEnvironment({
  siteAnchor,
  siteName,
  horizonRingPoints,
  sunTracePoints,
  earthTracePoints,
}: {
  siteAnchor: [number, number, number];
  siteName: string;
  horizonRingPoints: [number, number, number][];
  sunTracePoints: [number, number, number][];
  earthTracePoints: [number, number, number][];
}) {
  return (
    <>
      <ambientLight intensity={0.45} />
      <Stars radius={55} depth={25} count={800} factor={2} fade speed={0} />

      {/* Central Moon */}
      <Suspense
        fallback={
          <mesh>
            <sphereGeometry args={[1, 32, 32]} />
            <meshStandardMaterial color="#464d59" />
          </mesh>
        }
      >
        <TexturedMoonMesh />
      </Suspense>

      {/* Landing Site Beacon */}
      <mesh position={siteAnchor}>
        <sphereGeometry args={[0.042, 16, 16]} />
        <meshStandardMaterial
          color="#f5b83d"
          emissive="#f5b83d"
          emissiveIntensity={1.6}
        />
      </mesh>
      <Html position={siteAnchor} distanceFactor={7} style={{ pointerEvents: "none" }}>
        <div
          style={{
            background: "rgba(9, 13, 21, 0.88)",
            border: "1px solid rgba(245, 184, 61, 0.7)",
            borderRadius: "6px",
            padding: "2px 6px",
            fontSize: "11px",
            color: "#edf2f7",
            whiteSpace: "nowrap",
            transform: "translate(8px, -10px)",
          }}
        >
          {siteName}
        </div>
      </Html>

      {/* LOLA DEM 360-deg Terrain Horizon Crown */}
      {horizonRingPoints.length >= 2 && (
        <Line
          points={horizonRingPoints}
          color="#f5b83d"
          lineWidth={1.6}
          transparent
          opacity={0.78}
        />
      )}

      {/* Orbital Trace Arcs */}
      {sunTracePoints.length >= 2 && (
        <Line
          points={sunTracePoints}
          color="#f5b83d"
          lineWidth={1.1}
          transparent
          opacity={0.35}
          dashed
          dashScale={6}
        />
      )}
      {earthTracePoints.length >= 2 && (
        <Line
          points={earthTracePoints}
          color="#5ad2e6"
          lineWidth={1.1}
          transparent
          opacity={0.38}
        />
      )}
    </>
  );
});

function OrreryScene({
  series,
  sampleIndex,
  interpolationAlpha = 0,
}: SimulationOrreryCanvasClientProps) {
  const samples = series.samples ?? [];
  const safeIndex = Math.min(Math.max(0, sampleIndex), Math.max(0, samples.length - 1));
  const current: SimulationSampleOut | undefined = samples[safeIndex];
  const next: SimulationSampleOut | undefined =
    samples[Math.min(safeIndex + 1, Math.max(0, samples.length - 1))];

  const siteAnchor = useMemo(
    () => latLonToThreeVector(series.site.latitude_deg, series.site.longitude_deg, 1.02),
    [series.site.latitude_deg, series.site.longitude_deg],
  );

  const sunDir = useMemo<[number, number, number]>(() => {
    if (!current || !next) {
      return [1, 0, 0];
    }
    const a = spiceMoonMeToThree(current.sun.dir_moon_me);
    const b = spiceMoonMeToThree(next.sun.dir_moon_me);
    return lerpDirectionUnit(a, b, interpolationAlpha);
  }, [current, next, interpolationAlpha]);

  const earthDir = useMemo<[number, number, number]>(() => {
    if (!current || !next) {
      return [0.95, 0.08, 0];
    }
    const a = spiceMoonMeToThree(current.earth.dir_moon_me);
    const b = spiceMoonMeToThree(next.earth.dir_moon_me);
    return lerpDirectionUnit(a, b, interpolationAlpha);
  }, [current, next, interpolationAlpha]);

  const sunPos = scaleVec(sunDir, SUN_ORBIT_R);
  const earthPos = scaleVec(earthDir, EARTH_ORBIT_R);

  const sunTracePoints = useMemo(() => {
    return samples.map((s) =>
      scaleVec(spiceMoonMeToThree(s.sun.dir_moon_me), SUN_ORBIT_R),
    );
  }, [samples]);

  const earthTracePoints = useMemo(() => {
    return samples.map((s) =>
      scaleVec(spiceMoonMeToThree(s.earth.dir_moon_me), EARTH_ORBIT_R),
    );
  }, [samples]);

  const horizonRingPoints = useMemo(() => {
    const profile = series.horizon_profile;
    if (!profile || profile.azimuths_deg.length === 0) {
      return [];
    }
    const pts: Array<[number, number, number]> = [];
    for (let i = 0; i < profile.azimuths_deg.length; i += 1) {
      const dir = topocentricAzElToThree(
        series.site.latitude_deg,
        series.site.longitude_deg,
        profile.azimuths_deg[i],
        profile.horizon_elevations_deg[i],
      );
      pts.push([
        siteAnchor[0] + dir[0] * 0.55,
        siteAnchor[1] + dir[1] * 0.55,
        siteAnchor[2] + dir[2] * 0.55,
      ]);
    }
    if (pts.length > 0) {
      pts.push(pts[0]);
    }
    return pts;
  }, [
    series.horizon_profile,
    series.site.latitude_deg,
    series.site.longitude_deg,
    siteAnchor,
  ]);

  return (
    <>
      <pointLight position={sunPos} intensity={28} decay={1.1} color="#fff3d6" />
      <StaticOrreryEnvironment
        siteAnchor={siteAnchor}
        siteName={series.site.site_name}
        horizonRingPoints={horizonRingPoints}
        sunTracePoints={sunTracePoints}
        earthTracePoints={earthTracePoints}
      />

      {/* Line-of-Sight Vector Rays from Site */}
      <Line
        points={[siteAnchor, sunPos]}
        color="#f5b83d"
        lineWidth={1.4}
        transparent
        opacity={0.72}
      />
      <Line
        points={[siteAnchor, earthPos]}
        color="#5ad2e6"
        lineWidth={1.4}
        transparent
        opacity={0.72}
      />

      {/* Sun Marker */}
      <group position={sunPos}>
        <mesh>
          <sphereGeometry args={[0.24, 24, 24]} />
          <meshBasicMaterial color="#f5b83d" />
        </mesh>
        <Html distanceFactor={8} style={{ pointerEvents: "none" }}>
          <div
            style={{
              background: "rgba(9, 13, 21, 0.85)",
              border: "1px solid rgba(245, 184, 61, 0.75)",
              borderRadius: "6px",
              padding: "2px 6px",
              fontSize: "11px",
              color: "#f5b83d",
              whiteSpace: "nowrap",
              transform: "translate(10px, -10px)",
            }}
          >
            Sun
          </div>
        </Html>
      </group>

      {/* Earth Marker */}
      <group position={earthPos}>
        <mesh>
          <sphereGeometry args={[0.17, 24, 24]} />
          <meshStandardMaterial
            color="#3d8fd6"
            emissive="#1b4d89"
            emissiveIntensity={0.4}
            roughness={0.65}
          />
        </mesh>
        <Html distanceFactor={8} style={{ pointerEvents: "none" }}>
          <div
            style={{
              background: "rgba(9, 13, 21, 0.85)",
              border: "1px solid rgba(90, 210, 230, 0.75)",
              borderRadius: "6px",
              padding: "2px 6px",
              fontSize: "11px",
              color: "#5ad2e6",
              whiteSpace: "nowrap",
              transform: "translate(10px, -10px)",
            }}
          >
            Earth
          </div>
        </Html>
      </group>

      <OrbitControls
        enablePan={false}
        enableDamping
        dampingFactor={0.07}
        minDistance={2.2}
        maxDistance={12}
      />
    </>
  );
}

export default function SimulationOrreryCanvasClient(
  props: SimulationOrreryCanvasClientProps,
) {
  const [canvasEl, setCanvasEl] = useState<HTMLCanvasElement | null>(null);
  const [contextLost, setContextLost] = useState(false);

  useEffect(() => {
    if (!canvasEl) return;
    function onLost(event: Event) {
      event.preventDefault();
      setContextLost(true);
    }
    function onRestored() {
      setContextLost(false);
    }
    canvasEl.addEventListener("webglcontextlost", onLost);
    canvasEl.addEventListener("webglcontextrestored", onRestored);
    return () => {
      canvasEl.removeEventListener("webglcontextlost", onLost);
      canvasEl.removeEventListener("webglcontextrestored", onRestored);
    };
  }, [canvasEl]);

  if (contextLost) {
    return (
      <MoonFallbackView
        compact
        label="Schematic orbital fallback (WebGL context unavailable)"
      />
    );
  }

  return (
    <Canvas
      dpr={[1, 2]}
      camera={{ position: [4.2, 3.1, 4.4], fov: 44, near: 0.1, far: 150 }}
      gl={{ antialias: true, powerPreference: "high-performance" }}
      style={{ width: "100%", height: "100%", minHeight: "400px" }}
      aria-label="3D topocentric Sun-Earth-Moon simulation visualization"
      onCreated={({ gl }) => setCanvasEl(gl.domElement)}
    >
      <OrreryScene {...props} />
    </Canvas>
  );
}

