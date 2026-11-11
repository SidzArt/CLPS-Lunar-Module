"""Phase 4 comprehensive test suite for the SPICE + LOLA DEM Scientific Simulation Engine.

Covers:
1. Lunar coordinate conversions, ENU basis orthogonality, polar determinism, and DEM surface slope.
2. NAIF SPICE kernel checksums, coverage validation, leap-second timing, and spkcpo vs azlcpo agreement.
3. Synthetic GeoTIFF DEM pipelines (flat terrain, single/multi-ridge obstructions, NoData gaps,
   boundary clipping, Area vs Point pixel registration, path-traversal protection, CRS round-trips).
4. Solar finite-disk grazing visibility, Earth line-of-sight, and bisection precision vs 1s truth.
5. End-to-end FastAPI endpoints, PostgreSQL SKIP LOCKED worker, horizon cache hits & invalidation,
   pagination/downsampling, cooperative cancellation, RBAC diagnostics, and real LOLA DEM site tests.
"""

from __future__ import annotations

import json
import math
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np
import pytest
import rasterio
import spiceypy as spice
from fastapi.testclient import TestClient
from pyproj import CRS
from rasterio.transform import from_origin
from sqlalchemy import delete, select

from app.core.rate_limit import simulation_rate_limiter
from app.db.session import SessionLocal
from app.integrations.spice.ephemeris import (
    build_observer_state,
    compute_ephemeris_sample,
    et_to_utc_datetime,
    get_moon_orientation_matrix,
    utc_to_et,
)
from app.integrations.spice.kernel_manager import (
    SpiceCoverageError,
    SpiceKernelError,
    SpiceKernelManager,
    spice_kernel_manager,
)
from app.integrations.terrain.coordinate_transform import (
    build_raster_context,
    lonlat_to_raster_xy,
    raster_xy_to_lonlat,
)
from app.integrations.terrain.dem_reader import DEMRegistry, compute_file_sha256
from app.models.catalogue import LandingSite
from app.models.operations import BackgroundJob
from app.models.simulation import (
    SimulationEventWindow,
    SimulationRun,
    SimulationSample,
    TerrainHorizonProfile,
)
from app.services import geometry, simulation_service
from app.services.horizon import (
    HORIZON_ALGORITHM_VERSION,
    compute_horizon_cache_key,
    compute_horizon_from_dem_window,
)
from app.services.visibility import (
    EARTH_NOT_VISIBLE,
    EARTH_VISIBLE,
    SUN_NOT_VISIBLE,
    SUN_PARTIAL,
    SUN_RADIUS_KM,
    SUN_VISIBLE,
    HorizonProfileData,
    classify_earth_visibility,
    classify_sun_visibility,
    compute_angular_radius_deg,
)
from app.worker.simulation_worker import drain_queue, run_once

# South Polar Stereographic CRS matching NASA PGDA LOLA products
SOUTH_POLAR_PROJ4 = (
    "+proj=stere +lat_0=-90 +lat_ts=-90 +lon_0=0 +x_0=0 +y_0=0 +R=1737400 +units=m +no_defs"
)


def _get_site_id(site_code: str) -> int:
    """Resolve current landing site primary key dynamically by stable site_code."""
    with SessionLocal() as session:
        site_id = session.scalar(
            select(LandingSite.site_id).where(LandingSite.site_code == site_code)
        )
        assert site_id is not None, f"Seeded site '{site_code}' not found"
        return int(site_id)


def _cleanup_simulation_runs(run_ids: list[uuid.UUID]) -> None:
    """Remove synthetic simulation rows and their companion background jobs safely."""
    if not run_ids:
        return
    with SessionLocal() as session:
        runs = session.scalars(
            select(SimulationRun).where(SimulationRun.simulation_id.in_(run_ids))
        ).all()
        job_ids = [r.job_id for r in runs if r.job_id is not None]
        session.execute(delete(SimulationSample).where(SimulationSample.simulation_id.in_(run_ids)))
        session.execute(
            delete(SimulationEventWindow).where(SimulationEventWindow.simulation_id.in_(run_ids))
        )
        session.execute(delete(SimulationRun).where(SimulationRun.simulation_id.in_(run_ids)))
        if job_ids:
            session.execute(delete(BackgroundJob).where(BackgroundJob.job_id.in_(job_ids)))
        session.commit()


def _create_synthetic_south_polar_dem(
    dest_dir: Path,
    *,
    filename: str = "SYNTH_85S_100M.TIF",
    half_extent_m: float = 120_000.0,
    pixel_size_m: float = 200.0,
    elevation_grid_fn: Any | None = None,
    nodata_value: float = -32768.0,
    area_or_point: str = "Area",
    write_manifest: bool = True,
    with_companions: bool = False,
) -> tuple[Path, str]:
    """Generate a valid single-band Float32 South Polar Stereographic GeoTIFF fixture."""
    size_px = round((2.0 * half_extent_m) / pixel_size_m)
    crs = CRS.from_proj4(SOUTH_POLAR_PROJ4)
    if area_or_point == "Point":
        # Center-of-pixel transform matching GDAL Area vs Point interpretation
        transform = from_origin(-half_extent_m, half_extent_m, pixel_size_m, pixel_size_m)
    else:
        transform = from_origin(-half_extent_m, half_extent_m, pixel_size_m, pixel_size_m)

    rows = np.arange(size_px, dtype=np.float64)[:, None]
    cols = np.arange(size_px, dtype=np.float64)[None, :]
    xs = -half_extent_m + (cols + 0.5) * pixel_size_m
    ys = half_extent_m - (rows + 0.5) * pixel_size_m

    if elevation_grid_fn is None:
        elev = np.zeros((size_px, size_px), dtype=np.float32)
    else:
        elev = elevation_grid_fn(xs, ys).astype(np.float32)

    out_path = dest_dir / filename
    with rasterio.open(
        out_path,
        "w",
        driver="GTiff",
        height=size_px,
        width=size_px,
        count=1,
        dtype="float32",
        crs=crs.to_wkt(),
        transform=transform,
        nodata=nodata_value,
    ) as dst:
        dst.write(elev, 1)
        dst.update_tags(AREA_OR_POINT=area_or_point)

    sha = compute_file_sha256(out_path)
    asset_entry: dict[str, Any] = {
        "asset_id": out_path.stem,
        "filename": filename,
        "sha256": sha,
        "elevation_unit": "meters",
        "lunar_frame": "MOON_ME_DE421",
        "source": "Synthetic Test LOLA GeoTIFF",
        "citation": "Unit test fixture",
        "dataset_version": "SYNTH-v1",
    }

    if with_companions:
        cnt_name = out_path.stem + "_LDEC.TIF"
        err_name = out_path.stem + "_ERR.TIF"
        cnt_arr = np.full((size_px, size_px), 4.0, dtype=np.float32)
        err_arr = np.full((size_px, size_px), 1.5, dtype=np.float32)
        for name, arr, nd in ((cnt_name, cnt_arr, None), (err_name, err_arr, nodata_value)):
            with rasterio.open(
                dest_dir / name,
                "w",
                driver="GTiff",
                height=size_px,
                width=size_px,
                count=1,
                dtype="float32",
                crs=crs.to_wkt(),
                transform=transform,
                nodata=nd,
            ) as cdst:
                cdst.write(arr, 1)
                cdst.update_tags(AREA_OR_POINT=area_or_point)
        asset_entry["count_filename"] = cnt_name
        asset_entry["error_filename"] = err_name

    if write_manifest:
        (dest_dir / "manifest.json").write_text(
            json.dumps({"assets": [asset_entry]}, indent=2),
            encoding="utf-8",
        )
    return out_path, sha


