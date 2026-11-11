"""SPICE topocentric ephemeris computations for Sun, Earth, and lunar observer sites."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
import spiceypy as spice
from numpy.typing import NDArray

from app.integrations.spice.kernel_manager import (
    LoadedKernelState,
    SpiceKernelManager,
    datetime_to_spice_iso,
    spice_kernel_manager,
)
from app.services.geometry import (
    LUNAR_REFERENCE_RADIUS_KM,
    cartesian_m_to_lat_lon_elev,
    lat_lon_elev_to_cartesian_m,
    local_enu_basis,
    vector_to_az_el,
)


@dataclass(frozen=True)
class ObserverSiteState:
    """Immutable Moon-fixed observer geometry for a simulation run."""

    site_id: int
    latitude_deg: float
    longitude_deg: float
    effective_elevation_m: float
    lunar_frame: str
    aberration_correction: str
    moon_radius_km: float
    obs_pos_moon_me_km: NDArray[np.float64]
    east: NDArray[np.float64]
    north: NDArray[np.float64]
    up: NDArray[np.float64]


@dataclass(frozen=True)
class EphemerisSample:
    """Single SPICE-evaluated astronomical sample at a UTC timestamp / ET."""

    timestamp_utc: datetime
    et: float
    sun_azimuth_deg: float
    sun_elevation_deg: float
    sun_range_km: float
    earth_azimuth_deg: float
    earth_elevation_deg: float
    earth_range_km: float
    sun_dir_moon: tuple[float, float, float]
    earth_dir_moon: tuple[float, float, float]
    subsolar_lat_deg: float
    subsolar_lon_deg: float


@dataclass(frozen=True)
class InertialOrbitalSample:
    """Single SPICE ECLIPJ2000 3-body orbital position & Moon orientation sample."""

    timestamp_utc: datetime
    ephemeris_time: float
    elapsed_seconds: float
    earth_wrt_sun_eclipj2000_km: tuple[float, float, float]
    moon_wrt_earth_eclipj2000_km: tuple[float, float, float]
    moon_wrt_sun_eclipj2000_km: tuple[float, float, float]
    moon_me_to_eclipj2000: tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ]


def build_observer_state(
    site_id: int,
    latitude_deg: float,
    longitude_deg: float,
    effective_elevation_m: float,
    lunar_frame: str = "MOON_ME",
    aberration_correction: str = "LT+S",
    moon_radius_km: float = LUNAR_REFERENCE_RADIUS_KM,
) -> ObserverSiteState:
    """Build Moon-fixed Cartesian observer coordinates and local ENU basis."""
    obs_xyz_m = lat_lon_elev_to_cartesian_m(
        latitude_deg,
        longitude_deg,
        effective_elevation_m,
        radius_m=moon_radius_km * 1000.0,
    )
    obs_pos_km = obs_xyz_m / 1000.0
    east, north, up = local_enu_basis(latitude_deg, longitude_deg)
    return ObserverSiteState(
        site_id=site_id,
        latitude_deg=float(latitude_deg),
        longitude_deg=float(longitude_deg),
        effective_elevation_m=float(effective_elevation_m),
        lunar_frame=lunar_frame,
        aberration_correction=aberration_correction,
        moon_radius_km=float(moon_radius_km),
        obs_pos_moon_me_km=obs_pos_km,
        east=east,
        north=north,
        up=up,
    )


def utc_to_et(dt: datetime, manager: SpiceKernelManager | None = None) -> float:
    """Convert timezone-aware/naive UTC datetime to SPICE ephemeris time (TDB seconds past J2000)."""
    mgr = manager or spice_kernel_manager
    with mgr.lock:
        mgr.ensure_loaded()
        return float(spice.str2et(datetime_to_spice_iso(dt)))


def et_to_utc_datetime(et: float, manager: SpiceKernelManager | None = None) -> datetime:
    """Convert SPICE ephemeris time to exact leap-second-aware UTC datetime."""
    mgr = manager or spice_kernel_manager
    with mgr.lock:
        mgr.ensure_loaded()
        iso_str = str(spice.et2utc(et, "ISOC", 6))
    return datetime.fromisoformat(iso_str).replace(tzinfo=UTC)


def compute_ephemeris_sample(
    et: float,
    observer: ObserverSiteState,
    manager: SpiceKernelManager | None = None,
) -> EphemerisSample:
    """Compute topocentric Sun & Earth geometry and Moon-fixed directions at a single ET.

    Uses ``spkcpo`` (constant-position surface observer in ``MOON_ME``) paired with our
    polar-safe orthonormal ENU tangent projection, ensuring exact agreement with ``azlcpo`` away
    from the poles while avoiding ``SPICE(POINTONZAXIS)`` singularities at +/-90 deg.
    """
    mgr = manager or spice_kernel_manager
    frame = observer.lunar_frame
    abcorr = observer.aberration_correction

    with mgr.lock:
        mgr.ensure_loaded()
        iso_str = str(spice.et2utc(et, "ISOC", 6))
        ts_utc = datetime.fromisoformat(iso_str).replace(tzinfo=UTC)

        st_sun, _ = spice.spkcpo(
            "SUN", et, frame, "OBSERVER", abcorr, observer.obs_pos_moon_me_km, "MOON", frame
        )
        st_earth, _ = spice.spkcpo(
            "EARTH", et, frame, "OBSERVER", abcorr, observer.obs_pos_moon_me_km, "MOON", frame
        )
        sun_moon_pos, _ = spice.spkpos("SUN", et, frame, abcorr, "MOON")
        earth_moon_pos, _ = spice.spkpos("EARTH", et, frame, abcorr, "MOON")

    sun_vec = np.asarray(st_sun[:3], dtype=np.float64)
    earth_vec = np.asarray(st_earth[:3], dtype=np.float64)

    sun_az, sun_el, sun_rng = vector_to_az_el(sun_vec, observer.east, observer.north, observer.up)
    earth_az, earth_el, earth_rng = vector_to_az_el(
        earth_vec, observer.east, observer.north, observer.up
    )

    sun_moon_arr = np.asarray(sun_moon_pos, dtype=np.float64)
    sun_moon_unit = sun_moon_arr / float(np.linalg.norm(sun_moon_arr))
    earth_moon_arr = np.asarray(earth_moon_pos, dtype=np.float64)
    earth_moon_unit = earth_moon_arr / float(np.linalg.norm(earth_moon_arr))

    sub_lat, sub_lon, _ = cartesian_m_to_lat_lon_elev(sun_moon_arr * 1000.0)

    return EphemerisSample(
        timestamp_utc=ts_utc,
        et=float(et),
        sun_azimuth_deg=float(sun_az),
        sun_elevation_deg=float(sun_el),
        sun_range_km=float(sun_rng),
        earth_azimuth_deg=float(earth_az),
        earth_elevation_deg=float(earth_el),
        earth_range_km=float(earth_rng),
        sun_dir_moon=(
            round(float(sun_moon_unit[0]), 7),
            round(float(sun_moon_unit[1]), 7),
            round(float(sun_moon_unit[2]), 7),
        ),
        earth_dir_moon=(
            round(float(earth_moon_unit[0]), 7),
            round(float(earth_moon_unit[1]), 7),
            round(float(earth_moon_unit[2]), 7),
        ),
        subsolar_lat_deg=round(float(sub_lat), 4),
        subsolar_lon_deg=round(float(sub_lon), 4),
    )


def get_moon_orientation_matrix(
    et: float,
    from_frame: str = "J2000",
    to_frame: str = "MOON_ME",
    manager: SpiceKernelManager | None = None,
) -> list[list[float]]:
    """Compute 3x3 inertial-to-Moon-fixed rotation matrix at ephemeris time ``et``."""
    mgr = manager or spice_kernel_manager
    with mgr.lock:
        mgr.ensure_loaded()
        mat = spice.pxform(from_frame, to_frame, et)
    return [[float(val) for val in row] for row in mat]


def compute_inertial_orbital_trajectory(
    start_time_utc: datetime,
    end_time_utc: datetime,
    num_samples: int = 1024,
    frame: str = "ECLIPJ2000",
    abcorr: str = "NONE",
    manager: SpiceKernelManager | None = None,
) -> tuple[LoadedKernelState, list[InertialOrbitalSample]]:
    """Compute bounded DE440 inertial Sun-Earth-Moon vectors and Moon orientation over [start, end]."""
    if num_samples < 64 or num_samples > 4096:
        raise ValueError("num_samples must be between 64 and 4096.")

    start_utc = (
        start_time_utc.replace(tzinfo=UTC)
        if start_time_utc.tzinfo is None
        else start_time_utc.astimezone(UTC)
    )
    end_utc = (
        end_time_utc.replace(tzinfo=UTC)
        if end_time_utc.tzinfo is None
        else end_time_utc.astimezone(UTC)
    )

    mgr = manager or spice_kernel_manager
    samples: list[InertialOrbitalSample] = []

    with mgr.lock:
        start_et, end_et, kernel_state = mgr.validate_utc_interval(start_utc, end_utc)
        denom = float(num_samples - 1)
        span_et = end_et - start_et

        for idx in range(num_samples):
            if idx == 0:
                et = start_et
            elif idx == num_samples - 1:
                et = end_et
            else:
                et = start_et + span_et * (float(idx) / denom)

            iso_str = str(spice.et2utc(et, "ISOC", 6))
            ts_utc = datetime.fromisoformat(iso_str).replace(tzinfo=UTC)
            elapsed_s = 0.0 if idx == 0 else round((ts_utc - start_utc).total_seconds(), 3)

            earth_sun_arr, _ = spice.spkpos("EARTH", et, frame, abcorr, "SUN")
            moon_earth_arr, _ = spice.spkpos("MOON", et, frame, abcorr, "EARTH")

            ex = float(earth_sun_arr[0])
            ey = float(earth_sun_arr[1])
            ez = float(earth_sun_arr[2])

            mx = float(moon_earth_arr[0])
            my = float(moon_earth_arr[1])
            mz = float(moon_earth_arr[2])

            rot_mat = spice.pxform("MOON_ME", frame, et)
            rot_tuple = (
                (float(rot_mat[0][0]), float(rot_mat[0][1]), float(rot_mat[0][2])),
                (float(rot_mat[1][0]), float(rot_mat[1][1]), float(rot_mat[1][2])),
                (float(rot_mat[2][0]), float(rot_mat[2][1]), float(rot_mat[2][2])),
            )

            samples.append(
                InertialOrbitalSample(
                    timestamp_utc=ts_utc,
                    ephemeris_time=float(et),
                    elapsed_seconds=float(elapsed_s),
                    earth_wrt_sun_eclipj2000_km=(ex, ey, ez),
                    moon_wrt_earth_eclipj2000_km=(mx, my, mz),
                    moon_wrt_sun_eclipj2000_km=(ex + mx, ey + my, ez + mz),
                    moon_me_to_eclipj2000=rot_tuple,
                )
            )

    return kernel_state, samples


def summarize_kernel_metadata(state: LoadedKernelState) -> dict[str, object]:
    """Serialize loaded kernel metadata cleanly without exposing filesystem paths."""
    return {
        "manifest_version": state.manifest_version,
        "ephemeris_source": state.ephemeris_source,
        "ephemeris_version": state.ephemeris_version,
        "primary_lunar_frame": state.primary_lunar_frame,
        "resolved_lunar_frame": state.resolved_lunar_frame,
        "lsk_latest_leap_second": state.lsk_latest_leap_second,
        "moon_radii_km": list(state.moon_radii_km),
        "common_coverage_start_utc": state.common_start_utc,
        "common_coverage_end_utc": state.common_end_utc,
        "kernels": [
            {
                "filename": k.filename,
                "kind": k.kind,
                "sha256": k.actual_sha256,
                "size_bytes": k.size_bytes,
            }
            for k in state.kernels
        ],
    }
