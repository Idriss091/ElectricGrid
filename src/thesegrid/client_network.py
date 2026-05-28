from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from thesegrid.evidence import DATA_SOURCE_TYPES


REQUIRED_FILES = ("metadata.yaml", "buses.csv", "lines.csv", "loads.csv", "constraints.yaml")
OPTIONAL_FILES = (
    "transformers.csv",
    "generators.csv",
    "storage.csv",
    "profiles_load.csv",
    "profiles_generation.csv",
    "profiles_storage.csv",
)

REQUIRED_METADATA_KEYS = (
    "schema_version",
    "data_source_type",
    "network_name",
    "country",
    "voltage_level",
)

REQUIRED_CONSTRAINT_KEYS = (
    "voltage_min_pu",
    "voltage_max_pu",
    "max_loading_percent",
    "candidate_asset",
    "candidate_power_factor",
)

REQUIRED_COLUMNS = {
    "buses.csv": ("bus_id", "name", "vn_kv", "in_service"),
    "lines.csv": (
        "line_id",
        "from_bus",
        "to_bus",
        "length_km",
        "r_ohm_per_km",
        "x_ohm_per_km",
        "c_nf_per_km",
        "max_i_ka",
        "in_service",
    ),
    "transformers.csv": (
        "trafo_id",
        "hv_bus",
        "lv_bus",
        "sn_mva",
        "vn_hv_kv",
        "vn_lv_kv",
        "vk_percent",
        "vkr_percent",
        "pfe_kw",
        "i0_percent",
        "in_service",
    ),
    "loads.csv": ("load_id", "bus_id", "p_mw", "q_mvar", "in_service"),
    "generators.csv": ("generator_id", "bus_id", "type", "p_mw", "q_mvar", "in_service"),
    "storage.csv": ("storage_id", "bus_id", "p_mw", "max_e_mwh", "in_service"),
}


@dataclass(frozen=True)
class ClientNetworkValidation:
    package_path: Path
    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    metadata: dict[str, str]
    constraints: dict[str, str]
    checked_files: dict[str, str]


@dataclass(frozen=True)
class ClientNetworkValidationPaths:
    json_path: Path
    markdown_path: Path


def validate_client_network(package_path: Path) -> ClientNetworkValidation:
    errors: list[str] = []
    warnings: list[str] = []
    checked_files: dict[str, str] = {}
    metadata: dict[str, str] = {}
    constraints: dict[str, str] = {}

    if not package_path.exists():
        errors.append(f"client network package does not exist: {package_path}")
        return _result(package_path, errors, warnings, metadata, constraints, checked_files)
    if not package_path.is_dir():
        errors.append(f"client network package must be a directory: {package_path}")
        return _result(package_path, errors, warnings, metadata, constraints, checked_files)

    for filename in REQUIRED_FILES:
        path = package_path / filename
        checked_files[filename] = "present" if path.exists() else "missing"
        if not path.exists():
            errors.append(f"missing required file: {filename}")

    for filename in OPTIONAL_FILES:
        path = package_path / filename
        checked_files[filename] = "present" if path.exists() else "optional_missing"

    if (package_path / "metadata.yaml").exists():
        metadata = _read_flat_yaml(package_path / "metadata.yaml")
        _validate_keys("metadata.yaml", metadata, REQUIRED_METADATA_KEYS, errors)
        if metadata.get("schema_version") != "thesegrid-client-network-v1":
            errors.append("metadata.yaml schema_version must be thesegrid-client-network-v1")
        if metadata.get("data_source_type") and metadata["data_source_type"] not in DATA_SOURCE_TYPES:
            errors.append(
                "metadata.yaml data_source_type must be one of: "
                + ", ".join(DATA_SOURCE_TYPES)
            )

    if (package_path / "constraints.yaml").exists():
        constraints = _read_flat_yaml(package_path / "constraints.yaml")
        _validate_keys("constraints.yaml", constraints, REQUIRED_CONSTRAINT_KEYS, errors)
        if constraints.get("candidate_asset", "").lower() != "bess":
            errors.append("constraints.yaml candidate_asset must be bess for V1")
        _validate_float_range("voltage_min_pu", constraints, errors, minimum=0.0)
        _validate_float_range("voltage_max_pu", constraints, errors, minimum=0.0)
        _validate_float_range("max_loading_percent", constraints, errors, minimum=0.0)
        _validate_float_range("candidate_power_factor", constraints, errors, minimum=0.0)

    for filename, required_columns in REQUIRED_COLUMNS.items():
        path = package_path / filename
        if not path.exists():
            continue
        missing = _missing_columns(path, required_columns)
        if missing:
            errors.append(
                f"{filename} missing required columns: {', '.join(missing)}"
            )

    if not any((package_path / name).exists() for name in ("profiles_load.csv", "profiles_generation.csv")):
        warnings.append("QSTS validation needs hourly or sub-hourly profile files")

    return _result(package_path, errors, warnings, metadata, constraints, checked_files)


