from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class BessLiteAssumptions:
    """Minimal BESS sizing assumptions for pre-feasibility evidence.

    This is not an operational dispatch, degradation, revenue-stacking, or bankable
    valuation model.
    """

    power_mw: float
    duration_hours: float
    round_trip_efficiency: float = 0.9
    soc_min_fraction: float = 0.0
    soc_max_fraction: float = 1.0

    def __post_init__(self) -> None:
        if self.power_mw <= 0:
            raise ValueError("power_mw must be positive")
        if self.duration_hours <= 0:
            raise ValueError("duration_hours must be positive")
        if not 0.0 < self.round_trip_efficiency <= 1.0:
            raise ValueError("round_trip_efficiency must be in (0, 1]")
        if not 0.0 <= self.soc_min_fraction <= 1.0:
            raise ValueError("soc_min_fraction must be between 0 and 1")
        if not 0.0 <= self.soc_max_fraction <= 1.0:
            raise ValueError("soc_max_fraction must be between 0 and 1")
        if self.soc_max_fraction <= self.soc_min_fraction:
            raise ValueError("soc_max_fraction must be greater than soc_min_fraction")

    @property
    def nominal_energy_mwh(self) -> float:
        return round(self.power_mw * self.duration_hours, 6)

    @property
    def usable_soc_window(self) -> float:
        return round(self.soc_max_fraction - self.soc_min_fraction, 6)

    @property
    def usable_energy_mwh(self) -> float:
        return round(self.nominal_energy_mwh * self.usable_soc_window, 6)

    @property
    def efficiency_adjusted_usable_energy_mwh(self) -> float:
        return round(self.usable_energy_mwh * self.round_trip_efficiency, 6)

    def to_dict(self) -> dict[str, float]:
        return {
            **asdict(self),
            "nominal_energy_mwh": self.nominal_energy_mwh,
            "usable_soc_window": self.usable_soc_window,
            "usable_energy_mwh": self.usable_energy_mwh,
            "efficiency_adjusted_usable_energy_mwh": self.efficiency_adjusted_usable_energy_mwh,
        }