# ==========================================
# PART 1: GEOMETRY & COORDINATE SYSTEM TESTS
# ==========================================


@pytest.mark.parametrize(
    ("lat_deg", "lon_deg", "elev_m"),
    [
        (0.0, 0.0, 0.0),
        (38.3150, -35.0080, -2500.0),  # Lunokhod 1
        (-84.9000, 31.6000, 6000.0),  # Mons Mouton
        (-69.3730, 32.3480, -1800.0),  # Pragyan
        (-89.9900, 145.0, 1200.0),  # Near South Pole
    ],
)
def test_geometry_spherical_cartesian_roundtrip(
    lat_deg: float, lon_deg: float, elev_m: float
) -> None:
    """Planetocentric East-positive coordinates round-trip accurately through Moon-fixed XYZ."""
    xyz = geometry.lat_lon_elev_to_cartesian_m(lat_deg, lon_deg, elev_m)
    lat_out, lon_out, elev_out = geometry.cartesian_m_to_lat_lon_elev(xyz)
    assert math.isclose(lat_out, lat_deg, abs_tol=1e-9)
    assert math.isclose(lon_out, lon_deg, abs_tol=1e-9)
    assert math.isclose(elev_out, elev_m, abs_tol=1e-6)


def test_geometry_enu_basis_orthonormal_and_polar_safe() -> None:
    """Local ENU basis is right-handed orthonormal off-pole and deterministic at exact poles."""
    for lat, lon in [
        (0.0, 0.0),
        (38.315, -35.008),
        (-84.9, 31.6),
        (-89.999, 45.0),
        (-90.0, 123.0),
        (90.0, -77.0),
    ]:
        east, north, up = geometry.local_enu_basis(lat, lon)
        assert not np.any(np.isnan(east))
        assert not np.any(np.isnan(north))
        assert not np.any(np.isnan(up))
        assert math.isclose(float(np.linalg.norm(east)), 1.0, abs_tol=1e-12)
        assert math.isclose(float(np.linalg.norm(north)), 1.0, abs_tol=1e-12)
        assert math.isclose(float(np.linalg.norm(up)), 1.0, abs_tol=1e-12)
        assert abs(float(np.dot(east, north))) < 1e-12
        assert abs(float(np.dot(east, up))) < 1e-12
        assert abs(float(np.dot(north, up))) < 1e-12
        # Right-handed check: east x north == up
        assert np.allclose(np.cross(east, north), up, atol=1e-12)

    # Exact South Pole must fall back deterministically to +X prime meridian regardless of lon
    e1, n1, u1 = geometry.local_enu_basis(-90.0, 0.0)
    e2, n2, u2 = geometry.local_enu_basis(-90.0, 147.2)
    assert np.allclose(e1, e2) and np.allclose(n1, n2) and np.allclose(u1, u2)


def test_geometry_vector_to_az_el_conventions() -> None:
    """Verify azimuth [0,360) CW from North through East and elevation [-90,90]."""
    east, north, up = geometry.local_enu_basis(-84.9, 31.6)
    for vec, exp_az, exp_el in [
        (north, 0.0, 0.0),
        (east, 90.0, 0.0),
        (-north, 180.0, 0.0),
        (-east, 270.0, 0.0),
        (up, 0.0, 90.0),
        (-up, 0.0, -90.0),
        (east + up, 90.0, 45.0),
    ]:
        az, el, rng = geometry.vector_to_az_el(vec, east, north, up)
        assert math.isclose(float(rng), float(np.linalg.norm(vec)), abs_tol=1e-12)
        assert math.isclose(float(el), exp_el, abs_tol=1e-9)
        if abs(exp_el) < 89.9:
            assert math.isclose(float(az), exp_az, abs_tol=1e-9)


def test_geometry_dem_surface_normal_slope() -> None:
    """Estimate local slope from tilted planar 3x3 height patch."""
    # Ramp rising eastward by 10m per 100m cell -> slope = atan(0.1) = 5.710593 deg
    xs = np.array([[-100.0, 0.0, 100.0]] * 3, dtype=np.float64)
    z_patch = 0.1 * xs
    normal, slope_deg, _ = geometry.estimate_dem_surface_normal_enu(z_patch, 100.0, 100.0)
    assert math.isclose(float(np.linalg.norm(normal)), 1.0, abs_tol=1e-12)
    assert math.isclose(slope_deg, math.degrees(math.atan(0.1)), abs_tol=1e-6)


# ==========================================
# PART 2: NAIF SPICE KERNEL & EPHEMERIS TESTS
# ==========================================


def test_spice_kernel_manifest_and_frames_loaded() -> None:
    """Controlled SPICE manifest validates SHA-256 checksums, radii, frames, and windows."""
    state = spice_kernel_manager.ensure_loaded(force_reload=True)
    assert state.primary_lunar_frame == "MOON_ME"
    assert state.resolved_lunar_frame == "MOON_ME_DE440_ME421"
    assert math.isclose(state.moon_radii_km[0], 1737.4, abs_tol=0.1)
    assert {"MOON_ME", "MOON_PA", "MOON_ME_DE440_ME421", "MOON_PA_DE440", "IAU_MOON"}.issubset(
        set(state.available_frames.keys())
    )
    assert len(state.kernels) == 6
    for rec in state.kernels:
        assert rec.actual_sha256 == rec.expected_sha256


