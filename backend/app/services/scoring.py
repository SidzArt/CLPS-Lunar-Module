"""Mathematical transformation and scoring utilities for lunar landing site comparisons."""


def clamp(value: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    """Clamp a floating point value to [min_val, max_val]."""
    return max(min_val, min(value, max_val))


def normalize_benefit(value: float, lower_bound: float, upper_bound: float) -> float:
    """Higher-is-better parameter normalization: (value - lower) / (upper - lower)."""
    if upper_bound <= lower_bound:
        raise ValueError(
            f"Upper bound ({upper_bound}) must be strictly greater than lower bound ({lower_bound})."
        )
    raw = (value - lower_bound) / (upper_bound - lower_bound)
    return clamp(raw, 0.0, 1.0)


def normalize_cost(value: float, lower_bound: float, upper_bound: float) -> float:
    """Lower-is-better parameter normalization: (upper - value) / (upper - lower)."""
    if upper_bound <= lower_bound:
        raise ValueError(
            f"Upper bound ({upper_bound}) must be strictly greater than lower bound ({lower_bound})."
        )
    raw = (upper_bound - value) / (upper_bound - lower_bound)
    return clamp(raw, 0.0, 1.0)


def normalize_target(value: float, target_value: float, tolerance: float) -> float:
    """Target-based parameter normalization: max(0, 1 - |value - target| / tolerance)."""
    if tolerance <= 0:
        raise ValueError(f"Target tolerance ({tolerance}) must be strictly positive.")
    raw = 1.0 - (abs(value - target_value) / tolerance)
    return clamp(raw, 0.0, 1.0)


def calculate_normalized_score(
    value: float | None,
    direction: str,
    benchmark_min: float | None,
    benchmark_max: float | None,
    target_value: float | None = None,
    tolerance: float | None = None,
) -> float | None:
    """Calculate normalized score [0, 1] based on parameter direction and benchmark bounds.

    Returns None if:
    - value is None
    - direction is 'context' or 'informational'
    - required benchmark bounds are missing
    """
    if value is None:
        return None

    dir_clean = direction.lower().strip()
    if dir_clean in ("context", "informational"):
        return None

    if dir_clean == "higher":
        if benchmark_min is None or benchmark_max is None:
            return None
        return normalize_benefit(value, benchmark_min, benchmark_max)

    if dir_clean == "lower":
        if benchmark_min is None or benchmark_max is None:
            return None
        return normalize_cost(value, benchmark_min, benchmark_max)

    if dir_clean == "target":
        if target_value is None or tolerance is None:
            return None
        return normalize_target(value, target_value, tolerance)

    return None


def calculate_weighted_score(
    normalized_scores: dict[str, float | None],
    weights: dict[str, float],
    required_keys: set[str] | None = None,
) -> tuple[float | None, str, list[str]]:
    """Compute overall weighted score on a [0, 100] scale.

    Returns:
    - overall_score: float | None
    - coverage_status: 'complete', 'partial', or 'insufficient_data'
    - limitations: list of notes explaining any omitted metrics or re-normalization
    """
    required = required_keys or set()
    limitations: list[str] = []

    # Check for missing required parameters
    missing_required = [k for k in required if normalized_scores.get(k) is None]
    if missing_required:
        return (
            None,
            "insufficient_data",
            [
                (
                    f"Missing required parameter(s): {', '.join(sorted(missing_required))}. "
                    "A scientifically valid overall score cannot be calculated."
                )
            ],
        )

    # Calculate sum of weights for available scoreable parameters
    available_weighted_sum = 0.0
    total_valid_weight = 0.0
    total_configured_weight = sum(w for w in weights.values() if w > 0)
    missing_optional: list[str] = []

    for key, weight in weights.items():
        if weight <= 0:
            continue
        norm_val = normalized_scores.get(key)
        if norm_val is not None:
            available_weighted_sum += weight * norm_val
            total_valid_weight += weight
        else:
            missing_optional.append(key)

    if total_valid_weight <= 0:
        return (
            None,
            "insufficient_data",
            ["No valid scoreable metrics available for comparison."],
        )

    # Re-normalize if some optional metrics are missing
    if total_valid_weight < total_configured_weight:
        coverage_status = "partial"
        limitations.append(
            f"Optional parameter(s) missing: {', '.join(sorted(missing_optional))}. "
            f"Overall score re-normalized across available parameters (sum of weights: {total_valid_weight:.2f}/{total_configured_weight:.2f})."
        )
    else:
        coverage_status = "complete"

    overall_score = round(100.0 * (available_weighted_sum / total_valid_weight), 2)
    return overall_score, coverage_status, limitations


def determine_parameter_winner(
    val_a: float | None,
    val_b: float | None,
    direction: str,
    target_value: float | None = None,
    tolerance: float = 1e-6,
) -> str:
    """Determine winner key for a single parameter.

    Returns:
    - 'site_a'
    - 'site_b'
    - 'tie'
    - 'both' (for non-scored context)
    - 'none' (when one or both values missing)
    """
    if val_a is None or val_b is None:
        return "none"

    dir_clean = direction.lower().strip()
    if dir_clean in ("context", "informational"):
        return "both"

    if dir_clean == "higher":
        diff = val_a - val_b
        if abs(diff) <= tolerance:
            return "tie"
        return "site_a" if diff > 0 else "site_b"

    if dir_clean == "lower":
        diff = val_b - val_a
        if abs(diff) <= tolerance:
            return "tie"
        return "site_a" if diff > 0 else "site_b"

    if dir_clean == "target":
        if target_value is None:
            return "none"
        dist_a = abs(val_a - target_value)
        dist_b = abs(val_b - target_value)
        diff = dist_b - dist_a  # closer to target is better
        if abs(diff) <= tolerance:
            return "tie"
        return "site_a" if diff > 0 else "site_b"

    return "tie"
