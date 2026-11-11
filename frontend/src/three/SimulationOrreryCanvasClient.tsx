import { Line, OrbitControls, Stars, useTexture } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { memo, Suspense, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import type { OrbitalTrajectoryOut, SimulationSeriesOut } from "../api/endpoints";
import { MoonFallbackView } from "./MoonFallbackView";
import { latLonToThreeVector } from "./coordinates";
import {
  AU_KM,
  eclipJ2000ToThree,
  INSET_KM_TO_UNITS,
  INSET_MOON_ORBIT_UNITS,
  INSET_VS_OVERVIEW_MAGNIFICATION,
  interpolateOrbitalState,
  OVERVIEW_AU_UNITS,
  OVERVIEW_KM_TO_UNITS,
  OVERVIEW_MOON_OFFSET_MAGNIFICATION,
  type InterpolatedOrbitalState,
} from "./simulationOrbitMath";

export interface SimulationOrreryCanvasClientProps {
  series: SimulationSeriesOut;
  trajectory?: OrbitalTrajectoryOut | null;
  sampleIndex: number;
  elapsedSeconds?: number;
  isPlaying?: boolean;
  insetFocus?: "earth" | "moon";
  activeTimestampUtc?: string;
}

const SUN_MARKER_R = 0.72;
const OVERVIEW_EARTH_R = 0.34;
const OVERVIEW_MOON_R = 0.14;
const INSET_EARTH_R = 0.72;
const INSET_MOON_R = 0.52;

const Y_UP = new THREE.Vector3(0, 1, 0);

function createLabelTexture(
  text: string,
  color: string,
  borderColor: string,
): { texture: THREE.CanvasTexture; aspect: number } {
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  const font = '600 24px ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
  let textWidth = text.length * 14;
  if (ctx) {
    ctx.font = font;
    textWidth = ctx.measureText(text).width;
  }
  const padX = 20;
  const w = Math.max(72, Math.ceil(textWidth + padX * 2));
  const h = 44;
  canvas.width = w;
  canvas.height = h;
  if (ctx) {
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = "rgba(9, 13, 21, 0.92)";
    ctx.strokeStyle = borderColor;
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    if (typeof ctx.roundRect === "function") {
      ctx.roundRect(2, 2, w - 4, h - 4, 10);
    } else {
      ctx.rect(2, 2, w - 4, h - 4);
    }
    ctx.fill();
    ctx.stroke();
    ctx.font = font;
    ctx.fillStyle = color;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(text, w / 2, h / 2 + 1);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.minFilter = THREE.LinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.needsUpdate = true;
  return { texture, aspect: w / h };
}

function SpriteLabel({
  text,
  position = [0, 0, 0],
  color = "#edf2f7",
  borderColor = "rgba(90, 210, 230, 0.78)",
  height = 0.55,
}: {
  text: string;
  position?: readonly [number, number, number];
  color?: string;
  borderColor?: string;
  height?: number;
}) {
  const { texture, aspect } = useMemo(
    () => createLabelTexture(text, color, borderColor),
    [text, color, borderColor],
  );
  useEffect(() => () => texture.dispose(), [texture]);

  return (
    <sprite
      position={[position[0], position[1], position[2]]}
      scale={[height * aspect, height, 1]}
      renderOrder={10}
    >
      <spriteMaterial map={texture} transparent depthTest={false} depthWrite={false} />
    </sprite>
  );
}

function TexturedMoonMesh({ radius }: { radius: number }) {
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
      <sphereGeometry args={[radius, 48, 48]} />
      <meshStandardMaterial
        map={albedoMap}
        bumpMap={bumpMap}
        bumpScale={0.012}
        roughness={0.92}
      />
    </mesh>
  );
}

function DirectionArrow({
  origin,
  dir,
  length,
  color,
  coneRadius = 0.08,
  coneHeight = 0.22,
}: {
  origin: readonly [number, number, number];
  dir: readonly [number, number, number];
  length: number;
  color: string;
  coneRadius?: number;
  coneHeight?: number;
}) {
  const tip: [number, number, number] = [
    origin[0] + dir[0] * length,
    origin[1] + dir[1] * length,
    origin[2] + dir[2] * length,
  ];
  const quat = useMemo(() => {
    const v = new THREE.Vector3(dir[0], dir[1], dir[2]);
    if (v.lengthSq() < 1e-12) {
      return new THREE.Quaternion();
    }
    return new THREE.Quaternion().setFromUnitVectors(Y_UP, v.normalize());
  }, [dir]);

  return (
    <group>
      <Line points={[origin, tip]} color={color} lineWidth={1.8} transparent opacity={0.92} />
      <mesh position={tip} quaternion={quat}>
        <coneGeometry args={[coneRadius, coneHeight, 12]} />
        <meshBasicMaterial color={color} />
      </mesh>
    </group>
  );
}

const EclipticRing = memo(function EclipticRing({
  radius,
  color,
  opacity = 0.2,
}: {
  radius: number;
  color: string;
  opacity?: number;
}) {
  const pts = useMemo(() => {
    const arr: [number, number, number][] = [];
    const segs = 96;
    for (let i = 0; i <= segs; i += 1) {
      const a = (i / segs) * Math.PI * 2;
      arr.push([Math.cos(a) * radius, 0, -Math.sin(a) * radius]);
    }
    return arr;
  }, [radius]);
  return (
    <Line
      points={pts}
      color={color}
      lineWidth={1}
      transparent
      opacity={opacity}
      dashed
      dashScale={4}
    />
  );
});

function HeliocentricOverviewScene({
  trajectory,
  orbital,
}: {
  trajectory: OrbitalTrajectoryOut;
  orbital: InterpolatedOrbitalState;
}) {
  const { earthTracePoints, combinedMoonTracePoints, movingMoonRingPoints } = useMemo(() => {
    const samples = trajectory.samples;
    const earthPts: [number, number, number][] = [];
    const moonCombinedPts: [number, number, number][] = [];

    const stride = Math.max(1, Math.floor(samples.length / 720));
    for (let i = 0; i < samples.length; i += stride) {
      const s = samples[i];
      const ep = eclipJ2000ToThree(s.earth_wrt_sun_eclipj2000_km, OVERVIEW_KM_TO_UNITS);
      const mpOff = eclipJ2000ToThree(
        s.moon_wrt_earth_eclipj2000_km,
        OVERVIEW_KM_TO_UNITS * OVERVIEW_MOON_OFFSET_MAGNIFICATION,
      );
      earthPts.push(ep);
      moonCombinedPts.push([ep[0] + mpOff[0], ep[1] + mpOff[1], ep[2] + mpOff[2]]);
    }
    if (samples.length > 0) {
      const last = samples[samples.length - 1];
      const ep = eclipJ2000ToThree(last.earth_wrt_sun_eclipj2000_km, OVERVIEW_KM_TO_UNITS);
      const mpOff = eclipJ2000ToThree(
        last.moon_wrt_earth_eclipj2000_km,
        OVERVIEW_KM_TO_UNITS * OVERVIEW_MOON_OFFSET_MAGNIFICATION,
      );
      earthPts.push(ep);
      moonCombinedPts.push([ep[0] + mpOff[0], ep[1] + mpOff[1], ep[2] + mpOff[2]]);
    }

    // Visual reference radius for the magnified Moon ring centered on Earth's current position
    const ringPts: [number, number, number][] = [];
    const rVis = Math.hypot(
      orbital.overviewMoonPos[0] - orbital.overviewEarthPos[0],
      orbital.overviewMoonPos[1] - orbital.overviewEarthPos[1],
      orbital.overviewMoonPos[2] - orbital.overviewEarthPos[2],
    );
    const segs = 48;
    for (let k = 0; k <= segs; k += 1) {
      const a = (k / segs) * Math.PI * 2;
      ringPts.push([
        orbital.overviewEarthPos[0] + Math.cos(a) * rVis,
        orbital.overviewEarthPos[1],
        orbital.overviewEarthPos[2] - Math.sin(a) * rVis,
      ]);
    }

    return {
      earthTracePoints: earthPts,
      combinedMoonTracePoints: moonCombinedPts,
      movingMoonRingPoints: ringPts,
    };
  }, [trajectory.samples, orbital.overviewEarthPos, orbital.overviewMoonPos]);

  return (
    <>
      <ambientLight intensity={0.42} />
      <pointLight position={[0, 0, 0]} intensity={180} decay={0.5} color="#fff1cc" />
      <Stars radius={90} depth={30} count={900} factor={2} fade speed={0} />

      {/* Sun at focus [0, 0, 0] */}
      <group position={[0, 0, 0]}>
        <mesh>
          <sphereGeometry args={[SUN_MARKER_R, 32, 32]} />
          <meshBasicMaterial color="#f5b83d" />
        </mesh>
        <mesh>
          <sphereGeometry args={[SUN_MARKER_R * 1.35, 24, 24]} />
          <meshBasicMaterial color="#f5b83d" transparent opacity={0.14} />
        </mesh>
        <SpriteLabel
          text="Sun (Focus)"
          position={[0, 1.15, 0]}
          color="#f5b83d"
          borderColor="rgba(245, 184, 61, 0.78)"
          height={0.78}
        />
      </group>

      {/* Subtle 1 AU ecliptic reference circle */}
      <EclipticRing radius={OVERVIEW_AU_UNITS} color="#7c899e" opacity={0.16} />

      {/* Sampled SPICE Earth elliptical orbit around Sun */}
      {earthTracePoints.length >= 2 && (
        <Line points={earthTracePoints} color="#5ad2e6" lineWidth={1.6} transparent opacity={0.78} />
      )}

      {/* Sampled combined SPICE Moon path: Earth_Sun + Moon_Earth (magnified offset) */}
      {combinedMoonTracePoints.length >= 2 && (
        <Line
          points={combinedMoonTracePoints}
          color="#cbd5e1"
          lineWidth={1.15}
          transparent
          opacity={0.58}
        />
      )}

      {/* Instantaneous Sun -> Earth radius vector & moving local Moon ring around Earth */}
      <Line
        points={[[0, 0, 0], orbital.overviewEarthPos]}
        color="#f5b83d"
        lineWidth={1}
        transparent
        opacity={0.38}
        dashed
        dashScale={4}
      />
      <Line points={movingMoonRingPoints} color="#94a3b8" lineWidth={1} transparent opacity={0.35} />
      <Line
        points={[orbital.overviewEarthPos, orbital.overviewMoonPos]}
        color="#5ad2e6"
        lineWidth={1.3}
        transparent
        opacity={0.75}
      />

      {/* Earth at live SPICE position */}
      <group position={orbital.overviewEarthPos}>
        <mesh>
          <sphereGeometry args={[OVERVIEW_EARTH_R, 28, 28]} />
          <meshStandardMaterial
            color="#3d8fd6"
            emissive="#1a4576"
            emissiveIntensity={0.45}
            roughness={0.6}
          />
        </mesh>
        <SpriteLabel
          text="Earth"
          position={[0, 0.75, 0]}
          color="#5ad2e6"
          borderColor="rgba(90, 210, 230, 0.8)"
          height={0.68}
        />
      </group>

      {/* Earth orbital direction arrow */}
      <DirectionArrow
        origin={orbital.overviewEarthPos}
        dir={orbital.overviewEarthTangentDir}
        length={1.35}
        color="#5ad2e6"
        coneRadius={0.11}
        coneHeight={0.28}
      />

      {/* Moon at live connected SPICE position (Earth_Sun + Moon_Earth) */}
      <group position={orbital.overviewMoonPos} quaternion={orbital.moonQuaternion}>
        <mesh>
          <sphereGeometry args={[OVERVIEW_MOON_R, 20, 20]} />
          <meshStandardMaterial color="#e2e8f0" emissive="#475569" emissiveIntensity={0.3} />
        </mesh>
        <SpriteLabel
          text="Moon"
          position={[0, 0.46, 0]}
          color="#e2e8f0"
          borderColor="rgba(226, 232, 240, 0.75)"
          height={0.56}
        />
      </group>

      {/* Moon combined motion direction arrow */}
      <DirectionArrow
        origin={orbital.overviewMoonPos}
        dir={orbital.overviewMoonTangentDir}
        length={0.78}
        color="#f8fafc"
        coneRadius={0.07}
        coneHeight={0.18}
      />

      <OrbitControls
        enablePan
        enableDamping
        dampingFactor={0.07}
        minDistance={3.5}
        maxDistance={36}
      />
    </>
  );
}

function InsetControlsTracker({
  targetPos,
}: {
  targetPos: readonly [number, number, number];
}) {
  const controlsRef = useRef<OrbitControlsImpl | null>(null);
  const desired = useMemo(
    () => new THREE.Vector3(targetPos[0], targetPos[1], targetPos[2]),
    [targetPos],
  );

  useFrame(() => {
    if (controlsRef.current) {
      controlsRef.current.target.lerp(desired, 0.2);
      controlsRef.current.update();
    }
  });

  return (
    <OrbitControls
      ref={controlsRef}
      enablePan
      enableDamping
      dampingFactor={0.07}
      minDistance={1.4}
      maxDistance={16}
    />
  );
}

function EarthMoonInsetScene({
  trajectory,
  series,
  orbital,
  insetFocus,
}: {
  trajectory: OrbitalTrajectoryOut;
  series: SimulationSeriesOut;
  orbital: InterpolatedOrbitalState;
  insetFocus: "earth" | "moon";
}) {
  const insetMoonTracePoints = useMemo(() => {
    const samples = trajectory.samples;
    const pts: [number, number, number][] = [];
    const stride = Math.max(1, Math.floor(samples.length / 720));
    for (let i = 0; i < samples.length; i += stride) {
      pts.push(eclipJ2000ToThree(samples[i].moon_wrt_earth_eclipj2000_km, INSET_KM_TO_UNITS));
    }
    if (samples.length > 0) {
      pts.push(
        eclipJ2000ToThree(
          samples[samples.length - 1].moon_wrt_earth_eclipj2000_km,
          INSET_KM_TO_UNITS,
        ),
      );
    }
    return pts;
  }, [trajectory.samples]);

  const siteAnchorLocal = useMemo(
    () =>
      latLonToThreeVector(
        series.site.latitude_deg,
        series.site.longitude_deg,
        INSET_MOON_R * 1.03,
      ),
    [series.site.latitude_deg, series.site.longitude_deg],
  );

  const sunLightPos: [number, number, number] = [
    orbital.insetSunDirectionUnit[0] * 18,
    orbital.insetSunDirectionUnit[1] * 18,
    orbital.insetSunDirectionUnit[2] * 18,
  ];
  const sunIndicatorOrigin: [number, number, number] = [
    orbital.insetSunDirectionUnit[0] * 3.6,
    orbital.insetSunDirectionUnit[1] * 3.6,
    orbital.insetSunDirectionUnit[2] * 3.6,
  ];
  const towardMoonFromSunDir: [number, number, number] = [
    -orbital.insetSunDirectionUnit[0],
    -orbital.insetSunDirectionUnit[1],
    -orbital.insetSunDirectionUnit[2],
  ];

  const eclipticProjection: [number, number, number] = [
    orbital.insetMoonPos[0],
    0,
    orbital.insetMoonPos[2],
  ];

  const focusTarget: [number, number, number] =
    insetFocus === "moon" ? orbital.insetMoonPos : [0, 0, 0];

  return (
    <>
      <ambientLight intensity={0.28} />
      <directionalLight position={sunLightPos} intensity={2.7} color="#fff3d6" />
      <Stars radius={55} depth={20} count={650} factor={2} fade speed={0} />

      {/* Local Earth at [0, 0, 0] */}
      <group position={[0, 0, 0]}>
        <mesh>
          <sphereGeometry args={[INSET_EARTH_R, 36, 36]} />
          <meshStandardMaterial
            color="#3d8fd6"
            emissive="#12345e"
            emissiveIntensity={0.42}
            roughness={0.62}
          />
        </mesh>
        <SpriteLabel
          text="Earth (Local Origin)"
          position={[0, 1.05, 0]}
          color="#5ad2e6"
          borderColor="rgba(90, 210, 230, 0.8)"
          height={0.44}
        />
      </group>

      {/* Ecliptic reference plane (Y = 0) */}
      <EclipticRing radius={INSET_MOON_ORBIT_UNITS} color="#7c899e" opacity={0.25} />

      {/* Sampled 3D SPICE Moon orbit around Earth showing 5.145-deg inclination */}
      {insetMoonTracePoints.length >= 2 && (
        <Line points={insetMoonTracePoints} color="#5ad2e6" lineWidth={1.6} transparent opacity={0.78} />
      )}

      {/* Vertical height indicator above/below ecliptic plane + Earth->Moon vector */}
      <Line
        points={[[0, 0, 0], orbital.insetMoonPos]}
        color="#5ad2e6"
        lineWidth={1.25}
        transparent
        opacity={0.72}
      />
      <Line
        points={[eclipticProjection, orbital.insetMoonPos]}
        color="#f5b83d"
        lineWidth={1.1}
        transparent
        opacity={0.55}
        dashed
        dashScale={5}
      />

      {/* Sunlight direction vector from true instantaneous SPICE Sun direction */}
      <DirectionArrow
        origin={sunIndicatorOrigin}
        dir={towardMoonFromSunDir}
        length={0.95}
        color="#f5b83d"
        coneRadius={0.09}
        coneHeight={0.22}
      />
      <SpriteLabel
        text="Sun Rays"
        position={[
          sunIndicatorOrigin[0],
          sunIndicatorOrigin[1] + 0.36,
          sunIndicatorOrigin[2],
        ]}
        color="#f5b83d"
        borderColor="rgba(245, 184, 61, 0.7)"
        height={0.35}
      />

      {/* Moon oriented strictly by SPICE MOON_ME -> ECLIPJ2000 rotation matrix */}
      <group position={orbital.insetMoonPos} quaternion={orbital.moonQuaternion}>
        <Suspense
          fallback={
            <mesh>
              <sphereGeometry args={[INSET_MOON_R, 28, 28]} />
              <meshStandardMaterial color="#8c96a6" roughness={0.9} />
            </mesh>
          }
        >
          <TexturedMoonMesh radius={INSET_MOON_R} />
        </Suspense>

        {/* Sub-Earth Prime Meridian (+X_ME = 0° lon) demonstrating tidal locking */}
        <Line
          points={[
            [INSET_MOON_R, 0, 0],
            [INSET_MOON_R * 1.45, 0, 0],
          ]}
          color="#a7f3d0"
          lineWidth={1.5}
          transparent
          opacity={0.8}
        />

        {/* Selected landing-site marker fixed on the lunar surface */}
        <mesh position={siteAnchorLocal}>
          <sphereGeometry args={[0.048, 16, 16]} />
          <meshStandardMaterial
            color="#f5b83d"
            emissive="#f5b83d"
            emissiveIntensity={1.65}
          />
        </mesh>
        <SpriteLabel
          text={series.site.site_name}
          position={[
            siteAnchorLocal[0] * 1.4,
            siteAnchorLocal[1] * 1.4 + 0.25,
            siteAnchorLocal[2] * 1.4,
          ]}
          color="#edf2f7"
          borderColor="rgba(245, 184, 61, 0.82)"
          height={0.34}
        />
      </group>

      {/* Moon orbital direction arrow in Earth-centered frame */}
      <DirectionArrow
        origin={orbital.insetMoonPos}
        dir={orbital.insetMoonTangentDir}
        length={0.92}
        color="#f8fafc"
        coneRadius={0.08}
        coneHeight={0.2}
      />

      <InsetControlsTracker targetPos={focusTarget} />
    </>
  );
}

export default function SimulationOrreryCanvasClient({
  series,
  trajectory,
  elapsedSeconds = 0,
  insetFocus = "earth",
  activeTimestampUtc,
}: SimulationOrreryCanvasClientProps) {
  const [overviewCanvasEl, setOverviewCanvasEl] = useState<HTMLCanvasElement | null>(null);
  const [insetCanvasEl, setInsetCanvasEl] = useState<HTMLCanvasElement | null>(null);
  const [contextLost, setContextLost] = useState(false);

  useEffect(() => {
    const els = [overviewCanvasEl, insetCanvasEl].filter(Boolean) as HTMLCanvasElement[];
    if (els.length === 0) return;
    function onLost(event: Event) {
      event.preventDefault();
      setContextLost(true);
    }
    function onRestored() {
      setContextLost(false);
    }
    for (const el of els) {
      el.addEventListener("webglcontextlost", onLost);
      el.addEventListener("webglcontextrestored", onRestored);
    }
    return () => {
      for (const el of els) {
        el.removeEventListener("webglcontextlost", onLost);
        el.removeEventListener("webglcontextrestored", onRestored);
      }
    };
  }, [overviewCanvasEl, insetCanvasEl]);

  const orbital = useMemo(() => {
    if (!trajectory || !trajectory.samples || trajectory.samples.length === 0) {
      return null;
    }
    return interpolateOrbitalState(trajectory, elapsedSeconds);
  }, [trajectory, elapsedSeconds]);

  if (contextLost) {
    return (
      <MoonFallbackView
        compact
        label="Orbital WebGL context unavailable; scientific telemetry preserved below."
      />
    );
  }

  if (!trajectory || !orbital) {
    return (
      <div className="sim-canvas-stage" style={{ display: "grid", placeItems: "center", padding: "1.5rem" }}>
        <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "0.86rem" }}>
          Loading DE440 ECLIPJ2000 3-body Sun-Earth-Moon orbital trajectory from SPICE...
        </p>
      </div>
    );
  }

  return (
    <div className="sim-dual-viewport-grid">
      {/* Main Overview: Sun -> Earth -> Moon */}
      <div className="sim-viewport-pane">
        <div className="sim-viewport-header">
          <span className="sim-viewport-title">
            Main Overview: Sun -&gt; Earth -&gt; Moon (ECLIPJ2000)
          </span>
          <span className="sim-viewport-mag mono">
            NOT TO SCALE · Moon offset {OVERVIEW_MOON_OFFSET_MAGNIFICATION}x
          </span>
        </div>
        <div className="sim-canvas-stage">
          <Canvas
            dpr={[1, 1.75]}
            camera={{ position: [0, 18.8, 17.5], fov: 44, near: 0.1, far: 220 }}
            gl={{ antialias: true, powerPreference: "high-performance" }}
            style={{ width: "100%", height: "100%" }}
            aria-label="3D heliocentric Sun Earth Moon orbital simulation overview"
            onCreated={({ gl }) => setOverviewCanvasEl(gl.domElement)}
          >
            <HeliocentricOverviewScene trajectory={trajectory} orbital={orbital} />
          </Canvas>
        </div>
        <div className="sim-viewport-footer mono">
          <span>
            Earth-Sun: {(orbital.earthSunDistanceKm / 1_000_000).toFixed(3)}M km (
            {(orbital.earthSunDistanceKm / AU_KM).toFixed(4)} AU)
          </span>
          <span>UTC: {(activeTimestampUtc || orbital.timestampUtc).replace("T", " ").replace("Z", " UTC")}</span>
        </div>
      </div>

      {/* Synchronized Magnified Earth-Moon View */}
      <div className="sim-viewport-pane">
        <div className="sim-viewport-header">
          <span className="sim-viewport-title">
            Magnified Earth-Moon System (3D Inclination &amp; Tidal Lock)
          </span>
          <span className="sim-viewport-mag mono">
            NOT TO SCALE · Distance {INSET_VS_OVERVIEW_MAGNIFICATION}x vs Overview
          </span>
        </div>
        <div className="sim-canvas-stage">
          <Canvas
            dpr={[1, 1.75]}
            camera={{ position: [5.4, 3.1, 5.4], fov: 44, near: 0.1, far: 120 }}
            gl={{ antialias: true, powerPreference: "high-performance" }}
            style={{ width: "100%", height: "100%" }}
            aria-label="3D magnified Earth-Moon inclined orbital system and tidal-locked landing site"
            onCreated={({ gl }) => setInsetCanvasEl(gl.domElement)}
          >
            <EarthMoonInsetScene
              trajectory={trajectory}
              series={series}
              orbital={orbital}
              insetFocus={insetFocus}
            />
          </Canvas>
        </div>
        <div className="sim-viewport-footer mono">
          <span>
            Earth-Moon: {Math.round(orbital.moonEarthDistanceKm).toLocaleString()} km
          </span>
          <span>
            Ecliptic Lat: {orbital.moonWrtEarthElevationDeg >= 0 ? "+" : ""}
            {orbital.moonWrtEarthElevationDeg.toFixed(2)} deg
          </span>
        </div>
      </div>
    </div>
  );
}