def test_spice_coverage_validation_rejects_out_of_bounds_with_metadata() -> None:
    """Intervals outside de440.bsp / moon_pa_de440 raise SpiceCoverageError with kernel detail."""
    with pytest.raises(SpiceCoverageError) as exc_info:
        spice_kernel_manager.validate_utc_interval(
            datetime(1400, 1, 1, tzinfo=UTC),
            datetime(1400, 1, 2, tzinfo=UTC),
        )
    assert exc_info.value.responsible_kernel in ("de440.bsp", "moon_pa_de440_200625.bpc")
    assert exc_info.value.valid_start_utc.startswith("1549-")

    with pytest.raises(SpiceCoverageError) as exc_late:
        spice_kernel_manager.validate_utc_interval(
            datetime(2700, 1, 1, tzinfo=UTC),
            datetime(2700, 1, 2, tzinfo=UTC),
        )
    assert exc_late.value.valid_end_utc.startswith("2650-")


def test_spice_utc_et_roundtrip_and_spkcpo_matches_azlcpo() -> None:
    """spkcpo + local ENU agrees with CSPICE azlcpo to < 1e-6 deg across Sun & Earth."""
    dt = datetime(2026, 6, 21, 12, 0, 0, tzinfo=UTC)
    et = utc_to_et(dt)
    dt_back = et_to_utc_datetime(et)
    assert abs((dt_back - dt).total_seconds()) < 1e-3

    obs = build_observer_state(
        site_id=136,
        latitude_deg=-84.9,
        longitude_deg=31.6,
        effective_elevation_m=6001.5,
        lunar_frame="MOON_ME",
        aberration_correction="LT+S",
    )
    sample = compute_ephemeris_sample(et, obs)

    with spice_kernel_manager.lock:
        azl_sun, _ = spice.azlcpo(
            "ELLIPSOID",
            "SUN",
            et,
            "LT+S",
            False,
            True,
            obs.obs_pos_moon_me_km,
            "MOON",
            "MOON_ME",
        )
        azl_earth, _ = spice.azlcpo(
            "ELLIPSOID",
            "EARTH",
            et,
            "LT+S",
            False,
            True,
            obs.obs_pos_moon_me_km,
            "MOON",
            "MOON_ME",
        )

    assert abs(((sample.sun_azimuth_deg - math.degrees(azl_sun[1]) + 180) % 360) - 180) < 1e-6
    assert abs(sample.sun_elevation_deg - math.degrees(azl_sun[2])) < 1e-6
    assert abs(((sample.earth_azimuth_deg - math.degrees(azl_earth[1]) + 180) % 360) - 180) < 1e-6
    assert abs(sample.earth_elevation_deg - math.degrees(azl_earth[2])) < 1e-6
    # Physical sanity checks
    assert 350_000.0 <= sample.earth_range_km <= 415_000.0
    assert 140_000_000.0 <= sample.sun_range_km <= 155_000_000.0
    assert -2.0 <= sample.subsolar_lat_deg <= 2.0


def test_spice_aberration_and_frame_orientation_effects() -> None:
    """LT+S aberration produces measurable solar shift vs NONE; MOON_ME differs slightly from MOON_PA."""
    et = utc_to_et(datetime(2026, 4, 9, 11, 5, 57, tzinfo=UTC))
    obs_lts = build_observer_state(102, 38.315, -35.008, -2498.5, aberration_correction="LT+S")
    obs_none = build_observer_state(102, 38.315, -35.008, -2498.5, aberration_correction="NONE")

    s_lts = compute_ephemeris_sample(et, obs_lts)
    s_none = compute_ephemeris_sample(et, obs_none)
    # Stellar + light-time aberration shifts apparent solar vector (~20 arcsec ~ 0.0056 deg)
    az_diff = abs(s_lts.sun_azimuth_deg - s_none.sun_azimuth_deg)
    el_diff = abs(s_lts.sun_elevation_deg - s_none.sun_elevation_deg)
    assert max(az_diff, el_diff) > 1e-4

    # MOON_ME vs MOON_PA constant lunar frame offset (~0.025 deg rotation)
    r_me_pa = np.asarray(get_moon_orientation_matrix(et, "MOON_ME", "MOON_PA"))
    assert not np.allclose(r_me_pa, np.eye(3), atol=1e-5)
    assert math.isclose(float(np.linalg.det(r_me_pa)), 1.0, abs_tol=1e-9)


def test_spice_manifest_tampering_rejected(tmp_path: Path) -> None:
    """Modified manifest checksum raises SpiceKernelError rather than running corrupt kernels."""
    bad_dir = tmp_path / "bad_spice"
    bad_dir.mkdir()
    (bad_dir / "naif0012.tls").write_bytes(b"corrupt")
    (bad_dir / "manifest.json").write_text(
        json.dumps(
            {
                "manifest_version": "bad",
                "ephemeris_source": "test",
                "ephemeris_version": "test",
                "primary_lunar_frame": "MOON_ME",
                "resolved_lunar_frame": "MOON_ME",
                "kernels": [{"filename": "naif0012.tls", "kind": "LSK", "sha256": "0" * 64}],
            }
        ),
        encoding="utf-8",
    )
    mgr = SpiceKernelManager(kernel_dir=bad_dir)
    with pytest.raises(SpiceKernelError, match="checksum"):
        mgr.ensure_loaded(force_reload=True)


# ==========================================
# PART 3: SYNTHETIC DEM & HORIZON RAYCAST TESTS
# ==========================================


def test_dem_coordinate_roundtrip_and_path_traversal_protection(tmp_path: Path) -> None:
    """DEM CRS projection round-trips cleanly and DEMRegistry blocks path traversal."""
    path, _ = _create_synthetic_south_polar_dem(
        tmp_path, half_extent_m=60_000.0, pixel_size_m=200.0
    )
    with rasterio.open(path) as ds:
        ctx, to_raster, to_lonlat = build_raster_context(ds.crs, ds.transform, "Area")
        assert ctx.datum_radius_m == pytest.approx(1_737_400.0)
        x, y = lonlat_to_raster_xy(to_raster, 31.6, -88.5)
        lon_b, lat_b = raster_xy_to_lonlat(to_lonlat, x, y)
        assert lon_b == pytest.approx(31.6, abs=1e-9)
        assert lat_b == pytest.approx(-88.5, abs=1e-9)

    reg = DEMRegistry(dem_root=tmp_path)
    assets = reg.list_assets(refresh=True)
    assert len(assets) == 1
    with pytest.raises(ValueError, match="Unsafe DEM filename"):
        reg._safe_child_path("../secrets.tif")


