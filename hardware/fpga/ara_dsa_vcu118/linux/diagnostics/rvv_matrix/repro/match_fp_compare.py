"""Match explicit comparison flag failures, not aggregate error counts."""
import re

PREFIX = 'RVV_FP_COMPARE_DETAIL '
TRIGGER = ('op', 'seed', 'vl', 'mask', 'sticky')


def fields(line):
    values = {}
    for token in line[len(PREFIX):].split():
        match = re.fullmatch(r'(\w+)=(\d+)', token)
        if not match or match[1] in values:
            raise ValueError('Malformed or duplicate comparison detail')
        values[match[1]] = int(match[2])
    if not set(TRIGGER + ('expected_flags', 'actual_flags', 'errors')) <= values.keys():
        raise ValueError('Incomplete comparison detail')
    return values


def compare(original, reduced, measured_detail):
    """Caller must verify ELF lineage and board identity independently."""
    if any(r.get('status') != 'failed' or r.get('exit_code') != 1
           for r in (original, reduced)):
        return dict(confirmed=False, reason='Not two completed numerical failures')
    try:
        if not measured_detail.startswith(PREFIX):
            raise ValueError('Wrong detail type')
        wanted = fields(measured_detail)
        originals = [fields(line) for line in original.get('output', '').splitlines()
                     if line.startswith(PREFIX)]
        small = [fields(line) for line in reduced.get('output', '').splitlines()
                 if line.startswith(PREFIX)]
    except ValueError as exc:
        return dict(confirmed=False, reason=str(exc))
    if wanted not in originals:
        return dict(confirmed=False, reason='Measured original failure absent')
    # Presence of vstart distinguishes restart instrumentation from older tests.
    keys = TRIGGER + (('vstart',) if 'vstart' in wanted else ())
    matching = [d for d in small if ('vstart' in d) == ('vstart' in wanted)
                and all(d[k] == wanted[k] for k in keys)]
    if len(matching) != 1:
        return dict(confirmed=False, reason='Missing or ambiguous matching stimulus')
    actual = matching[0]
    if wanted['expected_flags'] == wanted['actual_flags']:
        return dict(confirmed=False, reason='No explicit original flag mismatch')
    if any(actual[k] != wanted[k] for k in ('expected_flags', 'actual_flags')):
        return dict(confirmed=False, reason='Different flag symptom')
    if any(d['errors'] < 1 or not 0 <= d['expected_flags'] <= 31
           or not 0 <= d['actual_flags'] <= 31 for d in (wanted, actual)):
        return dict(confirmed=False, reason='Invalid flag failure detail')
    return dict(confirmed=True, evidence='Matching architectural fflags mismatch',
                measured_trigger={k:wanted[k] for k in keys},
                expected_flags=wanted['expected_flags'], actual_flags=wanted['actual_flags'],
                vector_data_equivalence_proven=False, internal_rtl_root_cause_proven=False)
