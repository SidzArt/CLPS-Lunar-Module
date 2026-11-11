import * as THREE from "three";
import type {
  OrbitalTrajectoryOut,
  OrbitalTrajectorySampleOut,
  SimulationSampleOut,
} from "../api/endpoints";

export const SCIENTIFIC_DURATION_OPTIONS = [
  { seconds: 86400, label: "24 Hours (86,400 s)" },
  { seconds: 259200, label: "3 Days (259,200 s)" },
  { seconds: 604800, label: "7 Days (604,800 s)" },
  { seconds: 2360621, label: "~1 Lunar Sidereal Month (27.322 d / 2,360,621 s)" },
  { seconds: 2592000, label: "30 Days (2,592,000 s)" },
  { seconds: 31558118, label: "~1 Earth Sidereal Year (365.256 d / 31,558,118 s)" },
] as const;

export const ANIMATION_DURATION_PRESETS = [
  { seconds: 15, label: "15s" },
  { seconds: 30, label: "30s" },
  { seconds: 60, label: "60s" },
  { seconds: 120, label: "2m" },
  { seconds: 300, label: "5m" },
  { seconds: 600, label: "10m" },
] as const;

export const MIN_ANIMATION_DURATION_SECONDS = 5;
export const MAX_ANIMATION_DURATION_SECONDS = 3600;
export const DEFAULT_ANIMATION_DURATION_SECONDS = 60;

export const AU_KM = 149_597_870.7;
export const MEAN_EARTH_MOON_KM = 384_400;

export const OVERVIEW_AU_UNITS = 10.0;
export const OVERVIEW_KM_TO_UNITS = OVERVIEW_AU_UNITS / AU_KM;
/** Visual magnification of Moon-wrt-Earth offset inside heliocentric overview. */
export const OVERVIEW_MOON_OFFSET_MAGNIFICATION = 35;

export const INSET_MOON_ORBIT_UNITS = 3.6;
export const INSET_KM_TO_UNITS = INSET_MOON_ORBIT_UNITS / MEAN_EARTH_MOON_KM;
/** Distance magnification factor of the Earth-Moon inset relative to heliocentric AU scale. */
export const INSET_VS_OVERVIEW_MAGNIFICATION = Math.round(
  INSET_KM_TO_UNITS / OVERVIEW_KM_TO_UNITS,
);

export interface DurationValidationResult {
  valid: boolean;
  seconds: number | null;
  error: string | null;
}

export function validateAnimationDurationInput(raw: string): DurationValidationResult {
  const trimmed = raw.trim();
  if (trimmed.length === 0) {
    return {
      valid: false,
      seconds: null,
      error:
        "Please enter a whole number between 5 and 3600 seconds. Animation cannot start until the duration is corrected.",
    };
  }
  if (!/^-?\d+$/.test(trimmed)) {
    return {
      valid: false,
      seconds: null,
      error:
        "Please enter a valid whole number between 5 and 3600 seconds. Animation cannot start until the duration is corrected.",
    };
  }
  const parsed = Number(trimmed);
  if (
    !Number.isSafeInteger(parsed) ||
    parsed < MIN_ANIMATION_DURATION_SECONDS ||
    parsed > MAX_ANIMATION_DURATION_SECONDS
  ) {
    return {
      valid: false,
      seconds: null,
      error:
        "Please enter a duration between 5 and 3600 seconds. Animation cannot start until the duration is corrected.",
    };
  }
  return { valid: true, seconds: parsed, error: null };
}

export function computePlaybackRate(
  scientificDurationSeconds: number,
  animationDurationSeconds: number,
): number {
  if (
    !Number.isFinite(scientificDurationSeconds) ||
    scientificDurationSeconds <= 0 ||
    !Number.isFinite(animationDurationSeconds) ||
    animationDurationSeconds <= 0
  ) {
    return 0;
  }
  return scientificDurationSeconds / animationDurationSeconds;
}

