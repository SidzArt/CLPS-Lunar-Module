"""Solar illumination, Earth geometric visibility, and event-window analytics.

Implements strict distinction between:
- Terrain-aware solar illumination (comparing apparent solar disk elevation against radial DEM
  horizon obstruction, without claiming solar-panel electrical power availability).
- Earth geometric line-of-sight visibility (without claiming RF communication link margin).
- Concurrent visibility windows where both conditions hold simultaneously.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

import numpy as np
from numpy.typing import NDArray

SUN_RADIUS_KM: Final[float] = 695_700.0
EARTH_MEAN_RADIUS_KM: Final[float] = 6_371.0

SUN_VISIBLE: Final[str] = "VISIBLE"
SUN_PARTIAL: Final[str] = "PARTIALLY_OBSTRUCTED"
SUN_NOT_VISIBLE: Final[str] = "NOT_VISIBLE"

EARTH_VISIBLE: Final[str] = "VISIBLE"
EARTH_NOT_VISIBLE: Final[str] = "NOT_VISIBLE"


@dataclass(frozen=True)
class HorizonProfileData:
    """In-memory radial terrain horizon curve ``theta_hor(psi)`` in local ENU frame."""

    azimuths_deg: NDArray[np.float64]
    elevations_deg: NDArray[np.float64]
    quality_state: str
    azimuth_bins: int
    default_horizon_deg: float = 0.0
    _az_ext: NDArray[np.float64] = field(init=False, repr=False, compare=False)
    _el_ext: NDArray[np.float64] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Precompute circularly wrapped arrays once to avoid per-sample allocations."""
        if self.azimuths_deg.size > 0 and self.elevations_deg.size > 0:
            object.__setattr__(
                self,
                "_az_ext",
                np.concatenate([self.azimuths_deg, [self.azimuths_deg[0] + 360.0]]),
            )
            object.__setattr__(
                self,
                "_el_ext",
                np.concatenate([self.elevations_deg, [self.elevations_deg[0]]]),
            )
        else:
            empty = np.empty(0, dtype=np.float64)
            object.__setattr__(self, "_az_ext", empty)
            object.__setattr__(self, "_el_ext", empty)

    def interpolate(self, azimuth_deg: float) -> float:
        """Circularly interpolate terrain horizon elevation (deg) for azimuth in [0, 360)."""
        if self._az_ext.size == 0 or self._el_ext.size == 0:
            return self.default_horizon_deg
        az = float(azimuth_deg) % 360.0
        # Handle azimuths strictly before first bin center by wrapping +360
        az_query = az if az >= float(self.azimuths_deg[0]) else az + 360.0
        return float(np.interp(az_query, self._az_ext, self._el_ext))

    @classmethod
    def flat_geometric(cls, azimuth_bins: int = 360) -> HorizonProfileData:
        """Construct zero-elevation geometric horizon used only when DEM is unavailable."""
        bin_step = 360.0 / float(azimuth_bins)
        az = np.arange(azimuth_bins, dtype=np.float64) * bin_step
        el = np.zeros(azimuth_bins, dtype=np.float64)
        return cls(
            azimuths_deg=az,
            elevations_deg=el,
            quality_state="geometric_only",
            azimuth_bins=azimuth_bins,
        )


def compute_angular_radius_deg(body_radius_km: float, distance_km: float) -> float:
    """Compute angular semi-diameter (degrees) of a spherical body at range ``distance_km``."""
    if distance_km <= body_radius_km:
        return 90.0
    ratio = min(1.0, max(0.0, body_radius_km / distance_km))
    return float(math.degrees(math.asin(ratio)))


def classify_sun_visibility(
    sun_elevation_deg: float,
    horizon_elevation_deg: float,
    sun_range_km: float,
) -> tuple[str, float, float]:
    """Classify Sun visibility accounting for finite solar angular radius.

    Returns:
        Tuple ``(status, illuminated_disk_fraction, sun_angular_radius_deg)``.
    """
    ang_radius = compute_angular_radius_deg(SUN_RADIUS_KM, sun_range_km)
    margin = sun_elevation_deg - horizon_elevation_deg
    if margin >= ang_radius:
        return SUN_VISIBLE, 1.0, ang_radius
    if margin <= -ang_radius:
        return SUN_NOT_VISIBLE, 0.0, ang_radius

    x = float(np.clip(margin / ang_radius, -1.0, 1.0))
    # Exact circular disk segment illuminated above horizontal straight edge approximation
    disk_fraction = (math.acos(-x) + x * math.sqrt(max(0.0, 1.0 - x * x))) / math.pi
    return SUN_PARTIAL, float(np.clip(disk_fraction, 0.0, 1.0)), ang_radius


