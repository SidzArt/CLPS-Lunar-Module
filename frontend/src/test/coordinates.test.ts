import * as THREE from "three";
import { describe, expect, it } from "vitest";
import {
  latLonToThreeVector,
  lerpDirectionUnit,
  spiceMoonMeToThree,
  topocentricAzElToThree,
} from "../three/coordinates";

function getSphereVertexAtUv(u: number, v: number, radius = 1): [number, number, number] {
  const geom = new THREE.SphereGeometry(radius, 32, 32);
  const uv = geom.attributes.uv;
  const pos = geom.attributes.position;
  let bestIdx = 0;
  let bestDist = Infinity;
  for (let i = 0; i < uv.count; i += 1) {
    const du = uv.getX(i) - u;
    const dv = uv.getY(i) - v;
    const d = du * du + dv * dv;
    if (d < bestDist) {
      bestDist = d;
      bestIdx = i;
    }
  }
  const res: [number, number, number] = [
    pos.getX(bestIdx),
    pos.getY(bestIdx),
    pos.getZ(bestIdx),
  ];
  geom.dispose();
  return res;
}

describe("Lunar 3D coordinate & UV transforms", () => {
  it("matches Three.js SphereGeometry equirectangular UV alignment at cardinal meridians and poles", () => {
    // Equator prime meridian (lon 0° -> u=0.5, v=0.5)
    const primeVec = latLonToThreeVector(0, 0, 1);
    const spherePrime = getSphereVertexAtUv(0.5, 0.5, 1);
    expect(primeVec[0]).toBeCloseTo(spherePrime[0], 3);
    expect(primeVec[1]).toBeCloseTo(spherePrime[1], 2);
    expect(primeVec[2]).toBeCloseTo(spherePrime[2], 3);
    expect(primeVec[0]).toBeCloseTo(1, 5);

    // +90° East (u=0.75, v=0.5) -> Three -Z
    const east90 = latLonToThreeVector(0, 90, 1);
    const sphereEast = getSphereVertexAtUv(0.75, 0.5, 1);
    expect(east90[0]).toBeCloseTo(sphereEast[0], 3);
    expect(east90[2]).toBeCloseTo(sphereEast[2], 3);
    expect(east90[2]).toBeCloseTo(-1, 5);

    // -90° West (u=0.25, v=0.5) -> Three +Z
    const west90 = latLonToThreeVector(0, -90, 1);
    const sphereWest = getSphereVertexAtUv(0.25, 0.5, 1);
    expect(west90[0]).toBeCloseTo(sphereWest[0], 3);
    expect(west90[2]).toBeCloseTo(sphereWest[2], 3);
    expect(west90[2]).toBeCloseTo(1, 5);

    // Poles
    const north = latLonToThreeVector(90, 0, 1);
    expect(north[1]).toBeCloseTo(1, 5);
    const south = latLonToThreeVector(-90, 31.6, 1);
    expect(south[1]).toBeCloseTo(-1, 5);
  });

  it("maps SPICE MOON_ME vectors with unit length and consistent handedness", () => {
    const me = [0.6, 0.3, 0.7416198487] as const;
    const t = spiceMoonMeToThree(me);
    expect(t).toEqual([0.6, 0.7416198487, -0.3]);
    expect(Math.hypot(t[0], t[1], t[2])).toBeCloseTo(1, 5);
  });

  it("computes local topocentric horizon vectors aligned with East, North, Zenith", () => {
    const zenith = topocentricAzElToThree(0, 0, 0, 90);
    expect(zenith[0]).toBeCloseTo(1, 5);
    expect(Math.abs(zenith[1])).toBeLessThan(1e-5);

    const northHorizon = topocentricAzElToThree(0, 0, 0, 0);
    expect(northHorizon[1]).toBeCloseTo(1, 5);

    const eastHorizon = topocentricAzElToThree(0, 0, 90, 0);
    expect(eastHorizon[2]).toBeCloseTo(-1, 5);
  });

  it("interpolates and normalizes unit direction vectors cleanly", () => {
    const mid = lerpDirectionUnit([1, 0, 0], [0, 1, 0], 0.5);
    expect(mid[0]).toBeCloseTo(Math.SQRT1_2, 5);
    expect(mid[1]).toBeCloseTo(Math.SQRT1_2, 5);
    expect(Math.hypot(mid[0], mid[1], mid[2])).toBeCloseTo(1, 5);
  });
});

