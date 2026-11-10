"""Physics of a simulated 32 AWG annealed-copper wire: elastic, yield, hardening and creep."""

# frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC
from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field

from sadi.logging_setup import get_logger

_log = get_logger(__name__)

__all__ = ["CopperSpec", "OFFSET_STRAIN"]

#: Standard 0.2 % offset used for the ground-truth yield.
OFFSET_STRAIN = 0.002
_CAP = 0.995  # stress is capped below the ultimate so plastic strain stays finite


class CopperSpec(BaseModel):
    """Material constants; defaults are 32 AWG (0.2019 mm) annealed copper wire."""

    model_config = ConfigDict(frozen=True)

    diameter_m: float = Field(default=2.019e-4, gt=0)
    e_pa: float = Field(default=110e9, gt=0, description="Young's modulus")
    onset_pa: float = Field(default=60e6, gt=0, description="stress where plasticity starts")
    ultimate_pa: float = Field(default=132e6, gt=0, description="Voce saturation stress")
    hardening_strain: float = Field(default=0.05, gt=0, description="Voce strain constant")
    creep_a: float = Field(default=1e-5, ge=0, description="creep amplitude at onset stress")
    creep_exp: float = Field(default=4.0, gt=0, description="creep stress exponent")
    creep_tau_s: float = Field(default=5.0, gt=0, description="creep log time constant")

    @property
    def area_m2(self) -> float:
        """Cross-section area pi d^2 / 4."""
        return math.pi * self.diameter_m**2 / 4.0

    def force_n(self, stress_pa: float) -> float:
        """Axial force that gives `stress_pa`."""
        return stress_pa * self.area_m2

    def cap(self, stress_pa: float) -> float:
        """Stress limited below the ultimate (the wire is never loaded to break)."""
        return min(stress_pa, _CAP * self.ultimate_pa)

    def plastic_strain(self, max_stress_pa: float) -> float:
        """Permanent strain after the running maximum stress (Voce flow rule, inverted)."""
        s = self.cap(max_stress_pa)
        if s <= self.onset_pa:
            return 0.0
        frac = (s - self.onset_pa) / (self.ultimate_pa - self.onset_pa)
        return -self.hardening_strain * math.log(1.0 - frac)

    def creep_strain(self, stress_pa: float, t_s: float) -> float:
        """Creep strain after `t_s` seconds held at `stress_pa` (stress only, no carry-over)."""
        if t_s <= 0 or stress_pa <= 0:
            return 0.0
        amp = self.creep_a * (stress_pa / self.onset_pa) ** self.creep_exp
        return float(amp * math.log1p(t_s / self.creep_tau_s))

    def creep_rate(self, stress_pa: float, t_s: float) -> float:
        """Creep strain rate (1/s) at `t_s` into a hold."""
        if stress_pa <= 0:
            return 0.0
        amp = self.creep_a * (stress_pa / self.onset_pa) ** self.creep_exp
        return float(amp / (self.creep_tau_s + max(t_s, 0.0)))

    def strain(self, stress_pa: float, max_stress_pa: float, t_s: float = 0.0) -> float:
        """Total strain: elastic + permanent (from the running max) + creep during the hold."""
        s = self.cap(stress_pa)
        return s / self.e_pa + self.plastic_strain(max_stress_pa) + self.creep_strain(s, t_s)

    def offset_yield_pa(self, offset: float = OFFSET_STRAIN) -> float:
        """Ground-truth 0.2 % offset yield: the stress at which permanent strain equals `offset`."""
        frac = 1.0 - math.exp(-offset / self.hardening_strain)
        return self.onset_pa + (self.ultimate_pa - self.onset_pa) * frac
