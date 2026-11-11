"""Deterministic comparison service for evaluating exactly two lunar landing sites."""

import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.comparison import ComparisonProfile
from app.models.metrics import SiteMetric
from app.repositories import comparison_repo
from app.schemas.comparison import (
    ComparisonProfileOut,
    ComparisonProfileParameterOut,
    ComparisonRequestIn,
    ComparisonResultOut,
    ParameterComparisonOut,
)
from app.services import scoring


def get_comparison_profiles(db: Session) -> list[ComparisonProfileOut]:
    """Return all available pre-configured comparison profiles with parameter weights."""
    profiles = comparison_repo.list_active_profiles(db)
    result: list[ComparisonProfileOut] = []
    for p in profiles:
        params: list[ComparisonProfileParameterOut] = []
        for link in p.parameters:
            if link.parameter and link.parameter.is_active:
                params.append(
                    ComparisonProfileParameterOut(
                        parameter_key=link.parameter.parameter_key,
                        display_name=link.parameter.display_name,
                        unit=link.parameter.unit,
                        weight=link.weight,
                        required=link.required,
                        target_value=link.target_value,
                        comparison_direction=link.parameter.comparison_direction,
                    )
                )
        result.append(
            ComparisonProfileOut(
                profile_id=p.profile_id,
                profile_key=p.profile_key,
                name=p.name,
                purpose_description=p.purpose_description,
                version=p.version,
                parameters=params,
            )
        )
    return result


