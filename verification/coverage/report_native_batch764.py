"""Formal764: retain qualified763, append VMFPU10/SLDU2/C910240 only."""
import argparse
import copy
import inspect
import json
from pathlib import Path
from types import FunctionType

import report_native_batch763 as prior
import prepare_native_batch764 as prep

life, require, old, merge = prior.life, prior.require, prior.old, prior.merge
HERE = Path(__file__).resolve().parent
TCL = Path(__file__).with_suffix('.tcl')
BASE = prep.PREDECESSOR
BASE_SHA = '150ac4a03e2692367900551e054246fb0a7591d6c22d44e85bb3d72645668ce7'
SCHEMA = 'FORMAL764_RETAINED763_VMFPU10_SLDU2_C910240_V1'
CAPTURES = {
    'vmfpu10': ('vmfpu-ten-native762-agent-20261007-01', prep.VMFPU_SHA),
    'sldu2': ('sldu-two-native763-agent-20261007-02', prep.SLDU_SHA),
    'c910240': ('c910-prepare192-pack48-native-agent-20261007-02',
                'c9611bb7e6ea4bbe197f4198d639ed2b3148c88ea62afd4d4608da812362fada'),
}


def captures():
    result, pins = {}, None
    for key, (name, sha) in CAPTURES.items():
        item, bound = prep.load_native(key, life.OUT/name, sha)
        result[key] = item
        pins = merge(pins, bound) if pins else bound
    return result, pins


def records(text, c):
    if 'future_captures' not in c:
        return prior.records(text, c)
    cfg = c['future_captures']['c910240']['config']
    scopes = {i['scope'] for i in cfg['instances'] if i['targets']}
    previous, addition = [], []
    for scope, block in old.blocks(text):
        (addition if scope in scopes else previous).append(block)
    return dict(retained=prior.records(''.join(previous), c),
                c910240=old.normalized(prep.c910.parse_el(''.join(addition), cfg)))


def fsm_records(expected):
    return expected['retained']['prior']['original']['prior'][0]


def partition_check(expected, before, additions):
    retained = copy.deepcopy(expected['retained'])
    previous = fsm_records(before)
    actual = fsm_records(retained)
    wanted = {tuple(r) for key in ('vmfpu10', 'sldu2')
              for r in additions[key]['canonical_records']}
    require(len(wanted) == 12 and not set(map(tuple, previous)) & wanted and
            set(map(tuple, actual)) == set(map(tuple, previous)) | wanted and
            len(actual) == len(previous)+12, 'Not exact disjoint twelve FSM identities')
    retained['retained']['prior']['original']['prior'][0] = previous
    require(retained == before, 'Retained763 policies changed')
    require(len(expected['c910240']) == 240 and
            expected['c910240'] == additions['c910240']['canonical_records'], 'C910240 exact canonical union differs')


def selection_tail(c, original):
    atom = old.frozen.prior.old.base.capture.tcl_atom
    lines = []
    for index, g in enumerate(c['plan']['groups']):
        if index < len(original['plan']['groups']):
            require(g['scope'] == original['plan']['groups'][index]['scope'], 'FSM order drift')
            lines += ['set n764_group [lindex $fx_groups %d]\n' % index,
                      'set n764_group [lreplace $n764_group 5 5 [list %s]]\n' %
                      ' '.join(atom(r['name']) for r in g['rows'] if r['target']),
                      'set fx_groups [lreplace $fx_groups %d %d $n764_group]\n' % (index, index)]
        else:
            require(g['scope'] == prep.sldu.proof.SCOPE, 'Unknown added FSM scope')
            fields = (g['scope'], str(prep.sldu.proof.SOURCE), g['machine']['name'], g['mode'])
            lines.append('lappend fx_groups [list %s [list %s] [list %s]]\n' %
                         (' '.join(map(atom, fields)), ' '.join(atom(r['name']) for r in g['rows']),
                          ' '.join(atom(r['name']) for r in g['rows'] if r['target'])))
    lines.append('set combo_groups {}\n')
    for index, g in enumerate(c['toggle_groups']):
        lines.append('lappend combo_groups [list %s %d [list %s]]\n' %
                     (atom(g['scope']), index, ' '.join(atom(r[2]) for r in g['reference'])))
    return ''.join(lines)


