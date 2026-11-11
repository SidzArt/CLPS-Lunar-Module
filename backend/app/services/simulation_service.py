"""Scientific simulation orchestration service combining SPICE, LOLA DEM, and visibility analytics."""

from __future__ import annotations

import logging
import math
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from rasterio.errors import RasterioError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.spice.ephemeris import (
    ObserverSiteState,
    build_observer_state,
    compute_ephemeris_sample,
    summarize_kernel_metadata,
)
from app.integrations.spice.kernel_manager import (
    SpiceCoverageError,
    SpiceKernelError,
    spice_kernel_manager,
)
from app.integrations.terrain.dem_reader import DEMRegistry
from app.models.catalogue import LandingSite
from app.models.simulation import SimulationRun
from app.repositories import simulation_repo
from app.services.geometry import COORDINATE_CONTRACT, lat_lon_elev_to_cartesian_m
from app.services.horizon import (
    HORIZON_ALGORITHM_VERSION,
    HorizonComputationResult,
    build_geometric_only_horizon,
    compute_horizon_cache_key,
    evaluate_site_horizon,
)
from app.services.visibility import (
    EARTH_MEAN_RADIUS_KM,
    SUN_RADIUS_KM,
    EvaluatedState,
    HorizonProfileData,
    analyze_timeline,
    classify_earth_visibility,
    classify_sun_visibility,
    compute_angular_radius_deg,
)

logger = logging.getLogger("clps.simulation")

SIMULATION_ALGORITHM_VERSION = "v1.0-spice-dem"


class SimulationCancelledError(RuntimeError):
    """Raised when a running simulation job detects cooperative cancellation."""


def compute_sampling_policy(duration_seconds: int) -> dict[str, Any]:
    """Compute adaptive coarse sampling step and precision policy for requested duration."""
    if duration_seconds <= 86400:
        coarse_s = 300  # 5 min for <= 24 h
    elif duration_seconds <= 7 * 86400:
        coarse_s = 600  # 10 min for <= 7 days
    elif duration_seconds <= 35 * 86400:
        coarse_s = 900  # 15 min for <= 35 days
    elif duration_seconds <= 180 * 86400:
        coarse_s = 1800  # 30 min for <= 180 days
    else:
        coarse_s = max(
            3600,
            math.ceil(duration_seconds / max(1, settings.SIM_MAX_COARSE_SAMPLES)),
        )

    est_samples = max(2, math.ceil(duration_seconds / coarse_s) + 1)
    if est_samples > settings.SIM_MAX_COARSE_SAMPLES:
        coarse_s = math.ceil(duration_seconds / max(1, settings.SIM_MAX_COARSE_SAMPLES - 1))
        est_samples = math.ceil(duration_seconds / coarse_s) + 1

    return {
        "coarse_interval_seconds": coarse_s,
        "max_coarse_samples": settings.SIM_MAX_COARSE_SAMPLES,
        "transition_tolerance_seconds": settings.SIM_TRANSITION_TOLERANCE_SECONDS,
        "adaptive_refinement_enabled": True,
        "estimated_coarse_samples": est_samples,
        "horizon_max_radius_m": settings.SIM_HORIZON_MAX_RADIUS_M,
        "horizon_azimuth_bins": settings.SIM_HORIZON_AZIMUTH_BINS,
        "observer_height_m": settings.SIM_OBSERVER_HEIGHT_M,
        "precision_note": (
            f"Coarse ephemeris step {coarse_s}s; visibility transitions bracketed and refined "
            f"via bisection to <= {settings.SIM_TRANSITION_TOLERANCE_SECONDS}s."
        ),
    }


def _evaluate_at_et(
    et: float,
    observer: ObserverSiteState,
    horizon: HorizonProfileData,
    quality_state: str,
) -> EvaluatedState:
    ephem = compute_ephemeris_sample(et, observer)
    sun_hor = horizon.interpolate(ephem.sun_azimuth_deg)
    earth_hor = horizon.interpolate(ephem.earth_azimuth_deg)
    sun_status, sun_frac, _ = classify_sun_visibility(
        ephem.sun_elevation_deg, sun_hor, ephem.sun_range_km
    )
    earth_status = classify_earth_visibility(ephem.earth_elevation_deg, earth_hor)
    concurrent = (sun_status != "NOT_VISIBLE") and (earth_status == "VISIBLE")
    return EvaluatedState(
        timestamp_utc=ephem.timestamp_utc,
        et=ephem.et,
        sun_azimuth_deg=ephem.sun_azimuth_deg,
        sun_elevation_deg=ephem.sun_elevation_deg,
        sun_range_km=ephem.sun_range_km,
        earth_azimuth_deg=ephem.earth_azimuth_deg,
        earth_elevation_deg=ephem.earth_elevation_deg,
        earth_range_km=ephem.earth_range_km,
        sun_horizon_deg=sun_hor,
        earth_horizon_deg=earth_hor,
        sun_visibility_status=sun_status,
        sun_disk_fraction=sun_frac,
        earth_visibility_status=earth_status,
        concurrent_visible=concurrent,
        sun_dir_moon=ephem.sun_dir_moon,
        earth_dir_moon=ephem.earth_dir_moon,
        subsolar_lat_deg=ephem.subsolar_lat_deg,
        subsolar_lon_deg=ephem.subsolar_lon_deg,
        quality_status=quality_state,
    )


