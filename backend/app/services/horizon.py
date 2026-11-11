"""Terrain horizon profile calculator Theta_hor(psi) using 3D lunar curvature ray casting.

Uses great-circle vector propagation directly from the observer's right-handed ENU basis so
calculations remain smooth and singularity-free across mid-latitudes and lunar poles.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Final

import numpy as np
from pyproj import CRS, Transformer

from app.integrations.terrain.coordinate_transform import (
    lonlat_to_raster_xy,
)
from app.integrations.terrain.dem_reader import DEMRegistry, DEMWindowSample
from app.services.geometry import (
    LUNAR_REFERENCE_RADIUS_M,
    lat_lon_elev_to_cartesian_m,
    local_enu_basis,
)
from app.services.visibility import HorizonProfileData

HORIZON_ALGORITHM_VERSION: Final[str] = "v1.0-3d-raycast"


@dataclass(frozen=True)
class HorizonComputationResult:
    """Complete result and provenance of a site's horizon profile evaluation."""

    profile: HorizonProfileData
    cache_key: str
    cache_hit: bool
    site_id: int
    site_latitude_deg: float
    site_longitude_deg: float
    site_ground_elevation_m: float | None
    observer_height_m: float
    coordinate_frame: str
    dem_asset_id: str | None
    dem_filename: str | None
    dem_checksum: str | None
    dem_resolution_m: float | None
    dem_source: str | None
    dem_citation: str | None
    algorithm_version: str
    azimuth_bins: int
    azimuths_deg: list[float]
    horizon_elevations_deg: list[float]
    horizon_distances_m: list[float]
    uncertainty_deg: list[float] | None
    coverage_fraction: float
    nodata_fraction: float
    warnings: list[str]
    metadata: dict[str, object]


