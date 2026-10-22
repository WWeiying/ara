"""Rank formal760 FSM gaps against the previously qualified native scope."""
import argparse
from pathlib import Path
import rank_admitted_fsm_gaps746 as original
import rank_admitted_fsm_gaps746_v2 as normalized

BASE = original.life.OUT / 'qbs-affine-min-scale-offline-admitted-760-agent-20261007-01'
SEAL = '0b4ae9ddf332355cdbb02ff42f237487dd0857fa5872b86916bc5ac40b3b207e'


def collect():
    life, require = original.life, original.require
    book = life.read_bound(BASE / 'admission-manifest.json', SEAL)
    life.check(book['input_pins'])
    life.check(book['output_pins'])
    path = BASE / 'combined-bits.json'
    bitmap = life.read_bound(path, book['output_pins'][str(path)])
    require(len(bitmap['tests']) == len(set(bitmap['tests'])) == 760,
            'Wrong formal population')
    prior = normalized.collect()
    config_path = original.PRIOR / 'config.json'
    qualification = life.read_bound(original.PRIOR / 'qualification.json', original.QUAL_SHA)
    config = life.read_bound(config_path, qualification['config_seal'])
    excluded = {(r[2], r[3], r[4], r[6], r[7])
                for r in normalized.exclusions(config['expected_union'])}
    require(len(excluded) == 155, 'Qualified exclusion identities changed')
    shape_path = Path(config['input_ledger'][0]) / 'snps/coverage/db/shape/fsm.verilog.shape.xml'
    require(life.digest(shape_path) == bitmap['design']['shape/fsm.verilog.shape.xml'],
            'Frozen FSM shape drift')
    definitions = {n.get('chksum'): n for n in original.q.toggle.xml(shape_path).iter('fsmdef')}
    rows = [original.gaps(scope, row, definitions[row['checksum']], excluded)
            for scope, row in bitmap['metrics']['fsm'].items()
            if scope == original.SCOPE or scope.startswith(original.SCOPE + '.')]
    rows.sort(key=lambda r: (-r['remaining_transitions'], -r['remaining_states'], r['scope']))
    pins = dict(prior['pins'])
    for pinned in (BASE / 'admission-manifest.json', path, Path(__file__).resolve(),
                   Path(normalized.__file__).resolve()):
        pins[str(pinned)] = life.digest(pinned)
    life.check(pins)
    return dict(status='FORMAL760_FSM_PRIORITY_DIAGNOSTIC_ONLY', population=760,
                official_percentages_recomputed=False, exclusions_applied=False,
                native_qualification_population=745, instances=rows, pins=pins,
                qualified_exclusion_identities=len(excluded))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    original.require(args.output.parent.resolve() == original.life.OUT and not args.output.exists(),
                     'Fresh output only')
    result = collect()
    original.life.save(args.output, result)
    for row in result['instances'][:20]:
        print(row['remaining_transitions'], row['remaining_states'], row['scope'])
