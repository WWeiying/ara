"""Independent60 exact partial cause preparation and fail-closed native capture gates."""
import argparse
import copy
import csv
import io
import json
from pathlib import Path
import re
import sys

import review_scoreboard_acc796_closure_agent_20261008 as source
import run_masku_zero3_native796_v2 as mature
import qualify_csr_pmp0_native765 as labels

u, need = source.u, source.need
HERE = Path(__file__).resolve().parent
SCRIPT = Path(__file__).resolve()
ENTRY = SCRIPT.with_suffix('.tcl')
TEST = SCRIPT.with_name('test_scoreboard_cause60_native796.py')
SOURCE_SHA = '9a00f6dd16f3000dff528aefb7d48a5ceeb2a6057a5352f59787ef9349aeec2b'
OUT = u.OUT / 'scoreboard-cause60-native796-prepared-agent-20261008-03'
STAGES = ('before', 'selected', 'reset', 'reloaded', 'final')
EL_NAMES = dict(before='initial-empty.el', selected='first.el', reset='reset-empty.el',
                reloaded='second.el', final='final-empty.el')
SCHEMA = 'SCOREBOARD_CAUSE60_EXACT62_6_NATIVE796_V1'


def read_bound(path, sha):
    need(u.digest(path) == sha, 'Frozen evidence drift: ' + str(path))
    return json.loads(path.read_bytes())


def groups(report):
    expanded = copy.deepcopy(report)
    expanded['previously_independent14'] += expanded['newly_closed46']
    result = source.config(expanded)['groups']
    need(len(result) == 4 and sum(len(g['targets']) for g in result) == 60, 'Exact60 compiled leaves')
    return result


def el_config(c):
    return dict(groups=c['groups'])


def semantic(text, c):
    # The predecessor's strict typed partial parser has no direction-ID mapping.
    pending, active, count = False, False, 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('//'):
            continue
        if line.startswith('CHECKSUM:'):
            need(not pending and (not active or count > 0), 'Orphan/empty checksum block')
            pending, active, count = True, False, 0
        elif line.startswith('INSTANCE:'):
            need(pending, 'Instance without checksum')
            pending, active = False, True
        elif line.startswith('Toggle '):
            need(active and not pending, 'Directive outside checksum/scope')
            count += 1
        elif line.startswith('ANNOTATION:'):
            need(active and not pending, 'Orphan annotation')
    need(not pending and active and count > 0, 'Trailing orphan/empty block')
    need(source.validate_el(text, el_config(c)) == 6840, 'Exact6840 named-direction exclusions')
    return 6840


def atom(value):
    need(not any(x in str(value) for x in ('{', '}', '\\', '\n', '\r')), 'Unsafe Tcl atom')
    return '{' + str(value) + '}'


def selection(c):
    text = ''.join('set ::s60_' + k + ' ' + atom(c[k]) + '\n'
                   for k in ('design', 'vdb', 'test', 'python', 'helper'))
    text += 'set ::s60_groups [list ' + ' '.join('[list ' + atom(g['scope']) + ' [list ' +
        ' '.join(atom(t['name']) for t in g['targets']) + ']]' for g in c['groups']) + ']\n'
    return text


