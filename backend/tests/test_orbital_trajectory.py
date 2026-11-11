"""Verification suite for the additive read-only SPICE ECLIPJ2000 orbital trajectory contract."""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import numpy as np
import pytest
import spiceypy as spice
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.core.rate_limit import simulation_rate_limiter
from app.db.session import SessionLocal
from app.integrations.spice.ephemeris import compute_inertial_orbital_trajectory
from app.integrations.spice.kernel_manager import SpiceCoverageError
from app.models.catalogue import LandingSite
from app.models.operations import BackgroundJob
from app.models.simulation import (
    SimulationEventWindow,
    SimulationRun,
    SimulationSample,
)
from app.worker.simulation_worker import run_once


def _unwrap_revolutions(xy_vectors: list[tuple[float, float, float]]) -> float:
    """Compute cumulative signed ecliptic longitude swept in revolutions (360 deg = 1.0)."""
    angles = [math.atan2(v[1], v[0]) for v in xy_vectors]
    total_rad = 0.0
    for idx in range(1, len(angles)):
        delta = angles[idx] - angles[idx - 1]
        while delta <= -math.pi:
            delta += 2.0 * math.pi
        while delta > math.pi:
            delta -= 2.0 * math.pi
        total_rad += delta
    return total_rad / (2.0 * math.pi)


def _get_published_site_id(site_code: str = "HIST-LUNO-01") -> int:
    with SessionLocal() as session:
        site_id = session.scalar(
            select(LandingSite.site_id).where(LandingSite.site_code == site_code)
        )
        if site_id is None:
            site_id = session.scalar(
                select(LandingSite.site_id)
                .where(LandingSite.catalogue_status == "published")
                .limit(1)
            )
        assert site_id is not None
        return int(site_id)


def _cleanup_runs(run_ids: list[uuid.UUID]) -> None:
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


