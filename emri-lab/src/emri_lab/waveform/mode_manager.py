from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from emri_lab.domain.models import InspiralResult


@dataclass(frozen=True)
class HarmonicMode:
    n: int  # radial harmonic index
    m: int  # azimuthal harmonic index
    l: int | None = None  # optional spherical harmonic l

    def __str__(self):
        return f"({self.n},{self.m})"


class ModeSelectionPolicy:
    """Manages which harmonic modes to include in waveform summation."""

    POLICIES = ["dominant_only", "low_order_eccentric", "fixed_grid", "user_custom"]

    def select_modes(self, evolution, policy_name: str, **kwargs) -> list[HarmonicMode]:
        """Select modes based on policy and inspiral evolution."""
        if policy_name == "dominant_only":
            return [HarmonicMode(n=0, m=2, l=2)]

        elif policy_name == "low_order_eccentric":
            # Include n=-2,-1,0,1,2 with m=2 for eccentric orbits
            modes = []
            for n in range(-2, 3):
                modes.append(HarmonicMode(n=n, m=2, l=2))
                if n != 0:
                    modes.append(HarmonicMode(n=n, m=-2, l=2))
            return modes

        elif policy_name == "fixed_grid":
            n_max = kwargs.get("n_max", 3)
            modes = []
            for n in range(-n_max, n_max + 1):
                for m in [2, -2]:
                    modes.append(HarmonicMode(n=n, m=m, l=2))
            return modes

        elif policy_name == "user_custom":
            mode_list = kwargs.get("modes", [(0, 2)])
            return [HarmonicMode(n=n, m=m, l=2) for n, m in mode_list]

        else:
            raise ValueError(f"Unknown policy: {policy_name}. Choose from {self.POLICIES}")