def history(g):
    api = u.OUT / 'csr-reserved1193-native-agent-20261007-01'
    log = api / 'DVEfiles/dve_gui.log'
    need(u.digest(log) == '5c2cfac285e39c11e3482b167711823de27e93c5c555600f48f2cd888c8c7587',
         'Actual API help seal')
    text = log.read_text()
    need('compress/uncompress' in text and "Toggle transition: '0to1' or '1to0'." in text,
         'Explicit installed named-direction API help')
    pins = {str(log): u.digest(log)}
    path_records = []
    soc = u.OUT / 'soc-constants61-native-parent-20261008-03'
    decoder = u.OUT / 'cva6-fixed120-native768-agent-20261007-01'
    for group in g:
        directory = decoder if group['module'] == 'decoder' else soc
        p = directory / 'config.json'; c = json.loads(p.read_bytes()); pins[str(p)] = u.digest(p)
        found = [(i, n) for i, n in enumerate(c['instances']) if n['scope'] == group['scope']]
        need(len(found) == 1, 'One historical exact scope')
        index, historical = found[0]
        need(historical['design_module_checksum'] == group['design_checksum'] and
             historical['toggle_checksum'] == group['toggle_checksum'], 'Historical compiled scope identity')
        p = directory / ('native_before_%d.tsv' % index); pins[str(p)] = u.digest(p)
        rows = list(csv.DictReader(io.StringIO(p.read_text()), delimiter='\t'))
        for target in group['targets']:
            name = target['name'] + '[63:0]'
            match = [r for r in rows if r['name'] == name]
            need(len(match) == 1 and match[0]['path'] == match[0]['meta'] == name,
                 'Observed packed cause full path missing/ambiguous')
            path_records.append(dict(scope=group['scope'], name=target['name'],
                path=name, meta=name, label=name, evidence=str(p),
                old_handle_not_reused=True, per_bit_binding_not_yet_verified=True))
    return dict(status='HELP_AND_ALL60_COMPRESSED_PACKED_PATHS_VERIFIED_PARTIAL_BITS_HOLD',
        pins=pins, compressed_cause_paths=path_records,
        commands=dict(expand='gui_cov_tgl_double_click -id CovDetail.1 -item ACTUAL_PATH',
            rise='gui_exclusion -id CovDetail.1 -excluded -selected -tgl_transition 0to1',
            fall='gui_exclusion -id CovDetail.1 -excluded -selected -tgl_transition 1to0'),
        historical_failed_vector_capture=True, all64_bit_rows_required_per_copy=True,
        serialized_bitmap_direction_ID_mapping=False, native_qualified=False)


def source_packet():
    r = read_bound(source.REPORT, SOURCE_SHA)
    need(r == source.collect(), 'Frozen source closure recomputation')
    verification = source.PREP / 'verification.json'
    doc = json.loads(verification.read_bytes())
    manifest = Path(doc['HDL_manifest_pin']['path'])
    need(u.digest(manifest) == doc['HDL_manifest_pin']['sha256'], 'Original VCS manifest pin')
    aliases = source.snapshot.validate(u.ROOT, source.ARCHIVE)['source_aliases']
    book = json.loads((u.BUILD / 'build-source-pins.json').read_bytes())
    compiled = json.loads(manifest.read_bytes())
    bindings = []
    for row in compiled['files']:
        original = Path(row['path'])
        if original.suffix not in ('.sv', '.svh', '.v', '.vh'):
            continue
        evidence = Path(aliases.get(str(original), {}).get('snapshot', original))
        need(u.digest(evidence) == row['sha256'] == book[str(original)], 'Original compiled HDL pin')
        bindings.append(dict(original=str(original), evidence=str(evidence), sha256=row['sha256']))
    need(bindings == doc['original_compiled_HDL_bindings'] and len(bindings) == 450,
         'Complete450 original source chain')
    return r, bindings, {str(source.REPORT): SOURCE_SHA, str(verification): u.digest(verification),
                        str(manifest): u.digest(manifest)}


