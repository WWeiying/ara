"""Inventory source-proven narrow FF1 candidates, never produce exclusions."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import unittest

from test_ff1_parent_width_scope import FF1ParentWidthTests, ROOT
from test_divsqrt_ff1_width_scope import FF1WidthScopeTests


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args().output.absolute()
    if output.parent != ROOT / 'verification/out' or output.exists():
        raise ValueError('Fresh direct output required')
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(cls)
                               for cls in (FF1ParentWidthTests, FF1WidthScopeTests))
    if not unittest.TextTestRunner().run(suite).wasSuccessful():
        raise ValueError('Frozen structural checks failed')
    mapping_path = ROOT / 'verification/out/ff1-case-calibration-20261006-02/mapping.json'
    bitmap_path = ROOT / 'verification/out/gap94-offline-admitted-701-20261006-01/combined-bits.json'
    mapping, bitmap = [json.loads(p.read_bytes()) for p in (mapping_path, bitmap_path)]
    if mapping['status'] != 'STANDALONE_FF1_CASE_MAPPING_NOT_NATIVE_EXCLUSION' or mapping['cases'] != 54:
        raise ValueError('Incomplete calibration')
    pins = {**mapping['pins'], str(mapping_path): sha(mapping_path),
            str(bitmap_path): sha(bitmap_path), str(Path(__file__).resolve()): sha(__file__),
            str(ROOT / 'verification/coverage/test_ff1_parent_width_scope.py'):
                sha(ROOT / 'verification/coverage/test_ff1_parent_width_scope.py')}
    for row in mapping['observations']:
        pins[row['data']] = row['data_sha256']
    if any(sha(p) != h for p, h in pins.items()):
        raise ValueError('Calibration evidence drift')
    indices = {r['case']: r['raw_index'] for r in mapping['observations']}
    if set(indices) != {-2, -1, *range(52)} or set(indices.values()) != set(range(54)):
        raise ValueError('Incomplete/duplicate case mapping')
    targets, protected, scopes = [], [], []
    for scope, record in bitmap['metrics']['branch'].items():
        if '.i_ara.' not in scope or not scope.endswith(('x_frac0_expnt', 'x_frac1_expnt')):
            continue
        lane = re.search(r'\.gen_num_lanes\[([0-3])\]\.', scope)
        if lane is None or record['checksum'] != mapping['checksum'] or record['width'] != 54:
            raise ValueError('Compiled instance/case binding differs')
        scopes.append(scope)
        padding = (0, 29, 42, 42)[int(lane[1])]
        bits = int(record['bits'], 16)
        for case, index in indices.items():
            hit = bool(bits & (1 << (53 - index)))
            row = dict(scope=scope, input_bit=case, raw_index=index, hit=hit,
                       checksum=record['checksum'], low_zero_bits=padding)
            if 0 <= case < padding:
                if hit:
                    raise ValueError('Observed hit contradicts structural bound: ' + scope)
                targets.append(row)
            else:
                protected.append(row)
    if len(scopes) != 32 or len(targets) != 904 or len(protected) != 824:
        raise ValueError('Unexpected instance/position counts')
    if any(sha(p) != h for p, h in pins.items()):
        raise ValueError('Evidence drift')
    result = dict(status='FF1_NARROW_904_CANDIDATES_NOT_NATIVE_QUALIFIED',
                  tests=len(bitmap['tests']), target_count=len(targets),
                  protected_count=len(protected), pins=pins, targets=targets,
                  protected=protected, exclusions_applied=False,
                  native_binding=False, official_percentages=False,
                  limits='Normal reset two-state narrow formats only; preserve zero/default and all WIDTH64 positions')
    with output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({k: result[k] for k in ('status', 'tests', 'target_count', 'protected_count')}))


if __name__ == '__main__':
    main()
