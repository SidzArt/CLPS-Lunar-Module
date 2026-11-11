"""Mechanical kinematics, Kepler sanity reference, and trapezoidal stepper profiling for CODEX."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal

LUNAR_SIDEREAL_PERIOD_DAYS = 27.321661
LUNAR_SYNODIC_PERIOD_DAYS = 29.530589
EARTH_MOON_MU_KM3_S2 = 403503.2355022388  # GM_Earth + GM_Moon (approx DE440)
EARTH_MOON_SEMI_MAJOR_KM = 384400.0
MIN_PHYSICAL_DURATION_SECONDS = 5
MAX_PHYSICAL_DURATION_SECONDS = 300


class KinematicsError(ValueError):
    """Base error raised when mechanical or step constraints cannot be satisfied."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class CalibrationRequiredError(KinematicsError):
    """Raised when bench-verified motor calibration is missing or unverified."""

    def __init__(self, message: str):
        super().__init__("calibration_missing", message)


class MotionConstraintError(KinematicsError):
    """Raised when travel limits, step rate, or acceleration bounds are violated."""


@dataclass(frozen=True)
class CalibrationSpec:
    """Typed mechanical and electrical calibration constants for one CODEX motor axis."""

    motor_key: str
    controller_key: str
    motor_name: str
    calibration_version: str
    verification_status: str
    gear_reduction_ratio: float
    full_steps_per_rev: int
    microsteps: int
    direction_sign: int
    max_step_rate: int
    acceleration: int
    backlash_steps: int = 0
    zero_offset_deg: float = 0.0
    travel_min_deg: float | None = None
    travel_max_deg: float | None = None
    motor_model: str | None = None
    driver_model: str | None = None


