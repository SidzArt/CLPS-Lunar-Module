"""Lunar coordinate systems, spherical-to-Cartesian geometry, and topocentric ENU math.

All functions enforce the documented CLPS Luna Browser coordinate contract:
- Reference Frame: ``MOON_ME`` (Mean Earth / Polar Axis, aligned to DE440 ``MOON_ME_DE440_ME421``).
- Latitude: Planetocentric North-positive in ``[-90.0, +90.0]`` degrees.
- Longitude: East-positive in ``[-180.0, +180.0]`` degrees (prime meridian at mean sub-Earth axis).
- Elevation Datum: Meters above lunar reference sphere ``R_MOON = 1,737,400.0 m`` (1737.4 km),
  matching NASA/GSFC PGDA LOLA south-polar products.
- Topocentric Azimuth: Degrees in ``[0.0, 360.0)`` measured clockwise from local North through East.
- Topocentric Elevation: Degrees in ``[-90.0, +90.0]`` measured above local horizontal plane.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

LUNAR_REFERENCE_RADIUS_M: Final[float] = 1_737_400.0
LUNAR_REFERENCE_RADIUS_KM: Final[float] = 1_737.4
POLE_LAT_THRESHOLD_DEG: Final[float] = 90.0 - 1e-9
POLE_XY_TOLERANCE_RATIO: Final[float] = 1e-11


@dataclass(frozen=True)
class CoordinateContract:
    """Formal specification of lunar coordinate conventions used across SPICE and DEM layers."""

    lunar_reference_frame: str = "MOON_ME"
    de440_resolved_frame: str = "MOON_ME_DE440_ME421"
    latitude_convention: str = "planetocentric, north-positive [-90, +90] deg"
    longitude_convention: str = "east-positive [-180, +180] deg, prime meridian = mean Earth axis"
    elevation_datum: str = "meters above sphere R = 1737400.0 m (LOLA reference sphere)"
    azimuth_convention: str = "degrees [0, 360) clockwise from local North toward East"
    elevation_convention: str = "degrees [-90, +90] above local horizon plane"
    distance_unit: str = "kilometers (SPICE) / meters (DEM terrain)"


COORDINATE_CONTRACT = CoordinateContract()


def normalize_longitude_deg(lon_deg: float) -> float:
    """Normalize longitude in degrees into [-180.0, +180.0)."""
    wrapped = ((lon_deg + 180.0) % 360.0) - 180.0
    if wrapped == -180.0 and lon_deg > 0:
        return 180.0
    return float(wrapped)


def normalize_azimuth_deg(az_rad: float | NDArray[np.float64]) -> float | NDArray[np.float64]:
    """Convert azimuth angle(s) in radians to [0.0, 360.0) degrees."""
    deg = np.degrees(az_rad) % 360.0
    if np.ndim(deg) == 0:
        val = float(deg)
        return 0.0 if val >= 360.0 or np.isclose(val, 360.0, atol=1e-12) else val
    return np.where(np.isclose(deg, 360.0, atol=1e-12), 0.0, deg)


def lat_lon_elev_to_cartesian_m(
    lat_deg: float | NDArray[np.float64],
    lon_deg: float | NDArray[np.float64],
    elevation_m: float | NDArray[np.float64] = 0.0,
    radius_m: float = LUNAR_REFERENCE_RADIUS_M,
) -> NDArray[np.float64]:
    """Convert planetocentric (lat, lon, elevation) to Moon-fixed 3D Cartesian coordinates (m).

    Supports scalar inputs (returning shape ``(3,)``) and vectorized NumPy arrays
    (returning shape ``(..., 3)``).
    """
    lat_rad = np.radians(lat_deg)
    lon_rad = np.radians(lon_deg)
    r = radius_m + np.asarray(elevation_m, dtype=np.float64)

    cos_lat = np.cos(lat_rad)
    x = r * cos_lat * np.cos(lon_rad)
    y = r * cos_lat * np.sin(lon_rad)
    z = r * np.sin(lat_rad)

    if np.ndim(x) == 0 and np.ndim(y) == 0 and np.ndim(z) == 0:
        return np.array([float(x), float(y), float(z)], dtype=np.float64)
    return np.stack([x, y, z], axis=-1).astype(np.float64)


def cartesian_m_to_lat_lon_elev(
    xyz_m: NDArray[np.float64],
    radius_m: float = LUNAR_REFERENCE_RADIUS_M,
) -> tuple[float, float, float]:
    """Convert Moon-fixed 3D Cartesian vector (m) to (lat_deg, lon_deg, elevation_m)."""
    vec = np.asarray(xyz_m, dtype=np.float64)
    if vec.shape != (3,):
        raise ValueError(f"Expected 3D vector shape (3,), got {vec.shape}")
    r = float(np.linalg.norm(vec))
    if r <= 0.0:
        raise ValueError("Cartesian radius must be strictly positive")

    sin_lat = float(np.clip(vec[2] / r, -1.0, 1.0))
    lat_deg = float(np.degrees(np.arcsin(sin_lat)))
    xy_norm = float(np.hypot(vec[0], vec[1]))
    if xy_norm <= r * POLE_XY_TOLERANCE_RATIO:
        # Prime-meridian deterministic reference at the exact poles
        lon_deg = 0.0
    else:
        lon_deg = float(np.degrees(np.arctan2(vec[1], vec[0])))
    elevation_m = r - radius_m
    return lat_deg, lon_deg, elevation_m


def local_enu_basis(
    lat_deg: float,
    lon_deg: float,
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    """Construct right-handed orthonormal topocentric (east, north, up) basis vectors.

    Using exact trigonometric components eliminates the cos(phi) normalization singularity near
    the lunar poles. Only when the site sits at the exact pole (|lat| >= 90 - 1e-9 deg) does the
    reference direction fall back deterministically to the Moon frame prime meridian (+X axis).

    Returns:
        Tuple of 3 unit vectors ``(east, north, up)`` in the Moon body-fixed frame.
    """
    if lat_deg < -90.0 or lat_deg > 90.0:
        raise ValueError(f"Latitude out of valid [-90, 90] deg bounds: {lat_deg}")

    if abs(lat_deg) >= POLE_LAT_THRESHOLD_DEG:
        # Exact-pole fallback anchored deterministically to +X prime meridian and +Y east:
        # At South Pole (-90 deg): east=(0,1,0), north=(1,0,0), up=(0,0,-1); det=+1
        # At North Pole (+90 deg): east=(0,1,0), north=(-1,0,0), up=(0,0,1); det=+1
        sign = 1.0 if lat_deg >= 0.0 else -1.0
        east = np.array([0.0, 1.0, 0.0], dtype=np.float64)
        north = np.array([-sign, 0.0, 0.0], dtype=np.float64)
        up = np.array([0.0, 0.0, sign], dtype=np.float64)
        return east, north, up

    phi = float(np.radians(lat_deg))
    lam = float(np.radians(lon_deg))
    sin_phi, cos_phi = float(np.sin(phi)), float(np.cos(phi))
    sin_lam, cos_lam = float(np.sin(lam)), float(np.cos(lam))

    east = np.array([-sin_lam, cos_lam, 0.0], dtype=np.float64)
    north = np.array([-sin_phi * cos_lam, -sin_phi * sin_lam, cos_phi], dtype=np.float64)
    up = np.array([cos_phi * cos_lam, cos_phi * sin_lam, sin_phi], dtype=np.float64)
    return east, north, up


def cartesian_enu_basis(
    xyz_m: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    """Derive local (east, north, up) basis directly from a Moon-fixed 3D position vector."""
    lat_deg, lon_deg, _ = cartesian_m_to_lat_lon_elev(xyz_m)
    return local_enu_basis(lat_deg, lon_deg)


def vector_to_az_el(
    rho_vec: NDArray[np.float64],
    east: NDArray[np.float64],
    north: NDArray[np.float64],
    up: NDArray[np.float64],
) -> tuple[float | NDArray[np.float64], float | NDArray[np.float64], float | NDArray[np.float64]]:
    """Project site-to-target vector(s) ``rho_vec`` into local ENU and compute azimuth/elevation.

    Args:
        rho_vec: Vector ``(3,)`` or array ``(N, 3)`` from observer to target (same linear unit).
        east: Local unit East vector ``(3,)``.
        north: Local unit North vector ``(3,)``.
        up: Local unit Up vector ``(3,)``.

    Returns:
        Tuple ``(azimuth_deg [0, 360), elevation_deg [-90, 90], range_same_unit)``.
    """
    arr = np.asarray(rho_vec, dtype=np.float64)
    e_comp = arr @ east
    n_comp = arr @ north
    u_comp = arr @ up
    horiz = np.hypot(e_comp, n_comp)
    rng = np.hypot(horiz, u_comp)

    az_rad = np.arctan2(e_comp, n_comp)
    el_rad = np.arctan2(u_comp, horiz)
    az_deg = normalize_azimuth_deg(az_rad)
    el_deg = np.degrees(el_rad)

    if np.ndim(arr) == 1:
        return float(az_deg), float(el_deg), float(rng)
    return (
        np.asarray(az_deg, dtype=np.float64),
        np.asarray(el_deg, dtype=np.float64),
        np.asarray(rng, dtype=np.float64),
    )


def estimate_dem_surface_normal_enu(
    z_patch_m: NDArray[np.float64],
    dx_east_m: float,
    dy_north_m: float,
) -> tuple[NDArray[np.float64], float, float]:
    """Estimate local terrain unit normal in ENU coordinates via central differences on a 3x3 patch.

    Args:
        z_patch_m: 3x3 height patch ``z[row, col]`` oriented so column increases East and row
            increases South (standard north-up raster ordering), OR row 0 = North, row 2 = South.
        dx_east_m: Positive grid spacing in the East direction (meters).
        dy_north_m: Positive grid spacing magnitude in the North direction (meters).

    Returns:
        ``(normal_enu, slope_deg, aspect_deg)`` where ``normal_enu`` is a unit vector ``(e, n, u)``.
    """
    if z_patch_m.shape != (3, 3) or np.isnan(z_patch_m).any():
        return np.array([0.0, 0.0, 1.0], dtype=np.float64), 0.0, 0.0

    # North-up raster: row 0 is +dy North relative to row 1; row 2 is -dy South relative to row 1
    dz_deast = float((z_patch_m[1, 2] - z_patch_m[1, 0]) / (2.0 * dx_east_m))
    dz_dnorth = float((z_patch_m[0, 1] - z_patch_m[2, 1]) / (2.0 * dy_north_m))

    raw = np.array([-dz_deast, -dz_dnorth, 1.0], dtype=np.float64)
    norm = float(np.linalg.norm(raw))
    unit_normal = raw / norm
    slope_deg = float(np.degrees(np.arccos(np.clip(unit_normal[2], -1.0, 1.0))))
    aspect_deg = float(normalize_azimuth_deg(float(np.arctan2(unit_normal[0], unit_normal[1]))))
    return unit_normal, slope_deg, aspect_deg