export function formatPlaybackRate(rateSimPerRealSec: number): string {
  if (!Number.isFinite(rateSimPerRealSec) || rateSimPerRealSec <= 0) {
    return "—";
  }
  if (rateSimPerRealSec >= 86400) {
    return `${(rateSimPerRealSec / 86400).toFixed(2)} d/s (${Math.round(rateSimPerRealSec).toLocaleString()}x)`;
  }
  if (rateSimPerRealSec >= 3600) {
    return `${(rateSimPerRealSec / 3600).toFixed(2)} h/s (${Math.round(rateSimPerRealSec).toLocaleString()}x)`;
  }
  if (rateSimPerRealSec >= 60) {
    return `${(rateSimPerRealSec / 60).toFixed(1)} min/s (${Math.round(rateSimPerRealSec).toLocaleString()}x)`;
  }
  return `${rateSimPerRealSec.toFixed(1)}x`;
}

/**
 * Map right-handed SPICE ECLIPJ2000 [X, Y, Z] (ecliptic north +Z) into
 * right-handed Three.js Y-up coordinates [X, Z, -Y] (det = +1).
 */
export function eclipJ2000ToThree(
  vec: readonly [number, number, number],
  scale = 1,
): [number, number, number] {
  return [vec[0] * scale, vec[2] * scale, -vec[1] * scale];
}

/**
 * Convert a SPICE 3x3 rotation matrix M (MOON_ME -> ECLIPJ2000) into a Three.js
 * unit Quaternion representing R_three = P * M * P^T, where P maps SPICE -> Three.js.
 */
export function moonMeMatrixToThreeQuaternion(
  mat: readonly [
    readonly [number, number, number],
    readonly [number, number, number],
    readonly [number, number, number],
  ],
): [number, number, number, number] {
  const m00 = mat[0][0];
  const m01 = mat[0][1];
  const m02 = mat[0][2];
  const m10 = mat[1][0];
  const m11 = mat[1][1];
  const m12 = mat[1][2];
  const m20 = mat[2][0];
  const m21 = mat[2][1];
  const m22 = mat[2][2];

  // R_three = P * M * P^T
  const rMat = new THREE.Matrix4().set(
    m00,
    m02,
    -m01,
    0,
    m20,
    m22,
    -m21,
    0,
    -m10,
    -m12,
    m11,
    0,
    0,
    0,
    0,
    1,
  );
  const q = new THREE.Quaternion().setFromRotationMatrix(rMat).normalize();
  return [q.x, q.y, q.z, q.w];
}

function lerpVec3(
  a: readonly [number, number, number],
  b: readonly [number, number, number],
  alpha: number,
): [number, number, number] {
  return [
    a[0] + (b[0] - a[0]) * alpha,
    a[1] + (b[1] - a[1]) * alpha,
    a[2] + (b[2] - a[2]) * alpha,
  ];
}

function normalizeVec3(
  v: readonly [number, number, number],
  fallback: [number, number, number],
): [number, number, number] {
  const len = Math.hypot(v[0], v[1], v[2]);
  if (len < 1e-12) {
    return fallback;
  }
  return [v[0] / len, v[1] / len, v[2] / len];
}

export function findTrajectoryBracket(
  samples: readonly OrbitalTrajectorySampleOut[],
  elapsedSeconds: number,
): { lowIndex: number; highIndex: number; alpha: number } {
  const n = samples.length;
  if (n <= 1) {
    return { lowIndex: 0, highIndex: 0, alpha: 0 };
  }
  const tClamped = Math.max(
    samples[0].elapsed_seconds,
    Math.min(samples[n - 1].elapsed_seconds, elapsedSeconds),
  );
  let lo = 0;
  let hi = n - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (samples[mid].elapsed_seconds <= tClamped) {
      lo = mid;
    } else {
      hi = mid;
    }
  }
  const span = samples[hi].elapsed_seconds - samples[lo].elapsed_seconds;
  const alpha = span > 1e-9 ? Math.max(0, Math.min(1, (tClamped - samples[lo].elapsed_seconds) / span)) : 0;
  return { lowIndex: lo, highIndex: hi, alpha };
}