@dataclass(frozen=True)
class MotorMovePlan:
    """Computed deterministic trapezoidal motion plan for one physical motor axis."""

    motor_key: str
    calibration_version: str
    verification_status: str
    target_angle_deg: float
    current_angle_deg: float
    delta_angle_deg: float
    effective_delta_deg: float
    hardware_direction: Literal[1, -1]
    base_steps: int
    backlash_compensation_steps: int
    total_steps: int
    permitted_move_seconds: float
    min_trapezoidal_seconds: float
    step_frequency_hz: float
    peak_step_rate_hz: float
    step_interval_us: int
    accel_steps: int
    cruise_steps: int
    decel_steps: int
    profile_shape: Literal["idle", "triangular", "trapezoidal"]
    clamped_to_limits: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize motion plan into JSON-safe dictionary for command payloads."""
        return {
            "motor_key": self.motor_key,
            "calibration_version": self.calibration_version,
            "verification_status": self.verification_status,
            "target_angle_deg": round(self.target_angle_deg, 4),
            "current_angle_deg": round(self.current_angle_deg, 4),
            "delta_angle_deg": round(self.delta_angle_deg, 4),
            "effective_delta_deg": round(self.effective_delta_deg, 4),
            "hardware_direction": self.hardware_direction,
            "base_steps": self.base_steps,
            "backlash_compensation_steps": self.backlash_compensation_steps,
            "total_steps": self.total_steps,
            "permitted_move_seconds": round(self.permitted_move_seconds, 3),
            "min_trapezoidal_seconds": round(self.min_trapezoidal_seconds, 3),
            "step_frequency_hz": round(self.step_frequency_hz, 3),
            "peak_step_rate_hz": round(self.peak_step_rate_hz, 3),
            "step_interval_us": self.step_interval_us,
            "accel_steps": self.accel_steps,
            "cruise_steps": self.cruise_steps,
            "decel_steps": self.decel_steps,
            "profile_shape": self.profile_shape,
            "clamped_to_limits": self.clamped_to_limits,
            "warnings": list(self.warnings),
        }


def compute_kepler_orbital_reference(simulation_duration_s: int) -> dict[str, Any]:
    """Compute Kepler's 3rd law lunar orbital period sanity check independent of demo speed.

    Keeps astronomical simulation span (seconds) distinct from bench physical motor time.
    """
    kepler_period_s = (
        2.0 * math.pi * math.sqrt((EARTH_MOON_SEMI_MAJOR_KM**3) / EARTH_MOON_MU_KM3_S2)
    )
    kepler_period_days = kepler_period_s / 86400.0
    sidereal_fraction = simulation_duration_s / (LUNAR_SIDEREAL_PERIOD_DAYS * 86400.0)
    synodic_fraction = simulation_duration_s / (LUNAR_SYNODIC_PERIOD_DAYS * 86400.0)
    return {
        "simulation_duration_s": simulation_duration_s,
        "kepler_ideal_period_days": round(kepler_period_days, 4),
        "lunar_sidereal_period_days": LUNAR_SIDEREAL_PERIOD_DAYS,
        "lunar_synodic_period_days": LUNAR_SYNODIC_PERIOD_DAYS,
        "sidereal_orbits": round(sidereal_fraction, 6),
        "synodic_cycles": round(synodic_fraction, 6),
        "lunar_orbital_sweep_deg": round((sidereal_fraction * 360.0) % 360.0, 4),
    }


def resolve_physical_duration_seconds(
    simulation_duration_s: int,
    playback_speed: float,
    requested_physical_duration_s: int | None = None,
) -> int:
    """Resolve physical actuator move budget separately from SPICE span and UI playback speed."""
    if requested_physical_duration_s is not None:
        if (
            requested_physical_duration_s < MIN_PHYSICAL_DURATION_SECONDS
            or requested_physical_duration_s > MAX_PHYSICAL_DURATION_SECONDS
        ):
            raise MotionConstraintError(
                "invalid_physical_duration",
                (
                    f"Physical duration must be between {MIN_PHYSICAL_DURATION_SECONDS} and "
                    f"{MAX_PHYSICAL_DURATION_SECONDS} seconds (got {requested_physical_duration_s})."
                ),
            )
        return int(requested_physical_duration_s)

    scaled = round(simulation_duration_s / max(playback_speed, 1.0))
    return max(MIN_PHYSICAL_DURATION_SECONDS, min(MAX_PHYSICAL_DURATION_SECONDS, scaled))


def extract_orbital_target_angles_deg(
    *,
    site_lat_deg: float,
    site_lon_deg: float,
    sun_dir_moon_xyz: tuple[float, float, float] | None = None,
    earth_dir_moon_xyz: tuple[float, float, float] | None = None,
) -> dict[str, float]:
    """Derive uncalibrated nominal target angles (deg) from lunar orbital vectors and site.

    Note: Physical mapping to cam/groove hardware angles requires bench calibration offsets
    and travel limits from `motor_calibration_profiles` and cannot be assumed exact on
    unverified hardware.
    """
    if sun_dir_moon_xyz is not None:
        sx, sy, sz = sun_dir_moon_xyz
        arm_angle_deg = math.degrees(math.atan2(sy, sx)) % 360.0
        sun_decl_deg = math.degrees(math.asin(max(-1.0, min(1.0, sz))))
    else:
        arm_angle_deg = site_lon_deg % 360.0
        sun_decl_deg = 0.0

    if earth_dir_moon_xyz is not None:
        ex, ey, _ = earth_dir_moon_xyz
        earth_libration_lon_deg = math.degrees(math.atan2(ey, ex))
    else:
        earth_libration_lon_deg = 0.0

    # Relative phase between selected landing longitude and Moon-Earth axis
    earth_frame_deg = (site_lon_deg - earth_libration_lon_deg) % 360.0
    return {
        "nema17_arm_angle_deg": round(arm_angle_deg, 4),
        "byj_earth_frame_deg": round(earth_frame_deg, 4),
        "sun_declination_deg": round(sun_decl_deg, 4),
        "site_lat_deg": round(site_lat_deg, 6),
        "site_lon_deg": round(site_lon_deg, 6),
    }


def _validate_calibration_spec(
    spec: CalibrationSpec,
    *,
    require_verified: bool,
) -> None:
    """Validate numerical and verification invariants on a motor calibration profile."""
    if spec.verification_status == "deprecated":
        raise CalibrationRequiredError(
            f"Motor '{spec.motor_key}' calibration '{spec.calibration_version}' is deprecated."
        )
    if require_verified and spec.verification_status != "bench_verified":
        raise CalibrationRequiredError(
            f"Motor '{spec.motor_key}' calibration '{spec.calibration_version}' has status "
            f"'{spec.verification_status}'. Physical actuation is blocked until bench verification."
        )
    if spec.gear_reduction_ratio <= 0.0:
        raise KinematicsError(
            "invalid_gear_ratio",
            f"Motor '{spec.motor_key}' gear_reduction_ratio must be positive.",
        )
    if spec.full_steps_per_rev <= 0 or spec.microsteps <= 0:
        raise KinematicsError(
            "invalid_step_config",
            f"Motor '{spec.motor_key}' full_steps_per_rev and microsteps must be positive.",
        )
    if spec.direction_sign not in (1, -1):
        raise KinematicsError(
            "invalid_direction_sign",
            f"Motor '{spec.motor_key}' direction_sign must be +1 or -1.",
        )
    if spec.max_step_rate <= 0 or spec.acceleration <= 0:
        raise KinematicsError(
            "invalid_motion_limits",
            f"Motor '{spec.motor_key}' max_step_rate and acceleration must be positive.",
        )


def _compute_trapezoidal_profile(
    total_steps: int,
    max_step_rate: int,
    acceleration: int,
    permitted_move_seconds: float,
) -> tuple[int, int, int, float, float, float, Literal["idle", "triangular", "trapezoidal"]]:
    """Compute acceleration, cruise, and deceleration step splits and validate driver bounds."""
    if total_steps == 0:
        return 0, 0, 0, 0.0, 0.0, 0.0, "idle"

    a = float(acceleration)
    v_max = float(max_step_rate)
    two_d_accel = (v_max * v_max) / a

    if float(total_steps) <= two_d_accel:
        # Triangular profile (never reaches v_max cruise)
        accel_steps = total_steps // 2
        decel_steps = total_steps - accel_steps
        cruise_steps = 0
        min_time = 2.0 * math.sqrt(float(total_steps) / a)
        peak_rate = math.sqrt(float(total_steps) * a)
        shape: Literal["triangular", "trapezoidal"] = "triangular"
    else:
        accel_steps = math.floor(two_d_accel / 2.0)
        decel_steps = accel_steps
        cruise_steps = total_steps - accel_steps - decel_steps
        min_time = 2.0 * (v_max / a) + (float(cruise_steps) / v_max)
        peak_rate = v_max
        shape = "trapezoidal"

    if permitted_move_seconds + 1e-9 < min_time:
        raise MotionConstraintError(
            "acceleration_time_exceeded",
            (
                f"Move of {total_steps} steps requires at least {min_time:.2f}s under "
                f"max_step_rate={max_step_rate} Hz and accel={acceleration} steps/s^2, "
                f"exceeding permitted {permitted_move_seconds:.2f}s."
            ),
        )

    avg_rate = float(total_steps) / permitted_move_seconds
    if avg_rate > v_max + 1e-6:
        raise MotionConstraintError(
            "max_step_rate_exceeded",
            f"Average step rate {avg_rate:.1f} Hz exceeds limit {max_step_rate} Hz.",
        )

    return accel_steps, cruise_steps, decel_steps, min_time, avg_rate, peak_rate, shape


def compute_motor_move_plan(
    spec: CalibrationSpec,
    *,
    target_angle_deg: float,
    current_angle_deg: float = 0.0,
    permitted_move_seconds: float,
    require_verified: bool = True,
    clamp_to_travel_limits: bool = False,
) -> MotorMovePlan:
    """Convert desired mechanical output angle (deg) into bounded trapezoidal motor steps."""
    _validate_calibration_spec(spec, require_verified=require_verified)
    if permitted_move_seconds <= 0.0:
        raise MotionConstraintError(
            "invalid_move_time", "permitted_move_seconds must be strictly positive."
        )

    warnings: list[str] = []
    if spec.verification_status != "bench_verified":
        warnings.append(
            f"Motor '{spec.motor_key}' calibration '{spec.calibration_version}' is unverified."
        )

    adjusted_target = target_angle_deg + spec.zero_offset_deg
    clamped = False
    if spec.travel_min_deg is not None and adjusted_target < spec.travel_min_deg:
        if not clamp_to_travel_limits:
            raise MotionConstraintError(
                "travel_limit_violation",
                (
                    f"Target {adjusted_target:.2f} deg falls below travel_min_deg "
                    f"{spec.travel_min_deg:.2f} deg for '{spec.motor_key}'."
                ),
            )
        adjusted_target = spec.travel_min_deg
        clamped = True
        warnings.append(f"Clamped target to travel_min_deg={spec.travel_min_deg:.2f} deg.")

    if spec.travel_max_deg is not None and adjusted_target > spec.travel_max_deg:
        if not clamp_to_travel_limits:
            raise MotionConstraintError(
                "travel_limit_violation",
                (
                    f"Target {adjusted_target:.2f} deg exceeds travel_max_deg "
                    f"{spec.travel_max_deg:.2f} deg for '{spec.motor_key}'."
                ),
            )
        adjusted_target = spec.travel_max_deg
        clamped = True
        warnings.append(f"Clamped target to travel_max_deg={spec.travel_max_deg:.2f} deg.")

    delta_deg = adjusted_target - current_angle_deg
    # Signed mechanical step conversion matching PDF/specification formula
    steps_per_output_rev = (
        float(spec.full_steps_per_rev) * float(spec.microsteps) * spec.gear_reduction_ratio
    )
    base_steps = round((abs(delta_deg) / 360.0) * steps_per_output_rev)
    sign_move = 1 if delta_deg >= 0.0 else -1
    hardware_direction: Literal[1, -1] = 1 if (sign_move * spec.direction_sign) >= 0 else -1

    backlash_comp = spec.backlash_steps if base_steps > 0 and spec.backlash_steps > 0 else 0
    total_steps = base_steps + backlash_comp

    accel_steps, cruise_steps, decel_steps, min_time, avg_rate, peak_rate, shape = (
        _compute_trapezoidal_profile(
            total_steps=total_steps,
            max_step_rate=spec.max_step_rate,
            acceleration=spec.acceleration,
            permitted_move_seconds=permitted_move_seconds,
        )
    )

    step_interval_us = round(1_000_000.0 / avg_rate) if avg_rate > 0.0 else 0
    return MotorMovePlan(
        motor_key=spec.motor_key,
        calibration_version=spec.calibration_version,
        verification_status=spec.verification_status,
        target_angle_deg=adjusted_target,
        current_angle_deg=current_angle_deg,
        delta_angle_deg=target_angle_deg - current_angle_deg,
        effective_delta_deg=delta_deg,
        hardware_direction=hardware_direction,
        base_steps=base_steps,
        backlash_compensation_steps=backlash_comp,
        total_steps=total_steps,
        permitted_move_seconds=permitted_move_seconds,
        min_trapezoidal_seconds=min_time,
        step_frequency_hz=avg_rate,
        peak_step_rate_hz=peak_rate,
        step_interval_us=step_interval_us,
        accel_steps=accel_steps,
        cruise_steps=cruise_steps,
        decel_steps=decel_steps,
        profile_shape=shape,
        clamped_to_limits=clamped,
        warnings=warnings,
    )