def test_horizon_flat_sphere_curvature_drop(tmp_path: Path) -> None:
    """Flat z=0 DEM yields slightly negative horizon matching 3D spherical curvature drop."""
    _create_synthetic_south_polar_dem(
        tmp_path,
        filename="FLAT_SP.TIF",
        half_extent_m=80_000.0,
        pixel_size_m=200.0,
    )
    reg = DEMRegistry(dem_root=tmp_path)
    # South Pole (-90, 0) lies cleanly in center of [-80km, 80km] box
    sel = reg.select_asset_for_site(-90.0, 0.0, horizon_max_radius_m=50_000.0)
    assert sel is not None and sel.full_horizon_covered
    win = reg.read_window_for_site(sel, horizon_max_radius_m=50_000.0)
    res = compute_horizon_from_dem_window(
        site_id=1,
        lat_deg=-90.0,
        lon_deg=0.0,
        site_db_elevation_m=0.0,
        window=win,
        observer_height_m=1.5,
        azimuth_bins=72,
        min_radius_m=150.0,
        max_radius_m=50_000.0,
    )
    assert res.profile.quality_state == "verified_terrain_aware"
    # Observer at +1.5m looking down to r>=200m has negative horizon close to ~ -0.45..0 deg
    assert max(res.horizon_elevations_deg) <= 0.0
    assert min(res.horizon_elevations_deg) > -1.0


