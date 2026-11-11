"""Spherical 13-region Moon LED resolution with boundary tie-breaking and verification gates."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.services.geometry import lat_lon_elev_to_cartesian_m, local_enu_basis

BOUNDARY_EPSILON = 1e-6


class LedMappingError(ValueError):
    """Base error raised for invalid Moon LED region inputs or incomplete mappings."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class LedMappingVerificationError(LedMappingError):
    """Raised when bench-verified 13-region LED topology is required but unavailable."""

    def __init__(self, message: str):
        super().__init__("led_mapping_unverified", message)


@dataclass(frozen=True)
class LedPixelOutput:
    """Normalized physical LED/GPIO target associated with a lunar region."""

    pixel_index: int
    output_channel: int | None
    pixel_order: int
    topology_mode: str
    verification_status: str


@dataclass(frozen=True)
class LedRegionDefinition:
    """Self-contained 13-region geometric and physical LED mapping record."""

    region_index: int
    region_name: str
    mapping_version: str
    verification_status: str
    centroid_lat_deg: float | None
    centroid_lon_deg: float | None
    boundary_polygon: Any | None
    pixel_indices: list[int]
    orientation_reference: str | None = None
    geometry_source: str | None = None
    normalized_pixels: list[LedPixelOutput] = field(default_factory=list)
    is_active: bool = True


