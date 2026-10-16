"""Require unchanged reviewed physical violations after the two reset FF addition."""
import argparse
import hashlib
import json
from pathlib import Path
from check_rebuild_reports import summary, clock_violations


def check(current, baseline):
    now, old = summary(current), summary(baseline)
    if now[0] < 0 or now[1] != 0 or now[2] != 0:
        raise ValueError('Current synthesis setup failed')
    if old[0] < 0 or old[1] != 0 or old[2] != 0:
        raise ValueError('Baseline setup not approved')
    if clock_violations(current) != clock_violations(baseline):
        raise ValueError('New or changed physical violation group requires review')
    for start in (4, 8):
        if now[start:start+3] != old[start:start+3]:
            raise ValueError('Physical violation totals changed')
    return {'passed': True, 'scope': 'Synthesis estimates only; routed gates remain strict',
            'setup_wns_ns': str(now[0]), 'hold_whs_ns': str(now[4]),
            'pulse_width_wpws_ns': str(now[8]),
            'current_sha256': hashlib.sha256(current.encode()).hexdigest(),
            'baseline_sha256': hashlib.sha256(baseline.encode()).hexdigest()}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ('current', 'baseline', 'output'):
        p.add_argument(arg, type=Path)
    a = p.parse_args()
    try:
        result = check(a.current.read_text(), a.baseline.read_text())
    except (OSError, ValueError) as exc:
        result = {'passed': False, 'error': str(exc)}
    a.output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result))
    raise SystemExit(0 if result['passed'] else 1)
