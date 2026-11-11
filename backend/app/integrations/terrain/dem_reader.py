"""Controlled NASA LOLA DEM asset registry and bounded window reader."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from numpy.typing import NDArray
from rasterio.windows import Window, from_bounds
from shapely.geometry import Point, box

from app.core.config import settings
from app.integrations.terrain.coordinate_transform import (
    RasterTransformContext,
    build_raster_context,
    lonlat_to_raster_xy,
    raster_xy_to_rowcol,
)


@dataclass(frozen=True)
class DEMAssetMetadata:
    """Verified metadata and provenance of a single GeoTIFF DEM asset."""

    asset_id: str
    filename: str
    sha256: str
    file_size_bytes: int
    width: int
    height: int
    pixel_size_x_m: float
    pixel_size_y_m: float
    dtype: str
    nodata_value: float | None
    crs_proj4: str
    pixel_registration: str
    bounds_left_m: float
    bounds_bottom_m: float
    bounds_right_m: float
    bounds_top_m: float
    elevation_unit: str
    lunar_frame: str
    source: str
    citation: str
    dataset_version: str
    count_filename: str | None = None
    error_filename: str | None = None


@dataclass(frozen=True)
class DEMCoverageSelection:
    """Best controlled DEM asset covering a candidate landing site."""

    asset: DEMAssetMetadata
    site_x_m: float
    site_y_m: float
    min_edge_margin_m: float
    full_horizon_covered: bool


@dataclass
class DEMWindowSample:
    """Bounded terrain window plus companion count/uncertainty grids for horizon modeling."""

    asset: DEMAssetMetadata
    context: RasterTransformContext
    window_transform: Any
    elevation_m: NDArray[np.float64]
    count_grid: NDArray[np.float64] | None
    error_m_grid: NDArray[np.float64] | None
    site_elev_m: float | None
    site_count: float | None
    site_error_m: float | None
    site_x_m: float
    site_y_m: float
    min_edge_margin_m: float
    full_horizon_covered: bool
    to_lonlat: Any


def compute_file_sha256(file_path: Path) -> str:
    """Compute SHA-256 hex digest using buffered streaming."""
    digest = hashlib.sha256()
    with file_path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class DEMRegistry:
    """Manages verified GeoTIFF DEM assets within settings.resolved_dem_root only."""

    def __init__(self, dem_root: str | Path | None = None) -> None:
        self.dem_root = Path(dem_root or settings.resolved_dem_root).resolve()
        self._assets: list[DEMAssetMetadata] | None = None

    def _safe_child_path(self, filename: str) -> Path:
        """Resolve filename safely strictly inside dem_root (prevents path traversal)."""
        if "/" in filename or "\\" in filename or ".." in filename:
            raise ValueError(f"Unsafe DEM filename rejected: {filename!r}")
        resolved = (self.dem_root / filename).resolve()
        if resolved.parent != self.dem_root:
            raise ValueError(f"DEM path escape attempt rejected: {filename!r}")
        if not resolved.exists() or not resolved.is_file():
            raise FileNotFoundError(f"Controlled DEM asset not found: {filename}")
        return resolved

    def _load_manifest_entries(self) -> dict[str, dict[str, Any]]:
        manifest_path = self.dem_root / "manifest.json"
        if not manifest_path.exists():
            return {}
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries = data.get("assets", []) if isinstance(data, dict) else []
        return {
            str(item["filename"]): dict(item)
            for item in entries
            if isinstance(item, dict) and "filename" in item
        }

    def list_assets(self, refresh: bool = False) -> list[DEMAssetMetadata]:
        """Inspect and validate all DEM elevation GeoTIFFs in the controlled DEM directory."""
        if self._assets is not None and not refresh:
            return list(self._assets)
        if not self.dem_root.exists():
            self._assets = []
            return []

        manifest_map = self._load_manifest_entries()
        candidate_files: list[Path] = []
        if manifest_map:
            for fname in manifest_map:
                p = self._safe_child_path(fname)
                candidate_files.append(p)
        else:
            for p in sorted(self.dem_root.iterdir()):
                if p.is_file() and p.suffix.lower() == ".tif":
                    # Auto-discover only elevation DEMs unless manifest specifies otherwise
                    upper_name = p.name.upper()
                    if any(
                        token in upper_name
                        for token in ("LDEC", "_ERR", "_SLP", "HILL", "EFFRES", "CLONE")
                    ):
                        continue
                    candidate_files.append(p)

        assets: list[DEMAssetMetadata] = []
        for path in candidate_files:
            meta_entry = manifest_map.get(path.name, {})
            sha256 = str(meta_entry.get("sha256") or compute_file_sha256(path))
            if "sha256" in meta_entry:
                actual_sha = compute_file_sha256(path)
                if actual_sha != meta_entry["sha256"]:
                    raise ValueError(
                        f"DEM checksum mismatch for {path.name}: expected {meta_entry['sha256']}, got {actual_sha}"
                    )

            with rasterio.open(path) as ds:
                area_or_point = ds.tags().get("AREA_OR_POINT", "Area")
                ctx, _, _ = build_raster_context(ds.crs, ds.transform, area_or_point=area_or_point)
                res_x, res_y = float(ds.res[0]), float(ds.res[1])
                b = ds.bounds
                nodata_val: float | None = None
                if ds.nodata is not None and not (
                    isinstance(ds.nodata, float) and np.isnan(ds.nodata)
                ):
                    nodata_val = float(ds.nodata)

                count_fn = meta_entry.get("count_filename")
                err_fn = meta_entry.get("error_filename")
                if count_fn and not (self.dem_root / str(count_fn)).exists():
                    count_fn = None
                if err_fn and not (self.dem_root / str(err_fn)).exists():
                    err_fn = None

                assets.append(
                    DEMAssetMetadata(
                        asset_id=str(meta_entry.get("asset_id") or path.stem),
                        filename=path.name,
                        sha256=sha256,
                        file_size_bytes=path.stat().st_size,
                        width=int(ds.width),
                        height=int(ds.height),
                        pixel_size_x_m=res_x,
                        pixel_size_y_m=res_y,
                        dtype=str(ds.dtypes[0]),
                        nodata_value=nodata_val,
                        crs_proj4=ctx.raster_crs_proj4,
                        pixel_registration=ctx.pixel_registration,
                        bounds_left_m=float(b.left),
                        bounds_bottom_m=float(b.bottom),
                        bounds_right_m=float(b.right),
                        bounds_top_m=float(b.top),
                        elevation_unit=str(meta_entry.get("elevation_unit") or "meters"),
                        lunar_frame=str(meta_entry.get("lunar_frame") or "MOON_ME_DE421"),
                        source=str(
                            meta_entry.get("source")
                            or "NASA GSFC PGDA LOLA South Pole Elevation Product"
                        ),
                        citation=str(
                            meta_entry.get("citation")
                            or "Barker et al. (2021, 2023), NASA PGDA LOLA Products 78/90"
                        ),
                        dataset_version=str(meta_entry.get("dataset_version") or "LOLA-PGDA-2023"),
                        count_filename=str(count_fn) if count_fn else None,
                        error_filename=str(err_fn) if err_fn else None,
                    )
                )

        # Prefer finest resolution first
        assets.sort(key=lambda a: (a.pixel_size_x_m, a.asset_id))
        self._assets = assets
        return list(assets)

    def select_asset_for_site(
        self,
        lat_deg: float,
        lon_deg: float,
        horizon_max_radius_m: float,
    ) -> DEMCoverageSelection | None:
        """Find best DEM covering (lat_deg, lon_deg), preferring full horizon radius coverage."""
        assets = self.list_assets()
        if not assets:
            return None

        full_matches: list[DEMCoverageSelection] = []
        partial_matches: list[DEMCoverageSelection] = []

        for asset in assets:
            path = self._safe_child_path(asset.filename)
            with rasterio.open(path) as ds:
                _, to_raster, _ = build_raster_context(
                    ds.crs, ds.transform, area_or_point=asset.pixel_registration
                )
                sx, sy = lonlat_to_raster_xy(to_raster, float(lon_deg), float(lat_deg))
                x_val, y_val = float(sx), float(sy)
                bounds_poly = box(
                    asset.bounds_left_m,
                    asset.bounds_bottom_m,
                    asset.bounds_right_m,
                    asset.bounds_top_m,
                )
                if not bounds_poly.contains(Point(x_val, y_val)):
                    continue

                margin = min(
                    x_val - asset.bounds_left_m,
                    asset.bounds_right_m - x_val,
                    y_val - asset.bounds_bottom_m,
                    asset.bounds_top_m - y_val,
                )
                sel = DEMCoverageSelection(
                    asset=asset,
                    site_x_m=x_val,
                    site_y_m=y_val,
                    min_edge_margin_m=float(margin),
                    full_horizon_covered=margin >= horizon_max_radius_m,
                )
                if sel.full_horizon_covered:
                    full_matches.append(sel)
                else:
                    partial_matches.append(sel)

        if full_matches:
            # Finest resolution with full horizon radius margin
            full_matches.sort(key=lambda s: s.asset.pixel_size_x_m)
            return full_matches[0]
        if partial_matches:
            # Largest margin, then finest resolution
            partial_matches.sort(key=lambda s: (-s.min_edge_margin_m, s.asset.pixel_size_x_m))
            return partial_matches[0]
        return None

    def read_window_for_site(
        self,
        selection: DEMCoverageSelection,
        horizon_max_radius_m: float,
        max_window_pixels_per_side: int = 2600,
    ) -> DEMWindowSample:
        """Load bounded DEM elevation window (plus optional count & error bands) into memory.

        For very fine grids (e.g. 5 m/px over 100 km), automatically caps read window resolution via
        Rasterio ``out_shape`` to protect worker RAM, while 80 m/px and 240 m/px grids read at
        exact 1:1 native posting inside the horizon search radius.
        """
        asset = selection.asset
        dem_path = self._safe_child_path(asset.filename)
        pad_m = horizon_max_radius_m + max(asset.pixel_size_x_m, asset.pixel_size_y_m) * 4.0

        req_left = max(asset.bounds_left_m, selection.site_x_m - pad_m)
        req_right = min(asset.bounds_right_m, selection.site_x_m + pad_m)
        req_bottom = max(asset.bounds_bottom_m, selection.site_y_m - pad_m)
        req_top = min(asset.bounds_top_m, selection.site_y_m + pad_m)

        with rasterio.open(dem_path) as ds:
            area_or_point = ds.tags().get("AREA_OR_POINT", "Area")
            ctx, _, to_lonlat = build_raster_context(
                ds.crs, ds.transform, area_or_point=area_or_point
            )
            win = from_bounds(req_left, req_bottom, req_right, req_top, transform=ds.transform)
            win = win.round_offsets().round_lengths()
            col_off = max(0, int(win.col_off))
            row_off = max(0, int(win.row_off))
            width = min(ds.width - col_off, int(win.width))
            height = min(ds.height - row_off, int(win.height))
            clipped_win = Window(col_off=col_off, row_off=row_off, width=width, height=height)

            out_w = min(width, max_window_pixels_per_side)
            out_h = min(height, max_window_pixels_per_side)
            elev_arr = ds.read(
                1,
                window=clipped_win,
                out_shape=(out_h, out_w),
            ).astype(np.float64)

            if asset.nodata_value is not None:
                elev_arr = np.where(np.isclose(elev_arr, asset.nodata_value), np.nan, elev_arr)

            win_transform = ds.window_transform(clipped_win)
            if out_w != width or out_h != height:
                win_transform = win_transform * win_transform.scale(width / out_w, height / out_h)

            # Read exact center pixel at full native resolution for accurate observer ground elevation
            obs_r, obs_c = raster_xy_to_rowcol(ds.transform, selection.site_x_m, selection.site_y_m)
            site_elev_m: float | None = None
            if 0 <= obs_r < ds.height and 0 <= obs_c < ds.width:
                pt_win = Window(col_off=obs_c, row_off=obs_r, width=1, height=1)
                pt_val = float(ds.read(1, window=pt_win)[0, 0])
                if not np.isnan(pt_val) and (
                    asset.nodata_value is None or not np.isclose(pt_val, asset.nodata_value)
                ):
                    site_elev_m = pt_val

            count_grid: NDArray[np.float64] | None = None
            site_count: float | None = None
            if asset.count_filename:
                c_path = self._safe_child_path(asset.count_filename)
                with rasterio.open(c_path) as cds:
                    count_grid = cds.read(1, window=clipped_win, out_shape=(out_h, out_w)).astype(
                        np.float64
                    )
                    if cds.nodata is not None:
                        count_grid = np.where(
                            np.isclose(count_grid, float(cds.nodata)), np.nan, count_grid
                        )
                    if 0 <= obs_r < cds.height and 0 <= obs_c < cds.width:
                        c_pt = float(cds.read(1, window=Window(obs_c, obs_r, 1, 1))[0, 0])
                        if not np.isnan(c_pt):
                            site_count = c_pt

            err_grid: NDArray[np.float64] | None = None
            site_err: float | None = None
            if asset.error_filename:
                e_path = self._safe_child_path(asset.error_filename)
                with rasterio.open(e_path) as eds:
                    err_grid = eds.read(1, window=clipped_win, out_shape=(out_h, out_w)).astype(
                        np.float64
                    )
                    if eds.nodata is not None:
                        err_grid = np.where(
                            np.isclose(err_grid, float(eds.nodata)), np.nan, err_grid
                        )
                    if 0 <= obs_r < eds.height and 0 <= obs_c < eds.width:
                        e_pt = float(eds.read(1, window=Window(obs_c, obs_r, 1, 1))[0, 0])
                        if not np.isnan(e_pt):
                            site_err = e_pt

        return DEMWindowSample(
            asset=asset,
            context=ctx,
            window_transform=win_transform,
            elevation_m=elev_arr,
            count_grid=count_grid,
            error_m_grid=err_grid,
            site_elev_m=site_elev_m,
            site_count=site_count,
            site_error_m=site_err,
            site_x_m=selection.site_x_m,
            site_y_m=selection.site_y_m,
            min_edge_margin_m=selection.min_edge_margin_m,
            full_horizon_covered=selection.full_horizon_covered,
            to_lonlat=to_lonlat,
        )
