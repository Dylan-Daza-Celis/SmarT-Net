"""Versioned engineering interpretation, not measured asset value or attack probability."""
ALERT_CRITICALITY_VERSION = 'suricata-alert-criticality-v1'
LAB_SIGNATURE = 'SMARTIR WSL2 LAB ICMP TEST'
LAB_EVENT_TYPE = 'prueba_icmp'


def alert_criticality(severity):
    # Preserve the v1 numeric normalization: changing labels must not recalibrate weighted-v2.
    value = 50 if severity is None else 100 if severity <= 1 else 70 if severity == 2 else 40 if severity == 3 else 10
    standard = severity is not None and 1 <= severity <= 255
    level = ('Crítica' if value >= 75 else 'Alta' if value >= 50 else 'Media' if value >= 25 else 'Baja') if standard else None
    return {'policy_version':ALERT_CRITICALITY_VERSION, 'value':value, 'level':level,
            'observed':False, 'basis':'engineering_mapping_of_rule_priority' if standard else
                'unknown_neutral_default' if severity is None else 'legacy_nonstandard_zero',
            'source_field':'alert.severity', 'source_value':severity,
            'source_scale':'ordinal_rule_priority_1_highest', 'source_provided':severity is not None,
            'standard_priority':standard, 'defaulted':severity is None}


def classification(category, signature, protocol, category_map):
    normalized = (category or '').strip().casefold()
    if normalized in category_map:
        return {'type':category_map[normalized], 'matched':True, 'policy':'category_then_declared_lab_v2',
                'basis':'exact_category_v1', 'taxonomy':'six_incident_types', 'reason':None}
    # An exact declared test is an auxiliary kind, never a fabricated DoS/scan/malware label.
    if not normalized and signature == LAB_SIGNATURE and (protocol or '').upper() in ('ICMP','IPV6-ICMP','ICMPV6'):
        return {'type':LAB_EVENT_TYPE, 'matched':True, 'policy':'category_then_declared_lab_v2',
                'basis':'exact_lab_signature_and_icmp_empty_category', 'taxonomy':'auxiliary_non_attack',
                'reason':'declared_connectivity_test_not_verified_attack'}
    return {'type':'desconocido', 'matched':False, 'policy':'category_then_declared_lab_v2',
            'basis':None, 'taxonomy':'unclassified',
            'reason':'missing_or_empty_category_no_explicit_match' if not normalized else 'unmapped_category'}