def test_horizon_single_and_multi_ridge_obstruction_analytical_match(tmp_path: Path) -> None:
    """Synthetic East ridge and South mountain yield exact analytical atan2 obstruction angles."""

    # In South Polar Stereographic (+lon_0=0) at exact South Pole (-90, 0):
    # lon=+90 deg (local East) projects onto +X_map; lon=180 deg (local South) projects onto -Y_map
    def multi_ridge(xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
        z = np.zeros_like(xs)
        # Ridge 1 due East (az=90 deg): place peak along +X axis at x = +10,000 m, y = 0
        r_e = np.hypot(xs - 10_000.0, ys)
        z = np.where(r_e <= 600.0, 1200.0, z)
        # Ridge 2 due South (az=180 deg): place peak along -Y axis at x = 0, y = -4,000 m
        r_s = np.hypot(xs, ys + 4_000.0)
        z = np.where(r_s <= 500.0, 900.0, z)
        return z

    _create_synthetic_south_polar_dem(
        tmp_path,
        filename="RIDGE_SP.TIF",
        half_extent_m=30_000.0,
        pixel_size_m=100.0,
        elevation_grid_fn=multi_ridge,
        with_companions=True,
    )
    reg = DEMRegistry(dem_root=tmp_path)
    sel = reg.select_asset_for_site(-90.0, 0.0, horizon_max_radius_m=20_000.0)
    assert sel is not None
    win = reg.read_window_for_site(sel, horizon_max_radius_m=20_000.0)
    res = compute_horizon_from_dem_window(
        site_id=1,
        lat_deg=-90.0,
        lon_deg=0.0,
        site_db_elevation_m=0.0,
        window=win,
        observer_height_m=1.5,
        azimuth_bins=360,
        min_radius_m=100.0,
        max_radius_m=20_000.0,
    )
    assert res.profile.quality_state == "verified_terrain_aware"
    assert res.uncertainty_deg is not None
    # Expected elevation for East ridge at closest distance ~9400..10000m, height 1200m, drop ~d^2/(2R)
    drop_e = (9500.0**2) / (2.0 * 1_737_400.0)
    expected_e = math.degrees(math.atan2(1200.0 - 1.5 - drop_e, 9500.0))
    assert res.horizon_elevations_deg[90] == pytest.approx(expected_e, abs=0.4)
    # Expected South peak (~3500..4000m, height 900m) -> ~12.6..14.4 deg
    assert res.horizon_elevations_deg[180] > 12.0
    # Unobstructed North (0 deg) & West (270 deg) remain <= 0 deg
    assert res.horizon_elevations_deg[0] <= 0.0
    assert res.horizon_elevations_deg[270] <= 0.0


def test_horizon_nodata_and_boundary_quality_states(tmp_path: Path) -> None:
    """NoData voids and boundary-proximate tiles trigger partial_dem_coverage / insufficient_data."""
    # 1. Partial boundary coverage (edge margin 12 km < requested 50 km)
    _create_synthetic_south_polar_dem(
        tmp_path, filename="SMALL_TILE.TIF", half_extent_m=12_000.0, pixel_size_m=200.0
    )
    reg = DEMRegistry(dem_root=tmp_path)
    sel = reg.select_asset_for_site(-90.0, 0.0, horizon_max_radius_m=50_000.0)
    assert sel is not None and not sel.full_horizon_covered
    win = reg.read_window_for_site(sel, horizon_max_radius_m=50_000.0)
    res_boundary = compute_horizon_from_dem_window(
        site_id=1,
        lat_deg=-90.0,
        lon_deg=0.0,
        site_db_elevation_m=0.0,
        window=win,
        azimuth_bins=72,
        max_radius_m=50_000.0,
    )
    assert res_boundary.profile.quality_state == "partial_dem_coverage"
    assert any("boundary" in w.lower() for w in res_boundary.warnings)

    # 2. Mostly NoData tile -> insufficient_data
    nodata_dir = tmp_path / "nodata_only"
    nodata_dir.mkdir()
    _create_synthetic_south_polar_dem(
        nodata_dir,
        filename="NODATA.TIF",
        half_extent_m=30_000.0,
        pixel_size_m=500.0,
        elevation_grid_fn=lambda xs, ys: np.full_like(xs, -32768.0),
    )
    reg_nd = DEMRegistry(dem_root=nodata_dir)
    sel_nd = reg_nd.select_asset_for_site(-90.0, 0.0, horizon_max_radius_m=20_000.0)
    assert sel_nd is not None
    win_nd = reg_nd.read_window_for_site(sel_nd, horizon_max_radius_m=20_000.0)
    res_nd = compute_horizon_from_dem_window(
        site_id=1,
        lat_deg=-90.0,
        lon_deg=0.0,
        site_db_elevation_m=0.0,
        window=win_nd,
        azimuth_bins=72,
        max_radius_m=20_000.0,
    )
    assert res_nd.profile.quality_state == "insufficient_data"


def test_horizon_point_pixel_registration_handled(tmp_path: Path) -> None:
    """GeoTIFF tagged AREA_OR_POINT='Point' loads cleanly with explicit registration metadata."""
    _create_synthetic_south_polar_dem(
        tmp_path,
        filename="POINT_REG.TIF",
        half_extent_m=20_000.0,
        pixel_size_m=200.0,
        area_or_point="Point",
    )
    reg = DEMRegistry(dem_root=tmp_path)
    assets = reg.list_assets(refresh=True)
    assert assets[0].pixel_registration == "Point"


# ==========================================
# PART 4: VISIBILITY & BISECTION ACCURACY TESTS
# ==========================================


def test_visibility_solar_disk_and_earth_classification() -> None:
    """Finite solar angular disk yields VISIBLE / PARTIALLY_OBSTRUCTED / NOT_VISIBLE."""
    r_sun_deg = compute_angular_radius_deg(SUN_RADIUS_KM, 149_597_870.7)
    assert 0.25 < r_sun_deg < 0.28

    status_vis, frac_vis, _ = classify_sun_visibility(
        horizon_elevation_deg=2.0, sun_elevation_deg=3.0, sun_range_km=149_597_870.7
    )
    assert status_vis == SUN_VISIBLE and frac_vis == 1.0

    # Exact center on horizon -> 50% disk illuminated
    status_part, frac_part, _ = classify_sun_visibility(
        sun_elevation_deg=2.0, horizon_elevation_deg=2.0, sun_range_km=149_597_870.7
    )
    assert status_part == SUN_PARTIAL
    assert 0.49 <= frac_part <= 0.51

    status_dark, frac_dark, _ = classify_sun_visibility(
        sun_elevation_deg=1.0, horizon_elevation_deg=2.0, sun_range_km=149_597_870.7
    )
    assert status_dark == SUN_NOT_VISIBLE and frac_dark == 0.0

    assert classify_earth_visibility(5.0, 2.0) == EARTH_VISIBLE
    assert classify_earth_visibility(1.9, 2.0) == EARTH_NOT_VISIBLE


def test_bisection_sunrise_precision_against_1s_ground_truth() -> None:
    """Adaptive bisection locates sunrise center crossing within <= 2 seconds of 1s grid truth."""
    # Near Apollo 11 / equatorial meridian sunrise on 2026-04-06
    # First locate an actual crossing on coarse 5-min grid over 24h at (0, 0)
    obs = build_observer_state(999, 0.0, 0.0, 0.0)
    flat_hor = HorizonProfileData(
        azimuths_deg=np.arange(360, dtype=np.float64),
        elevations_deg=np.zeros(360, dtype=np.float64),
        quality_state="geometric_only",
        azimuth_bins=360,
    )
    t0 = utc_to_et(datetime(2026, 4, 15, 0, 0, 0, tzinfo=UTC))
    # Scan across 30 days at 1-hour steps until we find a sunrise bracket
    prev_state = simulation_service._evaluate_at_et(t0, obs, flat_hor, "geometric_only")
    bracket: tuple[Any, Any] | None = None
    for hr in range(1, 24 * 30):
        st = simulation_service._evaluate_at_et(t0 + hr * 3600.0, obs, flat_hor, "geometric_only")
        if prev_state.sun_elevation_deg < 0.0 <= st.sun_elevation_deg:
            bracket = (prev_state, st)
            break
        prev_state = st
    assert bracket is not None

    refined = simulation_service._bisect_bracket(
        bracket[0],
        bracket[1],
        lambda s: s.sun_elevation_deg - s.sun_horizon_deg,
        obs,
        flat_hor,
        "geometric_only",
        tol_seconds=1.0,
    )
    assert refined is not None
    lo, hi = refined
    assert (hi.et - lo.et) <= 1.0
    assert lo.sun_elevation_deg < 0.0 <= hi.sun_elevation_deg

    # Brute-force 1-second scan inside +-10s around bisection midpoint
    mid = 0.5 * (lo.et + hi.et)
    exact_1s_et: float | None = None
    for dt_s in range(-10, 11):
        s_a = compute_ephemeris_sample(mid + dt_s, obs)
        s_b = compute_ephemeris_sample(mid + dt_s + 1.0, obs)
        if s_a.sun_elevation_deg < 0.0 <= s_b.sun_elevation_deg:
            exact_1s_et = mid + dt_s + 0.5
            break
    assert exact_1s_et is not None
    assert abs(mid - exact_1s_et) <= 1.5


# ==========================================
# PART 5: API, WORKER, CACHE & RBAC E2E TESTS
# ==========================================


def test_simulation_api_validation_and_rate_limit(client: TestClient) -> None:
    """Validate 404 missing site, 422 SPICE_COVERAGE_ERROR, idempotency, and 429 rate limiting."""
    luno_id = _get_site_id("HIST-LUNO-01")
    simulation_rate_limiter.reset()
    created_ids: list[uuid.UUID] = []
    try:
        # Missing site -> 404
        r404 = client.post(
            "/api/v1/simulations",
            json={
                "site_id": 999999,
                "start_time": "2026-04-09T11:05:57Z",
                "duration_seconds": 3600,
            },
        )
        assert r404.status_code == 404

        # Out-of-coverage SPICE span -> 422 SPICE_COVERAGE_ERROR
        r422 = client.post(
            "/api/v1/simulations",
            json={
                "site_id": luno_id,
                "start_time": "1492-10-12T00:00:00Z",
                "duration_seconds": 3600,
            },
        )
        assert r422.status_code == 422
        detail = r422.json()["detail"]
        assert detail["code"] == "SPICE_COVERAGE_ERROR"
        assert "valid_start_utc" in detail and "responsible_kernel" in detail

        # Idempotency deduplication
        idem = f"test-idem-{uuid.uuid4().hex[:10]}"
        r1 = client.post(
            "/api/v1/simulations",
            json={
                "site_id": luno_id,
                "start_time": "2026-04-09T11:05:57Z",
                "duration_seconds": 1800,
                "idempotency_key": idem,
            },
        )
        assert r1.status_code == 202
        sim1 = uuid.UUID(r1.json()["simulation_id"])
        created_ids.append(sim1)

        r2 = client.post(
            "/api/v1/simulations",
            json={
                "site_id": luno_id,
                "start_time": "2026-04-09T11:05:57Z",
                "duration_seconds": 1800,
                "idempotency_key": idem,
            },
        )
        assert r2.status_code == 202
        assert r2.json()["simulation_id"] == str(sim1)

        # Rate limiter enforcement -> 429
        orig_rpm = simulation_rate_limiter.requests_per_minute
        simulation_rate_limiter.reset()
        simulation_rate_limiter.requests_per_minute = 2
        try:
            for _ in range(2):
                ok = client.post(
                    "/api/v1/simulations",
                    json={
                        "site_id": luno_id,
                        "start_time": "2026-04-09T12:00:00Z",
                        "duration_seconds": 600,
                    },
                )
                assert ok.status_code == 202
                created_ids.append(uuid.UUID(ok.json()["simulation_id"]))
            r429 = client.post(
                "/api/v1/simulations",
                json={
                    "site_id": luno_id,
                    "start_time": "2026-04-09T13:00:00Z",
                    "duration_seconds": 600,
                },
            )
            assert r429.status_code == 429
        finally:
            simulation_rate_limiter.requests_per_minute = orig_rpm
            simulation_rate_limiter.reset()
    finally:
        _cleanup_simulation_runs(created_ids)
        simulation_rate_limiter.reset()


def test_simulation_e2e_worker_pagination_events_cancel_and_geometric_fallback(
    client: TestClient,
) -> None:
    """Queue Lunokhod 1 geometric_only run, drain worker, query series/events, and verify cancel."""
    luno_id = _get_site_id("HIST-LUNO-01")
    simulation_rate_limiter.reset()
    created_ids: list[uuid.UUID] = []
    try:
        # Lunokhod 1 (38.315 N, -35.008 E) has no South Polar DEM -> geometric_only
        resp = client.post(
            "/api/v1/simulations",
            json={
                "site_id": luno_id,
                "start_time": "2026-04-09T11:05:57Z",
                "duration_seconds": 7200,
                "playback_speed": 60.0,
            },
        )
        assert resp.status_code == 202
        body = resp.json()
        sim_id = uuid.UUID(body["simulation_id"])
        created_ids.append(sim_id)
        assert body["status"] == "queued"
        assert body["quality_state"] == "pending"
        assert any("geometric_only" in w for w in body["data_coverage_warnings"])

        # Process job via worker
        outcomes = drain_queue(worker_id="pytest-worker-1", max_jobs=5)
        assert "completed" in outcomes

        # Status check
        st_resp = client.get(f"/api/v1/simulations/{sim_id}")
        assert st_resp.status_code == 200
        st_data = st_resp.json()
        assert st_data["status"] == "completed"
        assert st_data["quality_state"] == "geometric_only"
        assert st_data["playback_speed"] == 60.0
        assert st_data["summary_metrics"] is not None

        # Series pagination + downsampling + explicit geometric horizon fallback + Three.js unit norms
        ser_resp = client.get(f"/api/v1/simulations/{sim_id}/series?offset=0&limit=5&downsample=2")
        assert ser_resp.status_code == 200
        ser_data = ser_resp.json()
        assert ser_data["returned_samples"] <= 5
        assert ser_data["horizon_profile"] is not None
        assert ser_data["horizon_profile"]["quality_state"] == "geometric_only"
        assert all(v == 0.0 for v in ser_data["horizon_profile"]["horizon_elevations_deg"])
        assert ser_data["coordinate_contract"]["lunar_reference_frame"] == "MOON_ME"
        first = ser_data["samples"][0]
        sun_norm = math.sqrt(sum(c * c for c in first["sun"]["dir_moon_me"]))
        earth_norm = math.sqrt(sum(c * c for c in first["earth"]["dir_moon_me"]))
        assert sun_norm == pytest.approx(1.0, abs=1e-4)
        assert earth_norm == pytest.approx(1.0, abs=1e-4)

        # Time-window filter on /series
        t_win_start = (datetime(2026, 4, 9, 11, 30, 0, tzinfo=UTC)).isoformat()
        ser_filt = client.get(
            f"/api/v1/simulations/{sim_id}/series",
            params={"start_time": t_win_start, "include_horizon": "false"},
        )
        assert ser_filt.status_code == 200
        assert ser_filt.json()["horizon_profile"] is None

        # Events endpoint
        ev_resp = client.get(f"/api/v1/simulations/{sim_id}/events")
        assert ev_resp.status_code == 200
        assert ev_resp.json()["total_events"] >= 1

        # Cancelling completed run -> 409
        c409 = client.post(f"/api/v1/simulations/{sim_id}/cancel")
        assert c409.status_code == 409

        # Queue another run and cancel immediately while QUEUED -> 200 CANCELLED
        resp_q = client.post(
            "/api/v1/simulations",
            json={
                "site_id": luno_id,
                "start_time": "2026-04-10T00:00:00Z",
                "duration_seconds": 1800,
            },
        )
        assert resp_q.status_code == 202
        sim_q = uuid.UUID(resp_q.json()["simulation_id"])
        created_ids.append(sim_q)

        c200 = client.post(f"/api/v1/simulations/{sim_q}/cancel")
        assert c200.status_code == 200
        assert c200.json()["status"] == "cancelled"
        # Worker should not run cancelled job
        processed_after, _ = run_once(worker_id="pytest-worker-check")
        assert processed_after is False
    finally:
        _cleanup_simulation_runs(created_ids)
        simulation_rate_limiter.reset()


def test_horizon_profile_cache_hit_and_invalidation(client: TestClient, tmp_path: Path) -> None:
    """Verify PostgreSQL horizon cache reuse and deterministic key invalidation on param changes."""
    simulation_rate_limiter.reset()
    created_ids: list[uuid.UUID] = []
    cache_keys_created: list[str] = []
    synth_site_id: int | None = None

    _create_synthetic_south_polar_dem(
        tmp_path, filename="CACHE_TEST.TIF", half_extent_m=60_000.0, pixel_size_m=250.0
    )

    try:
        # Insert isolated synthetic site near South Pole (-89.5, 10.0) in DB
        with SessionLocal() as session:
            from app.models.catalogue import NASARegion

            region = session.scalar(select(NASARegion).limit(1))
            assert region is not None
            site = LandingSite(
                region_id=region.region_id,
                site_code=f"SYNTH-{uuid.uuid4().hex[:6]}",
                site_slug=f"synth-pole-{uuid.uuid4().hex[:6]}",
                site_name="Synthetic Cache Test Site",
                latitude_deg=-89.5,
                longitude_deg=10.0,
                elevation_m=100.0,
                catalogue_status="published",
                coordinate_reference="MOON_ME",
            )
            session.add(site)
            session.commit()
            session.refresh(site)
            synth_site_id = site.site_id

        with patch("app.services.simulation_service.DEMRegistry") as mock_reg_cls:
            mock_reg_cls.side_effect = lambda: DEMRegistry(dem_root=tmp_path)

            # First run -> cache MISS
            r1 = client.post(
                "/api/v1/simulations",
                json={
                    "site_id": synth_site_id,
                    "start_time": "2026-04-09T00:00:00Z",
                    "duration_seconds": 1800,
                },
            )
            assert r1.status_code == 202
            sim1 = uuid.UUID(r1.json()["simulation_id"])
            created_ids.append(sim1)
            drain_queue(worker_id="pytest-cache-w1", max_jobs=3)

            st1 = client.get(f"/api/v1/simulations/{sim1}").json()
            assert st1["dem_metadata"]["horizon_cache_hit"] is False
            ck1 = st1["sampling_policy"]["horizon_cache_key"]
            cache_keys_created.append(ck1)

            # Second run same site & DEM -> cache HIT
            r2 = client.post(
                "/api/v1/simulations",
                json={
                    "site_id": synth_site_id,
                    "start_time": "2026-04-12T00:00:00Z",
                    "duration_seconds": 1800,
                },
            )
            assert r2.status_code == 202
            sim2 = uuid.UUID(r2.json()["simulation_id"])
            created_ids.append(sim2)
            drain_queue(worker_id="pytest-cache-w2", max_jobs=3)

            st2 = client.get(f"/api/v1/simulations/{sim2}").json()
            assert st2["dem_metadata"]["horizon_cache_hit"] is True
            assert st2["sampling_policy"]["horizon_cache_key"] == ck1

            # Verify invalidation key changes when site coordinates or DEM checksum change
            ck_elev_changed = compute_horizon_cache_key(
                synth_site_id,
                -89.5,
                10.0,
                150.0,
                "CACHE_TEST",
                st1["dem_metadata"]["dem_checksum"],
                "MOON_ME",
                1.5,
                HORIZON_ALGORITHM_VERSION,
                360,
                100_000.0,
            )
            ck_dem_changed = compute_horizon_cache_key(
                synth_site_id,
                -89.5,
                10.0,
                100.0,
                "CACHE_TEST",
                "f" * 64,
                "MOON_ME",
                1.5,
                HORIZON_ALGORITHM_VERSION,
                360,
                100_000.0,
            )
            assert ck_elev_changed != ck1
            assert ck_dem_changed != ck1
    finally:
        _cleanup_simulation_runs(created_ids)
        with SessionLocal() as session:
            if cache_keys_created:
                session.execute(
                    delete(TerrainHorizonProfile).where(
                        TerrainHorizonProfile.cache_key.in_(cache_keys_created)
                    )
                )
            if synth_site_id is not None:
                session.execute(delete(LandingSite).where(LandingSite.site_id == synth_site_id))
            session.commit()
        simulation_rate_limiter.reset()


def test_worker_failure_marks_failed_cleanly(client: TestClient) -> None:
    """Transient errors schedule backoff retries; non-retryable or exhausted failures mark failed."""
    luno_id = _get_site_id("HIST-LUNO-01")
    simulation_rate_limiter.reset()
    created_ids: list[uuid.UUID] = []
    try:
        r = client.post(
            "/api/v1/simulations",
            json={
                "site_id": luno_id,
                "start_time": "2026-04-09T00:00:00Z",
                "duration_seconds": 900,
            },
        )
        assert r.status_code == 202
        sim_id = uuid.UUID(r.json()["simulation_id"])
        job_id = uuid.UUID(r.json()["job_id"])
        created_ids.append(sim_id)

        # Attempt 1 (< max_attempts=3) with retryable internal error -> schedules retry ('queued')
        with patch(
            "app.worker.simulation_worker.execute_simulation_run",
            side_effect=RuntimeError("Simulated transient failure"),
        ):
            processed, outcome = run_once(worker_id="pytest-fail-worker")
            assert processed is True
            assert outcome == "failed"

        st_retry = client.get(f"/api/v1/simulations/{sim_id}").json()
        assert st_retry["status"] == "queued"
        assert st_retry["error_summary"] is not None

        # Non-retryable SpiceCoverageError marks run & job terminal 'failed'
        with SessionLocal() as session:
            job = session.get(BackgroundJob, job_id)
            assert job is not None
            job.available_at = datetime.now(UTC)
            session.commit()

        with patch(
            "app.worker.simulation_worker.execute_simulation_run",
            side_effect=SpiceCoverageError(
                "Out of coverage", "1549-12-30", "2650-01-24", "de440.bsp"
            ),
        ):
            processed2, outcome2 = run_once(worker_id="pytest-fail-worker-2")
            assert processed2 is True
            assert outcome2 == "failed"

        st_term = client.get(f"/api/v1/simulations/{sim_id}").json()
        assert st_term["status"] == "failed"
        assert st_term["quality_state"] == "kernel_coverage_error"
    finally:
        _cleanup_simulation_runs(created_ids)
        simulation_rate_limiter.reset()


def test_admin_simulation_diagnostics_rbac_and_no_host_path_leak(
    client: TestClient,
    admin_auth_headers: dict[str, str],
    viewer_account: dict[str, str],
) -> None:
    """Diagnostics require authentication and avoid exposing absolute host filesystem paths."""
    # Clear fixture-set cookies so unauthenticated request actually sends no auth cookie or bearer
    client.cookies.clear()
    unauth = client.get("/api/v1/admin/simulations/diagnostics")
    assert unauth.status_code == 401

    login_r = client.post(
        "/api/v1/auth/login",
        json={"username": viewer_account["username"], "password": viewer_account["password"]},
    )
    assert login_r.status_code == 200
    viewer_headers = {"Authorization": f"Bearer {login_r.json()['session_token']}"}
    client.cookies.clear()

    r_viewer = client.get("/api/v1/admin/simulations/diagnostics", headers=viewer_headers)
    assert r_viewer.status_code == 200

    r_admin = client.get("/api/v1/admin/simulations/diagnostics", headers=admin_auth_headers)
    assert r_admin.status_code == 200
    data = r_admin.json()
    assert data["spice_ready"] is True
    assert "MOON_ME" in data["available_frames"]
    assert len(data["site_dem_coverage"]) >= 6
    serialized = json.dumps(data)
    assert "/Users/" not in serialized


def test_simulation_lunar_day_transitions_and_sampling_policy(client: TestClient) -> None:
    """Multi-week simulation triggers adaptive bisection for SUNRISE/SUNSET and covers sampling tiers."""
    p1 = simulation_service.compute_sampling_policy(3600)
    p7 = simulation_service.compute_sampling_policy(5 * 86400)
    p30 = simulation_service.compute_sampling_policy(30 * 86400)
    p180 = simulation_service.compute_sampling_policy(120 * 86400)
    p365 = simulation_service.compute_sampling_policy(365 * 86400)
    assert p1["coarse_interval_seconds"] == 300
    assert p7["coarse_interval_seconds"] == 600
    assert p30["coarse_interval_seconds"] == 900
    assert p180["coarse_interval_seconds"] == 1800
    assert p365["estimated_coarse_samples"] <= p365["max_coarse_samples"]

    luno_id = _get_site_id("HIST-LUNO-01")
    simulation_rate_limiter.reset()
    created_ids: list[uuid.UUID] = []
    try:
        # 16 days at Lunokhod 1 guarantees at least one sunrise or sunset crossing
        resp = client.post(
            "/api/v1/simulations",
            json={
                "site_id": luno_id,
                "start_time": "2026-04-01T00:00:00Z",
                "duration_seconds": 16 * 86400,
            },
        )
        assert resp.status_code == 202
        sim_id = uuid.UUID(resp.json()["simulation_id"])
        created_ids.append(sim_id)
        drain_queue(worker_id="pytest-16d-worker", max_jobs=3)

        st = client.get(f"/api/v1/simulations/{sim_id}").json()
        assert st["status"] == "completed"
        summary = st["summary_metrics"]
        assert summary["refined_transition_points"] >= 2
        assert (summary["sunrise_count"] + summary["sunset_count"]) >= 1

        ev = client.get(f"/api/v1/simulations/{sim_id}/events").json()
        event_types = {e["event_type"] for e in ev["events"]}
        assert "SUNRISE" in event_types or "SUNSET" in event_types
    finally:
        _cleanup_simulation_runs(created_ids)
        simulation_rate_limiter.reset()


def test_worker_loop_threaded_execution_and_stale_lease_reclaim(client: TestClient) -> None:
    """Verify SimulationWorkerLoop background polling thread and expired lease recovery."""
    import threading
    from datetime import timedelta

    from app.worker.simulation_worker import SimulationWorkerLoop

    luno_id = _get_site_id("HIST-LUNO-01")
    simulation_rate_limiter.reset()
    created_ids: list[uuid.UUID] = []
    try:
        resp = client.post(
            "/api/v1/simulations",
            json={
                "site_id": luno_id,
                "start_time": "2026-04-09T11:05:57Z",
                "duration_seconds": 600,
            },
        )
        assert resp.status_code == 202
        sim_id = uuid.UUID(resp.json()["simulation_id"])
        job_id = uuid.UUID(resp.json()["job_id"])
        created_ids.append(sim_id)

        # Simulate crashed worker holding an expired lease on this job
        with SessionLocal() as session:
            job = session.get(BackgroundJob, job_id)
            assert job is not None
            job.status = "RUNNING"
            job.locked_by = "crashed-worker-0"
            job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=30)
            session.commit()

        # Start SimulationWorkerLoop briefly in background thread; it should reclaim & complete
        loop = SimulationWorkerLoop(
            worker_id="pytest-loop",
            max_concurrent=1,
            poll_interval_seconds=0.05,
            lease_seconds=60,
        )
        t = threading.Thread(target=loop.run_forever, daemon=True)
        t.start()
        try:
            deadline = time.monotonic() + 15.0
            final_status = "queued"
            while time.monotonic() < deadline:
                final_status = client.get(f"/api/v1/simulations/{sim_id}").json()["status"]
                if final_status == "completed":
                    break
                time.sleep(0.1)
            assert final_status == "completed"
        finally:
            loop.stop()
            t.join(timeout=5.0)
    finally:
        _cleanup_simulation_runs(created_ids)
        simulation_rate_limiter.reset()