def classify_earth_visibility(
    earth_elevation_deg: float,
    horizon_elevation_deg: float,
) -> str:
    """Classify Earth center geometric line-of-sight against local terrain horizon."""
    return EARTH_VISIBLE if earth_elevation_deg >= horizon_elevation_deg else EARTH_NOT_VISIBLE


@dataclass(frozen=True)
class EvaluatedState:
    """Single evaluated timestamp geometry and visibility classification."""

    timestamp_utc: datetime
    et: float
    sun_azimuth_deg: float
    sun_elevation_deg: float
    sun_range_km: float
    earth_azimuth_deg: float
    earth_elevation_deg: float
    earth_range_km: float
    sun_horizon_deg: float
    earth_horizon_deg: float
    sun_visibility_status: str
    sun_disk_fraction: float
    earth_visibility_status: str
    concurrent_visible: bool
    sun_dir_moon: tuple[float, float, float]
    earth_dir_moon: tuple[float, float, float]
    subsolar_lat_deg: float
    subsolar_lon_deg: float
    quality_status: str


@dataclass(frozen=True)
class DetectedEventWindow:
    """Detected instantaneous transition or continuous interval window."""

    event_type: str
    window_start_utc: datetime
    window_end_utc: datetime
    duration_seconds: int
    confidence_status: str
    method_version: str
    metadata: dict[str, object]


def _extract_state_intervals(
    timeline: list[EvaluatedState],
    predicate: list[bool],
    event_type: str,
    confidence_map: dict[int, str],
    method_version: str,
) -> tuple[list[DetectedEventWindow], float, float]:
    """Extract contiguous True intervals plus total & longest duration (seconds)."""
    if len(timeline) < 2:
        total = 0.0
        windows: list[DetectedEventWindow] = []
        if len(timeline) == 1 and predicate[0]:
            windows.append(
                DetectedEventWindow(
                    event_type=event_type,
                    window_start_utc=timeline[0].timestamp_utc,
                    window_end_utc=timeline[0].timestamp_utc,
                    duration_seconds=0,
                    confidence_status=confidence_map.get(0, "boundary_start"),
                    method_version=method_version,
                    metadata={},
                )
            )
        return windows, total, total

    windows = []
    total_sec = 0.0
    longest_sec = 0.0
    in_run = predicate[0]
    run_start_idx = 0

    for i in range(len(timeline) - 1):
        curr = predicate[i]
        nxt = predicate[i + 1]
        if in_run and not nxt:
            # Interval ends cleanly at refined transition i (or transition midpoint i+1 if nxt flips)
            end_idx = i if not curr else i + 1
            start_dt = timeline[run_start_idx].timestamp_utc
            end_dt = timeline[end_idx].timestamp_utc
            dur = max(0.0, (end_dt - start_dt).total_seconds())
            total_sec += dur
            longest_sec = max(longest_sec, dur)
            windows.append(
                DetectedEventWindow(
                    event_type=event_type,
                    window_start_utc=start_dt,
                    window_end_utc=end_dt,
                    duration_seconds=round(dur),
                    confidence_status=confidence_map.get(end_idx, "refined_root"),
                    method_version=method_version,
                    metadata={},
                )
            )
            in_run = False
        elif not in_run and nxt:
            run_start_idx = i + 1
            in_run = True

    if in_run:
        start_dt = timeline[run_start_idx].timestamp_utc
        end_dt = timeline[-1].timestamp_utc
        dur = max(0.0, (end_dt - start_dt).total_seconds())
        total_sec += dur
        longest_sec = max(longest_sec, dur)
        windows.append(
            DetectedEventWindow(
                event_type=event_type,
                window_start_utc=start_dt,
                window_end_utc=end_dt,
                duration_seconds=round(dur),
                confidence_status="boundary_end",
                method_version=method_version,
                metadata={},
            )
        )

    return windows, total_sec, longest_sec


