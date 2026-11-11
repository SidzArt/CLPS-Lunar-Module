"""Strict allow-listed firmware template renderer and validator for CODEX code versions."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import Any

PLACEHOLDER_PATTERN = re.compile(r"\{\{([A-Z0-9_]+)\}\}")
RAW_TOKEN_PATTERN = re.compile(r"\{\{([^}]*)\}\}")
UNSAFE_C_FRAGMENTS = (
    "\n",
    "\r",
    ";",
    "#include",
    "#define",
    "/*",
    "*/",
    "//",
    '"',
    "'",
    "\\",
)


class TemplateRenderError(ValueError):
    """Raised when template placeholders, bounds, types, or checksums fail validation."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class PlaceholderSpec:
    """Allow-listed template placeholder specification backed by `code_placeholders`."""

    placeholder_key: str
    data_type: str  # 'int' | 'float' | 'bool' | 'string'
    required: bool = True
    default_value: Any | None = None
    validation_schema: dict[str, Any] | None = None
    injection_format: str = "cpp_literal"
    unit: str | None = None


@dataclass(frozen=True)
class RenderedTemplateResult:
    """Output of strictly validated firmware placeholder substitution."""

    rendered_source: str
    source_checksum_sha256: str
    rendered_checksum_sha256: str
    substituted_keys: dict[str, str]
    warnings: list[str] = field(default_factory=list)