def test_spice_ephemeris_one_day_one_month_and_one_year_kinematics() -> None:
    """Validate DE440 Earth@Sun, Moon@Earth, Sun->Earth->Moon vector sum, inclination & tidal lock."""
    start = datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)

    # 1. One-day simulation (86,400s): Earth ~0.9856 deg, Moon ~13.18 deg
    _, one_day = compute_inertial_orbital_trajectory(
        start,
        datetime(2026, 6, 2, 0, 0, 0, tzinfo=UTC),
        num_samples=96,
    )
    assert len(one_day) == 96
    assert one_day[0].elapsed_seconds == 0.0
    assert one_day[-1].elapsed_seconds == pytest.approx(86400.0, abs=1e-2)

    earth_1d_rev = _unwrap_revolutions([s.earth_wrt_sun_eclipj2000_km for s in one_day])
    moon_1d_rev = _unwrap_revolutions([s.moon_wrt_earth_eclipj2000_km for s in one_day])
    assert earth_1d_rev == pytest.approx(1.0 / 365.256, abs=0.0005)
    assert moon_1d_rev == pytest.approx(1.0 / 27.322, abs=0.006)

    # 2. One lunar sidereal month (27.322 days = 2,360,621s)
    from datetime import timedelta

    _, one_month = compute_inertial_orbital_trajectory(
        start,
        start + timedelta(seconds=2360621),
        num_samples=512,
    )
    moon_1m_rev = _unwrap_revolutions([s.moon_wrt_earth_eclipj2000_km for s in one_month])
    assert moon_1m_rev == pytest.approx(1.0, abs=0.02)

    # 3. One Earth sidereal year (365.256 days = 31,558,118s): ~1 Earth rev & ~13.37 Moon revs
    _, one_year = compute_inertial_orbital_trajectory(
        start,
        start + timedelta(seconds=31558118),
        num_samples=2048,
    )
    assert len(one_year) == 2048
    assert one_year[0].elapsed_seconds == 0.0
    assert one_year[-1].elapsed_seconds == pytest.approx(31558118.0, abs=1e-1)

    earth_1y_rev = _unwrap_revolutions([s.earth_wrt_sun_eclipj2000_km for s in one_year])
    moon_1y_rev = _unwrap_revolutions([s.moon_wrt_earth_eclipj2000_km for s in one_year])
    assert earth_1y_rev == pytest.approx(1.0, abs=0.01)
    assert moon_1y_rev == pytest.approx(365.256 / 27.322, abs=0.15)  # ~13.37 revolutions

    # Check heliocentric orbital eccentricity ~0.0167, lunar eccentricity ~0.0549, inclination ~5.145 deg
    earth_radii = [math.sqrt(sum(c * c for c in s.earth_wrt_sun_eclipj2000_km)) for s in one_year]
    earth_ecc = (max(earth_radii) - min(earth_radii)) / (max(earth_radii) + min(earth_radii))
    assert earth_ecc == pytest.approx(0.0167, abs=0.002)

    moon_radii = [math.sqrt(sum(c * c for c in s.moon_wrt_earth_eclipj2000_km)) for s in one_month]
    moon_ecc = (max(moon_radii) - min(moon_radii)) / (max(moon_radii) + min(moon_radii))
    assert 0.04 < moon_ecc < 0.08

    max_inclination_deg = max(
        abs(
            math.degrees(
                math.asin(s.moon_wrt_earth_eclipj2000_km[2] / math.sqrt(sum(c * c for c in s.moon_wrt_earth_eclipj2000_km)))
            )
        )
        for s in one_month
    )
    assert 4.8 < max_inclination_deg < 5.6

    # Check vector addition identity, monotonic ET/UTC, pxform orthogonality, and tidal locking
    for idx in (0, len(one_year) // 3, (2 * len(one_year)) // 3, len(one_year) - 1):
        pt = one_year[idx]
        if idx > 0:
            assert pt.ephemeris_time > one_year[idx - 1].ephemeris_time
            assert pt.timestamp_utc > one_year[idx - 1].timestamp_utc
            assert pt.elapsed_seconds > one_year[idx - 1].elapsed_seconds

        e = np.asarray(pt.earth_wrt_sun_eclipj2000_km)
        m = np.asarray(pt.moon_wrt_earth_eclipj2000_km)
        ms = np.asarray(pt.moon_wrt_sun_eclipj2000_km)
        np.testing.assert_allclose(ms, e + m, rtol=0.0, atol=1e-7)

        # Direct SPICE check MOON wrt SUN
        direct_ms, _ = spice.spkpos("MOON", pt.ephemeris_time, "ECLIPJ2000", "NONE", "SUN")
        np.testing.assert_allclose(ms, np.asarray(direct_ms), rtol=0.0, atol=1e-6)

        mat = np.asarray(pt.moon_me_to_eclipj2000)
        assert mat.shape == (3, 3)
        np.testing.assert_allclose(mat.T @ mat, np.eye(3), rtol=0.0, atol=1e-12)
        assert float(np.linalg.det(mat)) == pytest.approx(1.0, abs=1e-12)

        # Tidal locking: +X_MOON_ME (col 0) points toward Earth (-moon_wrt_earth) within <= 10 deg libration
        x_me_eclip = mat[:, 0]
        to_earth_unit = -m / float(np.linalg.norm(m))
        cos_libration = float(np.clip(np.dot(x_me_eclip, to_earth_unit), -1.0, 1.0))
        libration_deg = math.degrees(math.acos(cos_libration))
        assert libration_deg < 10.5


def test_orbital_trajectory_start_date_shift() -> None:
    """Changing start date must reflect true SPICE perihelion (Jan) vs aphelion (Jul) geometry."""
    jan = datetime(2026, 1, 3, 0, 0, 0, tzinfo=UTC)
    jul = datetime(2026, 7, 4, 0, 0, 0, tzinfo=UTC)
    from datetime import timedelta

    _, jan_traj = compute_inertial_orbital_trajectory(jan, jan + timedelta(days=1), num_samples=64)
    _, jul_traj = compute_inertial_orbital_trajectory(jul, jul + timedelta(days=1), num_samples=64)

    r_jan = math.sqrt(sum(c * c for c in jan_traj[0].earth_wrt_sun_eclipj2000_km))
    r_jul = math.sqrt(sum(c * c for c in jul_traj[0].earth_wrt_sun_eclipj2000_km))
    assert r_jan < 147_500_000.0  # Near perihelion (~147.1M km)
    assert r_jul > 151_800_000.0  # Near aphelion (~152.1M km)
    assert r_jul - r_jan > 4_500_000.0


def test_orbital_trajectory_api_endpoint_read_only_validation_and_regression(
    client: TestClient,
) -> None:
    """Verify HTTP endpoint contract, 64..4096 bounds, coverage errors, read-only guarantee & series pagination."""
    simulation_rate_limiter.reset()
    created_ids: list[uuid.UUID] = []
    site_id = _get_published_site_id()

    try:
        # 1. Missing simulation ID -> 404
        missing_resp = client.get(f"/api/v1/simulations/{uuid.uuid4()}/orbital-trajectory")
        assert missing_resp.status_code == 404

        # 2. Create and complete a real simulation (27.322 days -> >2000 coarse samples for series pagination!)
        resp = client.post(
            "/api/v1/simulations",
            json={
                "site_id": site_id,
                "start_time": "2026-06-01T00:00:00Z",
                "duration_seconds": 2360621,
                "playback_speed": 600,
            },
        )
        assert resp.status_code == 202, resp.text
        sim_id = uuid.UUID(resp.json()["simulation_id"])
        created_ids.append(sim_id)

        claimed, outcome = run_once(worker_id="orbital-test-worker")
        assert claimed is True
        assert outcome == "completed"

        with SessionLocal() as db:
            sample_count_before = int(
                db.scalar(
                    select(func.count(SimulationSample.sample_id)).where(
                        SimulationSample.simulation_id == sim_id
                    )
                )
                or 0
            )
            assert sample_count_before > 2000

        # 3. Invalid samples parameter rejected cleanly (64..4096)
        assert client.get(f"/api/v1/simulations/{sim_id}/orbital-trajectory?samples=32").status_code == 422
        assert client.get(f"/api/v1/simulations/{sim_id}/orbital-trajectory?samples=4097").status_code == 422

        # 4. Default samples=1024 returns full-interval ECLIPJ2000 vectors & MOON_ME matrix
        traj_resp = client.get(f"/api/v1/simulations/{sim_id}/orbital-trajectory")
        assert traj_resp.status_code == 200, traj_resp.text
        body = traj_resp.json()

        assert body["simulation_id"] == str(sim_id)
        assert body["coordinate_frame"] == "ECLIPJ2000"
        assert body["lunar_body_frame"] == "MOON_ME"
        assert body["distance_units"] == "kilometers"
        assert body["aberration_policy"] == "NONE"
        assert body["duration_seconds"] == 2360621
        assert body["sample_count"] == 1024
        assert len(body["samples"]) == 1024
        assert body["samples"][0]["elapsed_seconds"] == 0.0
        assert body["samples"][-1]["elapsed_seconds"] == pytest.approx(2360621.0, abs=1.0)
        assert body["site"]["site_id"] == site_id

        # Check vector addition identity on serialized payload
        s0 = body["samples"][512]
        assert s0["moon_wrt_sun_eclipj2000_km"][0] == pytest.approx(
            s0["earth_wrt_sun_eclipj2000_km"][0] + s0["moon_wrt_earth_eclipj2000_km"][0],
            abs=1e-6,
        )

        # 5. Series pagination covers complete period including exact last sample
        p1 = client.get(f"/api/v1/simulations/{sim_id}/series?offset=0&limit=2000").json()
        p2 = client.get(
            f"/api/v1/simulations/{sim_id}/series?offset={p1['returned_samples']}&limit=2000&include_horizon=false"
        ).json()
        combined = p1["samples"] + p2["samples"]
        assert len(combined) == p1["total_samples_available"]
        assert combined[0]["elapsed_seconds"] == 0.0
        assert combined[-1]["elapsed_seconds"] == pytest.approx(2360621.0, abs=1.0)

        # 6. Verify orbital-trajectory did NOT alter any database sample rows or internal paths leaked
        assert "/" not in body["ephemeris_source"] or "NASA" in body["ephemeris_source"]
        with SessionLocal() as db:
            sample_count_after = int(
                db.scalar(
                    select(func.count(SimulationSample.sample_id)).where(
                        SimulationSample.simulation_id == sim_id
                    )
                )
                or 0
            )
            assert sample_count_after == sample_count_before

        # 7. Coverage error handling must return 422 without leaking host filesystem paths
        with patch(
            "app.services.simulation_service.compute_inertial_orbital_trajectory",
            side_effect=SpiceCoverageError(
                message="Out of range",
                valid_start_utc="1549-12-31T00:00:00Z",
                valid_end_utc="2650-01-25T00:00:00Z",
                responsible_kernel="de440.bsp",
            ),
        ):
            cov_resp = client.get(f"/api/v1/simulations/{sim_id}/orbital-trajectory")
            assert cov_resp.status_code == 422
            detail = cov_resp.json()["detail"]
            assert detail["code"] == "SPICE_COVERAGE_ERROR"
            assert detail["responsible_kernel"] == "de440.bsp"
    finally:
        _cleanup_runs(created_ids)
        simulation_rate_limiter.reset()
