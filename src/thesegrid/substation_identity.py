from __future__ import annotations

import io
import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, IO, Literal
from urllib.request import urlopen

import pandas as pd

if TYPE_CHECKING:
    from thesegrid.osm_substations import OsmSubstation


ODRE_SUBSTATIONS_CSV_URL = (
    "https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
    "postes-electriques-rte/exports/csv"
    "?lang=fr&timezone=Europe%2FParis&use_labels=false&delimiter=%3B"
)

CARTOSTOCK_REQUIRED_COLUMNS = (
    "IDRPoste",
    "ADRPoste",
    "CodeCommuneINSEE",
    "NomCommune",
    "DemandeProximite",
    "CapaciteSansContrainte",
    "ZoneTarifaireTURPE",
    "PlageTarifInjection",
    "Gabarit",
    "CapacitePosteGabarit",
    "NomZoneGabarit",
    "CapaciteZoneGabarit",
)

ODRE_REQUIRED_COLUMNS = (
    "code_poste",
    "nom_poste",
    "fonction",
    "etat",
    "tension",
    "departement",
)

MatchConfidence = Literal["exact", "high", "unmatched"]
CsvSource = str | Path | IO[str]
ByteFetcher = Callable[[str], bytes]
Clock = Callable[[], datetime]


class CartostockSchemaError(ValueError):
    """Raised when a Cartostock export does not match the expected schema."""


class OdreDataAccessError(RuntimeError):
    """Raised when the ODRE substation export cannot be retrieved."""


class OdreSchemaError(ValueError):
    """Raised when the ODRE substation export does not match the expected schema."""


class Rte7000SubstationSchemaError(ValueError):
    """Raised when a RTE7000 substation frame cannot support identity enrichment."""


@dataclass(frozen=True)
class CartostockSubstation:
    cartostock_id: str
    address_label: str
    station_name: str
    normalized_name: str
    voltage_kv: float | None
    commune_insee_code: str
    commune_name: str
    nearby_demand: str | None
    capacity_without_constraint: str | None
    turpe_zone: str | None
    injection_period: str | None
    gabarit: str | None
    gabarit_substation_capacity: str | None
    gabarit_zone_name: str | None
    gabarit_zone_capacity: str | None


@dataclass(frozen=True)
class OdreSubstation:
    odre_code: str
    name: str
    normalized_name: str
    voltage_kv: float | None
    function: str
    status: str
    department: str | None


@dataclass(frozen=True)
class OdreSourceManifest:
    source_url: str
    source_type: str
    row_count: int
    retrieved_at_utc: str


@dataclass(frozen=True)
class OdreSubstationResult:
    substations: tuple[OdreSubstation, ...]
    manifest: OdreSourceManifest


@dataclass(frozen=True)
class FrenchSubstationIdentity:
    cartostock_id: str
    cartostock_station_name: str
    normalized_name: str
    voltage_kv: float | None
    commune_insee_code: str
    commune_name: str
    odre_code: str | None
    odre_name: str | None
    rte7000_id: str | None
    match_confidence: MatchConfidence
    match_method: str
    candidate_count: int
    manual_review_required: bool


@dataclass(frozen=True)
class OsmSubstationIdentityLink:
    substation: OsmSubstation
    identity: FrenchSubstationIdentity | None
    match_confidence: MatchConfidence
    match_method: str
    candidate_count: int
    manual_review_required: bool


def normalize_substation_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value))
    ascii_value = decomposed.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Z0-9]+", "", ascii_value.upper())