def analyze_timeline(
    timeline: list[EvaluatedState],
    refined_indices: set[int],
    quality_state: str,
    method_version: str = "v1.0",
) -> tuple[dict[str, float | int | str], list[DetectedEventWindow]]:
    """Compute summary metrics and extract transition/interval event windows.

    Assumes ``timeline`` is strictly sorted ascending by ``timestamp_utc`` and includes both
    coarse grid samples and root-refined transition timestamps.
    """
    if not timeline:
        return {"sample_count": 0}, []

    total_span_s = max(
        1.0, (timeline[-1].timestamp_utc - timeline[0].timestamp_utc).total_seconds()
    )
    confidence_map: dict[int, str] = {
        idx: ("geometric_only" if quality_state == "geometric_only" else "refined_root")
        if idx in refined_indices
        else "coarse_grid"
        for idx in range(len(timeline))
    }

    sun_center_up = [s.sun_elevation_deg >= s.sun_horizon_deg for s in timeline]
    sun_any_lit = [s.sun_visibility_status != SUN_NOT_VISIBLE for s in timeline]
    sun_full_lit = [s.sun_visibility_status == SUN_VISIBLE for s in timeline]
    sun_partial = [s.sun_visibility_status == SUN_PARTIAL for s in timeline]
    sun_dark = [s.sun_visibility_status == SUN_NOT_VISIBLE for s in timeline]
    earth_vis = [s.earth_visibility_status == EARTH_VISIBLE for s in timeline]
    earth_dark = [s.earth_visibility_status == EARTH_NOT_VISIBLE for s in timeline]
    concurrent_vis = [s.concurrent_visible for s in timeline]

    events: list[DetectedEventWindow] = []

    # 1. Instantaneous rise/set transitions (Solar center crossing & Earth center crossing)
    for idx in range(len(timeline) - 1):
        cur_s = timeline[idx]
        nxt_s = timeline[idx + 1]
        conf = (
            "geometric_only"
            if quality_state == "geometric_only"
            else (
                "refined_root"
                if (idx in refined_indices or (idx + 1) in refined_indices)
                else "coarse_bracket"
            )
        )
        if not sun_center_up[idx] and sun_center_up[idx + 1]:
            events.append(
                DetectedEventWindow(
                    event_type="SUNRISE",
                    window_start_utc=nxt_s.timestamp_utc,
                    window_end_utc=nxt_s.timestamp_utc,
                    duration_seconds=0,
                    confidence_status=conf,
                    method_version=method_version,
                    metadata={
                        "azimuth_deg": round(nxt_s.sun_azimuth_deg, 3),
                        "elevation_deg": round(nxt_s.sun_elevation_deg, 3),
                        "horizon_deg": round(nxt_s.sun_horizon_deg, 3),
                    },
                )
            )
        elif sun_center_up[idx] and not sun_center_up[idx + 1]:
            events.append(
                DetectedEventWindow(
                    event_type="SUNSET",
                    window_start_utc=nxt_s.timestamp_utc,
                    window_end_utc=nxt_s.timestamp_utc,
                    duration_seconds=0,
                    confidence_status=conf,
                    method_version=method_version,
                    metadata={
                        "azimuth_deg": round(cur_s.sun_azimuth_deg, 3),
                        "elevation_deg": round(nxt_s.sun_elevation_deg, 3),
                        "horizon_deg": round(nxt_s.sun_horizon_deg, 3),
                    },
                )
            )

        if not earth_vis[idx] and earth_vis[idx + 1]:
            events.append(
                DetectedEventWindow(
                    event_type="EARTH_RISE",
                    window_start_utc=nxt_s.timestamp_utc,
                    window_end_utc=nxt_s.timestamp_utc,
                    duration_seconds=0,
                    confidence_status=conf,
                    method_version=method_version,
                    metadata={
                        "azimuth_deg": round(nxt_s.earth_azimuth_deg, 3),
                        "elevation_deg": round(nxt_s.earth_elevation_deg, 3),
                        "horizon_deg": round(nxt_s.earth_horizon_deg, 3),
                    },
                )
            )
        elif earth_vis[idx] and not earth_vis[idx + 1]:
            events.append(
                DetectedEventWindow(
                    event_type="EARTH_SET",
                    window_start_utc=nxt_s.timestamp_utc,
                    window_end_utc=nxt_s.timestamp_utc,
                    duration_seconds=0,
                    confidence_status=conf,
                    method_version=method_version,
                    metadata={
                        "azimuth_deg": round(cur_s.earth_azimuth_deg, 3),
                        "elevation_deg": round(nxt_s.earth_elevation_deg, 3),
                        "horizon_deg": round(nxt_s.earth_horizon_deg, 3),
                    },
                )
            )

    # 2. Continuous interval windows
    sunlit_wins, sunlit_any_s, _ = _extract_state_intervals(
        timeline, sun_any_lit, "SUNLIT", confidence_map, method_version
    )
    _, sunlit_full_s, _ = _extract_state_intervals(
        timeline, sun_full_lit, "SUNLIT", confidence_map, method_version
    )
    partial_wins, partial_s, _ = _extract_state_intervals(
        timeline, sun_partial, "PARTIAL_ILLUMINATION", confidence_map, method_version
    )
    dark_wins, dark_s, longest_dark_s = _extract_state_intervals(
        timeline, sun_dark, "TOTAL_DARKNESS", confidence_map, method_version
    )
    earth_wins, earth_vis_s, _ = _extract_state_intervals(
        timeline, earth_vis, "EARTH_VISIBLE", confidence_map, method_version
    )
    _, _, longest_earth_blackout_s = _extract_state_intervals(
        timeline, earth_dark, "TOTAL_DARKNESS", confidence_map, method_version
    )
    conc_wins, conc_s, _ = _extract_state_intervals(
        timeline, concurrent_vis, "CONCURRENT_VISIBLE", confidence_map, method_version
    )

    events.extend(sunlit_wins)
    events.extend(partial_wins)
    events.extend(dark_wins)
    events.extend(earth_wins)
    events.extend(conc_wins)
    events.sort(key=lambda e: (e.window_start_utc, e.event_type))

    sun_els = [s.sun_elevation_deg for s in timeline]
    earth_els = [s.earth_elevation_deg for s in timeline]

    summary: dict[str, float | int | str] = {
        "total_duration_seconds": round(total_span_s),
        "sunlit_duration_seconds": round(sunlit_any_s, 2),
        "full_sun_duration_seconds": round(sunlit_full_s, 2),
        "partial_sun_duration_seconds": round(partial_s, 2),
        "sunlit_fraction_pct": round(100.0 * min(1.0, sunlit_any_s / total_span_s), 3),
        "full_sun_fraction_pct": round(100.0 * min(1.0, sunlit_full_s / total_span_s), 3),
        "total_darkness_seconds": round(dark_s, 2),
        "longest_darkness_seconds": round(longest_dark_s, 2),
        "longest_darkness_hours": round(longest_dark_s / 3600.0, 3),
        "earth_visible_duration_seconds": round(earth_vis_s, 2),
        "earth_visible_fraction_pct": round(100.0 * min(1.0, earth_vis_s / total_span_s), 3),
        "longest_earth_blackout_seconds": round(longest_earth_blackout_s, 2),
        "longest_earth_blackout_hours": round(longest_earth_blackout_s / 3600.0, 3),
        "concurrent_visible_seconds": round(conc_s, 2),
        "concurrent_visible_fraction_pct": round(100.0 * min(1.0, conc_s / total_span_s), 3),
        "max_sun_elevation_deg": round(max(sun_els), 3),
        "min_sun_elevation_deg": round(min(sun_els), 3),
        "max_earth_elevation_deg": round(max(earth_els), 3),
        "min_earth_elevation_deg": round(min(earth_els), 3),
        "sunrise_count": sum(1 for e in events if e.event_type == "SUNRISE"),
        "sunset_count": sum(1 for e in events if e.event_type == "SUNSET"),
        "earth_rise_count": sum(1 for e in events if e.event_type == "EARTH_RISE"),
        "earth_set_count": sum(1 for e in events if e.event_type == "EARTH_SET"),
        "quality_state": quality_state,
    }
    return summary, events
