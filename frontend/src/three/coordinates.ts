function degToRad(deg: number): number {
  return (deg * Math.PI) / 180;
}

/**
 * Transform a Moon-fixed MOON_ME Cartesian vector [x, y, z] into Three.js world [X, Y, Z].
 * Mapping: +X_three = +X_me (0° prime meridian), +Y_three = +Z_me (North Pole),
 * +Z_three = -Y_me (+90°W / -90°E) to match Three.js SphereGeometry equirectangular UV
 * while maintaining a strictly right-handed (det = +1) orthogonal frame.
 */
export function spiceMoonMeToThree(
  vec: readonly [number, number, number],
  scale = 1,
): [number, number, number] {
  return [vec[0] * scale, vec[2] * scale, -vec[1] * scale];
}

/**
 * Convert planetocentric/selenographic latitude and east-positive longitude (MOON_ME)
 * into a Three.js point on a sphere of given radius matching SphereGeometry UV u=0.5 at lon=0°.
 */
export function latLonToThreeVector(
  latDeg: number,
  lonDeg: number,
  radius = 1,
): [number, number, number] {
  const lat = degToRad(latDeg);
  const lon = degToRad(lonDeg);
  const cosLat = Math.cos(lat);
  const x = radius * cosLat * Math.cos(lon);
  const y = radius * Math.sin(lat);
  const z = -radius * cosLat * Math.sin(lon);
  return [x, y, z];
}

/**
 * Compute normalized East and North tangent basis vectors (in Three.js coordinates)
 * at a lunar landing site (latDeg, lonDeg).
 */
function localEnuBasisThree(latDeg: number, lonDeg: number): {
  east: [number, number, number];
  north: [number, number, number];
  up: [number, number, number];
} {
  const lat = degToRad(latDeg);
  const lon = degToRad(lonDeg);
  const sinLat = Math.sin(lat);
  const cosLat = Math.cos(lat);
  const sinLon = Math.sin(lon);
  const cosLon = Math.cos(lon);

  const upSpice: [number, number, number] = [
    cosLat * cosLon,
    cosLat * sinLon,
    sinLat,
  ];
  const eastSpice: [number, number, number] = [-sinLon, cosLon, 0];
  const northSpice: [number, number, number] = [
    -sinLat * cosLon,
    -sinLat * sinLon,
    cosLat,
  ];

  return {
    up: spiceMoonMeToThree(upSpice),
    east: spiceMoonMeToThree(eastSpice),
    north: spiceMoonMeToThree(northSpice),
  };
}

/**
 * Convert topocentric azimuth (degrees CW from local North via East) and elevation (degrees)
 * at (latDeg, lonDeg) into a Three.js direction unit vector in the Moon-fixed globe frame.
 */
export function topocentricAzElToThree(
  latDeg: number,
  lonDeg: number,
  azimuthDeg: number,
  elevationDeg: number,
): [number, number, number] {
  const { east, north, up } = localEnuBasisThree(latDeg, lonDeg);
  const az = degToRad(azimuthDeg);
  const el = degToRad(elevationDeg);
  const cosEl = Math.cos(el);
  const sinEl = Math.sin(el);
  const cosAz = Math.cos(az);
  const sinAz = Math.sin(az);

  return [
    cosEl * (cosAz * north[0] + sinAz * east[0]) + sinEl * up[0],
    cosEl * (cosAz * north[1] + sinAz * east[1]) + sinEl * up[1],
    cosEl * (cosAz * north[2] + sinAz * east[2]) + sinEl * up[2],
  ];
}

export function lerpDirectionUnit(
  a: readonly [number, number, number],
  b: readonly [number, number, number],
  alpha: number,
): [number, number, number] {
  const t = Math.min(1, Math.max(0, alpha));
  const x = a[0] + (b[0] - a[0]) * t;
  const y = a[1] + (b[1] - a[1]) * t;
  const z = a[2] + (b[2] - a[2]) * t;
  const mag = Math.hypot(x, y, z) || 1;
  return [x / mag, y / mag, z / mag];
}

export function detectWebGLSupport(): boolean {
  if (typeof window === "undefined" || typeof document === "undefined") {
    return false;
  }
  try {
    const canvas = document.createElement("canvas");
    const gl =
      canvas.getContext("webgl2") ||
      canvas.getContext("webgl") ||
      canvas.getContext("experimental-webgl");
    return Boolean(gl);
  } catch {
    return false;
  }
}

