from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


ARTIFACT_CANDIDATES = {
    "screening": (
        "screening/screening.csv",
        "screening.csv",
    ),
    "qsts_stratified": (
        "qsts_stratified/qsts_results.csv",
    ),
    "qsts_full_year": (
        "qsts_full_year/qsts_results.csv",
        "qsts_results.csv",
        "merged/qsts_results.csv",
    ),
    "validation": (
        "validation/validation_matrix.csv",
        "validation_matrix.csv",
    ),
    "resize": (
        "resize/resize_results.csv",
        "resize_results.csv",
    ),
    "decision_frontier": (
        "qsts_full_year/decision_frontier.csv",
        "decision_frontier.csv",
        "merged/decision_frontier.csv",
    ),
    "risk_summary": (
        "qsts_full_year/qsts_risk_summary.csv",
        "qsts_risk_summary.csv",
        "merged/qsts_risk_summary.csv",
    ),
    "contractual_envelope": (
        "qsts_full_year/contractual_envelope.csv",
        "contractual_envelope.csv",
        "merged/contractual_envelope.csv",
    ),
    "static_vs_qsts": (
        "qsts_full_year/static_vs_qsts_comparison.csv",
        "static_vs_qsts_comparison.csv",
        "merged/static_vs_qsts_comparison.csv",
    ),
    "performance": (
        "qsts_full_year/qsts_performance.json",
        "qsts_performance.json",
        "merged/qsts_performance.json",
    ),
    "manifest": (
        "pipeline_manifest.json",
        "qsts_full_year/run_manifest.json",
        "run_manifest.json",
        "merged/run_manifest.json",
    ),
}


@dataclass(frozen=True)
class ResultBundle:
    root: Path
    artifacts: dict[str, Path]
    tables: dict[str, pd.DataFrame]
    json_payloads: dict[str, dict[str, Any]]

    @property
    def available_tables(self) -> tuple[str, ...]:
        return tuple(name for name, frame in self.tables.items() if not frame.empty)


def load_result_bundle(root: Path) -> ResultBundle:
    artifacts = discover_artifacts(root)
    tables: dict[str, pd.DataFrame] = {}
    json_payloads: dict[str, dict[str, Any]] = {}
    for name, path in artifacts.items():
        if path.suffix == ".csv":
            tables[name] = read_table(path)
        elif path.suffix == ".json":
            json_payloads[name] = read_json(path)
    return ResultBundle(
        root=root,
        artifacts=artifacts,
        tables=tables,
        json_payloads=json_payloads,
    )


def discover_artifacts(root: Path) -> dict[str, Path]:
    artifacts: dict[str, Path] = {}
    if not root.exists() or not root.is_dir():
        return artifacts
    for name, candidates in ARTIFACT_CANDIDATES.items():
        for relative_path in candidates:
            path = root / relative_path
            if path.exists():
                artifacts[name] = path
                break
    return artifacts


def read_table(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame()


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def verdict_counts(frame: pd.DataFrame, column: str) -> dict[str, int]:
    if frame.empty or column not in frame:
        return {}
    counts = frame[column].fillna("").astype(str).value_counts().to_dict()
    return {str(key): int(value) for key, value in counts.items() if key}


def numeric_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if frame.empty or column not in frame:
        return pd.Series(dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def best_resize_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "acceptable" not in frame or "requested_mw" not in frame:
        return pd.DataFrame()
    working = frame.copy()
    acceptable = working["acceptable"].astype(str).str.lower().isin({"true", "1", "yes"})
    working = working[acceptable].copy()
    if working.empty:
        return working
    working["_requested_mw_numeric"] = numeric_column(working, "requested_mw")
    sort_columns = ["bus_id", "_requested_mw_numeric"] if "bus_id" in working else ["_requested_mw_numeric"]
    ascending = [True, False] if "bus_id" in working else [False]
    working = working.sort_values(sort_columns, ascending=ascending)
    if "bus_id" in working:
        working = working.drop_duplicates(subset=["bus_id"], keep="first")
    return working.drop(columns=["_requested_mw_numeric"])


def manifest_context(payload: dict[str, Any]) -> dict[str, str]:
    request = payload.get("request", {}) if isinstance(payload.get("request"), dict) else {}
    evidence = payload.get("evidence", {}) if isinstance(payload.get("evidence"), dict) else {}
    return {
        "network_code": str(request.get("network_code", "")),
        "requested_mw": str(request.get("requested_mw", "")),
        "asset": str(request.get("asset", "")),
        "data_source_type": str(evidence.get("data_source_type", "")),
        "evidence_level": str(evidence.get("evidence_level", "")),
        "decision_confidence": str(evidence.get("decision_confidence", "")),
    }