def load_cartostock_substations(source: CsvSource) -> tuple[CartostockSubstation, ...]:
    frame = pd.read_csv(source, sep=";", dtype=str, keep_default_na=False)
    _require_columns(frame, CARTOSTOCK_REQUIRED_COLUMNS, CartostockSchemaError, "Cartostock")

    records = tuple(
        CartostockSubstation(
            cartostock_id=str(row.IDRPoste).strip(),
            address_label=str(row.ADRPoste).strip(),
            station_name=_cartostock_station_name(str(row.ADRPoste)),
            normalized_name=normalize_substation_name(
                _cartostock_station_name(str(row.ADRPoste))
            ),
            voltage_kv=_extract_voltage_kv(str(row.ADRPoste)),
            commune_insee_code=str(row.CodeCommuneINSEE).strip(),
            commune_name=str(row.NomCommune).strip(),
            nearby_demand=_optional_text(row.DemandeProximite),
            capacity_without_constraint=_optional_text(row.CapaciteSansContrainte),
            turpe_zone=_optional_text(row.ZoneTarifaireTURPE),
            injection_period=_optional_text(row.PlageTarifInjection),
            gabarit=_optional_text(row.Gabarit),
            gabarit_substation_capacity=_optional_text(row.CapacitePosteGabarit),
            gabarit_zone_name=_optional_text(row.NomZoneGabarit),
            gabarit_zone_capacity=_optional_text(row.CapaciteZoneGabarit),
        )
        for row in frame.itertuples(index=False)
    )
    return tuple(sorted(records, key=lambda record: record.cartostock_id))


def load_odre_substations(
    *,
    source_url: str = ODRE_SUBSTATIONS_CSV_URL,
    fetcher: ByteFetcher | None = None,
    now: Clock | None = None,
) -> OdreSubstationResult:
    fetch = fetcher or _fetch_bytes
    try:
        payload = fetch(source_url)
    except Exception as exc:
        raise OdreDataAccessError(f"failed to retrieve ODRE substations from {source_url}: {exc}") from exc

    frame = pd.read_csv(
        io.BytesIO(payload),
        sep=";",
        dtype=str,
        keep_default_na=False,
    )
    _require_columns(frame, ODRE_REQUIRED_COLUMNS, OdreSchemaError, "ODRE")

    substations = tuple(
        sorted(
            (
                OdreSubstation(
                    odre_code=str(row.code_poste).strip(),
                    name=str(row.nom_poste).strip(),
                    normalized_name=normalize_substation_name(str(row.nom_poste)),
                    voltage_kv=_extract_voltage_kv(str(row.tension)),
                    function=str(row.fonction).strip(),
                    status=str(row.etat).strip(),
                    department=_optional_text(row.departement),
                )
                for row in frame.itertuples(index=False)
            ),
            key=lambda record: (record.odre_code, record.voltage_kv or -1.0),
        )
    )

    retrieved_at = (now or _utc_now)()
    if retrieved_at.tzinfo is None:
        retrieved_at = retrieved_at.replace(tzinfo=UTC)
    retrieved_at = retrieved_at.astimezone(UTC)
    return OdreSubstationResult(
        substations=substations,
        manifest=OdreSourceManifest(
            source_url=source_url,
            source_type="public_signal",
            row_count=len(substations),
            retrieved_at_utc=retrieved_at.isoformat(),
        ),
    )


def build_french_substation_identities(
    cartostock_substations: Iterable[CartostockSubstation],
    odre_substations: Iterable[OdreSubstation],
    rte7000_substations: pd.DataFrame,
) -> tuple[FrenchSubstationIdentity, ...]:
    if "id" not in rte7000_substations.columns:
        raise Rte7000SubstationSchemaError(
            "RTE7000 substation frame is missing required column: id"
        )

    odre_by_name: dict[str, list[OdreSubstation]] = defaultdict(list)
    for substation in odre_substations:
        odre_by_name[substation.normalized_name].append(substation)
    rte7000_ids = set(rte7000_substations["id"].dropna().astype(str))

    identities = [
        _match_cartostock_substation(substation, odre_by_name, rte7000_ids)
        for substation in cartostock_substations
    ]
    return tuple(sorted(identities, key=lambda identity: identity.cartostock_id))


