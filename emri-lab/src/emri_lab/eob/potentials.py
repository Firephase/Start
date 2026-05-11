"""EOB metric potentials: Schwarzschild (test-mass) and 3PN resummed variants."""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class EOBPotentialService(ABC):
    """Abstract EOB potential service."""

    @abstractmethod
    def A(self, u: float, params: dict) -> float:
        """EOB A potential evaluated at u = 1/r."""

    @abstractmethod
    def dA_du(self, u: float, params: dict) -> float:
        """dA/du."""

    @abstractmethod
    def B(self, u: float, params: dict) -> float:
        """EOB B potential (= 1/A in Schwarzschild convention)."""

    @abstractmethod
    def Q(self, u: float, pr: float, params: dict) -> float:
        """Higher-order momentum term Q(u, p_r)."""

    def D(self, u: float, params: dict) -> float:
        """D = A * B (Bini-Damour convention; = 1 in Schwarzschild limit)."""
        return self.A(u, params) * self.B(u, params)

    @abstractmethod
    def metadata(self) -> dict:
        """Return a dict describing this potential model."""


class SchwarzschildPotentials(EOBPotentialService):
    """Test-mass limit: exact Schwarzschild potentials.

    A(u) = 1 - 2u,  B(u) = 1/A(u),  D(u) = A*B = 1,  Q = 0.
    """

    def A(self, u: float, params: dict) -> float:  # noqa: D102
        return max(1.0 - 2.0 * u, 1e-10)

    def dA_du(self, u: float, params: dict) -> float:  # noqa: D102
        return -2.0

    def B(self, u: float, params: dict) -> float:  # noqa: D102
        A = self.A(u, params)
        return 1.0 / max(A, 1e-10)

    def Q(self, u: float, pr: float, params: dict) -> float:  # noqa: D102
        return 0.0

    def metadata(self) -> dict:  # noqa: D102
        return {"name": "schwarzschild", "order": "exact", "nu": 0}


class ResummedPotentials(EOBPotentialService):
    """3PN EOB potentials with Padé-inspired resummation (ν-dependent).

    Taylor 3PN form:
        A_3PN(u) = 1 - 2u + 2ν u³
        B_3PN(u) ≈ 1 - 6ν u²  (leading PN correction)

    For ν → 0 these reduce exactly to the Schwarzschild potentials.
    Q includes the leading 3PN p_r^4 term.
    """

    def A(self, u: float, params: dict) -> float:  # noqa: D102
        nu = params.get("nu", 0.0)
        A_raw = 1.0 - 2.0 * u + 2.0 * nu * u**3
        return max(A_raw, 1e-10)

    def dA_du(self, u: float, params: dict) -> float:  # noqa: D102
        nu = params.get("nu", 0.0)
        return -2.0 + 6.0 * nu * u**2

    def B(self, u: float, params: dict) -> float:  # noqa: D102
        nu = params.get("nu", 0.0)
        # Leading PN correction to B: B ≈ 1 - 6ν u²
        B_raw = 1.0 - 6.0 * nu * u**2
        return max(B_raw, 1e-10)

    def Q(self, u: float, pr: float, params: dict) -> float:  # noqa: D102
        nu = params.get("nu", 0.0)
        # Q = 2(4 - 3ν)ν u² p_r^4  (schematic 3PN term)
        return 2.0 * (4.0 - 3.0 * nu) * nu * u**2 * pr**4

    def metadata(self) -> dict:  # noqa: D102
        return {"name": "resummed_3pn", "order": "3PN", "approximant": "Pade"}


def get_potential_service(conservative_model: str) -> EOBPotentialService:
    """Factory: return the appropriate potential service.

    Parameters
    ----------
    conservative_model : str
        ``"schwarzschild"`` for the exact test-mass limit,
        ``"3pn"`` for the ν-dependent 3PN resummed potentials.

    Returns
    -------
    EOBPotentialService
        Concrete potential service instance.

    Raises
    ------
    ValueError
        For unknown model identifiers.
    """
    if conservative_model == "schwarzschild":
        return SchwarzschildPotentials()
    if conservative_model == "3pn":
        return ResummedPotentials()
    raise ValueError(f"Unknown conservative model: {conservative_model!r}")
