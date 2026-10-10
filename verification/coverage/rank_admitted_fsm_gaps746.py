"""Prioritize admitted FSM gaps without inventing official coverage scores."""
import argparse
from pathlib import Path
import queue_constant_native as q

life, require = q.life, q.require
BASE = life.OUT / 'external-reset-fpu-half-offline-admitted-746-agent-20261007-01'
BASE_SHA = 'edcc5b1614dd65c51c8e9c69f1ce60bb9196101eea89330c59fde05238a96ddb'
PRIOR = life.OUT / 'qualified-native-combo-full745-agent-20261007-01'
QUAL_SHA = '9f7260352368b2ba522a0a81943f133af3b9bdd1ee015ea9a5c2530b083f11a5'
SCOPE = 'ara_tb.dut.i_ara_soc.i_system'


def exclusions(tree):
    if isinstance(tree, dict):
        for value in tree.values():
            yield from exclusions(value)
    elif isinstance(tree, (list, tuple)):
        if len(tree) == 9 and tree[6] in ('State', 'Transition'):
            yield tuple(tree)
        else:
            for value in tree:
                yield from exclusions(value)


def gaps(scope, row, definition, excluded):
    bits = bin(int(row['bits'], 16))[2:].zfill(row['width'])
    require(len(bits) == row['width'], 'Bitmap exceeds shape width')
    position = 0
    missing = []
    for machine in definition.iter('fsmfsm'):
        states, transitions = machine.findall('state'), machine.findall('transition')
        names = {s.get('id'): s.get('name') for s in states}
        for kind, nodes in (('State', states), ('Transition', transitions)):
            for node in nodes:
                require(position < len(bits), 'FSM shape wider than data')
                name = node.get('name') if kind == 'State' else (
                    names[node.get('fromid')] + '->' + names[node.get('toid')])
                key = (scope, machine.get('name'), machine.get('chksum'), kind, name)
                if bits[position] == '0':
                    missing.append(dict(machine=machine.get('name'), kind=kind, name=name,
                        source_line=node.get('line'), raw_position=position,
                        already_native_qualified_exclusion=key in excluded))
                position += 1
    require(position == row['width'], 'FSM data wider than shape')
    return dict(scope=scope, checksum=row['checksum'], missing=missing,
                remaining_transitions=sum(x['kind'] == 'Transition' and
                    not x['already_native_qualified_exclusion'] for x in missing),
                remaining_states=sum(x['kind'] == 'State' and
                    not x['already_native_qualified_exclusion'] for x in missing))


def collect():
    book = life.read_bound(BASE / 'admission-manifest.json', BASE_SHA)
    bitmap_path = BASE / 'combined-bits.json'
    bitmap = life.read_bound(bitmap_path, book['output_pins'][str(bitmap_path)])
    require(len(bitmap['tests']) == len(set(bitmap['tests'])) == 746, 'Wrong admitted population')
    qualified = life.read_bound(PRIOR / 'qualification.json', QUAL_SHA)
    require(qualified['status'] == 'FULL745_QUALIFIED_NATIVE_UNION_REPORT_VERIFIED' and
            qualified['population'] == 745, 'Unqualified native exclusion report')
    config_path = PRIOR / 'config.json'
    config = life.read_bound(config_path, qualified['config_seal'])
    excluded = {(r[2], r[3], r[4], r[6], r[7]) for r in exclusions(config['expected_union'])}
    require(len(excluded) == 155, 'Unexpected qualified FSM exclusion identities')
    shape_path = Path(config['input_ledger'][0]) / 'snps/coverage/db/shape/fsm.verilog.shape.xml'
    require(life.digest(shape_path) == bitmap['design']['shape/fsm.verilog.shape.xml'], 'FSM shape drift')
    shape = q.toggle.xml(shape_path)
    definitions = {n.get('chksum'): n for n in shape.iter('fsmdef')}
    results = [gaps(scope, row, definitions[row['checksum']], excluded)
               for scope, row in bitmap['metrics']['fsm'].items()
               if scope == SCOPE or scope.startswith(SCOPE + '.')]
    results.sort(key=lambda r: (-r['remaining_transitions'], -r['remaining_states'], r['scope']))
    pins = {str(p): life.digest(p) for p in (
        BASE / 'admission-manifest.json', bitmap_path, PRIOR / 'qualification.json',
        config_path, shape_path, Path(__file__).resolve(),
        Path(__file__).with_name('test_rank_admitted_fsm_gaps746.py'))}
    life.check(pins)
    return dict(status='ADMITTED746_FSM_DIAGNOSTIC_GAP_PRIORITY_ONLY', population=746,
                official_percentages_recomputed=False, exclusions_applied=False,
                native_qualification_population=745, instances=results, pins=pins,
                qualified_exclusion_identities=len(excluded),
                note='Raw states and transitions are separate. This is not an official '
                     'denominator, unreachable proof, PASS verdict, or new exclusion approval.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(args.output.parent.resolve() == life.OUT and not args.output.exists(), 'Fresh output only')
    result = collect()
    life.save(args.output, result)
    for row in result['instances'][:15]:
        print(row['remaining_transitions'], row['remaining_states'], row['scope'])
