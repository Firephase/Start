from enum import Enum, auto


class OrbitType(str, Enum):
    CIRCULAR_STABLE = "circular_stable"
    CIRCULAR_UNSTABLE = "circular_unstable"
    BOUND_ECCENTRIC = "bound_eccentric"
    PLUNGING = "plunging"


class AppState(str, Enum):
    IDLE = "idle"
    CONFIGURING = "configuring"
    RUNNING_GEODESIC = "running_geodesic"
    RUNNING_INSPIRAL = "running_inspiral"
    VIEWING_RESULTS = "viewing_results"
    ERROR = "error"


class FluxModelId(str, Enum):
    BASELINE_PN = "baseline_pn"
    EXTENDED_TEST_MASS = "extended_test_mass"
