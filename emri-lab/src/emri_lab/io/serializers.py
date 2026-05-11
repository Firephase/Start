"""Serialization helpers for domain objects."""

import numpy as np

from emri_lab.domain.models import InspiralResult


def inspiral_to_dict(result: InspiralResult) -> dict:
    """Serialize an InspiralResult to a JSON-compatible dictionary.

    All NumPy arrays are converted to plain Python lists so the result
    can be serialized with ``json.dump`` or returned via a REST API.

    Parameters
    ----------
    result : InspiralResult
        Inspiral trajectory result to serialize.

    Returns
    -------
    dict
        Dictionary with keys: t, p, e, E, L, r_circ, plunged, message.
    """
    return {
        "t": result.t.tolist(),
        "p": result.p_arr.tolist(),
        "e": result.e_arr.tolist(),
        "E": result.E_arr.tolist(),
        "L": result.L_arr.tolist(),
        "r_circ": result.r_circ.tolist(),
        "plunged": result.plunged,
        "message": result.message,
    }
