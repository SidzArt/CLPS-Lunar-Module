"""AI Assist service orchestrating Ollama requirement extraction and deterministic landing site ranking."""

import logging
import re
import time
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.ollama.client import OllamaError, ollama_client
from app.integrations.ollama.prompts import (
    EXTRACTION_JSON_SCHEMA,
    EXTRACTION_SYSTEM_PROMPT,
)
from app.models.catalogue import LandingSite
from app.models.metrics import SiteMetric
from app.repositories import comparison_repo
from app.schemas.ai_assist import (
    AIAssistConstraint,
    AIAssistExtractedRequirements,
    AIAssistPriorityWeight,
    AIAssistRequestIn,
    AIAssistResponseOut,
    SiteRecommendationOut,
)
from app.services import scoring

logger = logging.getLogger("app.services.ai_assist")

# Prompt injection patterns to neutralize
DANGEROUS_PATTERNS = [
    re.compile(r"ignore\s+(previous|all)\s+instructions", re.IGNORECASE),
    re.compile(r"drop\s+table", re.IGNORECASE),
    re.compile(r"select\s+.*\s+from", re.IGNORECASE),
    re.compile(r"system\s*:", re.IGNORECASE),
    re.compile(r"admin\s*:", re.IGNORECASE),
    re.compile(r"<script", re.IGNORECASE),
]


def sanitize_user_prompt(prompt: str) -> str:
    """Sanitize user prompt text and verify basic security boundaries."""
    cleaned = prompt.strip()
    for pat in DANGEROUS_PATTERNS:
        cleaned = pat.sub("[sanitized]", cleaned)
    return cleaned


def extract_requirements_rule_based(prompt: str) -> AIAssistExtractedRequirements:
    """Deterministic keyword fallback extractor used when Ollama is offline or times out."""
    p_lower = prompt.lower()
    weights: list[AIAssistPriorityWeight] = []
    required: list[str] = []
    preferred: list[str] = []
    constraints: list[AIAssistConstraint] = []

    # Illumination / solar
    if any(
        k in p_lower for k in ("sun", "solar", "illumination", "light", "power", "photovoltaic")
    ):
        required.append("illumination_annual_avg")
        preferred.append("illumination_annual_avg")
        weights.append(AIAssistPriorityWeight(parameter_key="illumination_annual_avg", weight=0.35))

    # Earth line of sight / communications
    if any(
        k in p_lower for k in ("earth", "comm", "communication", "telemetry", "los", "visibility")
    ):
        required.append("earth_visibility_avg")
        preferred.append("earth_visibility_avg")
        weights.append(AIAssistPriorityWeight(parameter_key="earth_visibility_avg", weight=0.30))

    # Terrain slope / safety
    if any(
        k in p_lower for k in ("slope", "steep", "flat", "hazard", "safety", "roughness", "lander")
    ):
        required.append("max_slope_deg")
        preferred.append("max_slope_deg")
        weights.append(AIAssistPriorityWeight(parameter_key="max_slope_deg", weight=0.20))
        # Default safety constraint if slope is emphasized
        constraints.append(
            AIAssistConstraint(parameter_key="max_slope_deg", operator="lte", value=15.0)
        )

    # Volatiles / Water ice
    if any(
        k in p_lower for k in ("water", "ice", "volatile", "hydrogen", "psr", "prospecting", "trap")
    ):
        required.append("water_ice_probability")
        preferred.append("water_ice_probability")
        weights.append(AIAssistPriorityWeight(parameter_key="water_ice_probability", weight=0.40))

    # Science / Geology
    if any(
        k in p_lower for k in ("science", "geology", "sample", "crater", "research", "regolith")
    ):
        required.append("scientific_value_score")
        preferred.append("scientific_value_score")
        weights.append(AIAssistPriorityWeight(parameter_key="scientific_value_score", weight=0.25))

    # If no specific keywords matched, provide balanced baseline weights
    if not weights:
        preferred = ["illumination_annual_avg", "earth_visibility_avg", "max_slope_deg"]
        weights = [
            AIAssistPriorityWeight(parameter_key="illumination_annual_avg", weight=0.4),
            AIAssistPriorityWeight(parameter_key="earth_visibility_avg", weight=0.3),
            AIAssistPriorityWeight(parameter_key="max_slope_deg", weight=0.3),
        ]

    # Normalize weights so sum is 1.0
    total_w = sum(w.weight for w in weights)
    for w in weights:
        w.weight = round(w.weight / total_w, 2)

    return AIAssistExtractedRequirements(
        mission_summary="Mission requirements parsed using rule-based keyword extraction.",
        required_parameters=required,
        preferred_parameters=preferred,
        constraints=constraints,
        priority_weights=weights,
        needs_clarification=False,
    )