def compare_two_sites(db: Session, request: ComparisonRequestIn) -> ComparisonResultOut:
    """Execute a fully deterministic two-site scientific comparison."""
    # Step 1: Validate & retrieve the two site records
    sites_map = comparison_repo.get_sites_by_ids(db, [request.site_a_id, request.site_b_id])
    site_a = sites_map.get(request.site_a_id)
    site_b = sites_map.get(request.site_b_id)

    if not site_a or site_a.catalogue_status != "published":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Published landing site with ID {request.site_a_id} does not exist.",
        )
    if not site_b or site_b.catalogue_status != "published":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Published landing site with ID {request.site_b_id} does not exist.",
        )

    # Step 2: Retrieve scientific metrics for both sites
    metrics_map = comparison_repo.get_site_metrics_map(db, [site_a.site_id, site_b.site_id])
    metrics_a = metrics_map.get(site_a.site_id, {})
    metrics_b = metrics_map.get(site_b.site_id, {})

    # Step 3 & 4: Resolve comparison profile and requested parameters
    profile: ComparisonProfile | None = None
    if request.profile_key:
        profile = comparison_repo.get_profile_by_key(db, request.profile_key)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Comparison profile '{request.profile_key}' was not found.",
            )
    elif request.profile_id:
        profile = comparison_repo.get_profile_by_id(db, request.profile_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Comparison profile with ID {request.profile_id} was not found.",
            )

    # Build parameter configuration dictionary: {param_key: (weight, required, target_val)}
    param_configs: dict[str, dict[str, Any]] = {}
    if request.custom_parameters:
        # Validate weights non-negative
        for cp in request.custom_parameters:
            if cp.weight < 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Parameter weight for '{cp.parameter_key}' cannot be negative ({cp.weight}).",
                )
            param_configs[cp.parameter_key] = {
                "weight": cp.weight,
                "required": cp.required,
                "target_value": cp.target_value,
            }
        # Check sum of custom weights
        total_custom_weight = sum(c["weight"] for c in param_configs.values() if c["weight"] > 0)
        if abs(total_custom_weight - 1.0) > 0.01:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Custom parameter weights must sum to 1.0 within tolerance (±0.01). Current sum: {total_custom_weight:.4f}.",
            )
    elif profile:
        for link in profile.parameters:
            if link.parameter and link.parameter.is_active:
                param_configs[link.parameter.parameter_key] = {
                    "weight": link.weight,
                    "required": link.required,
                    "target_value": link.target_value,
                }
    else:
        # Default: all active comparable parameters with equal baseline weights
        all_params = comparison_repo.get_parameter_definitions(db)
        comparable_params = [p for p in all_params if p.is_comparable]
        num_comp = len(comparable_params) or 1
        base_weight = round(1.0 / num_comp, 4)
        for p in all_params:
            param_configs[p.parameter_key] = {
                "weight": base_weight if p.is_comparable else 0.0,
                "required": False,
                "target_value": p.target_value,
            }

    # Always include baseline parameters in comparison table even if unweighted
    all_active_params = comparison_repo.get_parameter_definitions(db)
    param_defs_map = {p.parameter_key: p for p in all_active_params}

    # Validate that all requested custom parameter keys exist in the database
    for k in param_configs:
        if k not in param_defs_map:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Requested comparison parameter '{k}' is not defined in the system.",
            )

    # Order parameters logically (scoreable first, then context)
    ordered_keys = [k for k in param_configs if param_defs_map[k].is_comparable]
    for p in all_active_params:
        if p.parameter_key not in ordered_keys:
            ordered_keys.append(p.parameter_key)

    # Steps 7-14: Evaluate each parameter
    parameter_rows: list[ParameterComparisonOut] = []
    normalized_scores_a: dict[str, float | None] = {}
    normalized_scores_b: dict[str, float | None] = {}
    active_weights: dict[str, float] = {}
    required_keys: set[str] = set()
    db_results_to_insert: list[dict[str, Any]] = []
    all_limitations: list[str] = []

    for key in ordered_keys:
        pdef = param_defs_map.get(key)
        if not pdef:
            continue

        cfg = param_configs.get(
            key, {"weight": 0.0, "required": False, "target_value": pdef.target_value}
        )
        weight = cfg["weight"]
        is_required = cfg["required"]
        target_val = cfg["target_value"] or pdef.target_value

        if is_required:
            required_keys.add(key)
        if pdef.is_comparable and weight > 0:
            active_weights[key] = weight

        metric_a: SiteMetric | None = metrics_a.get(key)
        metric_b: SiteMetric | None = metrics_b.get(key)

        val_a = metric_a.numeric_value if metric_a else None
        val_b = metric_b.numeric_value if metric_b else None
        txt_a = metric_a.text_value if metric_a else None
        txt_b = metric_b.text_value if metric_b else None

        # Fallback to site geographic table attribute for context elevation
        if key == "elevation_m":
            if val_a is None and site_a.elevation_m is not None:
                val_a = float(site_a.elevation_m)
            if val_b is None and site_b.elevation_m is not None:
                val_b = float(site_b.elevation_m)

        # Unit compatibility check
        unit_a = metric_a.unit_override if (metric_a and metric_a.unit_override) else pdef.unit
        unit_b = metric_b.unit_override if (metric_b and metric_b.unit_override) else pdef.unit
        if unit_a != unit_b:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unit mismatch for parameter '{pdef.display_name}': {site_a.site_name} uses '{unit_a}', while {site_b.site_name} uses '{unit_b}'.",
            )

        # Dataset version & time window compatibility check
        ver_a = metric_a.dataset_version if metric_a else None
        ver_b = metric_b.dataset_version if metric_b else None
        obs_time_a = metric_a.calculated_at if metric_a else None
        obs_time_b = metric_b.calculated_at if metric_b else None

        compat_note: str | None = None
        if val_a is not None and val_b is not None and (ver_a or ver_b) and ver_a != ver_b:
            compat_note = f"Dataset version discrepancy: {site_a.site_name} uses '{ver_a or 'unversioned'}' while {site_b.site_name} uses '{ver_b or 'unversioned'}'."
            all_limitations.append(
                f"Parameter '{pdef.display_name}' compares measurements from different dataset versions ({ver_a or 'unversioned'} vs {ver_b or 'unversioned'})."
            )
        elif (
            metric_a
            and metric_b
            and metric_a.valid_from
            and metric_b.valid_from
            and (
                metric_a.valid_from != metric_b.valid_from or metric_a.valid_to != metric_b.valid_to
            )
        ):
            compat_note = "Observation time-window difference between datasets."
            all_limitations.append(
                f"Parameter '{pdef.display_name}' has non-identical observation time windows."
            )

        # Normalization
        norm_a: float | None = None
        norm_b: float | None = None
        if pdef.is_comparable:
            norm_a = scoring.calculate_normalized_score(
                val_a,
                pdef.comparison_direction,
                pdef.benchmark_min,
                pdef.benchmark_max,
                target_val,
                pdef.tolerance,
            )
            norm_b = scoring.calculate_normalized_score(
                val_b,
                pdef.comparison_direction,
                pdef.benchmark_min,
                pdef.benchmark_max,
                target_val,
                pdef.tolerance,
            )

        normalized_scores_a[key] = norm_a
        normalized_scores_b[key] = norm_b

        # Differences
        abs_diff: float | None = None
        rel_diff: float | None = None
        if val_a is not None and val_b is not None:
            abs_diff = round(abs(val_a - val_b), 4)
            mean_val = (abs(val_a) + abs(val_b)) / 2.0
            if mean_val > 1e-6:
                rel_diff = round((abs(val_a - val_b) / mean_val) * 100.0, 2)

        # Winner
        winner_key = scoring.determine_parameter_winner(
            val_a,
            val_b,
            pdef.comparison_direction,
            target_value=target_val,
        )

        # Explanation & quality status generation (incorporate source_id provenance check)
        status_a = metric_a.data_quality_status if metric_a else None
        status_b = metric_b.data_quality_status if metric_b else None
        unsourced_a = bool(
            metric_a is not None and val_a is not None and metric_a.source_id is None
        )
        unsourced_b = bool(
            metric_b is not None and val_b is not None and metric_b.source_id is None
        )

        if val_a is None and val_b is None:
            explanation = f"Neither {site_a.site_name} nor {site_b.site_name} have published measurements for this parameter."
            quality_status = "missing"
        elif val_a is None:
            qual_note = (
                "unverified/unsourced" if (unsourced_b or status_b != "verified") else "verified"
            )
            explanation = f"Missing data for {site_a.site_name}; {site_b.site_name} has {qual_note} value of {val_b}{pdef.unit or ''}."
            quality_status = "missing"
        elif val_b is None:
            qual_note = (
                "unverified/unsourced" if (unsourced_a or status_a != "verified") else "verified"
            )
            explanation = f"Missing data for {site_b.site_name}; {site_a.site_name} has {qual_note} value of {val_a}{pdef.unit or ''}."
            quality_status = "missing"
        else:
            non_verified = [s for s in (status_a, status_b) if s and s != "verified"]
            if non_verified:
                priority = {"conflict": 4, "estimate": 3, "provisional": 2, "unverified": 1}
                non_verified.sort(key=lambda s: priority.get(s, 0), reverse=True)
                quality_status = non_verified[0]
                all_limitations.append(
                    f"Parameter '{pdef.display_name}' includes {quality_status} data quality measurements."
                )
            elif unsourced_a or unsourced_b:
                quality_status = "unverified"
                all_limitations.append(
                    f"Parameter '{pdef.display_name}' lacks linked source provenance (source_id missing)."
                )
            else:
                quality_status = "verified"

            if winner_key == "tie":
                explanation = f"Both sites exhibit equivalent values ({val_a}{pdef.unit or ''})."
            elif winner_key == "site_a":
                if pdef.comparison_direction == "higher":
                    direction_desc = "higher value"
                elif pdef.comparison_direction == "target":
                    direction_desc = f"closer to target {target_val}"
                else:
                    direction_desc = "safer/lower value"
                explanation = f"{site_a.site_name} performs better with {val_a}{pdef.unit or ''} vs {val_b}{pdef.unit or ''} ({direction_desc})."
            elif winner_key == "site_b":
                if pdef.comparison_direction == "higher":
                    direction_desc = "higher value"
                elif pdef.comparison_direction == "target":
                    direction_desc = f"closer to target {target_val}"
                else:
                    direction_desc = "safer/lower value"
                explanation = f"{site_b.site_name} performs better with {val_b}{pdef.unit or ''} vs {val_a}{pdef.unit or ''} ({direction_desc})."
            else:
                explanation = (
                    f"Contextual metric: {val_a}{pdef.unit or ''} vs {val_b}{pdef.unit or ''}."
                )

        source_ref = (
            metric_a.methodology
            if (metric_a and metric_a.methodology)
            else (
                metric_b.methodology
                if (metric_b and metric_b.methodology)
                else pdef.methodology_note
            )
        )

        param_row = ParameterComparisonOut(
            parameter_key=key,
            display_name=pdef.display_name,
            description=pdef.description,
            unit=pdef.unit,
            value_type=pdef.value_type,
            comparison_direction=pdef.comparison_direction,
            value_a=val_a,
            value_b=val_b,
            text_value_a=txt_a,
            text_value_b=txt_b,
            absolute_difference=abs_diff,
            relative_difference_percent=rel_diff,
            normalised_a=round(norm_a, 4) if norm_a is not None else None,
            normalised_b=round(norm_b, 4) if norm_b is not None else None,
            winner_key=winner_key,
            weight=round(weight, 4) if weight > 0 else None,
            required=is_required,
            is_scoreable=pdef.is_comparable
            and (pdef.benchmark_min is not None or target_val is not None),
            benchmark_min=pdef.benchmark_min,
            benchmark_max=pdef.benchmark_max,
            data_quality_status=quality_status,
            source_reference=source_ref,
            dataset_version_a=ver_a,
            dataset_version_b=ver_b,
            observation_time_a=obs_time_a,
            observation_time_b=obs_time_b,
            compatibility_note=compat_note,
            explanation=explanation,
        )
        parameter_rows.append(param_row)

        db_results_to_insert.append(
            {
                "parameter_id": pdef.parameter_id,
                "value_a": val_a,
                "value_b": val_b,
                "text_value_a": txt_a,
                "text_value_b": txt_b,
                "normalised_a": norm_a,
                "normalised_b": norm_b,
                "winner_key": winner_key,
                "explanation": explanation,
                "data_quality_status": quality_status,
            }
        )

    # Step 13: Calculate Overall Scores
    score_a, cov_a, lim_a = scoring.calculate_weighted_score(
        normalized_scores_a, active_weights, required_keys
    )
    score_b, cov_b, lim_b = scoring.calculate_weighted_score(
        normalized_scores_b, active_weights, required_keys
    )

    all_limitations.extend(lim_a)
    all_limitations.extend(lim_b)
    all_limitations = list(dict.fromkeys(all_limitations))

    if cov_a == "insufficient_data" or cov_b == "insufficient_data":
        data_coverage = "insufficient_data"
        overall_winner = "undetermined"
        winner_name: str | None = None
        scientific_conclusion = (
            f"Comparison between '{site_a.site_name}' and '{site_b.site_name}' cannot produce a valid overall score "
            f"due to insufficient data in one or more required mission parameters. "
            f"Review individual parameter rows above for available scientific evidence."
        )
    else:
        data_coverage = "partial" if (cov_a == "partial" or cov_b == "partial") else "complete"
        assert score_a is not None and score_b is not None
        diff = round(score_a - score_b, 2)
        if abs(diff) <= 0.1:
            overall_winner = "tie"
            winner_name = None
            scientific_conclusion = f"Both sites demonstrate equivalent suitability for the stated mission purpose ({score_a:.1f} vs {score_b:.1f})."
        elif score_a > score_b:
            overall_winner = "site_a"
            winner_name = site_a.site_name
            scientific_conclusion = (
                f"'{site_a.site_name}' ranks higher (Score: {score_a:.1f}/100) than '{site_b.site_name}' (Score: {score_b:.1f}/100) "
                f"for the mission purpose: '{request.mission_purpose}'."
            )
        else:
            overall_winner = "site_b"
            winner_name = site_b.site_name
            scientific_conclusion = (
                f"'{site_b.site_name}' ranks higher (Score: {score_b:.1f}/100) than '{site_a.site_name}' (Score: {score_a:.1f}/100) "
                f"for the mission purpose: '{request.mission_purpose}'."
            )

    # Step 16: Persist comparison run and results to PostgreSQL
    run_id = uuid.uuid4()
    run = comparison_repo.create_comparison_run(
        db,
        run_id=run_id,
        site_a_id=site_a.site_id,
        site_b_id=site_b.site_id,
        user_purpose=request.mission_purpose,
        parsed_requirements={
            "profile_key": profile.profile_key if profile else None,
            "weights": active_weights,
            "required": list(required_keys),
        },
        profile_id=profile.profile_id if profile else None,
        algorithm_version="v1.0",
        overall_score_a=score_a,
        overall_score_b=score_b,
        overall_winner=overall_winner,
        limitations_note="; ".join(all_limitations) if all_limitations else None,
        status="completed",
    )

    # Attach run_id to child records
    for res_row in db_results_to_insert:
        res_row["run_id"] = run_id
    comparison_repo.bulk_create_comparison_results(db, db_results_to_insert)
    db.commit()

    # Step 17: Return complete response DTO
    return ComparisonResultOut(
        run_id=str(run.run_id),
        site_a_id=site_a.site_id,
        site_b_id=site_b.site_id,
        site_a_name=site_a.site_name,
        site_b_name=site_b.site_name,
        site_a_code=site_a.site_code,
        site_b_code=site_b.site_code,
        site_a_slug=site_a.site_slug,
        site_b_slug=site_b.site_slug,
        mission_purpose=request.mission_purpose,
        profile_key=profile.profile_key if profile else None,
        profile_name=profile.name if profile else None,
        algorithm_version="v1.0",
        data_coverage=data_coverage,
        overall_score_a=score_a,
        overall_score_b=score_b,
        overall_winner=overall_winner,
        winner_site_name=winner_name,
        parameters=parameter_rows,
        scientific_conclusion=scientific_conclusion,
        limitations_and_caveats=all_limitations,
        created_at=run.created_at,
    )