@dataclass(frozen=True)
class MoonLedResolution:
    """Resolved region index, physical LED pixels, and provenance/verification flags."""

    region_index: int
    region_name: str
    mapping_version: str
    mapping_mode: (
        str  # 'polygon_verified' | 'polygon_boundary_tie_broken' | 'approximate_centroid_only'
    )
    verification_status: str
    is_verified_for_hardware: bool
    pixel_indices: list[int]
    output_channels: list[int]
    centroid_angular_distance_deg: float | None
    boundary_tie_broken: bool
    tie_candidate_regions: list[int]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize LED mapping output into JSON-safe command payload segment."""
        return {
            "region_index": self.region_index,
            "region_name": self.region_name,
            "mapping_version": self.mapping_version,
            "mapping_mode": self.mapping_mode,
            "verification_status": self.verification_status,
            "is_verified_for_hardware": self.is_verified_for_hardware,
            "pixel_indices": list(self.pixel_indices),
            "output_channels": list(self.output_channels),
            "centroid_angular_distance_deg": (
                round(self.centroid_angular_distance_deg, 4)
                if self.centroid_angular_distance_deg is not None
                else None
            ),
            "boundary_tie_broken": self.boundary_tie_broken,
            "tie_candidate_regions": list(self.tie_candidate_regions),
            "warnings": list(self.warnings),
        }


def validate_region_index(region_index: int) -> int:
    """Ensure Moon LED region index lies strictly in 1..13."""
    if region_index < 1 or region_index > 13:
        raise LedMappingError(
            "invalid_region_index",
            f"Moon LED region_index must be between 1 and 13 inclusive (got {region_index}).",
        )
    return region_index


def _extract_polygon_rings(raw_polygon: Any) -> list[list[tuple[float, float]]]:
    """Normalize GeoJSON Polygon, vertex dict list, or [lon, lat] lists into (lat, lon) rings."""
    if raw_polygon is None:
        return []

    if isinstance(raw_polygon, dict):
        geom_type = str(raw_polygon.get("type", "")).lower()
        coords = raw_polygon.get("coordinates")
        if geom_type == "polygon" and isinstance(coords, list) and coords:
            return _extract_polygon_rings(coords[0])
        if geom_type == "multipolygon" and isinstance(coords, list) and coords:
            rings: list[list[tuple[float, float]]] = []
            for poly in coords:
                if isinstance(poly, list) and poly:
                    rings.extend(_extract_polygon_rings(poly[0]))
            return rings
        return []

    if isinstance(raw_polygon, list) and raw_polygon:
        first = raw_polygon[0]
        # List of coordinate pairs or dicts representing a single outer ring
        if isinstance(first, dict) and "lat" in first and "lon" in first:
            ring = [(float(pt["lat"]), float(pt["lon"])) for pt in raw_polygon]
            return [ring] if len(ring) >= 3 else []
        if (
            isinstance(first, (list, tuple))
            and len(first) >= 2
            and isinstance(first[0], (int, float))
        ):
            # GeoJSON [lon, lat] convention by default
            ring = [(float(pt[1]), float(pt[0])) for pt in raw_polygon]
            return [ring] if len(ring) >= 3 else []
        if isinstance(first, list):
            rings = []
            for sub in raw_polygon:
                rings.extend(_extract_polygon_rings(sub))
            return rings

    return []


def _point_to_segment_distance(
    px: float, py: float, ax: float, ay: float, bx: float, by: float
) -> float:
    """Compute shortest 2D Euclidean distance from point P to segment AB."""
    vx, vy = bx - ax, by - ay
    seg_len_sq = vx * vx + vy * vy
    if seg_len_sq <= 1e-18:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / seg_len_sq))
    proj_x = ax + t * vx
    proj_y = ay + t * vy
    return math.hypot(px - proj_x, py - proj_y)


def _point_in_projected_ring(
    lat_deg: float, lon_deg: float, ring_lat_lon: list[tuple[float, float]]
) -> tuple[bool, bool]:
    """Test whether (lat, lon) lies inside or on the boundary of a spherical polygon ring.

    Projects vertices onto the polygon centroid's local East-North tangent plane so antimeridian
    wrap-around and high polar latitudes remain singularity-free.
    """
    ring_vecs = [
        lat_lon_elev_to_cartesian_m(lat, lon, 0.0, radius_m=1.0) for lat, lon in ring_lat_lon
    ]
    mean_vec = np.mean(np.stack(ring_vecs, axis=0), axis=0)
    mean_norm = float(np.linalg.norm(mean_vec))
    if mean_norm <= 1e-12:
        return False, False
    center_unit = mean_vec / mean_norm

    target_vec = lat_lon_elev_to_cartesian_m(lat_deg, lon_deg, 0.0, radius_m=1.0)
    # Reject opposite-hemisphere points (> 90 deg from polygon center)
    if float(np.dot(center_unit, target_vec)) <= 0.0:
        return False, False

    c_lat = math.degrees(math.asin(max(-1.0, min(1.0, float(center_unit[2])))))
    c_lon = math.degrees(math.atan2(float(center_unit[1]), float(center_unit[0])))
    east, north, up = local_enu_basis(c_lat, c_lon)

    def _project_gnomonic(vec: np.ndarray) -> tuple[float, float] | None:
        denom = float(np.dot(vec, up))
        if denom <= 1e-6:
            return None
        return float(np.dot(vec, east) / denom), float(np.dot(vec, north) / denom)

    proj_target = _project_gnomonic(target_vec)
    if proj_target is None:
        return False, False
    px, py = proj_target

    proj_ring: list[tuple[float, float]] = []
    for v in ring_vecs:
        pv = _project_gnomonic(v)
        if pv is None:
            return False, False
        proj_ring.append(pv)

    # Check exact boundary proximity first for deterministic shared-edge tie-breaking
    n = len(proj_ring)
    for idx in range(n):
        ax, ay = proj_ring[idx]
        bx, by = proj_ring[(idx + 1) % n]
        if _point_to_segment_distance(px, py, ax, ay, bx, by) <= BOUNDARY_EPSILON:
            return True, True

    # Standard even-odd ray cast in tangent plane
    inside = False
    for idx in range(n):
        x1, y1 = proj_ring[idx]
        x2, y2 = proj_ring[(idx + 1) % n]
        if (y1 > py) != (y2 > py):
            x_intersect = (x2 - x1) * (py - y1) / (y2 - y1) + x1
            if px <= x_intersect:
                inside = not inside
    return inside, False


def _great_circle_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute central angular distance in degrees on a sphere."""
    u = lat_lon_elev_to_cartesian_m(lat1, lon1, 0.0, radius_m=1.0)
    v = lat_lon_elev_to_cartesian_m(lat2, lon2, 0.0, radius_m=1.0)
    dot = max(-1.0, min(1.0, float(np.dot(u, v))))
    return math.degrees(math.acos(dot))


def _resolve_region_pixels(region: LedRegionDefinition) -> tuple[list[int], list[int], bool]:
    """Return ordered physical pixel indices, output channels, and verified hardware status."""
    active_norm = sorted(
        [p for p in region.normalized_pixels],
        key=lambda p: (p.pixel_order, p.pixel_index),
    )
    if active_norm:
        pixels = [p.pixel_index for p in active_norm]
        channels = [p.output_channel if p.output_channel is not None else 0 for p in active_norm]
        pixels_verified = all(p.verification_status == "bench_verified" for p in active_norm)
        return (
            pixels,
            channels,
            region.verification_status == "bench_verified" and pixels_verified and len(pixels) > 0,
        )

    pixels = list(region.pixel_indices)
    channels = [0 for _ in pixels]
    return pixels, channels, region.verification_status == "bench_verified" and len(pixels) > 0


