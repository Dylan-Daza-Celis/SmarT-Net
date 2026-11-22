"""Engineering baseline, not scientifically validated weights."""
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP

VERSION = "weighted-v2"
DEFAULT_PARAMETERS = {
    "algorithm_version": VERSION,
    "weights": {"severity": 0.35, "asset_criticality": 0.25, "recurrence": 0.15,
                "attack_type": 0.15, "context": 0.10},
    "attack_values": {"acceso_no_autorizado": 75, "malware": 90, "dos": 80,
                      "escaneo": 45, "uso_indebido": 55, "exfiltracion": 100},
    "unknown_attack": 40, "unknown_context": 50, "recurrence_per_event": 20,
    "rounding": "half_up", "context_policy": "unknown_neutral_prior_not_observed",
}


def parameters():
    return deepcopy(DEFAULT_PARAMETERS)


def priority(score):
    return "Crítica" if score >= 75 else "Alta" if score >= 50 else "Media" if score >= 25 else "Baja"


def evaluate(events, params):
    if params["algorithm_version"] not in ("weighted-v1", "weighted-v2"):
        raise ValueError("Unsupported frozen risk algorithm")
    if not events:
        raise ValueError("Cannot evaluate an empty incident")
    values = {
        "severity": max(e.severity for e in events),
        "asset_criticality": max(e.asset_criticality for e in events),
        "recurrence": min(100, len(events) * params["recurrence_per_event"]),
        "attack_type": params["attack_values"].get(events[0].event_type, params["unknown_attack"]),
        "context": params["unknown_context"],
    }
    contributions = {k: Decimal(str(v)) * Decimal(str(params["weights"][k])) for k, v in values.items()}
    total = sum(contributions.values())
    score = max(0, min(100, int(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))))
    result = {"algorithm_version": params["algorithm_version"], "parameters": deepcopy(params), "event_count": len(events),
            "factors": {k: {"value": v, "weight": params["weights"][k],
                             "contribution": float(contributions[k]),
                             "observed": k != "context" and (k != "attack_type" or events[0].event_type in params["attack_values"])} for k, v in values.items()},
            "context": {"known": False, "policy": params["context_policy"]},
            "unrounded_score": float(total), "score": score, "priority": priority(score)}
    if params["algorithm_version"] == "weighted-v2":
        # A supplied value is not necessarily measured. Legacy rows remain untracked.
        contributors = [e for e in events if e.asset_criticality == values["asset_criticality"]]
        flags = [getattr(e, "asset_criticality_observed", None) for e in contributors]
        factor = result["factors"]["asset_criticality"]
        factor["observed"] = all(flag is True for flag in flags)
        factor["basis"] = "supplied" if factor["observed"] else "legacy_untracked" if any(f is None for f in flags) else "policy_default_50"
        factor["policy"] = "max_asset_input_or_default_50_not_network_measurement"
    return result
