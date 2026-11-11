import { Html, OrbitControls, Stars, useTexture } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import type { SiteCardOut } from "../api/endpoints";
import { formatLatLon } from "../utils/formatting";
import { latLonToThreeVector } from "./coordinates";
import { MoonFallbackView } from "./MoonFallbackView";

export type LunarGlobeMode = "intro" | "browser" | "ambient" | "site-focus";

export interface LunarMoonCanvasClientProps {
  mode: LunarGlobeMode;
  sites: SiteCardOut[];
  selectedSiteSlug?: string | null;
  onSelectSite?: (site: SiteCardOut) => void;
  focusLatDeg?: number;
  focusLonDeg?: number;
  scrollProgress?: number;
  scrollProgressRef?: { current: number };
  reducedMotion?: boolean;
  rotationPaused?: boolean;
  resetTrigger?: number;
}

function LunarSphereMesh({
  sites,
  mode,
  selectedSiteSlug,
  onSelectSite,
  showPins,
  scrollProgress = 0,
  scrollProgressRef,
  reducedMotion = false,
  rotationPaused = false,
}: {
  sites: SiteCardOut[];
  mode: LunarGlobeMode;
  selectedSiteSlug?: string | null;
  onSelectSite?: (site: SiteCardOut) => void;
  showPins: boolean;
  scrollProgress?: number;
  scrollProgressRef?: { current: number };
  reducedMotion?: boolean;
  rotationPaused?: boolean;
}) {
  const groupRef = useRef<THREE.Group>(null);
  const [hoveredSlug, setHoveredSlug] = useState<string | null>(null);
  const [albedoMap, bumpMap] = useTexture([
    "/assets/moon/moon_albedo_2k.webp",
    "/assets/moon/moon_bump_2k.webp",
  ]);

  useEffect(() => {
    albedoMap.colorSpace = THREE.SRGBColorSpace;
    albedoMap.anisotropy = 4;
    albedoMap.needsUpdate = true;
  }, [albedoMap]);

  useEffect(
    () => () => {
      document.body.style.cursor = "default";
    },
    [],
  );

  useFrame((_state, delta) => {
    const grp = groupRef.current;
    if (!grp) {
      return;
    }
    if (mode === "intro") {
      // Base Near Side facing camera at +X (+0 rad), plus ~1.5 revolutions over full page scroll
      const baseAngle = -0.35;
      const activeScroll = scrollProgressRef ? scrollProgressRef.current : scrollProgress;
      const targetRot = reducedMotion
        ? baseAngle
        : baseAngle + activeScroll * Math.PI * 3.0;
      grp.rotation.y += (targetRot - grp.rotation.y) * Math.min(1, delta * 8);
      return;
    }

    if (mode === "ambient" && !reducedMotion && !rotationPaused) {
      grp.rotation.y += delta * 0.045;
      return;
    }

    if (mode === "browser" && !reducedMotion && !rotationPaused && !selectedSiteSlug) {
      grp.rotation.y += delta * 0.025;
    }
  });

  const pinEntries = useMemo(() => {
    return sites.map((site) => ({
      site,
      position: latLonToThreeVector(site.latitude_deg, site.longitude_deg, 1.018),
    }));
  }, [sites]);

  return (
    <group ref={groupRef}>
      <mesh receiveShadow castShadow>
        <sphereGeometry args={[1, 64, 64]} />
        <meshStandardMaterial
          map={albedoMap}
          bumpMap={bumpMap}
          bumpScale={0.018}
          roughness={0.94}
          metalness={0.04}
        />
      </mesh>

      {showPins &&
        pinEntries.map(({ site, position }) => {
          const isSelected = selectedSiteSlug === site.site_slug;
          const isHovered = hoveredSlug === site.site_slug;
          return (
            <group key={site.site_slug} position={position}>
              <mesh
                onClick={(event) => {
                  if (mode === "browser" && onSelectSite) {
                    event.stopPropagation();
                    onSelectSite(site);
                  }
                }}
                onPointerOver={(event) => {
                  if (mode === "browser") {
                    event.stopPropagation();
                    setHoveredSlug(site.site_slug);
                    document.body.style.cursor = "pointer";
                  }
                }}
                onPointerOut={() => {
                  setHoveredSlug((prev) =>
                    prev === site.site_slug ? null : prev,
                  );
                  document.body.style.cursor = "default";
                }}
              >
                <sphereGeometry args={[isSelected ? 0.032 : 0.023, 16, 16]} />
                <meshStandardMaterial
                  color={isSelected ? "#5ad2e6" : "#f5b83d"}
                  emissive={isSelected ? "#5ad2e6" : "#f5b83d"}
                  emissiveIntensity={isSelected || isHovered ? 1.4 : 0.85}
                />
              </mesh>

              {(mode === "intro" || isSelected || isHovered) && (
                <Html
                  distanceFactor={5.2}
                  occlude
                  style={{ pointerEvents: "none" }}
                >
                  <div
                    style={{
                      background: "rgba(10, 14, 22, 0.86)",
                      border: `1px solid ${
                        isSelected
                          ? "rgba(90, 210, 230, 0.75)"
                          : "rgba(245, 184, 61, 0.65)"
                      }`,
                      color: "#edf2f7",
                      padding: "2px 7px",
                      borderRadius: "6px",
                      fontSize: "11px",
                      fontWeight: 600,
                      whiteSpace: "nowrap",
                      transform: "translate(8px, -12px)",
                      boxShadow: "0 4px 12px rgba(0, 0, 0, 0.55)",
                    }}
                  >
                    <span>{site.site_name}</span>
                    {isHovered && (
                      <span
                        style={{
                          display: "block",
                          fontSize: "10px",
                          color: "#a8b3c7",
                          fontWeight: 400,
                        }}
                      >
                        {formatLatLon(site.latitude_deg, site.longitude_deg)}
                      </span>
                    )}
                  </div>
                </Html>
              )}
            </group>
          );
        })}
    </group>
  );
}

