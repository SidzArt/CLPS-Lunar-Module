"""Controlled NAIF SPICE kernel manifest loader, checksum verifier, and pool manager."""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import spiceypy as spice

from app.core.config import settings

REQUIRED_FRAMES: Final[tuple[str, ...]] = (
    "MOON_ME",
    "MOON_PA",
    "MOON_ME_DE440_ME421",
    "MOON_PA_DE440",
    "IAU_MOON",
)
REQUIRED_SPK_BODIES: Final[tuple[tuple[int, str], ...]] = (
    (10, "SUN"),
    (301, "MOON"),
    (399, "EARTH"),
)


class SpiceKernelError(RuntimeError):
    """Base error raised when required SPICE kernels or frames are missing/invalid."""


class SpiceCoverageError(SpiceKernelError):
    """Raised when a requested UTC interval falls outside loaded SPICE kernel coverage."""

    def __init__(
        self,
        message: str,
        valid_start_utc: str,
        valid_end_utc: str,
        responsible_kernel: str,
    ) -> None:
        super().__init__(message)
        self.valid_start_utc = valid_start_utc
        self.valid_end_utc = valid_end_utc
        self.responsible_kernel = responsible_kernel


@dataclass(frozen=True)
class KernelRecord:
    """Verified metadata of a single SPICE kernel listed in manifest.json."""

    filename: str
    kind: str
    description: str
    expected_sha256: str
    actual_sha256: str
    size_bytes: int


@dataclass(frozen=True)
class KernelWindowInfo:
    """Coverage window of an individual SPICE kernel."""

    filename: str
    kind: str
    target: str
    start_et: float
    end_et: float
    start_utc: str
    end_utc: str


@dataclass(frozen=True)
class LoadedKernelState:
    """Verified state of the active SPICE kernel pool."""

    manifest_version: str
    ephemeris_source: str
    ephemeris_version: str
    primary_lunar_frame: str
    resolved_lunar_frame: str
    lsk_latest_leap_second: str
    moon_radii_km: tuple[float, float, float]
    available_frames: dict[str, int]
    kernels: tuple[KernelRecord, ...]
    kernel_windows: tuple[KernelWindowInfo, ...]
    common_start_et: float
    common_end_et: float
    common_start_utc: str
    common_end_utc: str


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def datetime_to_spice_iso(dt: datetime) -> str:
    """Format a timezone-aware or naive datetime cleanly into CSPICE-compatible ISO UTC string."""
    utc_dt = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%S.%f")