def contract(c, r):
    canonical = lambda value: json.dumps(value, sort_keys=True, separators=(',',':'), allow_nan=False)
    need(c['schema'] == SCHEMA and canonical(c['groups']) == canonical(groups(r)) and
         canonical(c['source_closure']) == canonical(r) and
         c['selected_bits'] == list(range(6, 63)) and c['protected_bits'] == [0,1,2,3,4,5,63] and
         c['copies'] == 60 and c['physical_bits_per_copy'] == 57 and c['physical_bits'] == 3420 and
         c['directions'] == 6840 and type(c['timeout_seconds']) is int and c['timeout_seconds'] == 900 and
         c['population_application'] is False and c['automatic_retry'] is False and
         c['native_qualified'] is False and c['initial_X_qualified'] is False,
         'Exact60 range/source/config/full complement contract')
    need(c['serialized_native_direction_ID_mapping'] is False and
         not any('direction_id' in k.lower() or 'directionids' in k.lower() for k in c
                 if k != 'serialized_native_direction_ID_mapping'),
         'No serialized-derived native direction IDs')
    need(c['original_compiled_HDL_bindings'] == json.loads(
         (source.PREP / 'verification.json').read_bytes())['original_compiled_HDL_bindings'],
         'Complete original450 HDL binding required in config')
    required = dict(r['input_pins'], **{b['evidence']: b['sha256'] for b in c['original_compiled_HDL_bindings']})
    required[str(source.REPORT)] = SOURCE_SHA
    need(all(c['pins'].get(p) == sha for p, sha in required.items()), 'Required source/dispatcher pins omitted')


def check(out, seal):
    c = read_bound(out / 'config.json', seal)
    need(out == OUT and c['output'] == str(out), 'Exact independent output')
    source.check_pins(c['pins'])
    r = read_bound(source.REPORT, SOURCE_SHA); contract(c, r)
    need(json.loads((out / 'source-proof.json').read_bytes()) == r, 'Saved complete source proof')
    need((out / 'selection.tcl').read_text() == selection(c) and
         (out / 'native-bind.tcl').read_bytes() == ENTRY.read_bytes(), 'Exact generated Tcl drivers')
    need(c['API_evidence'] == history(c['groups']), 'Existing installed help/packed paths evidence')
    semantic((out / 'candidate.el').read_text(), c)
    mature.tools.revalidate(c['identity'])
    return c


def object_gate(text, group, stage, before=None):
    need(stage in STAGES, 'Exact stage')
    rows = list(csv.DictReader(io.StringIO(text), delimiter='\t'))
    names = {}
    targets = {t['name'] for t in group['targets']}
    for node in group['complete_typed_scope_inventory']:
        n = dict(kind=node['kind'], **node['attributes'])
        aliases = labels.aliases(n)
        # Mature SOC resolver: bare names only for protected internal singleton vectors.
        if n['kind'] == 'vectornode' and n['left'] == n['right'] and n['type'] in ('1','3') and n['portnode'] == '0' and n['name'] not in targets:
            aliases.add(n['name'])
        for alias in aliases:
            need(alias not in names, 'Ambiguous compiled typed alias')
            names[alias] = n
    found, handles, paths = {}, set(), set()
    for row in rows:
        need(set(row) == {'handle','path','meta','name','type','coverage','display','0to1','1to0'} and
             row['name'] in names and row['handle'].isdigit() and row['handle'] not in handles and
             row['path'] not in paths and row['path'] == row['meta'] == row['name'],
             'Exact unique actual typed full-scope identity')
        n = names[row['name']]; name = n['name']
        need(name not in found and row['0to1'] in ('0','1') and row['1to0'] in ('0','1'),
             'Unique object with both actual named direction flags')
        role = 'MDA' if n['kind'] == 'arrays' else 'port' if n['portnode'] in ('2','3') else 'signal'
        need(row['type'] == role, 'Ordered compiled MDA/port/signal role')
        if stage in ('before','reset','final') or name not in targets:
            need(row['0to1'] == row['1to0'] == '0', 'Protected object/direction excluded')
        if before is not None:
            keys = set(row) - {'handle'}
            if stage in ('selected','reloaded') and name in targets:
                keys -= {'coverage','display','0to1','1to0'}
            need(name in before and all(row[k] == before[name][k] for k in keys),
                 'Full-scope complement/identity/coverage changed')
        found[name] = row; handles.add(row['handle']); paths.add(row['path'])
    need(set(found) == {n['attributes']['name'] for n in group['complete_typed_scope_inventory']},
         'Complete scope complement missing; no flattening MDA')
    return found