def link_osm_substation_identity(
    substation: OsmSubstation,
    identities: Iterable[FrenchSubstationIdentity],
    *,
    preferred_voltage_kv: float | None = None,
) -> OsmSubstationIdentityLink:
    identity_records = tuple(identities)
    if substation.reference:
        reference_candidates = tuple(
            identity
            for identity in identity_records
            if identity.odre_code == substation.reference.strip()
        )
        selected = _select_voltage_identity(
            reference_candidates,
            substation,
            preferred_voltage_kv=preferred_voltage_kv,
        )
        if selected is not None:
            return _osm_link(
                substation,
                selected,
                confidence="exact",
                method=(
                    "odre_code"
                    if len(reference_candidates) == 1
                    else "odre_code_and_client_preference"
                ),
                candidate_count=len(reference_candidates),
            )
        if reference_candidates:
            return _osm_unmatched_link(
                substation,
                method="ambiguous_odre_code",
                candidate_count=len(reference_candidates),
            )

    osm_name_keys = _osm_normalized_name_keys(substation.normalized_name)
    name_candidates = tuple(
        identity
        for identity in identity_records
        if identity.normalized_name in osm_name_keys
    )
    voltage_candidates = tuple(
        identity
        for identity in name_candidates
        if _voltage_is_compatible(identity.voltage_kv, substation.voltage_levels_kv)
    )
    if len(voltage_candidates) == 1:
        return _osm_link(
            substation,
            voltage_candidates[0],
            confidence="exact",
            method="normalized_name_and_voltage",
            candidate_count=1,
        )
    if len(voltage_candidates) > 1:
        preferred = _select_preferred_identity(
            voltage_candidates,
            preferred_voltage_kv,
        )
        if preferred is not None:
            return _osm_link(
                substation,
                preferred,
                confidence="exact",
                method="normalized_name_voltage_and_client_preference",
                candidate_count=len(voltage_candidates),
            )
        return _osm_unmatched_link(
            substation,
            method="ambiguous_normalized_name_and_voltage",
            candidate_count=len(voltage_candidates),
        )
    if len(name_candidates) == 1:
        identity = name_candidates[0]
        has_voltage_conflict = (
            bool(substation.voltage_levels_kv)
            and identity.voltage_kv is not None
            and not _voltage_is_compatible(
                identity.voltage_kv,
                substation.voltage_levels_kv,
            )
        )
        if has_voltage_conflict:
            return _osm_unmatched_link(
                substation,
                method="voltage_conflict",
                candidate_count=1,
            )
        return _osm_link(
            substation,
            identity,
            confidence="high",
            method="unique_normalized_name",
            candidate_count=1,
        )
    if name_candidates:
        return _osm_unmatched_link(
            substation,
            method="ambiguous_normalized_name",
            candidate_count=len(name_candidates),
        )
    return _osm_unmatched_link(
        substation,
        method="no_deterministic_match",
        candidate_count=0,
    )


def _match_cartostock_substation(
    cartostock: CartostockSubstation,
    odre_by_name: dict[str, list[OdreSubstation]],
    rte7000_ids: set[str],
) -> FrenchSubstationIdentity:
    name_candidates = odre_by_name.get(cartostock.normalized_name, [])
    voltage_candidates = [
        candidate
        for candidate in name_candidates
        if candidate.voltage_kv == cartostock.voltage_kv
    ]

    matched: OdreSubstation | None = None
    if len(voltage_candidates) == 1:
        matched = voltage_candidates[0]
        confidence: MatchConfidence = "exact"
        method = "normalized_name_and_voltage"
        candidate_count = 1
    elif len(voltage_candidates) > 1:
        confidence = "unmatched"
        method = "ambiguous_normalized_name_and_voltage"
        candidate_count = len(voltage_candidates)
    else:
        unique_codes = {candidate.odre_code for candidate in name_candidates}
        if len(unique_codes) == 1 and name_candidates:
            matched = sorted(
                name_candidates,
                key=lambda candidate: (candidate.voltage_kv or -1.0, candidate.odre_code),
            )[0]
            confidence = "high"
            method = "unique_normalized_name"
            candidate_count = 1
        elif name_candidates:
            confidence = "unmatched"
            method = "ambiguous_normalized_name"
            candidate_count = len(unique_codes)
        else:
            confidence = "unmatched"
            method = "no_deterministic_match"
            candidate_count = 0

    return FrenchSubstationIdentity(
        cartostock_id=cartostock.cartostock_id,
        cartostock_station_name=cartostock.station_name,
        normalized_name=cartostock.normalized_name,
        voltage_kv=cartostock.voltage_kv,
        commune_insee_code=cartostock.commune_insee_code,
        commune_name=cartostock.commune_name,
        odre_code=None if matched is None else matched.odre_code,
        odre_name=None if matched is None else matched.name,
        rte7000_id=(
            matched.odre_code
            if matched is not None and matched.odre_code in rte7000_ids
            else None
        ),
        match_confidence=confidence,
        match_method=method,
        candidate_count=candidate_count,
        manual_review_required=confidence == "unmatched",
    )