def compute_sha256_hex(content: str) -> str:
    """Compute canonical UTF-8 SHA-256 hex digest for source code or rendered output."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _unwrap_default(raw_default: Any) -> Any:
    """Unwrap JSONB stored default representations cleanly."""
    if isinstance(raw_default, dict) and set(raw_default.keys()) == {"value"}:
        return raw_default["value"]
    return raw_default


def _coerce_and_validate_value(spec: PlaceholderSpec, raw_value: Any) -> str:
    """Coerce value to declared type, enforce schema bounds, and format safely for C/C++."""
    schema = spec.validation_schema or {}
    dtype = spec.data_type.lower().strip()

    if dtype in ("int", "integer"):
        if isinstance(raw_value, bool):
            raise TemplateRenderError(
                "invalid_placeholder_type",
                f"Placeholder '{spec.placeholder_key}' expects int, got bool.",
            )
        try:
            int_val = int(raw_value)
            if isinstance(raw_value, float) and not raw_value.is_integer():
                raise ValueError("non-integer float")
        except (TypeError, ValueError) as exc:
            raise TemplateRenderError(
                "invalid_placeholder_type",
                f"Placeholder '{spec.placeholder_key}' must be a valid integer.",
            ) from exc

        if "min" in schema and int_val < int(schema["min"]):
            raise TemplateRenderError(
                "placeholder_out_of_bounds",
                f"Placeholder '{spec.placeholder_key}'={int_val} is below min={schema['min']}.",
            )
        if "max" in schema and int_val > int(schema["max"]):
            raise TemplateRenderError(
                "placeholder_out_of_bounds",
                f"Placeholder '{spec.placeholder_key}'={int_val} exceeds max={schema['max']}.",
            )
        if "allowed_values" in schema and int_val not in [int(x) for x in schema["allowed_values"]]:
            raise TemplateRenderError(
                "placeholder_not_allowed",
                f"Placeholder '{spec.placeholder_key}'={int_val} is not in allowed_values.",
            )
        return str(int_val)

    if dtype in ("float", "number", "double"):
        if isinstance(raw_value, bool):
            raise TemplateRenderError(
                "invalid_placeholder_type",
                f"Placeholder '{spec.placeholder_key}' expects float, got bool.",
            )
        try:
            flt_val = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise TemplateRenderError(
                "invalid_placeholder_type",
                f"Placeholder '{spec.placeholder_key}' must be a finite number.",
            ) from exc
        if not math.isfinite(flt_val):
            raise TemplateRenderError(
                "placeholder_non_finite",
                f"Placeholder '{spec.placeholder_key}' must be finite.",
            )
        if "min" in schema and flt_val < float(schema["min"]):
            raise TemplateRenderError(
                "placeholder_out_of_bounds",
                f"Placeholder '{spec.placeholder_key}'={flt_val} is below min={schema['min']}.",
            )
        if "max" in schema and flt_val > float(schema["max"]):
            raise TemplateRenderError(
                "placeholder_out_of_bounds",
                f"Placeholder '{spec.placeholder_key}'={flt_val} exceeds max={schema['max']}.",
            )
        return f"{flt_val:.6f}".rstrip("0").rstrip(".") if "." in f"{flt_val:.6f}" else str(flt_val)

    if dtype in ("bool", "boolean"):
        if isinstance(raw_value, bool):
            bool_val = raw_value
        elif isinstance(raw_value, int) and raw_value in (0, 1):
            bool_val = bool(raw_value)
        elif isinstance(raw_value, str) and raw_value.lower() in ("true", "false", "1", "0"):
            bool_val = raw_value.lower() in ("true", "1")
        else:
            raise TemplateRenderError(
                "invalid_placeholder_type",
                f"Placeholder '{spec.placeholder_key}' must be boolean.",
            )
        if spec.injection_format == "int_flag":
            return "1" if bool_val else "0"
        return "true" if bool_val else "false"

    if dtype in ("str", "string", "identifier"):
        text = str(raw_value)
        if any(frag in text for frag in UNSAFE_C_FRAGMENTS):
            raise TemplateRenderError(
                "unsafe_placeholder_characters",
                f"Placeholder '{spec.placeholder_key}' contains disallowed C/C++ control tokens.",
            )
        max_len = int(schema.get("max_length", 64))
        if len(text) > max_len:
            raise TemplateRenderError(
                "placeholder_too_long",
                f"Placeholder '{spec.placeholder_key}' exceeds max_length={max_len}.",
            )
        pattern = schema.get("pattern")
        if pattern and not re.fullmatch(str(pattern), text):
            raise TemplateRenderError(
                "placeholder_pattern_mismatch",
                f"Placeholder '{spec.placeholder_key}' does not match required pattern '{pattern}'.",
            )
        if "allowed_values" in schema and text not in [str(x) for x in schema["allowed_values"]]:
            raise TemplateRenderError(
                "placeholder_not_allowed",
                f"Placeholder '{spec.placeholder_key}'='{text}' is not in allowed_values.",
            )
        if spec.injection_format == "c_identifier":
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", text):
                raise TemplateRenderError(
                    "invalid_c_identifier",
                    f"Placeholder '{spec.placeholder_key}' must be a valid C identifier.",
                )
            return text
        if spec.injection_format == "c_string":
            return f'"{text}"'
        return text

    raise TemplateRenderError(
        "unsupported_placeholder_type",
        f"Unsupported data_type '{spec.data_type}' on placeholder '{spec.placeholder_key}'.",
    )


def render_firmware_template(
    source_code: str,
    placeholders: list[PlaceholderSpec],
    values: dict[str, Any],
    *,
    expected_source_checksum: str | None = None,
) -> RenderedTemplateResult:
    """Strictly substitute allow-listed ``{{KEY}}`` tokens inside firmware source text."""
    actual_checksum = compute_sha256_hex(source_code)
    if expected_source_checksum and actual_checksum != expected_source_checksum:
        raise TemplateRenderError(
            "source_checksum_mismatch",
            (
                f"Template source SHA-256 '{actual_checksum}' does not match recorded "
                f"checksum '{expected_source_checksum}'."
            ),
        )

    spec_map = {p.placeholder_key: p for p in placeholders}
    raw_matches = [m.group(1) for m in RAW_TOKEN_PATTERN.finditer(source_code)]
    for token in raw_matches:
        if not re.fullmatch(r"[A-Z0-9_]+", token):
            raise TemplateRenderError(
                "malformed_placeholder_syntax",
                f"Malformed placeholder syntax '{{{{{token}}}}}' detected in firmware template.",
            )
        if token not in spec_map:
            raise TemplateRenderError(
                "undeclared_placeholder",
                f"Undeclared placeholder '{{{{{token}}}}}' is not in code_placeholders allow-list.",
            )

    substituted: dict[str, str] = {}
    warnings: list[str] = []
    tokens_in_source = set(raw_matches)

    for key, spec in spec_map.items():
        if key in values and values[key] is not None:
            raw_val = values[key]
        elif spec.default_value is not None:
            raw_val = _unwrap_default(spec.default_value)
            if key in tokens_in_source:
                warnings.append(f"Placeholder '{key}' used declared default value.")
        elif spec.required and key in tokens_in_source:
            raise TemplateRenderError(
                "missing_required_placeholder",
                f"Required placeholder '{{{{{key}}}}}' was not provided.",
            )
        else:
            continue

        substituted[key] = _coerce_and_validate_value(spec, raw_val)

    def _replace(match: re.Match[str]) -> str:
        k = match.group(1)
        if k not in substituted:
            raise TemplateRenderError(
                "missing_required_placeholder",
                f"Placeholder '{{{{{k}}}}}' has no resolved value.",
            )
        return substituted[k]

    rendered = PLACEHOLDER_PATTERN.sub(_replace, source_code)
    return RenderedTemplateResult(
        rendered_source=rendered,
        source_checksum_sha256=actual_checksum,
        rendered_checksum_sha256=compute_sha256_hex(rendered),
        substituted_keys=substituted,
        warnings=warnings,
    )