export function findSampleIndexAtElapsed(
  samples: readonly SimulationSampleOut[],
  elapsedSeconds: number,
): number {
  const n = samples.length;
  if (n <= 1) {
    return 0;
  }
  const tClamped = Math.max(
    samples[0].elapsed_seconds,
    Math.min(samples[n - 1].elapsed_seconds, elapsedSeconds),
  );
  let lo = 0;
  let hi = n - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (samples[mid].elapsed_seconds <= tClamped) {
      lo = mid;
    } else {
      hi = mid;
    }
  }
  const dLo = Math.abs(tClamped - samples[lo].elapsed_seconds);
  const dHi = Math.abs(samples[hi].elapsed_seconds - tClamped);
  return dHi < dLo ? hi : lo;
}

export interface InterpolatedOrbitalState {
  elapsedSeconds: number;
  timestampUtc: string;
  earthWrtSunKm: [number, number, number];
  moonWrtEarthKm: [number, number, number];
  moonWrtSunKm: [number, number, number];
  earthSunDistanceKm: number;
  moonEarthDistanceKm: number;
  moonWrtEarthElevationDeg: number;
  /** Scene positions in Heliocentric Overview (Sun at [0,0,0]). */
  overviewEarthPos: [number, number, number];
  overviewMoonPos: [number, number, number];
  overviewEarthTangentDir: [number, number, number];
  overviewMoonTangentDir: [number, number, number];
  /** Scene positions in Magnified Earth-Moon Inset (Earth at [0,0,0]). */
  insetMoonPos: [number, number, number];
  insetMoonTangentDir: [number, number, number];
  insetSunDirectionUnit: [number, number, number];
  /** Inertial MOON_ME -> ECLIPJ2000 mapped into Three.js Quaternion [x, y, z, w]. */
  moonQuaternion: [number, number, number, number];
}

