"""Compare board symptoms without promoting matching error counts to data proof."""
import re


def fields(line):
    return {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', line)}


def classified_trials(result):
    pending = None
    for line in result.get('output', '').splitlines():
        if line.startswith('RVV_FP_MOVE_DETAIL '):
            pending = fields(line)
        elif line.startswith('RVV_FP_MOVE_CLASSIFY ') and pending is not None:
            yield pending, fields(line)
            pending = None


def compare(original, prefix, reduced, measured_detail):
    """ELF/board identity must separately be verified by the report collector."""
    if any(r.get('status') != 'failed' or r.get('exit_code') != 1
           for r in (original, prefix, reduced)):
        return dict(confirmed=False, reason='Not three completed numerical failures')
    wanted = fields(measured_detail)
    if not any(line.startswith('RVV_FP_MOVE_DETAIL ') and fields(line)==wanted
               for line in original.get('output', '').splitlines()):
        return dict(confirmed=False, reason='Original measured detail absent')
    a = [detail for trigger, detail in classified_trials(prefix) if trigger==wanted]
    b = [detail for trigger, detail in classified_trials(reduced) if trigger==wanted]
    required = {'returned_vstart', 'first_bad_element', 'expected_bits', 'actual_bits',
                'scalar_expected', 'scalar_actual', 'guard_before', 'guard_after'}
    if len(a)!=1 or len(b)!=1 or not required <= a[0].keys() or not required <= b[0].keys():
        return dict(confirmed=False, reason='Missing or ambiguous classified trial')
    if a[0] != b[0]:
        return dict(confirmed=False, reason='Different classified architectural symptom',
                    prefix=a[0], reduced=b[0])
    if a[0]['expected_bits'] == a[0]['actual_bits']:
        return dict(confirmed=False, reason='No explicit vector-data mismatch; separate CSR/scalar analysis needed')
    if a[0]['guard_before'] != 0x5b or a[0]['guard_after'] != 0x5b:
        return dict(confirmed=False, reason='Buffer guard corruption requires separate attribution')
    return dict(confirmed=True, evidence='Matching vector-data symptom after original prefix and single trial',
                measured_trigger=wanted, classified_symptom=a[0], internal_rtl_root_cause_proven=False)