def add_c910_groups(c):
    item = c['future_captures']['c910240']
    cfg, out = item['config'], Path(item['output'])
    prior_scopes = set(old.ownership(c)) | set(prior.target_fields(c))
    for index, i in enumerate(cfg['instances']):
        require(not any(scope == i['scope'] for scope, _ in prior_scopes), 'C910 overlaps retained field scope')
        refs = sorted(old.table(out/('native_initial_%d.tsv' % index), ['handle','path','meta','name']))
        names = [r[2] for r in refs]
        require(len(names) == len(set(names)) and set(names) == set(i['native_names']), 'C910 complete complement differs')
        targets = [i['native_names'][i['objects'].index(t)] for t in i['targets']]
        c['toggle_groups'].append(dict(policy='c910240', index=index, scope=i['scope'], targets=targets,
            protected=[n for n in names if n not in targets], reference=refs))


def population(original):
    book = life.read_bound(prep.MANIFEST, prep.MANIFEST_SHA)
    pins = merge(book['input_pins'], book['output_pins'], {str(prep.MANIFEST):prep.MANIFEST_SHA})
    def read(name):
        path = prep.MANIFEST.parent/name
        require(str(path) in book['output_pins'], 'Unsealed admission output')
        return life.read_bound(path, book['output_pins'][str(path)])
    beforebook = life.read_bound(prior.MANIFEST, prior.MANIFEST_SHA)
    beforepath = prior.MANIFEST.parent/'combined-bits.json'
    before = life.read_bound(beforepath, beforebook['output_pins'][str(beforepath)])
    bits, one = read('combined-bits.json'), read('single-bits.json')
    prep.population_gate(book, bits, before, one, read('status.json'))
    ledger = (prep.MANIFEST.parent/'combined-inputs.txt').read_text().splitlines()
    require(original['input_ledger'][1:] == before['tests'] and
            ledger == [original['input_ledger'][0], *bits['tests']], 'Exact763 prefix ledger differs')
    selected = [str(Path(db).with_suffix('')/test.name) for db in ledger
                for test in sorted((Path(db)/'snps/coverage/db/testdata').glob('*')) if test.is_dir()]
    require(len(selected) == len(set(selected)) == 764, 'Actual764 selected population differs')
    life.check(pins)
    return ledger, selected, pins


def host_hook(selection, c):
    return FunctionType(prior.host_hook.__code__, dict(prior.host_hook.__globals__, TCL=TCL))(selection, c)