def _select_voltage_identity(
    identities: tuple[FrenchSubstationIdentity, ...],
    substation: OsmSubstation,
    *,
    preferred_voltage_kv: float | None,
) -> FrenchSubstationIdentity | None:
    if len(identities) == 1:
        return identities[0]
    voltage_candidates = tuple(
        identity
        for identity in identities
        if _voltage_is_compatible(identity.voltage_kv, substation.voltage_levels_kv)
    )
    if len(voltage_candidates) == 1:
        return voltage_candidates[0]
    return _select_preferred_identity(voltage_candidates, preferred_voltage_kv)


def _select_preferred_identity(
    identities: tuple[FrenchSubstationIdentity, ...],
    preferred_voltage_kv: float | None,
) -> FrenchSubstationIdentity | None:
    if preferred_voltage_kv is None:
        return None
    preferred = tuple(
        identity
        for identity in identities
        if identity.voltage_kv is not None
        and abs(identity.voltage_kv - preferred_voltage_kv) <= 0.5
    )
    return preferred[0] if len(preferred) == 1 else None


def _voltage_is_compatible(
    identity_voltage_kv: float | None,
    osm_voltage_levels_kv: tuple[float, ...],
) -> bool:
    if identity_voltage_kv is None or not osm_voltage_levels_kv:
        return False
    return any(
        abs(identity_voltage_kv - osm_voltage_kv) <= 0.5
        for osm_voltage_kv in osm_voltage_levels_kv
    )


def _osm_normalized_name_keys(normalized_name: str) -> set[str]:
    if not normalized_name:
        return set()
    keys = {normalized_name}
    for prefix in (
        "POSTEELECTRIQUEDE",
        "POSTEELECTRIQUED",
        "POSTEELECTRIQUE",
        "POSTEDE",
        "POSTED",
        "POSTE",
    ):
        if normalized_name.startswith(prefix) and len(normalized_name) > len(prefix):
            keys.add(normalized_name[len(prefix) :])
    return keys


def _osm_link(
    substation: OsmSubstation,
    identity: FrenchSubstationIdentity,
    *,
    confidence: MatchConfidence,
    method: str,
    candidate_count: int,
) -> OsmSubstationIdentityLink:
    return OsmSubstationIdentityLink(
        substation=substation,
        identity=identity,
        match_confidence=confidence,
        match_method=method,
        candidate_count=candidate_count,
        manual_review_required=False,
    )


def _osm_unmatched_link(
    substation: OsmSubstation,
    *,
    method: str,
    candidate_count: int,
) -> OsmSubstationIdentityLink:
    return OsmSubstationIdentityLink(
        substation=substation,
        identity=None,
        match_confidence="unmatched",
        match_method=method,
        candidate_count=candidate_count,
        manual_review_required=True,
    )


def _cartostock_station_name(address: str) -> str:
    value = str(address).strip()
    return re.sub(
        r"^POSTE\s+\d+(?:[.,]\d+)?\s*kV\s+N[O0]\s+\d+\s+",
        "",
        value,
        flags=re.IGNORECASE,
    ).strip()


def _extract_voltage_kv(value: str) -> float | None:
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*kV", str(value), re.IGNORECASE)
    if match is None:
        return None
    return float(match.group(1).replace(",", "."))


def _optional_text(value: object) -> str | None:
    text = str(value).strip()
    return text or None


def _require_columns(
    frame: pd.DataFrame,
    required: tuple[str, ...],
    error_type: type[ValueError],
    source_name: str,
) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise error_type(f"{source_name} data is missing required columns: {', '.join(missing)}")


def _fetch_bytes(url: str) -> bytes:
    with urlopen(url, timeout=30) as response:
        return response.read()


def _utc_now() -> datetime:
    return datetime.now(UTC)