def _bisect_bracket(
    state_a: EvaluatedState,
    state_b: EvaluatedState,
    sign_fn: Callable[[EvaluatedState], float],
    observer: ObserverSiteState,
    horizon: HorizonProfileData,
    quality_state: str,
    tol_seconds: float,
    max_iters: int = 24,
) -> tuple[EvaluatedState, EvaluatedState] | None:
    """Narrow a transition bracket [state_a, state_b] by bisection to within ``tol_seconds``."""
    fa = sign_fn(state_a)
    fb = sign_fn(state_b)
    if (fa > 0 and fb > 0) or (fa < 0 and fb < 0):
        return None

    lo, hi = state_a, state_b
    flo = fa
    for _ in range(max_iters):
        if (hi.et - lo.et) <= tol_seconds:
            break
        mid_et = 0.5 * (lo.et + hi.et)
        mid_state = _evaluate_at_et(mid_et, observer, horizon, quality_state)
        fmid = sign_fn(mid_state)
        if fmid == 0.0:
            lo = mid_state
            hi = _evaluate_at_et(min(hi.et, mid_et + 0.5), observer, horizon, quality_state)
            break
        if (flo <= 0.0 <= fmid) or (flo >= 0.0 >= fmid):
            hi = mid_state
        else:
            lo = mid_state
            flo = fmid
    return lo, hi


def _build_scientific_disclaimers(
    quality_state: str,
    has_dem: bool,
    aberration_policy: str = "LT+S",
    quality_warnings: list[str] | None = None,
) -> list[str]:
    notes = [
        f"Solar illumination reflects topocentric sky clearance (finite solar angular disk) evaluated in MOON_ME with SPICE aberration correction '{aberration_policy}' ({'apparent position with one-way light-time & stellar aberration' if aberration_policy == 'LT+S' else 'geometric state vector'}), NOT solar-array electrical power generation.",
        f"Earth visibility reflects topocentric line-of-sight clearance above the local horizon with SPICE aberration correction '{aberration_policy}', NOT RF link-budget, multipath, or antenna-pointing availability.",
        "Timekeeping uses NAIF leap-seconds kernel naif0012.tls (valid through 2017-01-01 IERS leap-second epoch; any future IERS leap-second declaration requires updating naif0012.tls).",
    ]
    if not has_dem or quality_state == "geometric_only":
        notes.insert(
            0,
            "GEOMETRIC-ONLY SIMULATION: No covering NASA LOLA DEM exists for this site; a 0.0 deg spherical horizon was applied and local crater/ridge shadowing is NOT modeled.",
        )
    elif quality_state == "partial_dem_coverage":
        notes.insert(
            0,
            "PARTIAL DEM COVERAGE: Terrain horizon extent contains NoData gaps or approaches DEM tile boundaries.",
        )
    if quality_warnings and any("LDEC=0" in w for w in quality_warnings):
        notes.append(
            "LOLA LDEC=0 INTERPOLATION CAVEAT: Portions of the horizon ridge rely on interpolated DEM pixels without direct LOLA laser altimetry returns."
        )
    return notes


def _build_simulation_site_summary(
    db: Session,
    run: SimulationRun,
    site: LandingSite,
    *,
    cached_horizon: Any | None = None,
) -> dict[str, Any]:
    """Build SiteSummary dict using resolved DEM ground elevation when available."""
    resolved_cached = cached_horizon
    if resolved_cached is None:
        cache_key = (run.sampling_policy or {}).get("horizon_cache_key")
        if cache_key:
            resolved_cached = simulation_repo.get_cached_horizon_profile(db, str(cache_key))

    elev_m = (
        float(resolved_cached.site_elevation_m)
        if resolved_cached is not None and resolved_cached.site_elevation_m is not None
        else float(site.elevation_m or 0.0)
    )
    site_xyz_km = (
        lat_lon_elev_to_cartesian_m(
            float(site.latitude_deg),
            float(site.longitude_deg),
            elev_m,
        )
        / 1000.0
    )
    return {
        "site_id": site.site_id,
        "site_code": site.site_code,
        "site_slug": site.site_slug,
        "site_name": site.site_name,
        "latitude_deg": float(site.latitude_deg),
        "longitude_deg": float(site.longitude_deg),
        "elevation_m": round(elev_m, 3)
        if resolved_cached is not None or site.elevation_m is not None
        else None,
        "coordinate_reference": site.coordinate_reference,
        "cartesian_moon_me_km": (
            round(float(site_xyz_km[0]), 4),
            round(float(site_xyz_km[1]), 4),
            round(float(site_xyz_km[2]), 4),
        ),
    }


