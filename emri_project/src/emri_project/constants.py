"""Physical constants and unit conventions for the EMRI project.

All computations use geometrized units: G = c = M = 1.
Lengths in units of M, time in units of M/c, energy per unit mass.
"""

# Gravitational radius r_s = 2GM/c^2 = 2 in our units
R_SCHWARZSCHILD: float = 2.0

# ISCO radius for Schwarzschild: r_ISCO = 6M
R_ISCO: float = 6.0

# Photon sphere radius
R_PHOTON: float = 3.0

# Innermost bound orbit
R_IBR: float = 4.0

# Default ODE tolerances
RTOL: float = 1e-12
ATOL: float = 1e-12
