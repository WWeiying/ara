"""Offline intersection gates for the next report; not a native EL parser.

Inputs must come from each sealed family's native parser, not XML row ordering.
Whole arrays are opaque protected objects; their indices must never be flattened.
This module neither prepares a report nor launches EDA.
"""
import re

STAGES = ('raw', 'applied', 'reset', 'reloaded', 'final')
FAMILIES = {'closed771', 'branch720', 'mfpu272', 'rvh0_exception60'}


def need(value, message):
    if not value:
        raise ValueError(message)


def identity(row):
    need(row['metric'] in ('Branch', 'Toggle', 'FSM'), 'Unknown metric')
    need(row['scope'].startswith('ara_tb.') and not any(
        c.isspace() for c in row['scope']), 'Noncanonical scope')
    need(row['checksum'] and row['object'], 'Missing native identity')
    need(row['role'] in ('target', 'protected'), 'Unknown role')
    need(row['family'] in FAMILIES, 'Unqualified family')
    need(type(row['array']) is bool, 'Explicit array identity required')
    need(type(row['low']) is int and type(row['high']) is int and
         0 <= row['low'] <= row['high'], 'Invalid exact bit interval')
    need(row['direction'] in ('0to1', '1to0', 'selector'), 'Unknown direction')
    need((row['metric'] == 'Toggle') == (row['direction'] != 'selector'),
         'Metric/direction mismatch')
    need(not (row['array'] and row['role'] == 'target'), 'Array target needs separate native proof')
    # Native indexed names remain literal identities, including one-bit ports.
    return (row['metric'], row['scope'], row['checksum'], row['object'],
            row['direction'], row['array'])


def overlap(a, b):
    return max(a['low'], b['low']) <= min(a['high'], b['high'])


def intersection_review(rows, approvals):
    """Return explicit ownership decisions; all approvals must be used exactly.

    Approval tuples contain complete identity, interval and BOTH family names.
    They must be independently source/native reviewed, not auto-generated from
    a detected overlap. No approval may discard an opaque array protection.
    """
    grouped = {}
    for row in rows:
        grouped.setdefault(identity(row), []).append(row)
    need(len(approvals) == len(set(approvals)), 'Duplicate approval')
    used = set()
    decisions = []
    for key, group in grouped.items():
        for n, a in enumerate(group):
            for b in group[n + 1:]:
                if not overlap(a, b):
                    continue
                need(a['family'] != b['family'], 'Duplicate/overlapping family inventory')
                if a['role'] == b['role'] == 'protected':
                    continue
                low, high = max(a['low'], b['low']), min(a['high'], b['high'])
                signature = key + (low, high) + tuple(sorted((a['family'], b['family'])))
                need(not key[-1] and signature in approvals,
                     'Unreviewed target/target or target/protection intersection')
                used.add(signature)
                decisions.append(dict(identity=list(key), low=low, high=high,
                                      families=sorted((a['family'], b['family'])),
                                      roles=sorted((a['role'], b['role']))))
    need(used == set(approvals), 'Unused/overbroad approval')
    return decisions


def population_gate(final, previous, design, manifest_sha):
    need(re.fullmatch(r'[0-9a-f]{64}', manifest_sha or '') is not None,
         'Explicit final manifest SHA required')
    need(final['coverage_admitted'] is True and final['design'] == design,
         'Formal same-design population required')
    tests = final['tests']
    need(len(tests) in (774, 775) and len(tests) == len(set(tests)) and
         tests[:len(previous)] == previous and len(previous) == 773,
         'Exact773 prefix and explicitly chosen774/775 required')
    need(final['metric_instances'] == 6162, 'Complete raw shape required')
    return dict(population=len(tests), manifest_sha256=manifest_sha,
                percentage_verified=False, official_denominator_verified=False,
                launch_authorized=False)


def stage_gate(stage, rows, flags):
    need(stage in STAGES, 'Unknown stage')
    expected = {}
    for row in rows:
        key = identity(row) + (row['low'], row['high'])
        active = row['role'] == 'target' and stage in ('applied', 'reloaded')
        need(key not in expected or expected[key] == int(active),
             'Unresolved ownership must be reviewed before stage audit')
        expected[key] = int(active)
    need(set(flags) == set(expected), 'Missing/extra protection or target')
    need(all(type(v) is int and v in (0, 1) and v == expected[k]
             for k, v in flags.items()), 'Exact per-object boolean flags required')


def receipt_gate(mfpu, rvh0):
    need(mfpu['status'] == 'MFPU272_EXACT_FIVE_PHASE_LOCAL_QUALIFIED_NOT_APPLIED'
         and mfpu['targets'] == 272 and mfpu['directions'] == 34816
         and mfpu['protected_child_scopes'] == 744 and mfpu['terminal_returncode'] == 0
         and mfpu['EL_semantic_roundtrip'] is True and mfpu['population_application'] is False
         and mfpu['initial_X_waiver'] is False
         and mfpu['stages'] == ['before', 'applied', 'reset', 'reloaded', 'final'],
         'Complete MFPU qualification required')
    need(rvh0['status'] == 'RVH0_EXCEPTION60_POST_WRAPPER_OFFLINE_CLOSURE_PASS_NOT_POPULATION_APPLIED'
         and rvh0['targets'] == 60 and rvh0['protected'] == 2794
         and rvh0['typed_EL_semantic_records'] == 79
         and rvh0['original_inspect_all_checks_replayed'] is True
         and rvh0['empty_before_reset_final_cleanup'] is True
         and rvh0['global_EL_protects_children'] is True
         and rvh0['population_applied'] is False, 'Complete RVH0 offline closure required')
    # These status gates do NOT replace exact receipt SHA and complete pin checks.
    return {'families': sorted(FAMILIES), 'EDA_launched': False}