def enqueue_simulation_request(
    db: Session,
    *,
    site_id: int,
    start_time: datetime,
    duration_seconds: int,
    playback_speed: float,
    request_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Validate inputs, SPICE coverage, and DEM availability, then queue background job."""
    if idempotency_key:
        existing = simulation_repo.get_run_by_idempotency_key(db, idempotency_key)
        if existing is not None:
            run, job = existing
            site = simulation_repo.get_site_for_simulation(db, run.site_id)
            return {
                "simulation_id": run.simulation_id,
                "job_id": job.job_id,
                "site_id": run.site_id,
                "site_name": site.site_name if site else str(run.site_id),
                "site_slug": site.site_slug if site else "",
                "status": run.status,
                "quality_state": run.quality_state,
                "start_time_utc": run.start_time_utc,
                "end_time_utc": run.end_time_utc
                or (run.start_time_utc + timedelta(seconds=run.duration_seconds)),
                "duration_seconds": run.duration_seconds,
                "playback_speed": run.playback_speed,
                "sampling_policy": run.sampling_policy,
                "data_coverage_warnings": run.quality_warnings or [],
                "created_at": run.created_at,
            }

    site = simulation_repo.get_site_for_simulation(db, site_id)
    if site is None or site.catalogue_status != "published":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Published landing site ID {site_id} not found.",
        )

    start_utc = (
        start_time.replace(tzinfo=UTC) if start_time.tzinfo is None else start_time.astimezone(UTC)
    )
    end_utc = start_utc + timedelta(seconds=duration_seconds)

    # Validate SPICE availability and time bounds before accepting job
    try:
        _, _, kernel_state = spice_kernel_manager.validate_utc_interval(start_utc, end_utc)
    except SpiceCoverageError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "SPICE_COVERAGE_ERROR",
                "message": str(exc),
                "valid_start_utc": exc.valid_start_utc,
                "valid_end_utc": exc.valid_end_utc,
                "responsible_kernel": exc.responsible_kernel,
            },
        ) from exc
    except SpiceKernelError as exc:
        logger.error("SPICE kernel validation failure [req=%s]: %s", request_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SPICE ephemeris kernels are unavailable or failed integrity verification.",
        ) from exc

    # Inspect DEM coverage metadata early to provide accurate creation warnings
    warnings: list[str] = []
    dem_id: str | None = None
    dem_registry = DEMRegistry()
    try:
        dem_sel = dem_registry.select_asset_for_site(
            lat_deg=float(site.latitude_deg),
            lon_deg=float(site.longitude_deg),
            horizon_max_radius_m=settings.SIM_HORIZON_MAX_RADIUS_M,
        )
        if dem_sel is None:
            warnings.append(
                f"No registered LOLA DEM covers site '{site.site_name}' ({float(site.latitude_deg):.3f}, "
                f"{float(site.longitude_deg):.3f}); simulation will be tagged 'geometric_only' with a 0.0 deg idealised horizon."
            )
        else:
            dem_id = dem_sel.asset.asset_id
            if not dem_sel.full_horizon_covered:
                warnings.append(
                    f"DEM tile '{dem_sel.asset.asset_id}' boundary is {dem_sel.min_edge_margin_m / 1000.0:.1f} km "
                    f"from site (< {settings.SIM_HORIZON_MAX_RADIUS_M / 1000.0:.0f} km radius); quality may be 'partial_dem_coverage'."
                )
    except (OSError, ValueError, KeyError, RuntimeError, RasterioError) as exc:
        logger.warning("DEM pre-check warning for site %s: %s", site_id, exc)
        warnings.append(
            "DEM pre-check encountered a configuration warning; worker will verify coverage."
        )

    policy = compute_sampling_policy(duration_seconds)
    kernel_meta = summarize_kernel_metadata(kernel_state)

    run, job = simulation_repo.create_simulation_with_job(
        db,
        site_id=site.site_id,
        start_time_utc=start_utc,
        end_time_utc=end_utc,
        duration_seconds=duration_seconds,
        playback_speed=playback_speed,
        sample_interval_seconds=int(policy["coarse_interval_seconds"]),
        ephemeris_source=kernel_state.ephemeris_source,
        ephemeris_version=kernel_state.ephemeris_version,
        coordinate_frame=settings.SIM_LUNAR_REFERENCE_FRAME,
        aberration_policy=settings.SIM_ABERRATION_CORRECTION,
        terrain_dataset_id=dem_id,
        algorithm_version=SIMULATION_ALGORITHM_VERSION,
        sampling_policy=policy,
        kernel_manifest=kernel_meta,
        quality_state="pending",
        quality_warnings=warnings,
        request_id=request_id,
        idempotency_key=idempotency_key,
    )

    return {
        "simulation_id": run.simulation_id,
        "job_id": job.job_id,
        "site_id": site.site_id,
        "site_name": site.site_name,
        "site_slug": site.site_slug,
        "status": run.status,
        "quality_state": run.quality_state,
        "start_time_utc": run.start_time_utc,
        "end_time_utc": run.end_time_utc,
        "duration_seconds": run.duration_seconds,
        "playback_speed": run.playback_speed,
        "sampling_policy": policy,
        "data_coverage_warnings": warnings,
        "created_at": run.created_at,
    }


def _resolve_or_compute_horizon(
    db: Session,
    site_id: int,
    lat_deg: float,
    lon_deg: float,
    site_elev_m: float | None,
    coordinate_frame: str,
) -> tuple[HorizonProfileData, dict[str, Any], list[str], float | None, str]:
    """Load cached horizon profile or compute from DEM window (or build geometric fallback)."""
    dem_registry = DEMRegistry()
    dem_sel = dem_registry.select_asset_for_site(
        lat_deg=lat_deg,
        lon_deg=lon_deg,
        horizon_max_radius_m=settings.SIM_HORIZON_MAX_RADIUS_M,
    )
    if dem_sel is None:
        geom_res = build_geometric_only_horizon(
            site_id=site_id,
            lat_deg=lat_deg,
            lon_deg=lon_deg,
            site_db_elevation_m=site_elev_m,
            observer_height_m=settings.SIM_OBSERVER_HEIGHT_M,
            coordinate_frame=coordinate_frame,
            azimuth_bins=settings.SIM_HORIZON_AZIMUTH_BINS,
        )
        return (
            geom_res.profile,
            {
                "terrain_dataset_id": None,
                "dem_checksum": None,
                "dem_resolution_m": None,
                "horizon_algorithm_version": geom_res.algorithm_version,
                "horizon_cache_hit": False,
                "azimuth_bins": geom_res.azimuth_bins,
                "cache_key": geom_res.cache_key,
            },
            geom_res.warnings,
            site_elev_m,
            geom_res.profile.quality_state,
        )

    cache_key = compute_horizon_cache_key(
        site_id=site_id,
        lat_deg=lat_deg,
        lon_deg=lon_deg,
        site_db_elevation_m=site_elev_m,
        dem_asset_id=dem_sel.asset.asset_id,
        dem_checksum=dem_sel.asset.sha256,
        coordinate_frame=coordinate_frame,
        observer_height_m=settings.SIM_OBSERVER_HEIGHT_M,
        algorithm_version=HORIZON_ALGORITHM_VERSION,
        azimuth_bins=settings.SIM_HORIZON_AZIMUTH_BINS,
        max_radius_m=settings.SIM_HORIZON_MAX_RADIUS_M,
    )

    cached = simulation_repo.get_cached_horizon_profile(db, cache_key)
    if cached is not None:
        import numpy as np

        profile = HorizonProfileData(
            azimuths_deg=np.asarray(cached.azimuths_deg, dtype=np.float64),
            elevations_deg=np.asarray(cached.horizon_elevations_deg, dtype=np.float64),
            quality_state=cached.quality_state,
            azimuth_bins=cached.azimuth_bins,
        )
        cached_warnings: list[str] = []
        if cached.quality_state == "partial_dem_coverage":
            cached_warnings.append(
                f"Cached DEM horizon ({cached.dem_asset_id}) marked partial_dem_coverage due to tile bounds or NoData gaps."
            )
        elif cached.quality_state == "insufficient_data":
            cached_warnings.append(
                f"Cached DEM horizon ({cached.dem_asset_id}) has insufficient valid terrain cells."
            )
        return (
            profile,
            {
                "terrain_dataset_id": cached.dem_asset_id,
                "dem_checksum": cached.dem_checksum,
                "dem_resolution_m": cached.dem_resolution_m,
                "horizon_algorithm_version": cached.algorithm_version,
                "horizon_cache_hit": True,
                "azimuth_bins": cached.azimuth_bins,
                "cache_key": cached.cache_key,
            },
            cached_warnings,
            cached.site_elevation_m if cached.site_elevation_m is not None else site_elev_m,
            cached.quality_state,
        )

    computed: HorizonComputationResult = evaluate_site_horizon(
        registry=dem_registry,
        site_id=site_id,
        lat_deg=lat_deg,
        lon_deg=lon_deg,
        site_db_elevation_m=site_elev_m,
        observer_height_m=settings.SIM_OBSERVER_HEIGHT_M,
        coordinate_frame=coordinate_frame,
        azimuth_bins=settings.SIM_HORIZON_AZIMUTH_BINS,
        min_radius_m=settings.SIM_HORIZON_MIN_RADIUS_M,
        max_radius_m=settings.SIM_HORIZON_MAX_RADIUS_M,
    )
    simulation_repo.save_horizon_profile_idempotent(db, computed)
    return (
        computed.profile,
        {
            "terrain_dataset_id": computed.dem_asset_id,
            "dem_checksum": computed.dem_checksum,
            "dem_resolution_m": computed.dem_resolution_m,
            "horizon_algorithm_version": computed.algorithm_version,
            "horizon_cache_hit": False,
            "azimuth_bins": computed.azimuth_bins,
            "cache_key": computed.cache_key,
        },
        computed.warnings,
        computed.site_ground_elevation_m
        if computed.site_ground_elevation_m is not None
        else site_elev_m,
        computed.profile.quality_state,
    )


def execute_simulation_run(
    db: Session,
    simulation_id: uuid.UUID,
    *,
    job_id: uuid.UUID | None = None,
    lease_seconds: int = 300,
) -> str:
    """Execute a queued scientific simulation end-to-end and persist all outputs.

    Can be invoked by ``SimulationWorker`` OR synchronously in controlled integration tests.
    """
    run = simulation_repo.get_simulation_run(db, simulation_id)
    if run is None:
        raise ValueError(f"SimulationRun {simulation_id} not found")
    if run.status == "cancelled":
        return "cancelled"

    effective_job_id = job_id or run.job_id
    site = simulation_repo.get_site_for_simulation(db, run.site_id)
    if site is None:
        raise ValueError(f"LandingSite {run.site_id} not found")

    def _check_cancel() -> None:
        if simulation_repo.is_simulation_cancelled(db, simulation_id):
            raise SimulationCancelledError(f"Simulation {simulation_id} cancelled mid-run")

    def _progress(pct: float, msg: str) -> None:
        _check_cancel()
        simulation_repo.update_job_progress(
            db, effective_job_id, simulation_id, pct, msg, lease_seconds=lease_seconds
        )

    start_utc = (
        run.start_time_utc.replace(tzinfo=UTC)
        if run.start_time_utc.tzinfo is None
        else run.start_time_utc.astimezone(UTC)
    )
    end_utc = start_utc + timedelta(seconds=int(run.duration_seconds))

    # 1. Validate SPICE kernels and time interval
    start_et, end_et, kernel_state = spice_kernel_manager.validate_utc_interval(start_utc, end_utc)
    _progress(15.0, "SPICE kernels and time coverage validated")

    # 2. Resolve DEM horizon profile (with PostgreSQL cache reuse)
    horizon_profile, dem_info, horizon_warnings, ground_elev_m, quality_state = (
        _resolve_or_compute_horizon(
            db=db,
            site_id=site.site_id,
            lat_deg=float(site.latitude_deg),
            lon_deg=float(site.longitude_deg),
            site_elev_m=float(site.elevation_m) if site.elevation_m is not None else None,
            coordinate_frame=run.coordinate_frame or settings.SIM_LUNAR_REFERENCE_FRAME,
        )
    )
    _progress(
        30.0,
        f"Horizon resolved (quality={quality_state}, cache_hit={dem_info['horizon_cache_hit']})",
    )

    # 3. Construct Moon-fixed observer state
    effective_obs_elev_m = float(ground_elev_m or 0.0) + settings.SIM_OBSERVER_HEIGHT_M
    observer = build_observer_state(
        site_id=site.site_id,
        latitude_deg=float(site.latitude_deg),
        longitude_deg=float(site.longitude_deg),
        effective_elevation_m=effective_obs_elev_m,
        lunar_frame=run.coordinate_frame or settings.SIM_LUNAR_REFERENCE_FRAME,
        aberration_correction=run.aberration_policy or settings.SIM_ABERRATION_CORRECTION,
        moon_radius_km=kernel_state.moon_radii_km[0],
    )

    # 4. Coarse ephemeris grid sampling
    policy = dict(run.sampling_policy or compute_sampling_policy(int(run.duration_seconds)))
    coarse_step_s = float(policy.get("coarse_interval_seconds", run.sample_interval_seconds))
    tol_s = float(
        policy.get("transition_tolerance_seconds", settings.SIM_TRANSITION_TOLERANCE_SECONDS)
    )

    n_steps = max(1, math.ceil((end_et - start_et) / coarse_step_s))
    coarse_ets = [min(end_et, start_et + k * coarse_step_s) for k in range(n_steps)]
    if abs(coarse_ets[-1] - end_et) > 1e-6:
        coarse_ets.append(end_et)

    coarse_states: list[EvaluatedState] = []
    total_c = len(coarse_ets)
    report_every = max(50, total_c // 6)
    for idx, et_val in enumerate(coarse_ets):
        coarse_states.append(_evaluate_at_et(et_val, observer, horizon_profile, quality_state))
        if idx > 0 and idx % report_every == 0:
            pct = 30.0 + 40.0 * (idx / total_c)
            _progress(pct, f"Evaluated {idx}/{total_c} coarse ephemeris steps")

    _progress(72.0, "Refining transition brackets via bisection")

    # 5. Adaptive transition bracketing & bisection refinement
    refined_pairs: list[tuple[EvaluatedState, EvaluatedState]] = []
    for idx in range(len(coarse_states) - 1):
        sa = coarse_states[idx]
        sb = coarse_states[idx + 1]

        # Solar center crossing
        if (sa.sun_elevation_deg >= sa.sun_horizon_deg) != (
            sb.sun_elevation_deg >= sb.sun_horizon_deg
        ):
            res = _bisect_bracket(
                sa,
                sb,
                lambda st: st.sun_elevation_deg - st.sun_horizon_deg,
                observer,
                horizon_profile,
                quality_state,
                tol_s,
            )
            if res is not None:
                refined_pairs.append(res)

        # Solar full-limb or lower-limb grazing transitions when status flips
        if sa.sun_visibility_status != sb.sun_visibility_status:
            # Upper limb contact (NOT_VISIBLE <-> PARTIAL): elev + ang_rad - horizon
            res_lo = _bisect_bracket(
                sa,
                sb,
                lambda st: (
                    st.sun_elevation_deg
                    + compute_angular_radius_deg(SUN_RADIUS_KM, st.sun_range_km)
                    - st.sun_horizon_deg
                ),
                observer,
                horizon_profile,
                quality_state,
                tol_s,
            )
            if res_lo is not None:
                refined_pairs.append(res_lo)
            # Lower limb clearance (PARTIAL <-> VISIBLE): elev - ang_rad - horizon
            res_hi = _bisect_bracket(
                sa,
                sb,
                lambda st: (
                    st.sun_elevation_deg
                    - compute_angular_radius_deg(SUN_RADIUS_KM, st.sun_range_km)
                    - st.sun_horizon_deg
                ),
                observer,
                horizon_profile,
                quality_state,
                tol_s,
            )
            if res_hi is not None:
                refined_pairs.append(res_hi)

        # Earth center geometric crossing
        if sa.earth_visibility_status != sb.earth_visibility_status:
            res_e = _bisect_bracket(
                sa,
                sb,
                lambda st: st.earth_elevation_deg - st.earth_horizon_deg,
                observer,
                horizon_profile,
                quality_state,
                tol_s,
            )
            if res_e is not None:
                refined_pairs.append(res_e)

    # Merge coarse + refined states sorted by ET, marking refined state indices
    marked: list[tuple[float, bool, EvaluatedState]] = [(st.et, False, st) for st in coarse_states]
    for st_lo, st_hi in refined_pairs:
        marked.append((st_lo.et, True, st_lo))
        marked.append((st_hi.et, True, st_hi))
    marked.sort(key=lambda item: item[0])

    merged_timeline: list[EvaluatedState] = []
    refined_indices: set[int] = set()
    for et_val, is_ref, st in marked:
        if merged_timeline and abs(et_val - merged_timeline[-1].et) < 0.05:
            if is_ref:
                merged_timeline[-1] = st
                refined_indices.add(len(merged_timeline) - 1)
        else:
            idx_new = len(merged_timeline)
            merged_timeline.append(st)
            if is_ref:
                refined_indices.add(idx_new)

    _check_cancel()
    _progress(86.0, f"Analyzing {len(merged_timeline)} timeline points and event windows")

    # 6. Summary statistics and event window extraction
    summary_metrics, events = analyze_timeline(
        timeline=merged_timeline,
        refined_indices=refined_indices,
        quality_state=quality_state,
        method_version=f"{SIMULATION_ALGORITHM_VERSION}-bisect",
    )
    summary_metrics["sample_count"] = len(merged_timeline)
    summary_metrics["coarse_sample_count"] = len(coarse_states)
    summary_metrics["refined_transition_points"] = len(refined_indices)
    summary_metrics["earth_angular_radius_approx_deg"] = round(
        compute_angular_radius_deg(EARTH_MEAN_RADIUS_KM, 384_400.0), 3
    )

    sample_rows: list[dict[str, Any]] = [
        {
            "simulation_id": simulation_id,
            "sample_index": idx,
            "timestamp_utc": st.timestamp_utc,
            "ephemeris_time": st.et,
            "sun_azimuth_deg": round(st.sun_azimuth_deg, 4),
            "sun_elevation_deg": round(st.sun_elevation_deg, 4),
            "sun_range_km": round(st.sun_range_km, 2),
            "earth_azimuth_deg": round(st.earth_azimuth_deg, 4),
            "earth_elevation_deg": round(st.earth_elevation_deg, 4),
            "earth_range_km": round(st.earth_range_km, 2),
            "sun_horizon_deg": round(st.sun_horizon_deg, 4),
            "earth_horizon_deg": round(st.earth_horizon_deg, 4),
            "sun_visibility_status": st.sun_visibility_status,
            "earth_visibility_status": st.earth_visibility_status,
            "concurrent_visible": st.concurrent_visible,
            "sun_dir_moon_x": st.sun_dir_moon[0],
            "sun_dir_moon_y": st.sun_dir_moon[1],
            "sun_dir_moon_z": st.sun_dir_moon[2],
            "earth_dir_moon_x": st.earth_dir_moon[0],
            "earth_dir_moon_y": st.earth_dir_moon[1],
            "earth_dir_moon_z": st.earth_dir_moon[2],
            "subsolar_lat_deg": st.subsolar_lat_deg,
            "subsolar_lon_deg": st.subsolar_lon_deg,
            "quality_status": st.quality_status,
        }
        for idx, st in enumerate(merged_timeline)
    ]

    summary_metric_specs = [
        ("sunlit_fraction_pct", "%"),
        ("full_sun_fraction_pct", "%"),
        ("earth_visible_fraction_pct", "%"),
        ("concurrent_visible_fraction_pct", "%"),
        ("longest_darkness_hours", "hours"),
        ("longest_earth_blackout_hours", "hours"),
        ("max_sun_elevation_deg", "deg"),
        ("min_sun_elevation_deg", "deg"),
    ]
    metric_rows: list[dict[str, Any]] = [
        {
            "simulation_id": simulation_id,
            "sample_time_utc": start_utc,
            "parameter_key": key,
            "numeric_value": float(summary_metrics[key]),
            "unit": unit,
            "quality_flag": quality_state,
        }
        for key, unit in summary_metric_specs
        if key in summary_metrics
    ]

    event_rows: list[dict[str, Any]] = [
        {
            "simulation_id": simulation_id,
            "event_type": ev.event_type,
            "window_start_utc": ev.window_start_utc,
            "window_end_utc": ev.window_end_utc,
            "duration_seconds": ev.duration_seconds,
            "confidence_status": ev.confidence_status,
            "method_version": ev.method_version,
            "event_metadata": ev.metadata,
        }
        for ev in events
    ]

    all_warnings = list(dict.fromkeys([*(run.quality_warnings or []), *horizon_warnings]))
    sampling_policy_updated = {
        **policy,
        "horizon_cache_hit": dem_info["horizon_cache_hit"],
        "horizon_cache_key": dem_info["cache_key"],
        "dem_resolution_m": dem_info["dem_resolution_m"],
    }

    run_updates = {
        "terrain_dataset_id": dem_info["terrain_dataset_id"],
        "dem_checksum": dem_info["dem_checksum"],
        "horizon_algorithm_version": dem_info["horizon_algorithm_version"],
        "kernel_manifest": summarize_kernel_metadata(kernel_state),
        "sampling_policy": sampling_policy_updated,
        "quality_state": quality_state,
        "quality_warnings": all_warnings,
        "summary_metrics": summary_metrics,
    }

    simulation_repo.persist_simulation_completion(
        db,
        simulation_id=simulation_id,
        job_id=effective_job_id,
        run_updates=run_updates,
        sample_rows=sample_rows,
        metric_rows=metric_rows,
        event_rows=event_rows,
    )
    return "completed"


def get_simulation_status_payload(db: Session, simulation_id: uuid.UUID) -> dict[str, Any]:
    """Assemble full simulation status, metadata, summary, and scientific caveats."""
    run = simulation_repo.get_simulation_run(db, simulation_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Simulation {simulation_id} not found.",
        )
    site = simulation_repo.get_site_for_simulation(db, run.site_id)
    if site is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Landing site {run.site_id} associated with simulation not found.",
        )
    job = simulation_repo.get_job_for_run(db, run.job_id)

    has_dem = bool(run.terrain_dataset_id)
    sampling_pol = dict(run.sampling_policy or {})
    kernel_man = dict(run.kernel_manifest or {})
    warnings_list = list(run.quality_warnings or [])

    return {
        "simulation_id": run.simulation_id,
        "job_id": run.job_id,
        "status": run.status,
        "progress_pct": float(run.progress_pct),
        "progress_message": job.progress_message if job else None,
        "quality_state": run.quality_state,
        "quality_warnings": warnings_list,
        "site": _build_simulation_site_summary(db, run, site),
        "start_time_utc": run.start_time_utc,
        "end_time_utc": run.end_time_utc,
        "duration_seconds": int(run.duration_seconds),
        "playback_speed": float(run.playback_speed),
        "coordinate_frame": run.coordinate_frame,
        "resolved_frame": kernel_man.get("resolved_lunar_frame"),
        "aberration_policy": run.aberration_policy,
        "algorithm_version": run.algorithm_version,
        "horizon_algorithm_version": run.horizon_algorithm_version,
        "sampling_policy": sampling_pol,
        "kernel_manifest": kernel_man,
        "dem_metadata": {
            "terrain_dataset_id": run.terrain_dataset_id,
            "dem_checksum": run.dem_checksum,
            "dem_resolution_m": sampling_pol.get("dem_resolution_m"),
            "horizon_cache_hit": sampling_pol.get("horizon_cache_hit"),
            "horizon_azimuth_bins": sampling_pol.get("horizon_azimuth_bins"),
        },
        "summary_metrics": run.summary_metrics,
        "limitations_disclaimers": _build_scientific_disclaimers(
            run.quality_state,
            has_dem,
            aberration_policy=run.aberration_policy,
            quality_warnings=warnings_list,
        ),
        "error_summary": run.error_summary,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
    }


def get_simulation_series_payload(
    db: Session,
    simulation_id: uuid.UUID,
    *,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    offset: int = 0,
    limit: int = 500,
    downsample_step: int = 1,
    include_horizon: bool = True,
) -> dict[str, Any]:
    """Return paginated, time-windowed, downsampled series and Three.js vector data."""
    run = simulation_repo.get_simulation_run(db, simulation_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Simulation {simulation_id} not found.",
        )
    site = simulation_repo.get_site_for_simulation(db, run.site_id)
    if site is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Landing site {run.site_id} not found.",
        )

    total, rows = simulation_repo.query_simulation_series(
        db,
        simulation_id=simulation_id,
        start_time=start_time,
        end_time=end_time,
        offset=offset,
        limit=limit,
        downsample_step=downsample_step,
    )

    horizon_out: dict[str, Any] | None = None
    cached: Any | None = None
    if include_horizon:
        cache_key = (run.sampling_policy or {}).get("horizon_cache_key")
        cached = (
            simulation_repo.get_cached_horizon_profile(db, str(cache_key)) if cache_key else None
        )
        if cached is not None:
            horizon_out = {
                "azimuth_bins": cached.azimuth_bins,
                "azimuths_deg": list(cached.azimuths_deg),
                "horizon_elevations_deg": list(cached.horizon_elevations_deg),
                "horizon_distances_m": list(cached.horizon_distances_m)
                if cached.horizon_distances_m
                else None,
                "uncertainty_deg": list(cached.uncertainty_deg) if cached.uncertainty_deg else None,
                "quality_state": cached.quality_state,
                "dem_asset_id": cached.dem_asset_id,
            }
        elif run.quality_state == "geometric_only":
            bins = int(
                (run.sampling_policy or {}).get("horizon_azimuth_bins")
                or settings.SIM_HORIZON_AZIMUTH_BINS
            )
            horizon_out = {
                "azimuth_bins": bins,
                "azimuths_deg": [float(i * (360.0 / bins)) for i in range(bins)],
                "horizon_elevations_deg": [0.0] * bins,
                "horizon_distances_m": None,
                "uncertainty_deg": None,
                "quality_state": "geometric_only",
                "dem_asset_id": None,
            }

    run_start = (
        run.start_time_utc.replace(tzinfo=UTC)
        if run.start_time_utc.tzinfo is None
        else run.start_time_utc.astimezone(UTC)
    )

    samples_payload: list[dict[str, Any]] = []
    for row in rows:
        ts = (
            row.timestamp_utc.replace(tzinfo=UTC)
            if row.timestamp_utc.tzinfo is None
            else row.timestamp_utc.astimezone(UTC)
        )
        samples_payload.append(
            {
                "sample_index": row.sample_index,
                "timestamp_utc": ts,
                "ephemeris_time": row.ephemeris_time,
                "elapsed_seconds": round((ts - run_start).total_seconds(), 3),
                "sun": {
                    "azimuth_deg": row.sun_azimuth_deg,
                    "elevation_deg": row.sun_elevation_deg,
                    "range_km": row.sun_range_km,
                    "horizon_deg": row.sun_horizon_deg,
                    "dir_moon_me": (row.sun_dir_moon_x, row.sun_dir_moon_y, row.sun_dir_moon_z),
                    "visibility_status": row.sun_visibility_status,
                },
                "earth": {
                    "azimuth_deg": row.earth_azimuth_deg,
                    "elevation_deg": row.earth_elevation_deg,
                    "range_km": row.earth_range_km,
                    "horizon_deg": row.earth_horizon_deg,
                    "dir_moon_me": (
                        row.earth_dir_moon_x,
                        row.earth_dir_moon_y,
                        row.earth_dir_moon_z,
                    ),
                    "visibility_status": row.earth_visibility_status,
                },
                "concurrent_visible": row.concurrent_visible,
                "subsolar_lat_deg": row.subsolar_lat_deg,
                "subsolar_lon_deg": row.subsolar_lon_deg,
                "quality_status": row.quality_status,
            }
        )

    return {
        "simulation_id": run.simulation_id,
        "status": run.status,
        "quality_state": run.quality_state,
        "playback_speed": float(run.playback_speed),
        "site": _build_simulation_site_summary(db, run, site, cached_horizon=cached),
        "coordinate_contract": {
            "lunar_reference_frame": COORDINATE_CONTRACT.lunar_reference_frame,
            "de440_resolved_frame": COORDINATE_CONTRACT.de440_resolved_frame,
            "latitude_convention": COORDINATE_CONTRACT.latitude_convention,
            "longitude_convention": COORDINATE_CONTRACT.longitude_convention,
            "azimuth_convention": COORDINATE_CONTRACT.azimuth_convention,
            "elevation_convention": COORDINATE_CONTRACT.elevation_convention,
            "elevation_datum": COORDINATE_CONTRACT.elevation_datum,
        },
        "units": {
            "angles": "degrees",
            "distances": "kilometers",
            "horizon_elevations": "degrees",
            "vectors": "unitless MOON_ME basis vectors",
            "time": "ISO-8601 UTC and TDB seconds past J2000",
        },
        "horizon_profile": horizon_out,
        "total_samples_available": total,
        "returned_samples": len(samples_payload),
        "offset": offset,
        "limit": limit,
        "downsample_step": downsample_step,
        "samples": samples_payload,
    }


def get_simulation_events_payload(
    db: Session,
    simulation_id: uuid.UUID,
    event_type: str | None = None,
) -> dict[str, Any]:
    """Retrieve transition events and visibility windows for a simulation."""
    run = simulation_repo.get_simulation_run(db, simulation_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Simulation {simulation_id} not found.",
        )
    events = simulation_repo.query_simulation_events(db, simulation_id, event_type=event_type)
    return {
        "simulation_id": run.simulation_id,
        "status": run.status,
        "quality_state": run.quality_state,
        "total_events": len(events),
        "events": [
            {
                "event_id": ev.event_id,
                "event_type": ev.event_type,
                "window_start_utc": ev.window_start_utc,
                "window_end_utc": ev.window_end_utc,
                "duration_seconds": int(ev.duration_seconds),
                "confidence_status": ev.confidence_status,
                "method_version": ev.method_version,
                "event_metadata": dict(ev.event_metadata or {}),
            }
            for ev in events
        ],
    }


def cancel_simulation_request(db: Session, simulation_id: uuid.UUID) -> dict[str, Any]:
    """Safely cancel a queued or running simulation."""
    try:
        run, job, cancelled_now = simulation_repo.cancel_simulation_run(db, simulation_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Simulation {simulation_id} not found.",
        ) from exc

    if not cancelled_now and run.status in ("completed", "failed"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot cancel simulation in terminal state '{run.status}'.",
        )
    return {
        "simulation_id": run.simulation_id,
        "job_id": job.job_id if job else run.job_id,
        "status": run.status,
        "message": "Simulation cancelled successfully."
        if cancelled_now
        else "Simulation was already cancelled.",
    }


def get_admin_simulation_diagnostics(db: Session) -> dict[str, Any]:
    """Assemble SPICE, DEM, site coverage, cache, and queue diagnostics for administrators."""
    spice_ready = False
    spice_error: str | None = None
    spice_manifest: dict[str, Any] = {}
    available_frames: dict[str, int] = {}
    try:
        kstate = spice_kernel_manager.ensure_loaded()
        spice_ready = True
        spice_manifest = summarize_kernel_metadata(kstate)
        available_frames = dict(kstate.available_frames)
    except (SpiceKernelError, OSError, ValueError, KeyError, RuntimeError) as exc:
        spice_error = str(exc)

    dem_registry = DEMRegistry()
    dem_assets_list: list[dict[str, Any]] = []
    try:
        for asset in dem_registry.list_assets():
            dem_assets_list.append(
                {
                    "asset_id": asset.asset_id,
                    "filename": asset.filename,
                    "sha256": asset.sha256,
                    "file_size_bytes": asset.file_size_bytes,
                    "dimensions": [asset.width, asset.height],
                    "resolution_m": [asset.pixel_size_x_m, asset.pixel_size_y_m],
                    "dtype": asset.dtype,
                    "nodata_value": asset.nodata_value,
                    "crs_proj4": asset.crs_proj4,
                    "pixel_registration": asset.pixel_registration,
                    "bounds_m": [
                        asset.bounds_left_m,
                        asset.bounds_bottom_m,
                        asset.bounds_right_m,
                        asset.bounds_top_m,
                    ],
                    "lunar_frame": asset.lunar_frame,
                    "source": asset.source,
                    "citation": asset.citation,
                    "count_filename": asset.count_filename,
                    "error_filename": asset.error_filename,
                }
            )
    except (OSError, ValueError, KeyError, RuntimeError, RasterioError) as exc:
        logger.warning("Failed to list DEM assets: %s", exc)

    site_coverage: list[dict[str, Any]] = []
    sites = list(db.scalars(select(LandingSite).order_by(LandingSite.site_id.asc())).all())
    for s in sites:
        try:
            sel = dem_registry.select_asset_for_site(
                float(s.latitude_deg),
                float(s.longitude_deg),
                settings.SIM_HORIZON_MAX_RADIUS_M,
            )
            if sel is None:
                site_coverage.append(
                    {
                        "site_id": s.site_id,
                        "site_slug": s.site_slug,
                        "site_name": s.site_name,
                        "latitude_deg": float(s.latitude_deg),
                        "longitude_deg": float(s.longitude_deg),
                        "coverage_status": "geometric_only",
                        "selected_dem_asset_id": None,
                        "resolution_m": None,
                        "min_edge_margin_km": None,
                    }
                )
            else:
                site_coverage.append(
                    {
                        "site_id": s.site_id,
                        "site_slug": s.site_slug,
                        "site_name": s.site_name,
                        "latitude_deg": float(s.latitude_deg),
                        "longitude_deg": float(s.longitude_deg),
                        "coverage_status": "full_coverage"
                        if sel.full_horizon_covered
                        else "partial_dem_coverage",
                        "selected_dem_asset_id": sel.asset.asset_id,
                        "resolution_m": sel.asset.pixel_size_x_m,
                        "min_edge_margin_km": round(sel.min_edge_margin_m / 1000.0, 2),
                    }
                )
        except (OSError, ValueError, KeyError, RuntimeError, RasterioError):
            site_coverage.append(
                {
                    "site_id": s.site_id,
                    "site_slug": s.site_slug,
                    "site_name": s.site_name,
                    "latitude_deg": float(s.latitude_deg),
                    "longitude_deg": float(s.longitude_deg),
                    "coverage_status": "error",
                }
            )

    cached_count, queue_counts = simulation_repo.get_diagnostics_counts(db)
    return {
        "spice_ready": spice_ready,
        "spice_error": spice_error,
        "spice_manifest": spice_manifest,
        "available_frames": available_frames,
        "dem_assets_count": len(dem_assets_list),
        "dem_assets": dem_assets_list,
        "site_dem_coverage": site_coverage,
        "cached_horizon_profiles_count": cached_count,
        "worker_queue_counts": queue_counts,
    }
