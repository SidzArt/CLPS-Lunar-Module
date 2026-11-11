"""Coordinate transformations between LOLA GeoTIFF raster grids and lunar MOON_ME frame.

Enforces explicit (longitude, latitude) axis ordering (``always_xy=True``) using the GeoTIFF's
own PyProj CRS and geodetic datum metadata rather than hardcoded EPSG assumptions.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
from affine import Affine
from numpy.typing import NDArray
from pyproj import CRS, Transformer
from rasterio.transform import rowcol

from app.services.geometry import LUNAR_REFERENCE_RADIUS_M


@dataclass(frozen=True)
class RasterTransformContext:
    """Validated CRS and affine mapping context extracted from a GeoTIFF DEM."""

    raster_crs_proj4: str
    raster_crs_wkt: str
    geodetic_crs_proj4: str
    datum_radius_m: float
    pixel_registration: str  # "Area" (pixel-centered) or "Point"
    transform: Affine
    frame_source: str = "MOON_ME_DE421"
    frame_target: str = "MOON_ME_DE440_ME421"


def build_raster_context(
    crs_input: object,
    transform: Affine,
    area_or_point: str | None = None,
    default_radius_m: float = LUNAR_REFERENCE_RADIUS_M,
) -> tuple[RasterTransformContext, Transformer, Transformer]:
    """Build forward and inverse PyProj transformers respecting GeoTIFF metadata.

    Args:
        crs_input: ``rasterio.crs.CRS``, WKT string, or PROJ string from opened GeoTIFF.
        transform: GeoTIFF affine transform matrix.
        area_or_point: GDAL ``AREA_OR_POINT`` tag (defaults to ``'Area'``).
        default_radius_m: Fallback lunar reference radius in meters if CRS lacks ellipsoid.

    Returns:
        ``(RasterTransformContext, to_raster_transformer, to_lonlat_transformer)``.
    """
    if crs_input is None:
        raise ValueError("GeoTIFF has no CRS metadata; cannot project coordinates safely.")

    raster_crs = CRS.from_user_input(crs_input)
    geodetic_crs = raster_crs if raster_crs.is_geographic else raster_crs.geodetic_crs
    if geodetic_crs is None:
        geodetic_crs = CRS.from_proj4(f"+proj=longlat +R={default_radius_m} +no_defs")

    radius_m = default_radius_m
    if raster_crs.ellipsoid is not None and raster_crs.ellipsoid.semi_major_metre:
        radius_m = float(raster_crs.ellipsoid.semi_major_metre)

    to_raster = Transformer.from_crs(geodetic_crs, raster_crs, always_xy=True)
    to_lonlat = Transformer.from_crs(raster_crs, geodetic_crs, always_xy=True)

    reg = (area_or_point or "Area").strip()
    if reg not in ("Area", "Point"):
        reg = "Area"

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        proj4_str = raster_crs.to_proj4()
        geodetic_proj4_str = geodetic_crs.to_proj4()

    ctx = RasterTransformContext(
        raster_crs_proj4=proj4_str,
        raster_crs_wkt=raster_crs.to_wkt(),
        geodetic_crs_proj4=geodetic_proj4_str,
        datum_radius_m=radius_m,
        pixel_registration=reg,
        transform=transform,
    )
    return ctx, to_raster, to_lonlat


def lonlat_to_raster_xy(
    to_raster: Transformer,
    lon_deg: float | NDArray[np.float64],
    lat_deg: float | NDArray[np.float64],
) -> tuple[float | NDArray[np.float64], float | NDArray[np.float64]]:
    """Transform east-positive (lon_deg, lat_deg) into projected raster (x, y)."""
    return to_raster.transform(lon_deg, lat_deg)


def raster_xy_to_lonlat(
    to_lonlat: Transformer,
    x_coords: float | NDArray[np.float64],
    y_coords: float | NDArray[np.float64],
) -> tuple[float | NDArray[np.float64], float | NDArray[np.float64]]:
    """Transform projected raster (x, y) into east-positive (lon_deg, lat_deg)."""
    return to_lonlat.transform(x_coords, y_coords)


def raster_xy_to_rowcol(
    transform: Affine,
    x_m: float,
    y_m: float,
) -> tuple[int, int]:
    """Convert projected map coordinates (x, y) to integer pixel (row, col)."""
    r, c = rowcol(transform, x_m, y_m)
    return int(r), int(c)
