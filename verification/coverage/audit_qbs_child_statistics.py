"""Review complete child performance fields; no exclusions or score claims."""
import argparse
import json
from pathlib import Path

import audit_diagnostic_sink_capacity_744 as parent

q = parent.q
ROOT, OUT = parent.ROOT, parent.OUT
BASE = parent.PREFIX + '.i_vlsu.i_qbs_engine'
FIELDS = (
    ('fp_uop_issue_o', 'fp_uop_issue_o', 'compute_fp_uop_issue', 'fp_uop_issue_o', 32),
    ('table_occupancy_sum_o', 'fp_table_occupancy_sum_o',
     'compute_fp_table_occupancy_sum', 'fp_table_occupancy_sum_o', 32),
    ('table_occupancy_max_o', 'fp_table_occupancy_max_o',
     'compute_fp_table_occupancy_max', 'fp_table_occupancy_max_o', 5),
    ('table_full_cycles_o', 'fp_table_full_cycles_o',
     'compute_fp_table_full_cycles', 'fp_table_full_cycles_o', 32),
    ('accumulator_updates_o', 'accumulator_updates_o',
     'compute_accumulator_updates', 'accumulator_updates_o', 32),
)


def expected_references(field):
    child, compute, alias, output, width = field
    decl = 'output logic [%s:0]' % (width - 1)
    increment = {
        'fp_uop_issue_o': [f'{child} <= {child} + 1\'b1;'],
        'table_occupancy_sum_o': [f'{child} <= {child} + entry_occupancy;'],
        'table_occupancy_max_o': [f'if (entry_occupancy > {child})',
                                  f'{child} <= entry_occupancy;'],
        'table_full_cycles_o': [f'{child} <= {child} + 1\'b1;'],
        'accumulator_updates_o': [f'{child} <= {child} + 1\'b1;'] * 2,
    }[child]
    return {
        'child': [f'{decl} {child}' + ('' if child == 'accumulator_updates_o' else ','),
                  f'{child} <= \'0;', f'{child} <= \'0;'] + increment,
        'compute': [f'{decl} {compute}' + ('' if compute == 'accumulator_updates_o' else ','),
                    f'.{child}' + ('' if child == 'accumulator_updates_o' else ',')
                    if child == compute else f'.{child} ({compute}),'],
        'alias': [f'logic [{width - 1}:0] {alias};', f'? {alias} : \'0;',
                  f'.{compute} ({alias})' + ('' if child == 'accumulator_updates_o' else ',')],
        'output': [f'{decl} {output},',
                   f'assign {output} = compute_counters_valid_q',
                   f'.{compute} ({alias})' + ('' if child == 'accumulator_updates_o' else ',')],
    }


def normalize(text):
    return ' '.join(text.split())


def check_references(text, name, expected):
    refs = parent.references(text, name)
    q.require([normalize(r['text']) for r in refs] ==
              [normalize(r) for r in expected], 'Unreviewed reference: ' + name)
    return refs


def collect():
    reviewed = parent.collect()
    pins = dict(reviewed['pins'])
    source_book = json.loads((OUT / 'repaired-aligned-build-20260930-01/'
                            'build-source-pins.json').read_bytes())
    names = ('qbs_fp_accumulator.sv', 'qbs_compute_engine.sv', 'qbs_engine.sv')
    texts = {}
    for name in names:
        path = ROOT / 'hardware/src/vlsu/qbs' / name
        q.require(q.life.digest(path) == source_book[str(path)], 'Frozen source drift')
        pins[str(path)] = source_book[str(path)]
        texts[name] = path.read_text()
    shape_base = OUT / 'repaired-aligned-build-20260930-01/sim/simv.vdb/snps/coverage/db'
    info = q.toggle.xml(shape_base / 'shape/tgl.verilog.info.xml')
    shape = q.toggle.xml(shape_base / 'shape/tgl.verilog.shape.xml')
    checks = {n.get('name'): n.get('chksum') for n in info.iter('instance_data')}
    defs = {n.get('chksum'): n for n in shape.findall('tgldef')}
    prior = {(g['scope'], f['name']) for g in reviewed['groups'] for f in g['fields']}
    groups = []
    for role, source, scope, index in (
            ('child', names[0], BASE + '.i_compute_engine.i_fp_accumulator', 0),
            ('compute', names[1], BASE + '.i_compute_engine', 1),
            ('alias', names[2], BASE, 2)):
        definition = defs[checks[scope]]
        nodes = {n.get('name'): n for n in definition.iter()
                 if n.tag in ('node', 'vectornode')}
        fields = []
        for field in FIELDS:
            name, width = field[index], field[4]
            refs = check_references(texts[source], name, expected_references(field)[role])
            output_refs = []
            if role == 'alias':
                output_refs = check_references(texts[source], field[3], expected_references(field)['output'])
            q.require((scope, name) not in prior, 'Already reviewed by parent scope')
            node = nodes[name]
            q.require(node.tag == 'vectornode' and node.get('excluded') == '0' and
                      int(node.get('left')) == width - 1 and int(node.get('right')) == 0,
                      'Compiled whole-field shape differs')
            fields.append(dict(name=name, bits=width, directions=2 * width,
                               compiled=dict(node.attrib), source_references=refs,
                               output_source_references=output_refs))
        protected = [dict(n.attrib) for n in definition.iter()
                     if n.tag in ('node', 'vectornode', 'arrays') and
                     n.get('name') not in {f['name'] for f in fields}]
        groups.append(dict(role=role, scope=scope, source=str(ROOT / 'hardware/src/vlsu/qbs' / source),
                           toggle_checksum=checks[scope], fields=fields,
                           all_other_objects_protected=protected))
    pins[str(Path(__file__).resolve())] = q.life.digest(Path(__file__).resolve())
    tests = Path(__file__).with_name('test_audit_qbs_child_statistics.py')
    pins[str(tests)] = q.life.digest(tests)
    pins[str(Path(parent.__file__).resolve())] = q.life.digest(Path(parent.__file__).resolve())
    q.life.check(pins)
    return dict(status='COMPLETE_CHILD_STATISTICS_SOURCE_COMPILED_REVIEW_NATIVE_HOLD',
                groups=groups, parent_groups=reviewed['groups'], pins=pins,
                total_objects=sum(len(g['fields']) for g in groups),
                total_bits=sum(f['bits'] for g in groups for f in g['fields']),
                total_directions=sum(f['directions'] for g in groups for f in g['fields']),
                selection_independent_of_hits=True,
                rationale='Complete self-updated statistics and pass-through aliases terminate '
                          'at reviewed engine output/VLSU display. No product decision feedback.',
                protected='All state, occupancy used for control, data, requests, flags, reset, '
                          'errors, assertions, and non-target child objects remain covered.',
                capacity_is_not_denominator_or_score=True,
                native_qualified=False, application_approved=False, EDA_started=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    q.require(args.output.parent.resolve() == OUT and not args.output.exists(), 'Fresh output only')
    result = collect()
    q.life.save(args.output, result)
    print(json.dumps({k: result[k] for k in ('status', 'total_objects', 'total_bits', 'total_directions')}))
