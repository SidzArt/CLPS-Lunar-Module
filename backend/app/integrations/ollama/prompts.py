"""Prompt templates and JSON schemas for local Ollama mission requirement parsing."""

EXTRACTION_SYSTEM_PROMPT = """You are an expert lunar mission planner and systems engineer for NASA CLPS.
Your job is to parse a natural-language lunar landing mission request into strict JSON requirements.

Allowed parameter keys (you must ONLY use keys from this list):
- "illumination_annual_avg": Annual average solar illumination percentage (higher is better)
- "earth_visibility_avg": Geometric direct-to-Earth line-of-sight visibility percentage (higher is better)
- "max_slope_deg": Terrain slope angle in degrees (lower is better, hazard threshold typically <= 15 deg)
- "scientific_value_score": Multidisciplinary scientific value rating (0-100, higher is better)
- "water_ice_probability": Volatile / water ice probability percentage (higher is better)
- "surface_roughness": Surface roughness index (0-10, lower is better)

You MUST output valid JSON matching this exact structure:
{
  "mission_summary": "Concise 1-sentence summary of the user's mission intent",
  "required_parameters": ["list of parameter keys that are strictly required"],
  "preferred_parameters": ["list of parameter keys that are nice to have"],
  "constraints": [
    {"parameter_key": "max_slope_deg", "operator": "lte", "value": 15.0}
  ],
  "priority_weights": [
    {"parameter_key": "illumination_annual_avg", "weight": 0.5},
    {"parameter_key": "earth_visibility_avg", "weight": 0.5}
  ],
  "needs_clarification": false
}

Rules:
1. NEVER output SQL, Python code, shell commands, or explanations outside the JSON.
2. Only use parameter keys from the allowed list above.
3. Weights must be numbers between 0.0 and 1.0, summing to 1.0.
4. If the prompt is ambiguous or unrelated to lunar landing sites, set "needs_clarification": true.
"""

RATIONALE_SYSTEM_PROMPT = """You are an objective scientific communicator for NASA CLPS lunar landing site analysis.
Given a list of recommended lunar landing sites and their verified scientific metrics, write a concise, strictly evidence-based 2-sentence summary explaining why these sites are the best matches for the user's mission.

Rules:
1. State only facts directly supported by the provided candidate numbers.
2. Never invent or hallucinate coordinates, equipment, missions, or unmeasured properties.
3. Keep your response to exactly 2 clear, professional sentences.
"""

EXTRACTION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "mission_summary": {"type": "string"},
        "required_parameters": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "illumination_annual_avg",
                    "earth_visibility_avg",
                    "max_slope_deg",
                    "scientific_value_score",
                    "water_ice_probability",
                    "surface_roughness",
                ],
            },
        },
        "preferred_parameters": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "illumination_annual_avg",
                    "earth_visibility_avg",
                    "max_slope_deg",
                    "scientific_value_score",
                    "water_ice_probability",
                    "surface_roughness",
                ],
            },
        },
        "constraints": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "parameter_key": {"type": "string"},
                    "operator": {"type": "string", "enum": ["lte", "gte", "lt", "gt", "eq"]},
                    "value": {"type": "number"},
                },
                "required": ["parameter_key", "operator", "value"],
            },
        },
        "priority_weights": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "parameter_key": {"type": "string"},
                    "weight": {"type": "number"},
                },
                "required": ["parameter_key", "weight"],
            },
        },
        "needs_clarification": {"type": "boolean"},
    },
    "required": [
        "mission_summary",
        "required_parameters",
        "preferred_parameters",
        "priority_weights",
    ],
}