class SpiceKernelManager:
    """Thread-safe controller for loading, verifying, and inspecting NAIF SPICE kernels."""

    def __init__(self, kernel_dir: str | Path | None = None) -> None:
        self.kernel_dir = Path(kernel_dir or settings.resolved_spice_kernel_dir).resolve()
        self._lock = threading.RLock()
        self._loaded_signature: tuple[str, tuple[tuple[str, str], ...]] | None = None
        self._loaded_stats: tuple[int, tuple[tuple[str, int, int], ...]] | None = None
        self._state: LoadedKernelState | None = None

    @property
    def lock(self) -> threading.RLock:
        """Process-wide lock guarding non-reentrant CSPICE global kernel pool operations."""
        return self._lock

    def _safe_kernel_path(self, filename: str) -> Path:
        if "/" in filename or "\\" in filename or ".." in filename:
            raise SpiceKernelError(f"Unsafe kernel filename rejected: {filename!r}")
        p = (self.kernel_dir / filename).resolve()
        if p.parent != self.kernel_dir:
            raise SpiceKernelError(
                f"Kernel path outside configured directory rejected: {filename!r}"
            )
        if not p.exists() or not p.is_file():
            raise SpiceKernelError(f"Required SPICE kernel missing: {filename}")
        return p

    def ensure_loaded(self, force_reload: bool = False) -> LoadedKernelState:
        """Verify manifest, validate SHA-256 checksums, furnish kernels once, and check coverage."""
        with self._lock:
            manifest_path = self.kernel_dir / "manifest.json"
            if not manifest_path.exists():
                raise SpiceKernelError("SPICE kernel manifest.json is missing.")

            # Fast path: reuse verified pool state when manifest & file stats are unchanged
            if not force_reload and self._state is not None and self._loaded_stats is not None:
                exp_man_mtime, exp_kernel_stats = self._loaded_stats
                if manifest_path.stat().st_mtime_ns == exp_man_mtime and spice.ktotal("ALL") >= len(
                    exp_kernel_stats
                ):
                    stats_unchanged = True
                    for fn, exp_size, exp_mtime in exp_kernel_stats:
                        p = self.kernel_dir / fn
                        if not p.exists():
                            stats_unchanged = False
                            break
                        st = p.stat()
                        if st.st_size != exp_size or st.st_mtime_ns != exp_mtime:
                            stats_unchanged = False
                            break
                    if stats_unchanged:
                        return self._state

            man_mtime_ns = manifest_path.stat().st_mtime_ns
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest_version = str(manifest.get("manifest_version") or "unknown")
            kernel_specs = manifest.get("kernels", [])
            if not isinstance(kernel_specs, list) or not kernel_specs:
                raise SpiceKernelError("SPICE manifest.json defines no kernels.")

            records: list[KernelRecord] = []
            resolved_paths: list[Path] = []
            signature_items: list[tuple[str, str]] = []
            stat_items: list[tuple[str, int, int]] = []

            for entry in kernel_specs:
                fn = str(entry["filename"])
                k_path = self._safe_kernel_path(fn)
                st_info = k_path.stat()
                expected_sha = str(entry.get("sha256") or "").lower()
                actual_sha = _sha256_file(k_path).lower()
                if expected_sha and actual_sha != expected_sha:
                    raise SpiceKernelError(f"SPICE kernel checksum verification failed for {fn}.")
                records.append(
                    KernelRecord(
                        filename=fn,
                        kind=str(entry.get("kind") or "UNKNOWN"),
                        description=str(entry.get("description") or ""),
                        expected_sha256=expected_sha or actual_sha,
                        actual_sha256=actual_sha,
                        size_bytes=st_info.st_size,
                    )
                )
                resolved_paths.append(k_path)
                signature_items.append((fn, actual_sha))
                stat_items.append((fn, st_info.st_size, st_info.st_mtime_ns))

            signature = (manifest_version, tuple(signature_items))
            if (
                not force_reload
                and self._state is not None
                and self._loaded_signature == signature
                and spice.ktotal("ALL") >= len(resolved_paths)
            ):
                self._loaded_stats = (man_mtime_ns, tuple(stat_items))
                return self._state

            # Clear stale or incompatible kernel pool state cleanly before furnishing
            spice.kclear()
            for k_path in resolved_paths:
                spice.furnsh(str(k_path))

            # Validate required frames & resolve frame hierarchy
            available_frames: dict[str, int] = {}
            for frame_name in REQUIRED_FRAMES:
                fid = int(spice.namfrm(frame_name))
                if fid == 0:
                    raise SpiceKernelError(
                        f"Required lunar frame '{frame_name}' could not be resolved."
                    )
                available_frames[frame_name] = fid

            # Verify MOON body constants
            try:
                _, radii = spice.bodvrd("MOON", "RADII", 3)
                moon_radii = (float(radii[0]), float(radii[1]), float(radii[2]))
            except Exception as exc:
                raise SpiceKernelError(f"Failed to resolve MOON RADII from PCK: {exc}") from exc

            # Extract SPK and Binary PCK coverage intervals dynamically via SPICE
            kernel_windows: list[KernelWindowInfo] = []
            interval_bounds: list[tuple[float, float]] = []

            for rec, k_path in zip(records, resolved_paths, strict=True):
                if rec.kind == "SPK":
                    for body_id, body_label in REQUIRED_SPK_BODIES:
                        cov = spice.spkcov(str(k_path), body_id)
                        n_iv = int(spice.wncard(cov))
                        if n_iv <= 0:
                            raise SpiceKernelError(
                                f"SPK kernel {rec.filename} lacks coverage for body {body_label} ({body_id})."
                            )
                        iv_min, iv_max = spice.wnfetd(cov, 0)
                        for idx in range(1, n_iv):
                            s, e = spice.wnfetd(cov, idx)
                            iv_min = min(iv_min, s)
                            iv_max = max(iv_max, e)
                        kernel_windows.append(
                            KernelWindowInfo(
                                filename=rec.filename,
                                kind=rec.kind,
                                target=f"{body_label} ({body_id})",
                                start_et=float(iv_min),
                                end_et=float(iv_max),
                                start_utc=str(spice.et2utc(iv_min, "ISOC", 3)) + "Z",
                                end_utc=str(spice.et2utc(iv_max, "ISOC", 3)) + "Z",
                            )
                        )
                        interval_bounds.append((float(iv_min), float(iv_max)))
                elif rec.kind == "PCK_BINARY":
                    # Check MOON_PA_DE440 (31008) binary PCK coverage
                    bpc_frame_id = available_frames["MOON_PA_DE440"]
                    cov = spice.pckcov(str(k_path), bpc_frame_id)
                    n_iv = int(spice.wncard(cov))
                    if n_iv <= 0:
                        raise SpiceKernelError(
                            f"Binary lunar PCK {rec.filename} lacks coverage for frame {bpc_frame_id}."
                        )
                    iv_min, iv_max = spice.wnfetd(cov, 0)
                    for idx in range(1, n_iv):
                        s, e = spice.wnfetd(cov, idx)
                        iv_min = min(iv_min, s)
                        iv_max = max(iv_max, e)
                    kernel_windows.append(
                        KernelWindowInfo(
                            filename=rec.filename,
                            kind=rec.kind,
                            target=f"MOON_PA_DE440 ({bpc_frame_id})",
                            start_et=float(iv_min),
                            end_et=float(iv_max),
                            start_utc=str(spice.et2utc(iv_min, "ISOC", 3)) + "Z",
                            end_utc=str(spice.et2utc(iv_max, "ISOC", 3)) + "Z",
                        )
                    )
                    interval_bounds.append((float(iv_min), float(iv_max)))

            if not interval_bounds:
                raise SpiceKernelError("No SPK/BPC time coverage windows found in loaded kernels.")

            common_start_et = max(b[0] for b in interval_bounds)
            common_end_et = min(b[1] for b in interval_bounds)
            if common_start_et >= common_end_et:
                raise SpiceKernelError("SPK and binary PCK kernels have zero overlapping coverage.")

            state = LoadedKernelState(
                manifest_version=manifest_version,
                ephemeris_source=str(manifest.get("ephemeris_source") or "NASA/JPL NAIF"),
                ephemeris_version=str(manifest.get("ephemeris_version") or "DE440"),
                primary_lunar_frame=str(manifest.get("primary_lunar_frame") or "MOON_ME"),
                resolved_lunar_frame=str(
                    manifest.get("resolved_lunar_frame") or "MOON_ME_DE440_ME421"
                ),
                lsk_latest_leap_second=str(manifest.get("lsk_latest_leap_second") or "2017-01-01"),
                moon_radii_km=moon_radii,
                available_frames=available_frames,
                kernels=tuple(records),
                kernel_windows=tuple(kernel_windows),
                common_start_et=float(common_start_et),
                common_end_et=float(common_end_et),
                common_start_utc=str(spice.et2utc(common_start_et, "ISOC", 3)) + "Z",
                common_end_utc=str(spice.et2utc(common_end_et, "ISOC", 3)) + "Z",
            )
            self._loaded_signature = signature
            self._loaded_stats = (man_mtime_ns, tuple(stat_items))
            self._state = state
            return state

    def validate_utc_interval(
        self, start_time_utc: datetime, end_time_utc: datetime
    ) -> tuple[float, float, LoadedKernelState]:
        """Convert [start, end] UTC datetimes to SPICE ET and verify strict kernel coverage."""
        with self._lock:
            state = self.ensure_loaded()
            start_et = float(spice.str2et(datetime_to_spice_iso(start_time_utc)))
            end_et = float(spice.str2et(datetime_to_spice_iso(end_time_utc)))

            if end_et <= start_et:
                raise ValueError("Simulation end time must be strictly after start time.")

            for win in state.kernel_windows:
                if start_et < win.start_et or end_et > win.end_et:
                    raise SpiceCoverageError(
                        message=(
                            f"Requested simulation interval [{start_time_utc.isoformat()} .. {end_time_utc.isoformat()}] "
                            f"falls outside verified coverage of {win.filename} "
                            f"[{win.start_utc} .. {win.end_utc}] for {win.target}."
                        ),
                        valid_start_utc=state.common_start_utc,
                        valid_end_utc=state.common_end_utc,
                        responsible_kernel=win.filename,
                    )
            return start_et, end_et, state

    def clear(self) -> None:
        """Reset active SPICE kernel pool state safely."""
        with self._lock:
            spice.kclear()
            self._loaded_signature = None
            self._loaded_stats = None
            self._state = None


# Module-level singleton used across API diagnostics and worker runs
spice_kernel_manager = SpiceKernelManager()