def resolve_site_to_moon_led_region(
    *,
    site_lat_deg: float,
    site_lon_deg: float,
    regions: list[LedRegionDefinition],
    require_verified_mapping: bool = True,
    allow_centroid_fallback: bool = False,
) -> MoonLedResolution:
    """Map landing site (lat, lon) onto one of the 13 physical Moon LED regions.

    Priority:
    1. Regions with explicit ``boundary_polygon`` containing (or on boundary of) the site,
       deterministically breaking boundary/overlap ties by lowest ``region_index``.
    2. Nearest spherical centroid only when polygons do not cover the site and
       ``allow_centroid_fallback=True`` (explicitly tagged ``approximate_centroid_only``).
    """
    active_regions = sorted(
        [r for r in regions if r.is_active and r.verification_status != "deprecated"],
        key=lambda r: r.region_index,
    )
    if not active_regions:
        raise LedMappingVerificationError(
            "No active Moon LED regions configured; physical region topology is unmapped."
        )

    for r in active_regions:
        validate_region_index(r.region_index)

    polygon_matches: list[tuple[LedRegionDefinition, bool]] = []
    for region in active_regions:
        rings = _extract_polygon_rings(region.boundary_polygon)
        for ring in rings:
            inside, on_boundary = _point_in_projected_ring(site_lat_deg, site_lon_deg, ring)
            if inside:
                polygon_matches.append((region, on_boundary))
                break

    warnings: list[str] = []
    tie_broken = False
    tie_candidates: list[int] = []
    mapping_mode = "polygon_verified"
    selected: LedRegionDefinition | None = None
    centroid_dist_deg: float | None = None

    if polygon_matches:
        polygon_matches.sort(key=lambda item: item[0].region_index)
        tie_candidates = [item[0].region_index for item in polygon_matches]
        selected = polygon_matches[0][0]
        if len(polygon_matches) > 1 or polygon_matches[0][1]:
            tie_broken = True
            mapping_mode = "polygon_boundary_tie_broken"
            warnings.append(
                f"Boundary/overlap tie resolved deterministically to lowest region_index={selected.region_index} "
                f"(candidates={tie_candidates})."
            )
    else:
        if not allow_centroid_fallback:
            raise LedMappingVerificationError(
                "No verified Moon LED boundary polygon contains the landing site, and centroid-only "
                "fallback is disabled until bench-verified region geometry is uploaded."
            )
        centroid_ranked: list[tuple[float, int, LedRegionDefinition]] = []
        for region in active_regions:
            if region.centroid_lat_deg is not None and region.centroid_lon_deg is not None:
                dist = _great_circle_deg(
                    site_lat_deg,
                    site_lon_deg,
                    region.centroid_lat_deg,
                    region.centroid_lon_deg,
                )
                centroid_ranked.append((dist, region.region_index, region))
        if not centroid_ranked:
            raise LedMappingVerificationError(
                "No Moon LED region polygons or centroids are available for site mapping."
            )
        centroid_ranked.sort(key=lambda item: (round(item[0], 6), item[1]))
        centroid_dist_deg, _, selected = centroid_ranked[0]
        mapping_mode = "approximate_centroid_only"
        warnings.append(
            f"Resolved via nearest spherical centroid ({centroid_dist_deg:.2f} deg); "
            "exact 13-region boundary geometry is unverified."
        )
        if len(centroid_ranked) > 1 and abs(centroid_ranked[1][0] - centroid_dist_deg) <= 1e-4:
            tie_broken = True
            tie_candidates = [centroid_ranked[0][1], centroid_ranked[1][1]]

    assert selected is not None
    if centroid_dist_deg is None and (
        selected.centroid_lat_deg is not None and selected.centroid_lon_deg is not None
    ):
        centroid_dist_deg = _great_circle_deg(
            site_lat_deg, site_lon_deg, selected.centroid_lat_deg, selected.centroid_lon_deg
        )

    pixels, channels, is_verified = _resolve_region_pixels(selected)
    if not pixels:
        raise LedMappingVerificationError(
            f"Moon LED region {selected.region_index} ('{selected.region_name}') has no mapped pixel indices."
        )

    if selected.verification_status != "bench_verified":
        warnings.append(
            f"Moon LED region {selected.region_index} verification_status='{selected.verification_status}'."
        )

    if require_verified_mapping and not is_verified:
        raise LedMappingVerificationError(
            f"Moon LED region {selected.region_index} ('{selected.region_name}', "
            f"status='{selected.verification_status}') is not bench_verified."
        )

    return MoonLedResolution(
        region_index=selected.region_index,
        region_name=selected.region_name,
        mapping_version=selected.mapping_version,
        mapping_mode=mapping_mode,
        verification_status=selected.verification_status,
        is_verified_for_hardware=is_verified and mapping_mode != "approximate_centroid_only",
        pixel_indices=pixels,
        output_channels=channels,
        centroid_angular_distance_deg=centroid_dist_deg,
        boundary_tie_broken=tie_broken,
        tie_candidate_regions=tie_candidates,
        warnings=warnings,
    )