export function interpolateOrbitalState(
  trajectory: OrbitalTrajectoryOut,
  elapsedSeconds: number,
): InterpolatedOrbitalState | null {
  const samples = trajectory.samples;
  if (!samples || samples.length === 0) {
    return null;
  }
  const { lowIndex, highIndex, alpha } = findTrajectoryBracket(samples, elapsedSeconds);
  const s0 = samples[lowIndex];
  const s1 = samples[highIndex];

  const earthWrtSunKm = lerpVec3(
    s0.earth_wrt_sun_eclipj2000_km,
    s1.earth_wrt_sun_eclipj2000_km,
    alpha,
  );
  const moonWrtEarthKm = lerpVec3(
    s0.moon_wrt_earth_eclipj2000_km,
    s1.moon_wrt_earth_eclipj2000_km,
    alpha,
  );
  // Strict connected hierarchy identity: Moon_Sun = Earth_Sun + Moon_Earth
  const moonWrtSunKm: [number, number, number] = [
    earthWrtSunKm[0] + moonWrtEarthKm[0],
    earthWrtSunKm[1] + moonWrtEarthKm[1],
    earthWrtSunKm[2] + moonWrtEarthKm[2],
  ];

  const earthSunDistanceKm = Math.hypot(earthWrtSunKm[0], earthWrtSunKm[1], earthWrtSunKm[2]);
  const moonEarthDistanceKm = Math.hypot(
    moonWrtEarthKm[0],
    moonWrtEarthKm[1],
    moonWrtEarthKm[2],
  );
  const moonWrtEarthElevationDeg =
    moonEarthDistanceKm > 0
      ? (Math.asin(Math.max(-1, Math.min(1, moonWrtEarthKm[2] / moonEarthDistanceKm))) * 180) /
        Math.PI
      : 0;

  const overviewEarthPos = eclipJ2000ToThree(earthWrtSunKm, OVERVIEW_KM_TO_UNITS);
  const overviewMoonOffset = eclipJ2000ToThree(
    moonWrtEarthKm,
    OVERVIEW_KM_TO_UNITS * OVERVIEW_MOON_OFFSET_MAGNIFICATION,
  );
  const overviewMoonPos: [number, number, number] = [
    overviewEarthPos[0] + overviewMoonOffset[0],
    overviewEarthPos[1] + overviewMoonOffset[1],
    overviewEarthPos[2] + overviewMoonOffset[2],
  ];
  const insetMoonPos = eclipJ2000ToThree(moonWrtEarthKm, INSET_KM_TO_UNITS);

  // Instantaneous forward orbital direction vectors along real sampled ephemeris
  let tIdxA = lowIndex;
  let tIdxB = highIndex;
  if (tIdxA === tIdxB && samples.length >= 2) {
    if (tIdxA === 0) {
      tIdxA = 0;
      tIdxB = 1;
    } else {
      tIdxA = Math.max(0, tIdxB - 1);
    }
  }
  const tA = samples[tIdxA];
  const tB = samples[tIdxB];
  const earthDelta = eclipJ2000ToThree([
    tB.earth_wrt_sun_eclipj2000_km[0] - tA.earth_wrt_sun_eclipj2000_km[0],
    tB.earth_wrt_sun_eclipj2000_km[1] - tA.earth_wrt_sun_eclipj2000_km[1],
    tB.earth_wrt_sun_eclipj2000_km[2] - tA.earth_wrt_sun_eclipj2000_km[2],
  ]);
  const moonRelDelta = eclipJ2000ToThree([
    tB.moon_wrt_earth_eclipj2000_km[0] - tA.moon_wrt_earth_eclipj2000_km[0],
    tB.moon_wrt_earth_eclipj2000_km[1] - tA.moon_wrt_earth_eclipj2000_km[1],
    tB.moon_wrt_earth_eclipj2000_km[2] - tA.moon_wrt_earth_eclipj2000_km[2],
  ]);
  const overviewMoonTraceDelta: [number, number, number] = [
    earthDelta[0] + moonRelDelta[0] * OVERVIEW_MOON_OFFSET_MAGNIFICATION,
    earthDelta[1] + moonRelDelta[1] * OVERVIEW_MOON_OFFSET_MAGNIFICATION,
    earthDelta[2] + moonRelDelta[2] * OVERVIEW_MOON_OFFSET_MAGNIFICATION,
  ];

  const overviewEarthTangentDir = normalizeVec3(earthDelta, [0, 0, -1]);
  const insetMoonTangentDir = normalizeVec3(moonRelDelta, [0, 0, -1]);
  const overviewMoonTangentDir = normalizeVec3(overviewMoonTraceDelta, insetMoonTangentDir);

  // Direction from Earth toward Sun in Three.js space = -earthWrtSunKm
  const insetSunDirectionUnit = normalizeVec3(
    eclipJ2000ToThree([-earthWrtSunKm[0], -earthWrtSunKm[1], -earthWrtSunKm[2]]),
    [1, 0, 0],
  );

  // Quaternion SLERP for SPICE MOON_ME -> ECLIPJ2000 inertial Moon orientation
  const qArr0 = moonMeMatrixToThreeQuaternion(s0.moon_me_to_eclipj2000);
  const q0 = new THREE.Quaternion(qArr0[0], qArr0[1], qArr0[2], qArr0[3]);
  if (lowIndex !== highIndex && alpha > 0) {
    const qArr1 = moonMeMatrixToThreeQuaternion(s1.moon_me_to_eclipj2000);
    const q1 = new THREE.Quaternion(qArr1[0], qArr1[1], qArr1[2], qArr1[3]);
    q0.slerp(q1, alpha);
  }

  const clampedElapsed = Math.max(
    0,
    Math.min(
      trajectory.duration_seconds,
      s0.elapsed_seconds + (s1.elapsed_seconds - s0.elapsed_seconds) * alpha,
    ),
  );
  const startMs = Date.parse(trajectory.start_time_utc);
  const timestampUtc = Number.isFinite(startMs)
    ? new Date(startMs + clampedElapsed * 1000).toISOString().replace(".000Z", "Z")
    : s0.timestamp_utc;

  return {
    elapsedSeconds: clampedElapsed,
    timestampUtc,
    earthWrtSunKm,
    moonWrtEarthKm,
    moonWrtSunKm,
    earthSunDistanceKm,
    moonEarthDistanceKm,
    moonWrtEarthElevationDeg,
    overviewEarthPos,
    overviewMoonPos,
    overviewEarthTangentDir,
    overviewMoonTangentDir,
    insetMoonPos,
    insetMoonTangentDir,
    insetSunDirectionUnit,
    moonQuaternion: [q0.x, q0.y, q0.z, q0.w],
  };
}