def bit_gate(text, group, stage, before=None):
    need(stage in STAGES, 'Exact native bit stage')
    rows = list(csv.DictReader(io.StringIO(text), delimiter='\t'))
    targets = {t['name'] for t in group['targets']}
    found, paths = {}, set()
    for row in rows:
        need(set(row) == {'signal','bit','path','meta','name','coverage','0to1','1to0'} and
             row['signal'] in targets and row['bit'].isdecimal(), 'Exact observed native bit schema')
        name, bit = row['signal'], int(row['bit']); key = name, bit
        need(0 <= bit <= 63 and key not in found and row['path'] and row['meta'] and
             row['path'] not in paths and row['name'] == name + '[%d]' % bit,
             'Unique actual per-bit packed cause path/label')
        expected = '1' if stage in ('selected','reloaded') and 6 <= bit <= 62 else '0'
        need(row['0to1'] == row['1to0'] == expected, 'Exact selected/protected named direction flags')
        if stage == 'before' and 6 <= bit <= 62:
            need(row['coverage'] == '0.00%', 'Observed covered cause high contradicts source candidate')
        if before is not None:
            need(key in before and all(row[k] == before[key][k] for k in ('path','meta','name')),
                 'Native physical bit identity changed')
            if stage in ('reset','final') or bit < 6 or bit == 63:
                need(row['coverage'] == before[key]['coverage'], 'Protected/reset per-bit coverage changed')
        found[key] = row; paths.add(row['path'])
    need(set(found) == {(name, bit) for name in targets for bit in range(64)},
         'All64 bits per copy required, including low6 and interrupt63')
    return found


def inventory(out, c, stage):
    for index, group in enumerate(c['groups']):
        objects = (out / ('objects_%s_%d.tsv' % (stage,index))).read_text()
        bits = (out / ('bits_%s_%d.tsv' % (stage,index))).read_text()
        obj_before = bit_before = None
        if stage != 'before':
            obj_before = object_gate((out / ('objects_before_%d.tsv' % index)).read_text(), group, 'before')
            bit_before = bit_gate((out / ('bits_before_%d.tsv' % index)).read_text(), group, 'before')
        object_gate(objects, group, stage, obj_before)
        bit_gate(bits, group, stage, bit_before)


def el(out, c, stage):
    text = (out / EL_NAMES[stage]).read_text()
    if stage in ('before','reset','final'):
        need(text == '', 'Global initial/reset/final EL must be empty')
        return 0
    return semantic(text, c)


def inspect_capture(out, seal):
    c = check(out, seal)
    need(not (out / 'error.txt').exists(), 'Native error is HOLD, not qualification')
    log = (out / 'DVEfiles/dve_gui.log').read_text()
    need(log.splitlines().count('SCOREBOARD_CAUSE60_FIVE_PHASE_DONE') == 1 and
         'SCOREBOARD_CAUSE60_FAILED' not in log and 'compress/uncompress' in log and
         "Toggle transition: '0to1' or '1to0'." in log, 'Actual API help and completion required')
    need((out / 'selected_tests.txt').read_text() == c['test'] + '\n', 'One exact admitted PASS sample')
    for stage in STAGES:
        inventory(out, c, stage); el(out, c, stage)
    # Both exports independently equal the exact physical named-direction set.
    pins = dict(c['pins'])
    for pattern in ('objects_*.tsv', 'bits_*.tsv'):
        pins.update({str(p): u.digest(p) for p in out.glob(pattern)})
    for name in ('config.json','selected_tests.txt','DVEfiles/dve_gui.log', *EL_NAMES.values()):
        pins[str(out / name)] = u.digest(out / name)
    return dict(status='CAUSE60_LOCAL_NATIVE_GATES_PASS_NOT_POPULATION_APPLIED', copies=60,
        physical_bits=3420, named_directions=6840, config_sha256=seal, pins=pins,
        per_bit_API_bindings_verified=True, population_application=False)