function CameraController({
  mode,
  selectedSite,
  focusLatDeg,
  focusLonDeg,
  resetTrigger = 0,
}: {
  mode: LunarGlobeMode;
  selectedSite?: SiteCardOut;
  focusLatDeg?: number;
  focusLonDeg?: number;
  resetTrigger?: number;
}) {
  const { camera } = useThree();
  const targetCameraPos = useRef<THREE.Vector3 | null>(null);

  useEffect(() => {
    if (mode === "site-focus" && focusLatDeg !== undefined && focusLonDeg !== undefined) {
      const vec = latLonToThreeVector(focusLatDeg, focusLonDeg, 2.05);
      camera.position.set(vec[0], vec[1], vec[2]);
      camera.lookAt(0, 0, 0);
      targetCameraPos.current = null;
      return;
    }
    if (mode === "browser" && selectedSite) {
      const vec = latLonToThreeVector(
        selectedSite.latitude_deg,
        selectedSite.longitude_deg,
        2.35,
      );
      targetCameraPos.current = new THREE.Vector3(vec[0], vec[1], vec[2]);
      return;
    }
    if (mode === "browser" && resetTrigger > 0) {
      targetCameraPos.current = new THREE.Vector3(2.85, 0.35, 0.5);
    }
  }, [camera, mode, selectedSite, focusLatDeg, focusLonDeg, resetTrigger]);

  useFrame((_state, delta) => {
    if (!targetCameraPos.current) {
      return;
    }
    camera.position.lerp(targetCameraPos.current, Math.min(1, delta * 4.5));
    camera.lookAt(0, 0, 0);
    if (camera.position.distanceTo(targetCameraPos.current) < 0.03) {
      targetCameraPos.current = null;
    }
  });

  if (mode !== "browser") {
    return null;
  }

  return (
    <OrbitControls
      enablePan={false}
      enableDamping
      dampingFactor={0.07}
      minDistance={1.55}
      maxDistance={4.8}
    />
  );
}

export default function LunarMoonCanvasClient(props: LunarMoonCanvasClientProps) {
  const {
    mode,
    sites,
    selectedSiteSlug,
    onSelectSite,
    focusLatDeg,
    focusLonDeg,
    scrollProgress,
    scrollProgressRef,
    reducedMotion,
    rotationPaused,
    resetTrigger,
  } = props;

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

  const selectedSite = useMemo(
    () => sites.find((s) => s.site_slug === selectedSiteSlug),
    [sites, selectedSiteSlug],
  );

  if (contextLost) {
    return (
      <MoonFallbackView
        dimmed={mode === "ambient"}
        compact={mode === "site-focus"}
        label="WebGL context unavailable — showing fallback lunar surface preview."
      />
    );
  }

  const initialPos: [number, number, number] =
    mode === "site-focus" && focusLatDeg !== undefined && focusLonDeg !== undefined
      ? latLonToThreeVector(focusLatDeg, focusLonDeg, 2.25)
      : mode === "browser"
        ? [3.1, 0.35, 0.5]
        : [3.35, 0.15, 0.45];

  return (
    <Canvas
      dpr={[1, 2]}
      camera={{ position: initialPos, fov: 40, near: 0.1, far: 100 }}
      gl={{ antialias: true, powerPreference: "high-performance", alpha: true }}
      style={{ width: "100%", height: "100%", touchAction: mode === "browser" ? "none" : "auto" }}
      aria-label="Interactive 3D Lunar Globe showing CLPS landing sites"
      onCreated={({ gl }) => setCanvasEl(gl.domElement)}
    >
      <ambientLight intensity={0.42} />
      <directionalLight position={[4.5, 2.2, 3.5]} intensity={2.2} color="#fff8e8" />
      <directionalLight position={[-4, -2, -3]} intensity={0.28} color="#8ab4f8" />
      {mode !== "ambient" && (
        <Stars radius={45} depth={30} count={900} factor={2.1} fade speed={0} />
      )}

      <Suspense
        fallback={
          <mesh>
            <sphereGeometry args={[1, 32, 32]} />
            <meshStandardMaterial color="#3c434f" roughness={0.95} />
          </mesh>
        }
      >
        <LunarSphereMesh
          sites={sites}
          mode={mode}
          selectedSiteSlug={selectedSiteSlug}
          onSelectSite={onSelectSite}
          showPins={mode !== "ambient"}
          scrollProgress={scrollProgress}
          scrollProgressRef={scrollProgressRef}
          reducedMotion={reducedMotion}
          rotationPaused={rotationPaused}
        />
      </Suspense>

      <CameraController
        mode={mode}
        selectedSite={selectedSite}
        focusLatDeg={focusLatDeg}
        focusLonDeg={focusLonDeg}
        resetTrigger={resetTrigger}
      />
    </Canvas>
  );
}
