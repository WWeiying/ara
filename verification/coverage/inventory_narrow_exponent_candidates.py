"""Inventory narrow double-exponent table gaps; no native exclusion generation."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import unittest

from inventory_operand_debug import Design, ROOT
from closure_point_inventory import points
from test_divsqrt_narrow_exponent_scope import NarrowExponentScopeTests


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args().output.absolute()
    if output.parent != ROOT / 'verification/out' or output.exists():
        raise ValueError('Fresh direct output required')
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(NarrowExponentScopeTests)
    if not unittest.TextTestRunner().run(suite).wasSuccessful():
        raise ValueError('Narrow exponent proof failed')
    base = ROOT / 'verification/out/gap94-offline-admitted-701-20261006-01'
    build = ROOT / 'verification/out/repaired-aligned-build-20260930-01'
    bitmap = json.loads((base / 'combined-bits.json').read_bytes())
    status = json.loads((base / 'status.json').read_bytes())
    if status['aggregate_passed'] != 701 or status['status'] != 'PASS_RAW_UNION_HISTORICAL_ONLY':
        raise ValueError('Not admitted701')
    pins = {str(p): sha(p) for p in (base / 'combined-bits.json', base / 'status.json',
            base / 'combined-inputs.txt', build / 'build-source-pins.json', Path(__file__),
            ROOT / 'verification/coverage/test_divsqrt_narrow_exponent_scope.py')}
    design = Design(build / 'sim/simv.vdb')
    for relative, expected in bitmap['design'].items():
        path = design.db / relative
        if sha(path) != expected:
            raise ValueError('Design drift')
        pins[str(path)] = expected
    targets, protected, scopes = [], [], []
    owners = {'x_ct_vfdsu_srt': ('ct_vfdsu_srt.v', '423'),
              'x_ct_vfdsu_round': ('ct_vfdsu_round.v', '414')}
    for scope, record in bitmap['metrics']['branch'].items():
        name = scope.rsplit('.', 1)[-1]
        inner = re.search(r'\.gen_num_lanes\[([0-3])\]\.', scope)
        if '.i_ara.' not in scope or name not in owners or inner is None:
            continue
        source = Path(design.source(scope)['resolved_path'])
        if source.name != owners[name][0]:
            raise ValueError('Compiled source owner differs')
        pins[str(source)] = sha(source)
        definition = design.definition(scope, 'branch')
        if definition.get('chksum') != record['checksum']:
            raise ValueError('Definition binding differs')
        rows = points('branch', definition, record['width'])
        table = [p for p in rows if str(p['line']) == owners[name][1]]
        if len(table) != 54 or len({p['native_id'] for p in table}) != 1:
            raise ValueError('Double table shape differs')
        bits = int(record['bits'], 16)
        table_hits = sum(bool(bits & (1 << (record['width'] - 1 - p['raw_index']))) for p in table)
        if table_hits != (54 if inner[1] == '0' else 1):
            raise ValueError('Observed table contradicts reviewed population')
        for point in rows:
            hit = bool(bits & (1 << (record['width'] - 1 - point['raw_index'])))
            candidate = inner[1] != '0' and str(point['line']) == owners[name][1] and not hit
            row = dict(scope=scope, checksum=record['checksum'], point=point, hit=hit)
            (targets if candidate else protected).append(row)
        scopes.append(scope)
    if len(scopes) != 32 or len(targets) != 1272:
        raise ValueError('Incomplete instance/candidate population')
    if any(sha(p) != h for p, h in pins.items()):
        raise ValueError('Evidence drift')
    result = dict(status='NARROW_DOUBLE_EXPONENT_1272_DIAGNOSTIC_CANDIDATES', tests=701,
                  targets=targets, protected=protected, pins=pins, scope_count=32,
                  target_count=len(targets), protected_count=len(protected),
                  native_selector_binding=False, exclusions_applied=False,
                  limits='Diagnostic raw coordinates only; independent case/default native binding still required')
    with output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({k: result[k] for k in ('status', 'tests', 'target_count', 'protected_count')}))


if __name__ == '__main__':
    main()
