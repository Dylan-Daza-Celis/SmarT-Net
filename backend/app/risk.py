"""Motor de priorización ponderada del prototipo (pesos experimentales)."""

from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP

VERSION = "weighted-v2"

DEFAULT_PARAMETERS = {
    "algorithm_version": VERSION,
    "weights": {
        "severity": 0.35,
        "asset_criticality": 0.25,
        "recurrence": 0.15,
        "attack_type": 0.15,
        "context": 0.10,
    },
    "attack_values": {
        "acceso_no_autorizado": 75,
        "malware": 90,
        "dos": 80,
        "escaneo": 45,
        "uso_indebido": 55,
        "exfiltracion": 100,
    },
    "unknown_attack": 40,
    "unknown_context": 50,
    "recurrence_per_event": 20,
    "rounding": "half_up",
    "context_policy": "unknown_neutral_prior_not_observed",
}


def parameters():
    return deepcopy(DEFAULT_PARAMETERS)


def priority(score):
    if score >= 75:
        return "Crítica"
    if score >= 50:
        return "Alta"
    if score >= 25:
        return "Media"
    return "Baja"


def evaluate(events, params):
    if params["algorithm_version"] not in ("weighted-v1", "weighted-v2"):
        raise ValueError("Unsupported frozen risk algorithm")
    if not events:
        raise ValueError("Cannot evaluate an empty incident")

    values = {
        "severity": max(e.severity for e in events),
        "asset_criticality": max(e.asset_criticality for e in events),
        "recurrence": min(100, len(events) * params["recurrence_per_event"]),
        "attack_type": params["attack_values"].get(
            events[0].event_type, params["unknown_attack"]
        ),
        "context": params["unknown_context"],
    }
    contributions = {
        name: Decimal(str(value)) * Decimal(str(params["weights"][name]))
        for name, value in values.items()
    }
    total = sum(contributions.values())
    score = max(
        0,
        min(100, int(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))),
    )

    factors = {
        name: {
            "value": value,
            "weight": params["weights"][name],
            "contribution": float(contributions[name]),
            "observed": name != "context"
            and (name != "attack_type" or events[0].event_type in params["attack_values"]),
        }
        for name, value in values.items()
    }
    result = {
        "algorithm_version": params["algorithm_version"],
        "parameters": deepcopy(params),
        "event_count": len(events),
        "factors": factors,
        "context": {"known": False, "policy": params["context_policy"]},
        "unrounded_score": float(total),
        "score": score,
        "priority": priority(score),
    }

    if params["algorithm_version"] == "weighted-v2":
        # La criticidad predeterminada no equivale a una medición del activo.
        contributors = [
            e for e in events if e.asset_criticality == values["asset_criticality"]
        ]
        flags = [getattr(e, "asset_criticality_observed", None) for e in contributors]
        factor = result["factors"]["asset_criticality"]
        factor["observed"] = all(flag is True for flag in flags)
        factor["basis"] = (
            "supplied"
            if factor["observed"]
            else "legacy_untracked"
            if any(flag is None for flag in flags)
            else "policy_default_50"
        )
        factor["policy"] = "max_asset_input_or_default_50_not_network_measurement"

    return result
