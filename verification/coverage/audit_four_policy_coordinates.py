"""Check exact target-set disjointness before a mixed native application."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification/out'


def load(path, pins):
    pins[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return json.loads(path.read_bytes())


def targets_from_plan(config):
    result = set()
    for scope, metrics in config['plan']['scopes'].items():
        for item in metrics['branch']:
            if item['target']:
                point = scope, item['point']['raw_index']
                if point in result:
                    raise ValueError('Duplicate target coordinate')
                result.add(point)
    return result


def check_disjoint(sets):
    for left, right in itertools.combinations(sets, 2):
        if sets[left] & sets[right]:
            raise ValueError('Overlapping target policies: ' + left + '/' + right)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args().output.absolute()
    if output.parent != OUT or output.exists():
        raise ValueError('Fresh direct output required')
    pins = {}
    rebind = load(OUT / 'operand-native1144-rebound-701-parentcheck-20261006-01.json', pins)
    if rebind['status'] != 'NATIVE1144_REBOUND_TO_RAW701_NOT_APPLIED' or rebind['tests'] != 701:
        raise ValueError('Unqualified operand rebind')
    debug = load(OUT / 'operand-debug-1832-application-full701-20261006-01/config.json', pins)
    ff1 = load(OUT / 'ff1-native904-capture-20261006-02/config.json', pins)
    qbs = load(OUT / 'qbs-rooted-report-701-20261006-01/config.json', pins)
    bitmap = load(OUT / 'gap94-offline-admitted-701-20261006-01/combined-bits.json', pins)
    sets = dict(operand1144={(item['scope'], item['raw_index']) for item in rebind['records']},
                debug1832=targets_from_plan(debug['native_config']),
                ff1_904=targets_from_plan(ff1), qbs448=targets_from_plan(qbs))
    expected = dict(operand1144=1144, debug1832=1832, ff1_904=904, qbs448=448)
    if {name: len(value) for name, value in sets.items()} != expected:
        raise ValueError('Incomplete target population')
    check_disjoint(sets)
    hits = {}
    for name, coordinates in sets.items():
        hits[name] = 0
        for scope, index in coordinates:
            row = bitmap['metrics']['branch'][scope]
            if not 0 <= index < row['width']:
                raise ValueError('Coordinate outside bitmap')
            hits[name] += bool(int(row['bits'], 16) & (1 << (row['width'] - index - 1)))
        if name != 'debug1832' and hits[name]:
            raise ValueError('Hit contradicts unreachable classification')
    if hits['debug1832'] != 408:
        raise ValueError('Instrumentation hit population differs')
    pins[str(Path(__file__).resolve())] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != h for p, h in pins.items()):
        raise ValueError('Evidence changed during coordinate audit')
    result = dict(status='FOUR_POLICY_COORDINATES_DISJOINT_NOT_APPLICATION_APPROVAL',
                  target_counts=expected, target_hits=hits, unique_targets=sum(expected.values()),
                  pins=pins, tests=701, application_approval=False,
                  limits='Coordinate diagnostic only; no native export or denominator approval')
    with output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({k: result[k] for k in ('status', 'target_counts', 'target_hits', 'unique_targets')}))


if __name__ == '__main__':
    main()
