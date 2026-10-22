"""Rank admitted762 FSM gaps against sealed761 exclusions; no EDA or waivers."""
import argparse
from pathlib import Path
import rank_admitted_fsm_gaps746 as original
import rank_admitted_fsm_gaps746_v2 as normalized

life, require = original.life, original.require
BASE = life.OUT / 'load-ni-tlb-offline-admitted-762-agent-20261007-01'
BASE_SHA = '6959f676c022f38f9ee2977252c600cfeb5b89fe50b3c4b22d08bf5de7b95cc5'
PRIOR = life.OUT / 'native-population-union-full761-agent-20261007-03'
QUAL_SHA = '4cd4ea9aee8d032fd496f93f2662a66c882a818a9af5ccdc5c9ab8f1fd384346'


def rank(bitmap, definitions, excluded):
    require(len(bitmap['tests']) == len(set(bitmap['tests'])) == 762,
            'Not exact admitted762 membership')
    rows = []
    for scope, row in bitmap['metrics']['fsm'].items():
        if scope != original.SCOPE and not scope.startswith(original.SCOPE + '.'):
            continue
        require(row['checksum'] in definitions, 'FSM checksum has no definition')
        rows.append(original.gaps(scope, row, definitions[row['checksum']], excluded))
    rows.sort(key=lambda r: (-r['remaining_transitions'], -r['remaining_states'], r['scope']))
    return rows


def collect():
    book = life.read_bound(BASE / 'admission-manifest.json', BASE_SHA)
    life.check(book['input_pins'])
    life.check(book['output_pins'])
    path = BASE / 'combined-bits.json'
    bitmap = life.read_bound(path, book['output_pins'][str(path)])
    qualification = life.read_bound(PRIOR / 'qualification.json', QUAL_SHA)
    require(qualification['status'] == 'SEALED_POPULATION_CANONICAL_NATIVE_UNION_REPORT_VERIFIED'
            and qualification['population'] == 761, 'Wrong prior native qualification')
    config_path = PRIOR / 'config.json'
    config = life.read_bound(config_path, qualification['config_seal'])
    excluded = {(r[2], r[3], r[4], r[6], r[7])
                for r in normalized.exclusions(config['expected_union'])}
    require(len(excluded) == 155, 'Sealed761 FSM identity inventory differs')
    shape = Path(config['input_ledger'][0]) / 'snps/coverage/db/shape/fsm.verilog.shape.xml'
    require(life.digest(shape) == bitmap['design']['shape/fsm.verilog.shape.xml'],
            'Admitted data and compiled FSM shape differ')
    definitions = {n.get('chksum'): n for n in original.q.toggle.xml(shape).iter('fsmdef')}
    pins = {str(p): life.digest(p) for p in (
        BASE / 'admission-manifest.json', path, PRIOR / 'qualification.json',
        config_path, shape, Path(__file__).resolve(),
        Path(__file__).with_name('test_rank_admitted_fsm_gaps762.py'),
        Path(original.__file__), Path(normalized.__file__))}
    life.check(pins)
    return dict(status='ADMITTED762_FSM_DIAGNOSTIC_PRIORITY_ONLY', population=762,
                native_qualification_population=761, qualified_exclusion_identities=155,
                pins=pins, instances=rank(bitmap, definitions, excluded),
                exclusions_applied=False, official_percentages_recomputed=False,
                dispatcher_four_new_candidates_included=False,
                note='Ranks unhit coordinates only. No new reachability proof, waiver '
                     'approval or official denominator. Dispatcher4 remains visible '
                     'until the successor unified report is independently verified.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    require(args.output.parent.resolve() == life.OUT and not args.output.exists(),
            'Fresh diagnostic output required')
    result = collect()
    life.save(args.output, result)
    print('population=762; diagnostic only; no new percentage')
    for row in result['instances'][:15]:
        print(row['remaining_transitions'], row['remaining_states'], row['scope'])
