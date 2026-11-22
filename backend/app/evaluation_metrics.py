"""Pure post-hoc metrics. No ranking code or operational writes."""
from datetime import datetime

VERSION = "evaluation-metrics-v1"
CLASSES = ["Baja", "Media", "Alta", "Crítica"]


def metric(value, unit="ratio", reason=None):
    return {"value": value, "unit": unit, "status": "No calculable" if value is None else "Calculable", "reason": reason}


def ratio(numerator, denominator, reason):
    return metric(numerator / denominator if denominator else None, reason=None if denominator else reason)


def classification(predicted, references):
    n = len(predicted)
    missing = sum(references.get(key, {}).get("priority") is None for key in predicted)
    if not n or missing:
        return {"accuracy": metric(None, reason="Cohorte vacía o referencias de prioridad incompletas"),
                "matrix": None, "classes": CLASSES, "labeled": n - missing, "total": n,
                "per_class": {}, "macro": {k: metric(None, reason="Referencias incompletas") for k in ("precision", "recall", "f1")}}
    matrix = [[0] * 4 for _ in CLASSES]
    for key, prediction in predicted.items():
        matrix[CLASSES.index(references[key]["priority"])][CLASSES.index(prediction)] += 1
    per_class = {}
    for index, label in enumerate(CLASSES):
        tp = matrix[index][index]
        fp = sum(row[index] for row in matrix) - tp
        fn = sum(matrix[index]) - tp
        per_class[label] = {
            "support": sum(matrix[index]),
            "precision": ratio(tp, tp + fp, "No hay predicciones de esta clase"),
            "recall": ratio(tp, tp + fn, "No hay referencias de esta clase"),
            "f1": ratio(2 * tp, 2 * tp + fp + fn, "Clase ausente en referencias y predicciones")}
    macro = {}
    for key in ("precision", "recall", "f1"):
        values = [per_class[label][key]["value"] for label in CLASSES]
        macro[key] = metric(sum(values) / 4 if all(v is not None for v in values) else None,
                            reason=None if all(v is not None for v in values) else "Alguna clase tiene denominador cero; no se sustituye por cero")
    return {"accuracy": ratio(sum(matrix[i][i] for i in range(4)), n, "Cohorte vacía"),
            "matrix": matrix, "classes": CLASSES, "labeled": n, "total": n,
            "per_class": per_class, "macro": macro}


def false_positive_rate(predicted, references):
    if not predicted or any(references.get(k, {}).get("malicious") is None for k in predicted):
        return {"rate": metric(None, reason="Se requieren etiquetas binarias malicious para toda la cohorte"),
                "definition": "Positivo predicho: Alta o Crítica; positivo real: malicious=true"}
    negatives = [k for k in predicted if references[k]["malicious"] is False]
    fp = sum(predicted[k] in ("Alta", "Crítica") for k in negatives)
    return {"rate": ratio(fp, len(negatives), "No hay negativos de referencia"), "false_positives": fp,
            "true_negatives": len(negatives) - fp,
            "definition": "Positivo predicho: Alta o Crítica; positivo real: malicious=true"}


def attention(order, references, budget, event_counts):
    selected = order[:budget]
    missing = any(references.get(k, {}).get("priority") is None for k in order)
    critical = [k for k in order if references.get(k, {}).get("priority") == "Crítica"]
    rate = metric(None, reason="Referencias de prioridad incompletas") if missing else ratio(
        sum(k in selected for k in critical), len(critical), "No hay incidentes críticos de referencia")
    return {"critical_coverage": rate, "selected": metric(len(selected), "incidentes"),
            "backlog": metric(len(order) - len(selected), "incidentes"),
            "selected_events": metric(sum(event_counts[k] for k in selected), "eventos"),
            "budget_used": metric(len(selected), "unidades de atención simulada"),
            "unit_definition": "Una selección de incidente consume una unidad, sin duración ni operador simulado"}


def timing(keys, references, data_kind):
    result = {}
    for name, start, end in (("mttd", "occurred_at", "detected_at"), ("mttr", "detected_at", "response_completed_at")):
        values, invalid = [], 0
        for key in keys:
            ref = references.get(key, {})
            a, b = ref.get(start), ref.get(end)
            chronology_invalid = any(ref.get(x) and ref.get(y) and datetime.fromisoformat(ref[y]) < datetime.fromisoformat(ref[x])
                for x, y in (("occurred_at", "detected_at"), ("detected_at", "response_completed_at")))
            if chronology_invalid:
                invalid += 1
                continue
            if a and b and ref.get("timing_evidence"):
                delta = (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()
                if delta >= 0:
                    values.append(delta)
                else:
                    invalid += 1
        complete = bool(keys) and len(values) == len(keys) and data_kind != "synthetic"
        result[name] = metric(sum(values) / len(values) if complete else None, "segundos",
            None if complete else "Se requiere cohorte completa, tiempos no negativos, evidencia temporal y datos no sintéticos")
        result[name].update({"valid_pairs": len(values), "invalid_pairs": invalid, "total": len(keys),
                             "attribution": "Descripción del dataset; no efecto causal de ordenar la cola"})
    return result