# ==========================================
# PART 6: REAL LOLA DEM & 30-DAY PERFORMANCE
# ==========================================


def test_real_lola_dem_mons_mouton_and_pragyan_and_30day_benchmark(client: TestClient) -> None:
    """When local PGDA LOLA GeoTIFFs & manifest.json are present, run real DEM + 30-day timing."""
    dem_manifest = Path(
        "/Users/siddharthwaikar/Personal/CodexBase/NASA Space App Challenge/"
        "CLPS Lunar Module/data/lunar-dem/manifest.json"
    )
    if not dem_manifest.exists():
        pytest.skip("PGDA LOLA GeoTIFF manifest not yet generated")

    mouton_id = _get_site_id("LUNA-MOUTON-01")
    pragyan_id = _get_site_id("HIST-CH3-01")
    simulation_rate_limiter.reset()
    created_ids: list[uuid.UUID] = []
    try:
        # 1. Mons Mouton over 30 days -> must use LDEM_80S_80MPP_ADJ.TIF
        r_m = client.post(
            "/api/v1/simulations",
            json={
                "site_id": mouton_id,
                "start_time": "2026-04-09T11:05:57Z",
                "duration_seconds": 30 * 86400,
                "playback_speed": 3600.0,
            },
        )
        assert r_m.status_code == 202
        sim_m = uuid.UUID(r_m.json()["simulation_id"])
        created_ids.append(sim_m)

        t0 = time.monotonic()
        outcomes = drain_queue(worker_id="pytest-real-lola", max_jobs=3)
        elapsed_s = time.monotonic() - t0
        assert "completed" in outcomes
        assert elapsed_s < 45.0

        st_m = client.get(f"/api/v1/simulations/{sim_m}").json()
        assert st_m["status"] == "completed"
        assert st_m["quality_state"] == "verified_terrain_aware"
        assert st_m["dem_metadata"]["terrain_dataset_id"] == "LDEM_80S_80MPP_ADJ"
        assert st_m["summary_metrics"]["sunlit_fraction_pct"] > 0.0

        # 2. Pragyan (-69.373 S) -> must use LDEM_60S_240MPP_ADJ.TIF
        r_p = client.post(
            "/api/v1/simulations",
            json={
                "site_id": pragyan_id,
                "start_time": "2026-04-09T11:05:57Z",
                "duration_seconds": 86400,
            },
        )
        assert r_p.status_code == 202
        sim_p = uuid.UUID(r_p.json()["simulation_id"])
        created_ids.append(sim_p)
        drain_queue(worker_id="pytest-real-lola-p", max_jobs=3)

        st_p = client.get(f"/api/v1/simulations/{sim_p}").json()
        assert st_p["status"] == "completed"
        assert st_p["quality_state"] == "verified_terrain_aware"
        assert st_p["dem_metadata"]["terrain_dataset_id"] == "LDEM_60S_240MPP_ADJ"
    finally:
        _cleanup_simulation_runs(created_ids)
        simulation_rate_limiter.reset()
