from __future__ import annotations

import io
import json
from dataclasses import asdict
from datetime import UTC, datetime

import pandas as pd
import pytest

from thesegrid.osm_substations import OsmSubstation
from thesegrid.substation_identity import (
    CartostockSchemaError,
    FrenchSubstationIdentity,
    OdreSchemaError,
    Rte7000SubstationSchemaError,
    build_french_substation_identities,
    link_osm_substation_identity,
    load_cartostock_substations,
    load_odre_substations,
    normalize_substation_name,
)


CARTOSTOCK_COLUMNS = (
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


def _cartostock_csv(rows: list[dict[str, str]]) -> str:
    frame = pd.DataFrame(rows, columns=CARTOSTOCK_COLUMNS).fillna("")
    return frame.to_csv(index=False, sep=";")


def _cartostock_row(
    identifier: str,
    address: str,
    *,
    insee: str = "75056",
    commune: str = "Paris",
) -> dict[str, str]:
    return {
        "IDRPoste": identifier,
        "ADRPoste": address,
        "CodeCommuneINSEE": insee,
        "NomCommune": commune,
        "DemandeProximite": "",
        "CapaciteSansContrainte": "< 5 MW",
        "ZoneTarifaireTURPE": "",
        "PlageTarifInjection": "",
        "Gabarit": "",
        "CapacitePosteGabarit": "",
        "NomZoneGabarit": "",
        "CapaciteZoneGabarit": "",
    }


def test_normalize_substation_name_removes_accents_punctuation_and_spacing():
    assert normalize_substation_name("  Argelès-sur-Mer / l'Étang  ") == "ARGELESSURMERLETANG"


def test_load_cartostock_extracts_name_voltage_and_sorts_by_identifier():
    csv_text = _cartostock_csv(
        [
            _cartostock_row("B.POST4", "POSTE 90kV N0 1 ÉTANG-DU-NORD"),
            _cartostock_row("A.POST3", "POSTE 63kV N0 1 AIRE-SUR-ADOUR"),
        ]
    )

    records = load_cartostock_substations(io.StringIO(csv_text))

    assert [record.cartostock_id for record in records] == ["A.POST3", "B.POST4"]
    assert records[0].station_name == "AIRE-SUR-ADOUR"
    assert records[0].normalized_name == "AIRESURADOUR"
    assert records[0].voltage_kv == 63.0
    assert records[0].capacity_without_constraint == "< 5 MW"


def test_load_cartostock_rejects_missing_required_columns():
    with pytest.raises(CartostockSchemaError, match="ADRPoste"):
        load_cartostock_substations(io.StringIO("IDRPoste\nA.POST3\n"))


def test_load_odre_fetches_csv_normalizes_rows_and_records_provenance():
    csv_bytes = (
        "code_poste;nom_poste;fonction;etat;tension;departement\n"
        "AIREP;AIRE-SUR-ADOUR;Poste de transformation;EN EXPLOITATION;63kV;Landes\n"
    ).encode()
    calls: list[str] = []

    def fetcher(url: str) -> bytes:
        calls.append(url)
        return csv_bytes

    result = load_odre_substations(
        fetcher=fetcher,
        now=lambda: datetime(2026, 6, 11, 14, 0, tzinfo=UTC),
    )

    assert calls == [result.manifest.source_url]
    assert result.substations[0].odre_code == "AIREP"
    assert result.substations[0].normalized_name == "AIRESURADOUR"
    assert result.substations[0].voltage_kv == 63.0
    assert result.manifest.source_type == "public_signal"
    assert result.manifest.row_count == 1
    assert result.manifest.retrieved_at_utc == "2026-06-11T14:00:00+00:00"
    json.dumps(asdict(result.manifest))


def test_load_odre_rejects_missing_required_columns():
    with pytest.raises(OdreSchemaError, match="tension"):
        load_odre_substations(
            fetcher=lambda _url: b"code_poste;nom_poste\nAIREP;AIRE-SUR-ADOUR\n"
        )


def test_build_identities_uses_conservative_matching_and_exact_rte7000_codes():
    cartostock = load_cartostock_substations(
        io.StringIO(
            _cartostock_csv(
                [
                    _cartostock_row("A.EXACT3", "POSTE 63kV N0 1 AIRE-SUR-ADOUR"),
                    _cartostock_row("B.HIGH4", "POSTE 90kV N0 1 NOM-UNIQUE"),
                    _cartostock_row("C.AMBI3", "POSTE 63kV N0 1 NOM-AMBIGU"),
                    _cartostock_row("D.NONE3", "POSTE 63kV N0 1 SANS-CORRESPONDANCE"),
                ]
            )
        )
    )
    odre = load_odre_substations(
        fetcher=lambda _url: (
            "code_poste;nom_poste;fonction;etat;tension;departement\n"
            "AIREP;AIRE-SUR-ADOUR;Poste;EN EXPLOITATION;63kV;Landes\n"
            "UNIQP;NOM UNIQUE;Poste;EN EXPLOITATION;225kV;Paris\n"
            "AMBIA;NOM AMBIGU;Poste;EN EXPLOITATION;63kV;Nord\n"
            "AMBIB;NOM-AMBIGU;Poste;EN EXPLOITATION;63kV;Sud\n"
        ).encode()
    ).substations
    rte7000 = pd.DataFrame({"id": ["AIREP", "UNIQP", "OTHER"]})

    identities = build_french_substation_identities(cartostock, odre, rte7000)
    by_id = {identity.cartostock_id: identity for identity in identities}

    assert by_id["A.EXACT3"].match_confidence == "exact"
    assert by_id["A.EXACT3"].match_method == "normalized_name_and_voltage"
    assert by_id["A.EXACT3"].odre_code == "AIREP"
    assert by_id["A.EXACT3"].rte7000_id == "AIREP"
    assert by_id["A.EXACT3"].candidate_count == 1
    assert by_id["A.EXACT3"].manual_review_required is False

    assert by_id["B.HIGH4"].match_confidence == "high"
    assert by_id["B.HIGH4"].match_method == "unique_normalized_name"
    assert by_id["B.HIGH4"].odre_code == "UNIQP"
    assert by_id["B.HIGH4"].rte7000_id == "UNIQP"
    assert by_id["B.HIGH4"].manual_review_required is False

    assert by_id["C.AMBI3"].match_confidence == "unmatched"
    assert by_id["C.AMBI3"].match_method == "ambiguous_normalized_name_and_voltage"
    assert by_id["C.AMBI3"].odre_code is None
    assert by_id["C.AMBI3"].candidate_count == 2
    assert by_id["C.AMBI3"].manual_review_required is True

    assert by_id["D.NONE3"].match_confidence == "unmatched"
    assert by_id["D.NONE3"].match_method == "no_deterministic_match"
    assert by_id["D.NONE3"].candidate_count == 0
    assert by_id["D.NONE3"].manual_review_required is True


def test_build_identities_keeps_odre_match_when_code_is_absent_from_rte7000():
    cartostock = load_cartostock_substations(
        io.StringIO(
            _cartostock_csv(
                [_cartostock_row("A.EXACT3", "POSTE 63kV N0 1 AIRE-SUR-ADOUR")]
            )
        )
    )
    odre = load_odre_substations(
        fetcher=lambda _url: (
            "code_poste;nom_poste;fonction;etat;tension;departement\n"
            "AIREP;AIRE-SUR-ADOUR;Poste;EN EXPLOITATION;63kV;Landes\n"
        ).encode()
    ).substations

    identity = build_french_substation_identities(
        cartostock,
        odre,
        pd.DataFrame({"id": ["OTHER"]}),
    )[0]

    assert identity.match_confidence == "exact"
    assert identity.odre_code == "AIREP"
    assert identity.rte7000_id is None


def test_build_identities_rejects_rte7000_frame_without_id_column():
    with pytest.raises(Rte7000SubstationSchemaError, match="id"):
        build_french_substation_identities((), (), pd.DataFrame({"name": []}))


def _identity(
    cartostock_id: str,
    name: str,
    voltage_kv: float,
    odre_code: str,
) -> FrenchSubstationIdentity:
    return FrenchSubstationIdentity(
        cartostock_id=cartostock_id,
        cartostock_station_name=name,
        normalized_name=normalize_substation_name(name),
        voltage_kv=voltage_kv,
        commune_insee_code="75056",
        commune_name="Paris",
        odre_code=odre_code,
        odre_name=name,
        rte7000_id=odre_code,
        match_confidence="exact",
        match_method="normalized_name_and_voltage",
        candidate_count=1,
        manual_review_required=False,
    )


def _osm(
    *,
    osm_id: int,
    name: str | None,
    reference: str | None,
    voltages: tuple[float, ...],
) -> OsmSubstation:
    return OsmSubstation(
        osm_type="node",
        osm_id=osm_id,
        latitude=48.85,
        longitude=2.35,
        distance_km=5.0,
        name=name,
        normalized_name="" if name is None else normalize_substation_name(name),
        reference=reference,
        operator="RTE",
        operator_is_rte=True,
        voltage_levels_kv=voltages,
        source_url=f"https://www.openstreetmap.org/node/{osm_id}",
    )


def test_link_osm_identity_prefers_exact_odre_reference():
    alpha = _identity("ALPHA7", "ALPHA", 225.0, ".ALPH")
    candidate = _osm(
        osm_id=1,
        name="Un autre libellé",
        reference=".ALPH",
        voltages=(225.0,),
    )

    link = link_osm_substation_identity(candidate, (alpha,))

    assert link.identity == alpha
    assert link.match_confidence == "exact"
    assert link.match_method == "odre_code"
    assert link.manual_review_required is False


def test_link_osm_identity_uses_name_and_voltage_then_unique_name():
    alpha = _identity("ALPHA7", "POSTE ALPHA", 225.0, ".ALPH")
    beta = _identity("BETA3", "POSTE BETA", 63.0, ".BETA")

    voltage_link = link_osm_substation_identity(
        _osm(
            osm_id=1,
            name="Poste Alpha",
            reference=None,
            voltages=(225.0,),
        ),
        (alpha, beta),
    )
    unique_name_link = link_osm_substation_identity(
        _osm(
            osm_id=2,
            name="Poste Beta",
            reference=None,
            voltages=(),
        ),
        (alpha, beta),
    )

    assert voltage_link.identity == alpha
    assert voltage_link.match_confidence == "exact"
    assert voltage_link.match_method == "normalized_name_and_voltage"
    assert unique_name_link.identity == beta
    assert unique_name_link.match_confidence == "high"
    assert unique_name_link.match_method == "unique_normalized_name"


def test_link_osm_identity_ignores_generic_poste_de_name_prefix():
    jalis = _identity("JALISP6", "JALIS", 225.0, "JALIS")

    link = link_osm_substation_identity(
        _osm(
            osm_id=604408491,
            name="Poste de Jalis",
            reference=None,
            voltages=(20.0, 63.0, 225.0),
        ),
        (jalis,),
    )

    assert link.identity == jalis
    assert link.match_confidence == "exact"
    assert link.match_method == "normalized_name_and_voltage"


def test_link_osm_identity_uses_client_preferred_voltage_for_multivoltage_station():
    jalis_63 = _identity("JALISP3", "JALIS", 63.0, "JALIS")
    jalis_225 = _identity("JALISP6", "JALIS", 225.0, "JALIS")

    link = link_osm_substation_identity(
        _osm(
            osm_id=604408491,
            name="Poste de Jalis",
            reference=None,
            voltages=(20.0, 63.0, 225.0),
        ),
        (jalis_63, jalis_225),
        preferred_voltage_kv=225.0,
    )

    assert link.identity == jalis_225
    assert link.match_confidence == "exact"
    assert link.match_method == "normalized_name_voltage_and_client_preference"


def test_link_osm_identity_flags_ambiguous_and_unmatched_candidates():
    alpha_63 = _identity("ALPHA3", "ALPHA", 63.0, ".ALPH")
    alpha_225 = _identity("ALPHA7", "ALPHA", 225.0, ".ALPH")

    ambiguous = link_osm_substation_identity(
        _osm(
            osm_id=1,
            name="Alpha",
            reference=".ALPH",
            voltages=(63.0, 225.0),
        ),
        (alpha_63, alpha_225),
    )
    unmatched = link_osm_substation_identity(
        _osm(
            osm_id=2,
            name="Unknown",
            reference=None,
            voltages=(90.0,),
        ),
        (alpha_63, alpha_225),
    )

    assert ambiguous.identity is None
    assert ambiguous.match_confidence == "unmatched"
    assert ambiguous.match_method == "ambiguous_odre_code"
    assert ambiguous.candidate_count == 2
    assert ambiguous.manual_review_required is True
    assert unmatched.identity is None
    assert unmatched.match_method == "no_deterministic_match"