def prepare(out):
    require(out.parent == life.OUT and not out.exists(), 'Fresh independent output only')
    q = life.read_bound(BASE/'qualification.json', BASE_SHA)
    original = life.read_bound(BASE/'config.json', prep.PREDECESSOR_CONFIG_SHA)
    prep.predecessor_gate(q, original)
    life.check(original['pins']); life.check(q['output_pins'])
    ledger, selected, ppins = population(original)
    additions, apins = captures()
    c = copy.deepcopy(original)
    c.update(schema=SCHEMA, output=str(out), population=764, successor_entry=str(Path(__file__).resolve()),
        admission=dict(manifest=str(prep.MANIFEST), seal=prep.MANIFEST_SHA, population=764,
                       exact763prefix=True, full6162_OR=True),
        input_ledger=ledger, expected_selected=selected, future_captures=additions,
        runtime_apply_authorized=True, runtime_timeout_seconds=5400, qualified_fsm_union=173)
    for key in ('vmfpu10','sldu2'):
        c['plan'], _ = prep.merge_fsm(c['plan'], additions[key]['config']['plan'])
    add_c910_groups(c)
    selection = (BASE/'selection.tcl').read_text()+selection_tail(c, original)
    combined = (BASE/'applied.el').read_text()+''.join((Path(i['output'])/'first.el').read_text() for i in additions.values())
    c['expected_union'] = records(combined, c)
    partition_check(c['expected_union'], original['expected_union'], additions)
    deps = [Path(__file__).resolve(), TCL, HERE/'test_report_native_batch764.py',
            HERE/'native_audit_exactcount764.tcl', Path(prep.__file__).resolve(), Path(prior.__file__).resolve()]
    pins = merge(original['pins'], q['output_pins'], ppins, apins,
                 {str(BASE/'qualification.json'):BASE_SHA, str(BASE/'config.json'):prep.PREDECESSOR_CONFIG_SHA},
                 {str(p):life.digest(p) for p in deps})
    life.check(pins); out.mkdir()
    for name, text in [('selection.tcl', selection), ('combined.el', combined), ('inputs.txt','\n'.join(ledger)+'\n')]:
        with (out/name).open('x') as stream: stream.write(text)
        require((out/name).read_bytes() == text.encode('ascii'), 'Text serialization differs')
        pins[str(out/name)] = life.digest(out/name)
    syntax = old.parser(HERE/'check_generated_tcl.py')
    checks = [syntax.check(out/'selection.tcl'), syntax.check(TCL)]
    evaluation = old.generated.evaluate(out/'selection.tcl', {str(out/'selection.tcl'):pins[str(out/'selection.tcl')]},
        ('fx_groups','combo_groups','batch_scale_instances','report745_roots'))
    hook = host_hook(out/'selection.tcl',c)
    life.save(out/'host-generated-tcl-evidence.json', dict(syntax=checks, selection=evaluation, hook=hook, no_EDA=True))
    pins[str(out/'host-generated-tcl-evidence.json')] = life.digest(out/'host-generated-tcl-evidence.json')
    c['pins'] = pins; life.check(pins); life.save(out/'config.json',c)
    print(json.dumps(dict(status='PREPARED_NO_DVE', output=str(out), seal=life.digest(out/'config.json'),
                         population=764, qualified_fsm_union=173, pins=len(pins))), flush=True)


def check(out, seal):
    c = life.read_bound(out/'config.json',seal)
    require(c['schema'] == SCHEMA and c['population'] == 764 and c['output'] == str(out) and
            c['successor_entry'] == str(Path(__file__).resolve()) and c['qualified_fsm_union'] == 173 and
            c['runtime_timeout_seconds'] == 5400 and c['runtime_apply_authorized'] is True, 'Batch764 identity differs')
    life.check(c['pins'])
    require(c['admission']['seal'] == prep.MANIFEST_SHA and set(c['future_captures']) == set(CAPTURES), 'Unapproved scope')
    require((out/'inputs.txt').read_text().splitlines() == c['input_ledger'] and
            len(c['expected_selected']) == len(set(c['expected_selected'])) == 764, 'Population membership differs')
    for key, item in c['future_captures'].items():
        require(item['seal'] == CAPTURES[key][1], 'Capture seal differs')
        prep.native_gate(key, item['qualification'])
    require(records((out/'combined.el').read_text(),c) == c['expected_union'], 'Canonical combined union differs')
    return c


def snapshot_stdout(data,out):
    prior.snapshot_stdout(data,out)
    data.update(population=764, qualified_fsm_union=173,
                future_capture_seals={k:v[1] for k,v in CAPTURES.items()},
                added_vmfpu_native_points=10, added_sldu_transitions=2, added_c910_objects=240,
                added_c910_bits=10896, no_new_simulation=True)


def namespace():
    ns = prior.namespace()
    ns.update(__file__=__file__, TCL=TCL, check=check, records=records, snapshot_stdout=snapshot_stdout)
    ns['verify'] = FunctionType(ns['verify'].__code__, ns)
    ns['run'] = FunctionType(ns['run'].__code__, ns)
    return ns


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare','check','verify','run'))
    p.add_argument('--output', type=Path, required=True); p.add_argument('--seal')
    a = p.parse_args(); out = a.output.resolve()
    if a.mode == 'prepare': prepare(out)
    else:
        require(a.seal, 'Sealed config required')
        if a.mode == 'check': check(out,a.seal); print('BATCH764_CHECK_PASS_NO_EDA')
        else: namespace()[a.mode](out,a.seal)