async def recommend_sites(db: Session, request: AIAssistRequestIn) -> AIAssistResponseOut:
    """Recommend landing sites based on natural-language user prompt."""
    t0 = time.perf_counter()
    sanitized_prompt = sanitize_user_prompt(request.mission_request)

    # 1. Fetch all active parameter definitions from PostgreSQL
    active_params = comparison_repo.get_parameter_definitions(db)
    param_defs_map = {p.parameter_key: p for p in active_params}
    allowed_keys = set(param_defs_map.keys())

    # 2. Extract structured requirements via Ollama or fallback
    fallback_used = False
    extracted_reqs: AIAssistExtractedRequirements

    try:
        raw_json = await ollama_client.generate_json(
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
            user_prompt=sanitized_prompt,
            schema=EXTRACTION_JSON_SCHEMA,
        )

        # Validate and filter extracted parameters against DB allowlist
        valid_required = [k for k in raw_json.get("required_parameters", []) if k in allowed_keys]
        valid_preferred = [k for k in raw_json.get("preferred_parameters", []) if k in allowed_keys]
        valid_constraints = [
            AIAssistConstraint(**c)
            for c in raw_json.get("constraints", [])
            if isinstance(c, dict)
            and c.get("parameter_key") in allowed_keys
            and c.get("operator") in ("lte", "gte", "lt", "gt", "eq")
            and isinstance(c.get("value"), (int, float))
        ]
        valid_weights = [
            AIAssistPriorityWeight(**w)
            for w in raw_json.get("priority_weights", [])
            if isinstance(w, dict)
            and w.get("parameter_key") in allowed_keys
            and isinstance(w.get("weight"), (int, float))
            and w.get("weight", 0) > 0
        ]

        # Normalize weights to sum to 1.0
        total_w = sum(w.weight for w in valid_weights)
        if total_w > 0:
            for w in valid_weights:
                w.weight = round(w.weight / total_w, 4)
        else:
            valid_weights = [
                AIAssistPriorityWeight(parameter_key="illumination_annual_avg", weight=0.5),
                AIAssistPriorityWeight(parameter_key="max_slope_deg", weight=0.5),
            ]

        extracted_reqs = AIAssistExtractedRequirements(
            mission_summary=raw_json.get("mission_summary") or "Mission requirements extracted.",
            required_parameters=valid_required,
            preferred_parameters=valid_preferred,
            constraints=valid_constraints,
            priority_weights=valid_weights,
            needs_clarification=raw_json.get("needs_clarification", False),
        )

    except (OllamaError, httpx.HTTPError, OSError, ValueError, KeyError) as exc:
        logger.warning("Ollama extraction unavailable (%s). Engaging deterministic fallback.", exc)
        fallback_used = True
        extracted_reqs = extract_requirements_rule_based(sanitized_prompt)

    # 3. Fetch published candidate landing sites from PostgreSQL (excluding test fixture prefixes)
    published_sites = db.scalars(
        select(LandingSite).where(
            LandingSite.catalogue_status == "published",
            ~LandingSite.site_code.ilike("CLPS-TEST-%"),
            ~LandingSite.site_slug.ilike("clps-test-%"),
        )
    ).all()

    if not published_sites:
        return AIAssistResponseOut(
            mission_request=request.mission_request,
            mission_summary=extracted_reqs.mission_summary,
            extracted_requirements=extracted_reqs,
            recommendations=[],
            fallback_used=fallback_used,
            model_used="rule-based-fallback" if fallback_used else settings.OLLAMA_MODEL,
            execution_time_ms=round((time.perf_counter() - t0) * 1000, 2),
            clarification_message="No published landing sites available in catalogue.",
            limitations=["The landing site catalogue is currently empty."],
        )

    # 4. Fetch metrics for all candidate sites
    site_ids = [s.site_id for s in published_sites]
    metrics_map = comparison_repo.get_site_metrics_map(db, site_ids)

    # 5. Evaluate eligibility and score each candidate deterministically
    weight_dict = {w.parameter_key: w.weight for w in extracted_reqs.priority_weights}
    required_set = set(extracted_reqs.required_parameters)

    evaluated_candidates: list[dict[str, Any]] = []

    for site in published_sites:
        site_metrics = metrics_map.get(site.site_id, {})

        # Check hard constraints
        violates_constraint = False
        for c in extracted_reqs.constraints:
            m = site_metrics.get(c.parameter_key)
            if m is None or m.numeric_value is None:
                # Sites without verified data for a hard-constrained parameter are disqualified
                violates_constraint = True
                break
            val = m.numeric_value
            if c.operator == "lte" and not (val <= c.value):
                violates_constraint = True
                break
            if c.operator == "lt" and not (val < c.value):
                violates_constraint = True
                break
            if c.operator == "gte" and not (val >= c.value):
                violates_constraint = True
                break
            if c.operator == "gt" and not (val > c.value):
                violates_constraint = True
                break
            if c.operator == "eq" and not (abs(val - c.value) < 1e-6):
                violates_constraint = True
                break

        if violates_constraint:
            continue

        # Compute normalized scores for priority and required parameters
        norm_scores: dict[str, float | None] = {}
        matched_vals: dict[str, float | None] = {}
        missing_params: list[str] = []
        matched_metrics_meta: list[SiteMetric] = []

        eval_keys = set(weight_dict.keys()) | required_set
        for pkey in eval_keys:
            pdef = param_defs_map.get(pkey)
            m = site_metrics.get(pkey)
            if m is not None and m.numeric_value is not None and pdef is not None:
                matched_vals[pkey] = m.numeric_value
                matched_metrics_meta.append(m)
                norm_val = scoring.calculate_normalized_score(
                    m.numeric_value,
                    pdef.comparison_direction,
                    pdef.benchmark_min,
                    pdef.benchmark_max,
                    pdef.target_value,
                    pdef.tolerance,
                )
                norm_scores[pkey] = norm_val
            else:
                matched_vals[pkey] = None
                norm_scores[pkey] = None
                missing_params.append(pkey)

        # Calculate weighted overall score
        score, cov_status, _ = scoring.calculate_weighted_score(
            norm_scores, weight_dict, required_set
        )

        # Determine honest provenance status from matched site metrics
        all_sourced_verified = bool(matched_metrics_meta) and all(
            m.source_id is not None and m.data_quality_status == "verified"
            for m in matched_metrics_meta
        )
        if cov_status != "complete":
            cand_quality_status = "partial"
        elif all_sourced_verified:
            cand_quality_status = "verified"
        elif matched_metrics_meta and any(
            m.data_quality_status == "provisional" for m in matched_metrics_meta
        ):
            cand_quality_status = "provisional"
        else:
            cand_quality_status = "unverified"

        if score is not None and score >= request.min_score_threshold:
            evaluated_candidates.append(
                {
                    "site": site,
                    "score": score,
                    "matched_vals": matched_vals,
                    "missing_params": missing_params,
                    "quality_status": cand_quality_status,
                }
            )

    # 6. Rank candidates descending by deterministic score
    evaluated_candidates.sort(key=lambda x: x["score"], reverse=True)
    top_candidates = evaluated_candidates[: request.max_recommendations]

    # 7. Generate concise rationales
    recommendations: list[SiteRecommendationOut] = []
    for rank_idx, cand in enumerate(top_candidates, start=1):
        cand_site: LandingSite = cand["site"]
        cand_score: float = float(cand["score"])
        vals: dict[str, float | None] = cand["matched_vals"]
        missing: list[str] = cand["missing_params"]
        cand_quality: str = str(cand["quality_status"])

        # Deterministic evidence summary
        metrics_summary = []
        for k, v in vals.items():
            if v is not None:
                pdef = param_defs_map.get(k)
                unit_str = pdef.unit if pdef and pdef.unit else ""
                metrics_summary.append(f"{pdef.display_name if pdef else k}: {v}{unit_str}")

        evidence_text = (
            ", ".join(metrics_summary)
            if metrics_summary
            else "Baseline geographic criteria satisfied"
        )

        telemetry_qualifier = (
            "verified sourced telemetry"
            if cand_quality == "verified"
            else f"catalogued metrics (provenance status: {cand_quality})"
        )
        rationale = f"Ranks #{rank_idx} with deterministic score of {cand_score:.1f}/100 based on {telemetry_qualifier}: {evidence_text}."

        recommendations.append(
            SiteRecommendationOut(
                rank=rank_idx,
                site_id=cand_site.site_id,
                site_code=cand_site.site_code,
                site_name=cand_site.site_name,
                site_slug=cand_site.site_slug,
                latitude_deg=float(cand_site.latitude_deg),
                longitude_deg=float(cand_site.longitude_deg),
                elevation_m=cand_site.elevation_m,
                terrain_type=cand_site.terrain_type,
                overview_summary=cand_site.overview_summary,
                score=cand_score,
                rationale=rationale,
                matched_parameters=vals,
                missing_parameters=missing,
                data_quality_status=cand["quality_status"],
            )
        )

    t1 = time.perf_counter()
    exec_ms = round((t1 - t0) * 1000, 2)

    limitations = [
        "Rankings are calculated deterministically by pure Python algorithms from PostgreSQL metrics.",
        "Ollama is strictly confined to natural-language requirement extraction and never calculates rankings or executes queries.",
    ]
    if fallback_used:
        limitations.append(
            "Local Ollama was unreachable or timed out; deterministic rule-based keyword extraction was used."
        )

    return AIAssistResponseOut(
        mission_request=request.mission_request,
        mission_summary=extracted_reqs.mission_summary,
        extracted_requirements=extracted_reqs,
        recommendations=recommendations,
        fallback_used=fallback_used,
        model_used="rule-based-fallback" if fallback_used else settings.OLLAMA_MODEL,
        execution_time_ms=exec_ms,
        clarification_message=None
        if recommendations
        else "No published landing sites matched all specified constraints.",
        limitations=limitations,
    )
