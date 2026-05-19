from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum

from thesegrid.models import Direction


class GabaritKind(str, Enum):
    FIRM_ONLY = "firm-only"
    RTE_INJECTION = "RTE injection-gabarit"
    RTE_WITHDRAWAL = "RTE withdrawal-gabarit"
    CUSTOM = "custom envelope"


@dataclass(frozen=True)
class GabaritRule:
    """Explicit V1 business object for an RTE/CRE-inspired BESS operating gabarit."""

    name: str
    gabarit: GabaritKind
    season: str
    time_block: str
    direction: Direction
    months: tuple[int, ...]
    start_hour: int
    end_hour: int
    allowed_fraction: float
    allowed_mw: float | None
    source_label: str
    valid_from: str
    prudence_level: str
    notes: str

    def matches(self, timestamp: datetime, direction: Direction, gabarit: GabaritKind) -> bool:
        return (
            self.gabarit == gabarit
            and self.direction == direction
            and timestamp.month in self.months
            and self.start_hour <= timestamp.hour < self.end_hour
        )


SOURCE_LABEL = "RTE/CRE-inspired V1 storage gabarit"
VALID_FROM = "2026-02-12"
PRUDENCE_LEVEL = "conservative_pre_feasibility"


def rte_cre_inspired_v1_rules() -> tuple[GabaritRule, ...]:
    """Return the explicit V1 French BESS gabarit proxy rules.

    These rules preserve the historical V1 behavior while making the source, validity,
    direction, season, and time-block assumptions inspectable and testable.
    """
    notes = (
        "Buyer-side pre-feasibility proxy aligned with French BESS gabarit vocabulary; "
        "not an official connection offer, PTF, or operator study."
    )
    return (
        GabaritRule(
            name="rte_cre_inspired_v1_injection",
            gabarit=GabaritKind.RTE_INJECTION,
            season="solar_mar_oct",
            time_block="10-18",
            direction="injection",
            months=(3, 4, 5, 6, 7, 8, 9, 10),
            start_hour=10,
            end_hour=18,
            allowed_fraction=0.0,
            allowed_mw=None,
            source_label=SOURCE_LABEL,
            valid_from=VALID_FROM,
            prudence_level=PRUDENCE_LEVEL,
            notes=notes,
        ),
        GabaritRule(
            name="rte_cre_inspired_v1_withdrawal_morning",
            gabarit=GabaritKind.RTE_WITHDRAWAL,
            season="winter_nov_mar",
            time_block="07-13",
            direction="withdrawal",
            months=(11, 12, 1, 2, 3),
            start_hour=7,
            end_hour=13,
            allowed_fraction=0.0,
            allowed_mw=None,
            source_label=SOURCE_LABEL,
            valid_from=VALID_FROM,
            prudence_level=PRUDENCE_LEVEL,
            notes=notes,
        ),
        GabaritRule(
            name="rte_cre_inspired_v1_withdrawal_evening",
            gabarit=GabaritKind.RTE_WITHDRAWAL,
            season="winter_nov_mar",
            time_block="17-21",
            direction="withdrawal",
            months=(11, 12, 1, 2, 3),
            start_hour=17,
            end_hour=21,
            allowed_fraction=0.0,
            allowed_mw=None,
            source_label=SOURCE_LABEL,
            valid_from=VALID_FROM,
            prudence_level=PRUDENCE_LEVEL,
            notes=notes,
        ),
    )


def is_restricted(timestamp: datetime, direction: Direction, gabarit: GabaritKind) -> bool:
    """Return whether the CRE/RTE-inspired V1 gabarit forbids operation."""
    return any(rule.matches(timestamp, direction, gabarit) for rule in rte_cre_inspired_v1_rules())


def gabarit_rule_rows(rules: tuple[GabaritRule, ...]) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            **asdict(rule),
            "gabarit": rule.gabarit.value,
            "months": ",".join(str(month) for month in rule.months),
        }
        for rule in rules
    )


def render_gabarit_rules_markdown(rules: tuple[GabaritRule, ...]) -> str:
    lines = [
        "# RTE/CRE-Inspired BESS Gabarit Rules",
        "",
        "This V1 preset uses French buyer-side connection vocabulary: PTF, "
        "gabarit injection/soutirage, capacite d'accueil, zone contrainte, and "
        "offre optimisee. It remains a public-context pre-feasibility proxy, not an "
        "official operator offer.",
        "",
        "| name | direction | season | time_block | allowed_fraction | source | valid_from | prudence |",
        "| --- | --- | --- | --- | ---: | --- | --- | --- |",
    ]
    for rule in rules:
        lines.append(
            "| "
            f"{rule.name} | {rule.direction} | {rule.season} | {rule.time_block} | "
            f"{rule.allowed_fraction:.3f} | {rule.source_label} | {rule.valid_from} | "
            f"{rule.prudence_level} |"
        )
    return "\n".join(lines)


def write_gabarit_rules_markdown(rules: tuple[GabaritRule, ...], output_path: object) -> None:
    from pathlib import Path

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_gabarit_rules_markdown(rules), encoding="utf-8")


def annual_timestamps(year: int) -> tuple[datetime, ...]:
    start = datetime(year, 1, 1)
    end = datetime(year + 1, 1, 1)
    timestamps: list[datetime] = []
    current = start
    while current < end:
        timestamps.append(current)
        current += timedelta(hours=1)
    return tuple(timestamps)


def restricted_hours(
    timestamps: tuple[datetime, ...],
    direction: Direction,
    gabarit: GabaritKind,
) -> int:
    return sum(1 for timestamp in timestamps if is_restricted(timestamp, direction, gabarit))