def compute_horizon_cache_key(
    site_id: int,
    lat_deg: float,
    lon_deg: float,
    site_db_elevation_m: float | None,
    dem_asset_id: str,
    dem_checksum: str,
    coordinate_frame: str,
    observer_height_m: float,
    algorithm_version: str,
    azimuth_bins: int,
    max_radius_m: float,
) -> str:
    """Compute deterministic SHA-256 cache key matching all required invalidation dimensions."""
    payload = {
        "site_id": site_id,
        "lat_deg": round(float(lat_deg), 8),
        "lon_deg": round(float(lon_deg), 8),
        "site_db_elevation_m": None
        if site_db_elevation_m is None
        else round(float(site_db_elevation_m), 4),
        "dem_asset_id": dem_asset_id,
        "dem_checksum": dem_checksum,
        "coordinate_frame": coordinate_frame,
        "observer_height_m": round(float(observer_height_m), 4),
        "algorithm_version": algorithm_version,
        "azimuth_bins": int(azimuth_bins),
        "max_radius_m": round(float(max_radius_m), 1),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def compute_horizon_from_dem_window(
    site_id: int,
    lat_deg: float,
    lon_deg: float,
    site_db_elevation_m: float | None,
    window: DEMWindowSample,
    observer_height_m: float = 1.5,
    coordinate_frame: str = "MOON_ME",
    azimuth_bins: int = 360,
    min_radius_m: float = 50.0,
    max_radius_m: float = 100_000.0,
    max_radial_samples: int = 1400,
) -> HorizonComputationResult:
    """Compute radial horizon profile ``theta_hor(psi)`` from a bounded DEM window.

    Uses full 3D Moon-fixed spherical vector differences so lunar curvature drop is exact
    at every range without flat-Earth approximations.
    """
    warnings: list[str] = []
    if window.asset.lunar_frame != coordinate_frame:
        warnings.append(
            f"DEM uses {window.asset.lunar_frame}; simulation target frame is {coordinate_frame} "
            "(DE440 MOON_ME_DE440_ME421 provides close alignment with LOLA DE421 MOON_ME)."
        )

    ground_elev = window.site_elev_m
    if ground_elev is None:
        if site_db_elevation_m is not None:
            ground_elev = float(site_db_elevation_m)
            warnings.append(
                "DEM center cell is NoData; observer ground elevation fell back to catalogued site elevation."
            )
        else:
            ground_elev = 0.0
            warnings.append(
                "DEM center cell is NoData and site elevation missing; defaulting ground elevation to 0 m."
            )

    datum_r = window.context.datum_radius_m or LUNAR_REFERENCE_RADIUS_M
    obs_height_above_datum = float(ground_elev) + float(observer_height_m)
    obs_xyz = lat_lon_elev_to_cartesian_m(
        lat_deg, lon_deg, obs_height_above_datum, radius_m=datum_r
    )
    east, north, up = local_enu_basis(lat_deg, lon_deg)

    # Determine effective pixel posting inside bounded window (handles downsampled out_shape)
    win_h, win_w = window.elevation_m.shape
    eff_dx = abs(float(window.window_transform.a))
    eff_dy = abs(float(window.window_transform.e))
    eff_res_m = max(eff_dx, eff_dy, float(window.asset.pixel_size_x_m))

    start_r = max(float(min_radius_m), eff_res_m * 0.75)
    if start_r >= max_radius_m:
        start_r = max(10.0, max_radius_m * 0.05)

    # Linear stepping capped at max_radial_samples so memory & runtime remain bounded
    n_radial = min(
        max_radial_samples,
        max(64, int(np.ceil((max_radius_m - start_r) / max(eff_res_m * 0.9, 10.0)))),
    )
    radii_m = np.linspace(start_r, max_radius_m, n_radial, dtype=np.float64)
    sigmas = radii_m / datum_r  # (M,) central angular distances in radians

    bin_step_deg = 360.0 / float(azimuth_bins)
    azimuths_deg = np.arange(azimuth_bins, dtype=np.float64) * bin_step_deg
    psi_rad = np.radians(azimuths_deg)  # (K,)

    # Horizontal directions on local tangent plane: d_h(k) = sin(psi)*east + cos(psi)*north -> (K, 3)
    d_horiz = (
        np.sin(psi_rad)[:, None] * east[None, :] + np.cos(psi_rad)[:, None] * north[None, :]
    )  # (K, 3)

    # Exact 3D great-circle unit directions u_2(k, m) = cos(sigma)*up + sin(sigma)*d_horiz
    cos_sig = np.cos(sigmas)[None, :, None]  # (1, M, 1)
    sin_sig = np.sin(sigmas)[None, :, None]  # (1, M, 1)
    u2 = cos_sig * up[None, None, :] + sin_sig * d_horiz[:, None, :]  # (K, M, 3)

    # Convert unit vectors u2 to planetocentric (lat2, lon2) degrees for CRS projection
    sin_lat2 = np.clip(u2[..., 2], -1.0, 1.0)
    lat2_deg = np.degrees(np.arcsin(sin_lat2))
    lon2_deg = np.degrees(np.arctan2(u2[..., 1], u2[..., 0]))

    raster_crs = CRS.from_wkt(window.context.raster_crs_wkt)
    geodetic_crs = CRS.from_proj4(window.context.geodetic_crs_proj4)
    to_raster = Transformer.from_crs(geodetic_crs, raster_crs, always_xy=True)

    qx_flat, qy_flat = lonlat_to_raster_xy(to_raster, lon2_deg.ravel(), lat2_deg.ravel())
    inv_t = ~window.window_transform
    # inv_t * (x, y) gives fractional (col, row); floor gives pixel index matching Area center [i, i+1)
    cols_f, rows_f = inv_t @ (
        np.asarray(qx_flat, dtype=np.float64),
        np.asarray(qy_flat, dtype=np.float64),
    )
    cols_i = np.floor(cols_f).astype(np.int64).reshape(azimuth_bins, n_radial)
    rows_i = np.floor(rows_f).astype(np.int64).reshape(azimuth_bins, n_radial)

    in_bounds = (rows_i >= 0) & (rows_i < win_h) & (cols_i >= 0) & (cols_i < win_w)
    safe_r = np.clip(rows_i, 0, max(0, win_h - 1))
    safe_c = np.clip(cols_i, 0, max(0, win_w - 1))

    sampled_z = np.where(in_bounds, window.elevation_m[safe_r, safe_c], np.nan)
    valid_mask = in_bounds & np.isfinite(sampled_z)

    total_samples = int(azimuth_bins * n_radial)
    in_bounds_count = int(in_bounds.sum())
    valid_count = int(valid_mask.sum())
    nodata_in_bounds = max(0, in_bounds_count - valid_count)
    nodata_fraction = float(nodata_in_bounds / max(1, in_bounds_count))

    # Full 3D vector delta from observer to terrain cell center: r_terr * u2 - obs_xyz
    z_clean = np.where(valid_mask, sampled_z, 0.0)
    terr_xyz = (datum_r + z_clean)[..., None] * u2  # (K, M, 3)
    delta_xyz = terr_xyz - obs_xyz[None, None, :]

    e_comp = np.einsum("kmc,c->km", delta_xyz, east)
    n_comp = np.einsum("kmc,c->km", delta_xyz, north)
    u_comp = np.einsum("kmc,c->km", delta_xyz, up)
    horiz_dist = np.hypot(e_comp, n_comp)

    angles_deg = np.degrees(np.arctan2(u_comp, np.maximum(horiz_dist, 1e-6)))
    angles_masked = np.where(valid_mask, angles_deg, -90.0)

    has_any_valid_per_ray = valid_mask.any(axis=1)
    valid_ray_fraction = float(has_any_valid_per_ray.mean())

    best_idx = np.argmax(angles_masked, axis=1)
    ray_idx = np.arange(azimuth_bins)
    horizon_elev_deg = angles_masked[ray_idx, best_idx]
    horizon_dist_m = horiz_dist[ray_idx, best_idx]

    # Mark rays with zero valid terrain samples cleanly (0.0 fallback + insufficient quality flag)
    horizon_elev_deg = np.where(has_any_valid_per_ray, horizon_elev_deg, 0.0)
    horizon_dist_m = np.where(has_any_valid_per_ray, horizon_dist_m, 0.0)

    # Propagate vertical Z error to angular elevation uncertainty when ERR grid is available
    uncertainty_deg: list[float] | None = None
    if window.error_m_grid is not None:
        obs_err = float(window.site_error_m or 0.5)
        best_r = safe_r[ray_idx, best_idx]
        best_c = safe_c[ray_idx, best_idx]
        ridge_err = window.error_m_grid[best_r, best_c]
        ridge_err = np.where(np.isfinite(ridge_err), ridge_err, obs_err)
        comb_err = np.hypot(obs_err, ridge_err)
        ang_err = np.degrees(comb_err / np.maximum(horizon_dist_m, start_r))
        uncertainty_deg = [round(float(x), 4) for x in ang_err]

    sampled_count_stats: dict[str, float] | None = None
    if window.count_grid is not None:
        best_r = safe_r[ray_idx, best_idx]
        best_c = safe_c[ray_idx, best_idx]
        counts_at_ridge = window.count_grid[best_r, best_c]
        finite_counts = counts_at_ridge[np.isfinite(counts_at_ridge)]
        zero_shot_frac = float((finite_counts <= 0).mean()) if finite_counts.size > 0 else 1.0
        sampled_count_stats = {
            "observer_lola_count": float(window.site_count)
            if window.site_count is not None
            else 0.0,
            "ridge_interpolated_zero_shot_fraction": round(zero_shot_frac, 4),
            "ridge_mean_lola_count": round(float(finite_counts.mean()), 2)
            if finite_counts.size > 0
            else 0.0,
        }
        if zero_shot_frac > 0.5:
            warnings.append(
                f"{zero_shot_frac * 100:.1f}% of horizon ridge cells have LDEC=0 interpolated height rather than direct LOLA laser returns."
            )

    # Determine strict scientific data quality state per Part O
    if valid_count == 0 or window.site_elev_m is None or valid_ray_fraction < 0.5:
        if window.site_elev_m is None and valid_ray_fraction >= 0.85:
            quality_state = "partial_dem_coverage"
        else:
            quality_state = "insufficient_data"
            warnings.append(
                "Insufficient valid DEM cells around site to determine reliable terrain horizon."
            )
    elif not window.full_horizon_covered or valid_ray_fraction < 0.99 or nodata_fraction > 0.05:
        quality_state = "partial_dem_coverage"
        if not window.full_horizon_covered:
            warnings.append(
                f"Site is {window.min_edge_margin_m / 1000.0:.1f} km from DEM tile boundary "
                f"(less than requested {max_radius_m / 1000.0:.1f} km horizon radius)."
            )
        if nodata_fraction > 0.05:
            warnings.append(
                f"DEM window contains {nodata_fraction * 100:.1f}% NoData pixels inside horizon search extent."
            )
    else:
        quality_state = "verified_terrain_aware"

    coverage_fraction = float(valid_count / max(1, total_samples))
    cache_key = compute_horizon_cache_key(
        site_id=site_id,
        lat_deg=lat_deg,
        lon_deg=lon_deg,
        site_db_elevation_m=site_db_elevation_m,
        dem_asset_id=window.asset.asset_id,
        dem_checksum=window.asset.sha256,
        coordinate_frame=coordinate_frame,
        observer_height_m=observer_height_m,
        algorithm_version=HORIZON_ALGORITHM_VERSION,
        azimuth_bins=azimuth_bins,
        max_radius_m=max_radius_m,
    )

    profile = HorizonProfileData(
        azimuths_deg=azimuths_deg,
        elevations_deg=horizon_elev_deg.astype(np.float64),
        quality_state=quality_state,
        azimuth_bins=azimuth_bins,
    )

    metadata: dict[str, object] = {
        "pixel_registration": window.context.pixel_registration,
        "datum_radius_m": datum_r,
        "observer_ground_elev_m": round(float(ground_elev), 3),
        "observer_height_m": float(observer_height_m),
        "effective_window_res_m": round(eff_res_m, 2),
        "radial_steps": int(n_radial),
        "min_edge_margin_m": round(float(window.min_edge_margin_m), 1),
        "full_horizon_covered": window.full_horizon_covered,
        "valid_ray_fraction": round(valid_ray_fraction, 4),
    }
    if sampled_count_stats is not None:
        metadata["lola_count_diagnostics"] = sampled_count_stats

    return HorizonComputationResult(
        profile=profile,
        cache_key=cache_key,
        cache_hit=False,
        site_id=site_id,
        site_latitude_deg=lat_deg,
        site_longitude_deg=lon_deg,
        site_ground_elevation_m=window.site_elev_m,
        observer_height_m=observer_height_m,
        coordinate_frame=coordinate_frame,
        dem_asset_id=window.asset.asset_id,
        dem_filename=window.asset.filename,
        dem_checksum=window.asset.sha256,
        dem_resolution_m=window.asset.pixel_size_x_m,
        dem_source=window.asset.source,
        dem_citation=window.asset.citation,
        algorithm_version=HORIZON_ALGORITHM_VERSION,
        azimuth_bins=azimuth_bins,
        azimuths_deg=[round(float(x), 4) for x in azimuths_deg],
        horizon_elevations_deg=[round(float(x), 5) for x in horizon_elev_deg],
        horizon_distances_m=[round(float(x), 1) for x in horizon_dist_m],
        uncertainty_deg=uncertainty_deg,
        coverage_fraction=round(coverage_fraction, 4),
        nodata_fraction=round(nodata_fraction, 4),
        warnings=warnings,
        metadata=metadata,
    )


def build_geometric_only_horizon(
    site_id: int,
    lat_deg: float,
    lon_deg: float,
    site_db_elevation_m: float | None,
    observer_height_m: float = 1.5,
    coordinate_frame: str = "MOON_ME",
    azimuth_bins: int = 360,
    reason: str = "No registered LOLA DEM asset covers this landing site coordinate.",
) -> HorizonComputationResult:
    """Explicitly build an idealised geometric-only zero-elevation horizon when DEM is absent."""
    profile = HorizonProfileData.flat_geometric(azimuth_bins=azimuth_bins)
    cache_key = compute_horizon_cache_key(
        site_id=site_id,
        lat_deg=lat_deg,
        lon_deg=lon_deg,
        site_db_elevation_m=site_db_elevation_m,
        dem_asset_id="NONE_GEOMETRIC_ONLY",
        dem_checksum="NONE",
        coordinate_frame=coordinate_frame,
        observer_height_m=observer_height_m,
        algorithm_version=HORIZON_ALGORITHM_VERSION,
        azimuth_bins=azimuth_bins,
        max_radius_m=0.0,
    )
    return HorizonComputationResult(
        profile=profile,
        cache_key=cache_key,
        cache_hit=False,
        site_id=site_id,
        site_latitude_deg=lat_deg,
        site_longitude_deg=lon_deg,
        site_ground_elevation_m=site_db_elevation_m,
        observer_height_m=observer_height_m,
        coordinate_frame=coordinate_frame,
        dem_asset_id=None,
        dem_filename=None,
        dem_checksum=None,
        dem_resolution_m=None,
        dem_source=None,
        dem_citation=None,
        algorithm_version=HORIZON_ALGORITHM_VERSION,
        azimuth_bins=azimuth_bins,
        azimuths_deg=[round(float(x), 4) for x in profile.azimuths_deg],
        horizon_elevations_deg=[0.0 for _ in range(azimuth_bins)],
        horizon_distances_m=[0.0 for _ in range(azimuth_bins)],
        uncertainty_deg=None,
        coverage_fraction=0.0,
        nodata_fraction=1.0,
        warnings=[
            f"{reason} Horizon set to idealised spherical 0.0 deg; outputs are geometric-only and exclude local crater/mountain shadowing."
        ],
        metadata={"geometric_only": True},
    )


def evaluate_site_horizon(
    registry: DEMRegistry,
    site_id: int,
    lat_deg: float,
    lon_deg: float,
    site_db_elevation_m: float | None,
    observer_height_m: float = 1.5,
    coordinate_frame: str = "MOON_ME",
    azimuth_bins: int = 360,
    min_radius_m: float = 100.0,
    max_radius_m: float = 100_000.0,
) -> HorizonComputationResult:
    """Resolve DEM coverage for a site and compute its horizon profile (or geometric fallback)."""
    selection = registry.select_asset_for_site(
        lat_deg=lat_deg,
        lon_deg=lon_deg,
        horizon_max_radius_m=max_radius_m,
    )
    if selection is None:
        return build_geometric_only_horizon(
            site_id=site_id,
            lat_deg=lat_deg,
            lon_deg=lon_deg,
            site_db_elevation_m=site_db_elevation_m,
            observer_height_m=observer_height_m,
            coordinate_frame=coordinate_frame,
            azimuth_bins=azimuth_bins,
        )
    window = registry.read_window_for_site(selection, horizon_max_radius_m=max_radius_m)
    return compute_horizon_from_dem_window(
        site_id=site_id,
        lat_deg=lat_deg,
        lon_deg=lon_deg,
        site_db_elevation_m=site_db_elevation_m,
        window=window,
        observer_height_m=observer_height_m,
        coordinate_frame=coordinate_frame,
        azimuth_bins=azimuth_bins,
        min_radius_m=min_radius_m,
        max_radius_m=max_radius_m,
    )
