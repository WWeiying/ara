"""Diagnostic ranking outside reviewed/pending candidates; never a waiver report."""
from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path

from audit_four_policy_coordinates import targets_from_plan, check_disjoint
from closure_point_inventory import points
from inventory_operand_debug import Design, ROOT

OUT = ROOT / 'verification/out'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args().output.absolute()
    if output.parent != OUT or output.exists():
        raise ValueError('Fresh direct output required')
    pins = {}
    def load(relative):
        path = OUT / relative
        pins[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        return json.loads(path.read_bytes())
    bitmap = load('gap94-offline-admitted-701-20261006-01/combined-bits.json')
    status = load('gap94-offline-admitted-701-20261006-01/status.json')
    if status['status'] != 'PASS_RAW_UNION_HISTORICAL_ONLY' or status['aggregate_passed'] != 701:
        raise ValueError('Not admitted701')
    rebind = load('operand-native1144-rebound-701-parentcheck-20261006-01.json')
    debug = load('operand-debug-1832-application-full701-20261006-01/config.json')['native_config']
    ff1 = load('ff1-native904-capture-20261006-02/config.json')
    qbs = load('qbs-rooted-report-701-20261006-01/config.json')
    exponent = load('narrow-exponent-candidates-701-20261006-01.json')
    candidates = dict(operand={(r['scope'], r['raw_index']) for r in rebind['records']},
                      debug=targets_from_plan(debug), ff1=targets_from_plan(ff1),
                      qbs=targets_from_plan(qbs),
                      exponent_pending={(r['scope'], r['point']['raw_index']) for r in exponent['targets']})
    counts = {k: len(v) for k, v in candidates.items()}
    if counts != dict(operand=1144, debug=1832, ff1=904, qbs=448, exponent_pending=1272):
        raise ValueError('Candidate population differs')
    check_disjoint(candidates)
    masked = set().union(*candidates.values())
    design = Design(Path(qbs['plan']['design_vdb']))
    for relative, expected in bitmap['design'].items():
        path = design.db / relative
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Compiled design drift')
        pins[str(path)] = expected
    ranks, unresolved, removed = Counter(), [], 0
    for scope, record in bitmap['metrics']['branch'].items():
        if '.i_ara.' not in scope:
            continue
        if record['checksum'] is None:
            unresolved.append(scope)
            continue
        definition = design.definition(scope, 'branch')
        if definition.get('chksum') != record['checksum']:
            raise ValueError('Definition differs')
        source = design.source(scope)['resolved_path']
        for point in points('branch', definition, record['width']):
            index = point['raw_index']
            hit = int(record['bits'], 16) & (1 << (record['width'] - index - 1))
            if not hit:
                if (scope, index) in masked:
                    removed += 1
                else:
                    ranks[source, point['line']] += 1
    pins[str(Path(__file__).resolve())] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != h for p, h in pins.items()):
        raise ValueError('Evidence changed')
    result = dict(status='REMAINING_GAP_DIAGNOSTIC_NOT_WAIVED', tests=701,
                  candidate_counts=counts, source_bound_masked_unhit=removed,
                  unresolved_scopes=unresolved, exclusions_applied=False,
                  official_percentages=False, pins=pins,
                  ranks=[dict(source=k[0], line=k[1], unhit_positions=v)
                         for k, v in sorted(ranks.items(), key=lambda x: (-x[1], x[0]))])
    with output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(status=result['status'], top=result['ranks'][:8]), indent=2))


if __name__ == '__main__':
    main()