def write_client_network_validation(
    result: ClientNetworkValidation,
    output_dir: Path,
) -> ClientNetworkValidationPaths:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "client_network_validation.json"
    markdown_path = output_dir / "client_network_validation.md"
    payload = asdict(result)
    payload["package_path"] = result.package_path.as_posix()
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_client_network_validation(result), encoding="utf-8")
    return ClientNetworkValidationPaths(json_path=json_path, markdown_path=markdown_path)


def render_client_network_validation(result: ClientNetworkValidation) -> str:
    status = "valid" if result.valid else "invalid"
    errors = "\n".join(f"- {error}" for error in result.errors) or "- none"
    warnings = "\n".join(f"- {warning}" for warning in result.warnings) or "- none"
    files = "\n".join(
        f"| {filename} | {status} |" for filename, status in sorted(result.checked_files.items())
    )
    data_source_type = result.metadata.get("data_source_type", "")
    return f"""# Client Network Validation

- status: {status}
- package_path: {result.package_path}
- schema_version: {result.metadata.get("schema_version", "")}
- data_source_type: {data_source_type}
- network_name: {result.metadata.get("network_name", "")}

## Checked Files

| file | status |
| --- | --- |
{files}

## Errors

{errors}

## Warnings

{warnings}

## Boundary

This validation checks package structure and declared schema only. It does not certify
network correctness and does not replace an official grid-connection study.
"""


def _result(
    package_path: Path,
    errors: list[str],
    warnings: list[str],
    metadata: dict[str, str],
    constraints: dict[str, str],
    checked_files: dict[str, str],
) -> ClientNetworkValidation:
    return ClientNetworkValidation(
        package_path=package_path,
        valid=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
        metadata=metadata,
        constraints=constraints,
        checked_files=checked_files,
    )


def _read_flat_yaml(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = _strip_inline_comment(value.strip()).strip('"').strip("'")
    return values


def _strip_inline_comment(value: str) -> str:
    if " #" not in value:
        return value
    return value.split(" #", 1)[0].strip()


def _validate_keys(
    filename: str,
    values: dict[str, str],
    required_keys: tuple[str, ...],
    errors: list[str],
) -> None:
    missing = [key for key in required_keys if key not in values or values[key] == ""]
    if missing:
        errors.append(f"{filename} missing required keys: {', '.join(missing)}")


def _validate_float_range(
    key: str,
    values: dict[str, str],
    errors: list[str],
    *,
    minimum: float,
) -> None:
    if key not in values:
        return
    try:
        value = float(values[key])
    except ValueError:
        errors.append(f"constraints.yaml {key} must be numeric")
        return
    if value < minimum:
        errors.append(f"constraints.yaml {key} must be >= {minimum}")


def _missing_columns(path: Path, required_columns: tuple[str, ...]) -> list[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader, [])
    present = {column.strip() for column in header}
    return [column for column in required_columns if column not in present]