def prepare(out):
    need(out == OUT and not out.exists(), 'Fresh successor only, frozen14 unchanged')
    r, bindings, extra = source_packet(); g = groups(r)
    api = history(g)
    chosen, passed = mature.pass_evidence()
    sample = mature.SAMPLE
    ledger = next(Path(p) for p in r['input_pins'] if p.endswith('/combined-inputs.txt'))
    need(str(sample) in ledger.read_text().splitlines(), 'PASS sample must also be admitted796')
    dirs = list((sample / 'snps/coverage/db/testdata').iterdir())
    need(len(dirs) == 1 and dirs[0].is_dir(), 'One native sample test')
    identity = mature.tools.prepare('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/dve', '/usr/bin/xvfb-run')
    pins = dict(r['input_pins'], **extra, **chosen, **api['pins'],
                **{b['evidence']: b['sha256'] for b in bindings})
    pins.update({f['path']: f['sha256'] for f in identity['files']})
    for module in list(sys.modules.values()):
        p = getattr(module, '__file__', None)
        if p and Path(p).resolve().parent == HERE:
            pins[str(Path(p).resolve())] = u.digest(Path(p))
    for p in (SCRIPT, ENTRY, TEST, HERE / 'run_scoreboard_cause60_native796.py',
              HERE / 'test_run_scoreboard_cause60_native796.py',
              HERE / 'capture_csr_reserved1193.tcl', HERE / 'apply_points740_v4.tcl'):
        pins[str(p)] = u.digest(p)
    for p, sha in mature.EXTRA.items():
        pins[str(p)] = sha
    c = dict(schema=SCHEMA, output=str(out), population=796, copies=60,
        physical_bits_per_copy=57, physical_bits=3420, directions=6840,
        selected_bits=list(range(6,63)), protected_bits=[0,1,2,3,4,5,63], groups=g,
        original_compiled_HDL_bindings=bindings, source_closure=r, API_evidence=api,
        already_PASS_sample=passed, identity=identity, pins=pins,
        design=str(u.BUILD / 'sim/simv.vdb'), vdb=str(sample),
        test=str(sample.with_suffix('') / dirs[0].name), python=str(Path(sys.executable).resolve()),
        helper=str(SCRIPT), timeout_seconds=900, automatic_retry=False, population_application=False,
        native_qualified=False, initial_X_qualified=False, serialized_native_direction_ID_mapping=False)
    contract(c, r); source.check_pins(pins)
    text = source.candidate_el(el_config(c)); semantic(text, c)
    out.mkdir()
    source.write_json(out / 'source-proof.json', r)
    for name, data in [('candidate.el', text), ('selection.tcl', selection(c)), ('native-bind.tcl', ENTRY.read_text())]:
        with (out / name).open('x') as stream:
            stream.write(data)
    for name in ('source-proof.json','candidate.el','selection.tcl','native-bind.tcl'):
        pins[str(out / name)] = u.digest(out / name)
    source.write_json(out / 'config.json', c)
    return dict(status='CAUSE60_PREPARED_NOT_AUTHORIZED_NOT_STARTED', output=str(out),
        config_sha256=u.digest(out / 'config.json'), EDA_started=False, native_qualified=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare','check','inventory','el'))
    p.add_argument('--output', type=Path, default=OUT); p.add_argument('--seal')
    p.add_argument('--stage', choices=STAGES)
    a = p.parse_args(); out = a.output.resolve()
    if a.mode == 'prepare':
        need(a.seal is None, 'Prepare cannot authorize launch'); result = prepare(out)
    else:
        c = check(out, a.seal or __import__('os').environ.get('CAUSE60_CONFIG_SEAL'))
        if a.mode in ('inventory','el'):
            need(a.stage in STAGES, 'Explicit capture stage')
            (inventory if a.mode == 'inventory' else el)(out, c, a.stage)
        result = dict(status=a.mode + '_PASS_NO_LAUNCH')
    print(json.dumps(result, indent=2), flush=True)
