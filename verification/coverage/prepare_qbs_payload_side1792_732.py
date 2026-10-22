"""Rebind the reviewed exact1792 source proof to formal732; no EDA/apply entry."""
import argparse
from collections import Counter
import itertools
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
import inventory_operand_debug as compiled
import prove_mask_store_snapshot_zero as lexical
import prepare_mask_store_snapshot_cond24 as native
from closure_point_inventory import definition, read_xml

ROOT, OUT = compiled.ROOT, compiled.ROOT / 'verification/out'
SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_prepare_qbs_payload_side1792_732.py')
PARENT = OUT / 'payload-cond731-static-parent-20261006-01/review.json'
PARENT_SHA = '21bc8ee97c3f1e10465e2526e8b41a96531b1647c52e8a452be4ae00d95172b3'
BASE = OUT / 'gap109-offline-admitted-732-parent-20261006-01'
BASE_SHA = 'badbcc7aad21ce6dab6c8c0eeabc7f85b2c13226bbe893a56c88995eab149794'
OLD = OUT / 'pure-war-offline-admitted-731-parent-20261006-01'
OLD_SHA = '79b146c964a009b7185e8f8b90616feab8ebeb8c859d08e0a782daea6e2f5641'
DESIGN = OUT / 'repaired-aligned-build-20260930-01/sim/simv.vdb'
BUILD = OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
FIXTURE = OUT / 'mask-store-cond24-native-prepared-agent-725-20261006-01/first.el'
ANNOTATION = 'QBS payload side old exact1792 native qualification only; not application approval'
STATUS = 'QBS_SIDE1792_SOURCE_PROOF_732_NATIVE_HOLD_NOT_APPLIED'
require, digest = lexical.require, lexical.digest


def writes(text, names):
    """Indexed storage-write ledger; exact pinned bytes remain the authority."""
    pattern = (r'\b(' + '|'.join(map(re.escape, names)) + r')\b'
               r'((?:\s*\[[^\]\n]+\]|\s*\.\s*\w+)*)\s*(<=|=(?!=))\s*([^;]+);')
    return [(re.sub(r'\s+', '', m[1] + m[2]), m[3], re.sub(r'\s+', '', m[4]))
            for m in re.finditer(pattern, lexical.clean(text))]


def source_contract(adapter, payload, engine):
    compact = lambda t: re.sub(r'\s+', '', lexical.clean(t))
    a, p, e = map(compact, (adapter, payload, engine))
    ledger = {}
    for kind, row_name in (('weight', 'row'), ('activation', 'ctx')):
        q = kind + '_pending_q'
        names = (q, q + '_valid', kind + '_pending_target_q', kind + '_pending_location_q',
                 kind + '_target', kind + '_remaining')
        got = writes(adapter, names)
        selected = lambda name: [r for r in got if r[0] == name or r[0].startswith(name + '.')]
        require(selected(q) == [(q, '<=', "'0"), (q, '<=', kind + '_source[1]'),
                (q + '.strb', '<=', kind + '_remaining[31:16]'),
                (q + '.strb', '<=', kind + '_remaining[15:0]')], 'Pending storage writers differ')
        require(selected(q + '_valid') == [(q + '_valid', '<=', "1'b0"),
                (q + '_valid', '<=', "1'b0"), (q + '_valid', '<=', '|' + kind + '_remaining[31:16]'),
                (q + '_valid', '<=', '|' + kind + '_remaining[15:0]')], 'Pending valid writers differ')
        expected_target = '{%s_pending_target_q[b].valid&&%s_pending_q.strb[b],%s_pending_target_q[b].%s,%s_pending_target_q[b].offset}' % (kind, kind, kind, row_name, kind)
        require([r for r in got if r[0].startswith(kind + '_target')] == [
                (kind + '_target[b]', '=', expected_target),
                (kind + '_target[16+b]', '=', kind + '_ingress_target_q[' + kind + '_ingress_rd_q][b]')],
                'Old mask route/alternate target writer differs')
        for suffix in ('target', 'location'):
            name = kind + '_pending_' + suffix + '_q[b]'
            require([r for r in got if r[0].startswith(kind + '_pending_' + suffix + '_q')] ==
                    [(name, '<=', kind + '_' + suffix + '[16+b]')], 'Pending metadata writer differs')
        capture_block = ('if(%s_source_valid[1]&&(|%s_remaining[31:16]))begin'
                         '%s_pending_target_q[b]<=%s_target[16+b];'
                         '%s_pending_location_q[b]<=%s_location[16+b];end') % ((kind,) * 6)
        require(capture_block in a, 'Metadata/strb capture ownership differs')
        require((kind + '_remaining', '=', kind + '_mask&~' + kind + '_consumed') in got,
                'Remaining mask is not consumed subtraction')
        consumed = writes(payload, (kind + '_consumed_o',))
        require(consumed == [(kind + '_consumed_o[B]', '=', '(|' + kind + '_grants)||(' + kind +
                '_valid_i[slot]&&' + kind + '_mask_i[B]&&' + kind + '_location[B].plane==2)')],
                'Side plane is not immediately consumed')
        side = writes(payload, (kind + '_side_row',))
        row_port = 'weight_row_i' if kind == 'weight' else 'activation_context_i'
        require(side == [(kind + '_side_row[row][n]', '=', kind + '_mask_i[n]&&' + kind +
                '_location[n].plane==2&&' + row_port + "[n]==2'(row)")], 'Side hit route differs')
        needles = [
            'wire[31:0]hit=' + kind + '_side_row[row]&' + kind + '_side_offset[b];',
            'wire[8:0]older=StreamWriteData?{(|hit[15:0]),stream_' + kind + '_side[0][row][',
            'wireuse_newer=' + kind + '_valid_i[1]&&newer[8];',
            'wireenable=use_newer||(' + kind + '_valid_i[0]&&older[8]);',
            'always_ff@(posedgeclk_i)if(enable)' + kind + '_side_q[row][b]<=use_newer?newer[7:0]:older[7:0];']
        require(all(p.count(v) == 1 for v in needles), 'Side gate/storage projection differs')
        require(writes(payload, (kind + '_side_q',)) == [(kind + '_side_q[row][b]', '<=',
                'use_newer?newer[7:0]:older[7:0]')], 'Alternate side storage writer')
        for port, signal in [('valid_i', 'source_valid'), ('mask_i', 'mask'),
                             ('location_i', 'location'), ('consumed_o', 'consumed')]:
            require(a.count('.%s_%s(%s_%s)' % (kind, port, kind, signal)) == 1, 'Payload/adapter wire differs')
        ledger[kind] = dict(pending_writes=got, consumed=consumed, side_row=side)
    require(a.count(".PredecodedWriteLocations(1'b1)") == a.count(".StreamWriteData(1'b1)") == 1,
            'Frozen payload parameters differ')
    require('if(PredecodedWriteLocations)begin:gen_registeredassignweight_location[b]=weight_location_i[b];'
            'assignactivation_location[b]=activation_location_i[b];' in p, 'Registered location path differs')
    require(e.count(".NativeView(1'b0),.UniqueInputBytes(1'b1)") == 2 and
            '.ActivationContextBase(0)' in e and '.ActivationContextBase(4)' in e,
            'Frozen two-bank configuration differs')
    return ledger


def pending_bit(mask, side, *, reset=False, clear=False, accept=False,
                incoming_mask=False, incoming_side=False, global_remaining=False,
                drain=False, consumed=False):
    """One stored strb/location bit; valid-clear does not reset retained metadata."""
    if reset:
        return False, side
    require(not (mask and side), 'Input violates pending invariant')
    if clear:
        return mask, side
    if accept:
        if global_remaining:
            return incoming_mask and not incoming_side, incoming_side
        return mask, side
    return (mask and not consumed, side) if drain else (mask, side)


def induction_check(step=None):
    step = pending_bit if step is None else step
    for mask, side in itertools.product((False, True), repeat=2):
        require(step(mask, side, reset=True) == (False, side), 'Reset invents location reset or preserves strb')
    count = 0
    for mask, side in ((False, False), (True, False), (False, True)):
        for flags in itertools.product((False, True), repeat=8):
            reset, clear, accept, incoming_mask, incoming_side, remaining, drain, consumed = flags
            m, s = step(mask, side, reset=reset, clear=clear, accept=accept,
                incoming_mask=incoming_mask, incoming_side=incoming_side,
                global_remaining=remaining, drain=drain, consumed=consumed)
            require(type(m) is bool and type(s) is bool and not (m and s), 'Induction counterexample')
            count += 1
    require(count == 768, 'Incomplete exhaustive Boolean checks')
    return dict(status='PASS', scope='BOOLEAN_SOURCE_STORAGE_PROJECTION_NOT_DUT_CASES',
                reset_base_states_checked=4, invariant_old_states=3, transition_combinations_checked=count,
                actual_DUT_cases=0, reset_resets_location=False,
                invariant='pending_strb AND (registered_plane == 2) == 0')


def target_class(point):
    line = int(point['line'])
    if line not in (375, 378, 401, 403):
        return None
    match = re.fullmatch(r'row=([0-3]),b=([0-9]+)', point['spec']['generate_info'])
    require(match is not None and point['file_id'] == '571', 'Target source/generator differs')
    kind = 'weight' if line in (375, 378) else 'activation'
    row, byte = map(int, match.groups())
    require(byte < (20 if kind == 'weight' else 36), 'Target side byte differs')
    prefix = 'gen_side_row[%d].gen_%s_byte[%d]' % (row, kind, byte)
    older = '(%s_valid_i[0] && %s.older[8])' % (kind, prefix)
    expressions = {
        older: ('01', '11'),
        '(' + prefix + '.use_newer || ' + older + ')': ('01',),
        '(%s.use_newer ? %s.newer[7:0] : %s.older[7:0])' % (prefix, prefix, prefix): ('0',)}
    require(point['expression'] in expressions, 'Unknown expression in reviewed target lines')
    return kind if point['vector'] in expressions[point['expression']] else None


def inventory(design, before, latest, original):
    shape = read_xml(design.db / 'shape/cond.verilog.shape.xml')
    candidates, guards, scopes = [], [], {}
    for bank in (0, 1):
        scope = original['banks'][str(bank)]['scope']
        old, new = before['metrics']['cond'][scope], latest['metrics']['cond'][scope]
        require(new == old, 'Actual732 payload condition bitmap changed')
        require((new['width'], new['checksum']) == (21503, '2947893042'), 'Payload metric shape differs')
        source = design.source(scope)
        require(source['file_id'] == '571' and source['definition_checksum'] == '1651389237' and
                source['resolved_path'] == str(ROOT / 'hardware/src/vlsu/qbs/qbs_payload_buffer.sv'),
                'Compiled source owner differs')
        points = compiled.points('cond', definition(shape, design.hierarchy[scope], new['checksum']), new['width'])
        require(len(points) == 21503 and {p['raw_index'] for p in points} == set(range(21503)),
                'Incomplete raw condition population')
        targets, keys = [], []
        for point in points:
            selected = target_class(point) is not None
            row = dict(scope=scope, metric='cond', point=point, width=new['width'], checksum=new['checksum'],
                       module_checksum=source['definition_checksum'], native_GUI_bound=False,
                       hit_before=bool(int(new['bits'], 16) & (1 << (new['width'] - 1 - point['raw_index']))))
            if selected:
                require(not row['hit_before'], 'Source-impossible candidate actually hit')
                candidates.append(row); targets.append(row)
                gen = re.fullmatch(r'row=([0-3]),b=([0-9]+)', point['spec']['generate_info'])
                keys.append([point['raw_index'], point['native_id'], point['vector'],
                             point['attributes']['chksum'], int(point['line']), int(gen[1]), int(gen[2])])
            else:
                guards.append(row)
        require(keys == original['banks'][str(bank)]['side_induction_candidates']['coordinates'] and
                len(targets) == 896, 'Not exact reviewed896 per bank')
        selected_bits = sum(1 << (21502-r['point']['raw_index']) for r in targets)
        scopes[scope] = dict(width=21503, metric_checksum=new['checksum'],
                module_checksum=source['definition_checksum'], target_count=896, protected_count=20607,
                target_raw_bitmap=hex(selected_bits), protected_raw_bitmap=hex(((1 << 21503)-1) ^ selected_bits),
                actual_native_identity='HOLD_NOT_DISCOVERED')
    require(len(candidates) == 1792 and len(guards) == 41214, 'Population differs')
    return candidates, guards, scopes


def groups(candidates, guards):
    expected = {(c['scope'], c['point']['raw_index']) for c in candidates}
    require(len(expected) == len(candidates) == 1792 and all(target_class(c['point']) for c in candidates),
            'Not exact reviewed targets')
    result = {}
    expressions = {(c['scope'], c['point']['expression']) for c in candidates}
    for row in candidates + guards:
        point = row['point']; key = row['scope'], point['expression']
        if key not in expressions:
            continue
        t = point['truth_table']; ncols, nrows = int(t['ncols']), int(t['nrows'])
        require((ncols, nrows) in ((1, 2), (2, 3)) and len(t['vecs']) == ncols*nrows, 'Target table differs')
        names = [t['vecs'][i*ncols:(i+1)*ncols] for i in range(nrows)]
        identity = point['native_id'], point['attributes']['chksum']
        g = result.setdefault(key, dict(scope=key[0], expression=key[1], compiled_identity_NOT_GUI=identity,
            names=names, targets=[], retained=[], width=point['attributes']['width'],
            point_checksum=identity[1], generate_info=point['spec']['generate_info']))
        require(g['names'] == names and tuple(g['compiled_identity_NOT_GUI']) == identity, 'Ambiguous compiled expression')
        (g['targets'] if (row['scope'], point['raw_index']) in expected else g['retained']).append(point['vector'])
    require(len(result) == 1344, 'Incomplete native group population')
    for g in result.values():
        require(g['retained'] and len(set(g['names'])) == len(g['names']) and
                sorted(g['targets'] + g['retained']) == sorted(g['names']), 'Whole/missing/duplicate condition vectors')
    require(sum(len(g['targets']) for g in result.values()) == 1792 and
            sum(len(g['retained']) for g in result.values()) == 1792, 'Neighbor protection differs')
    return [result[k] for k in sorted(result)]


def bind_native(raw, candidates):
    require(raw.endswith(b'\n') and b'\r' not in raw and b'\x00' not in raw, 'Invalid native bytes')
    text = raw.decode('ascii')
    records = native.parse_records(text)
    native.bind(records, candidates)
    # Annotation is provenance, not a selector. Optional prefix is observed DVE format.
    annotations = re.findall(r'^ANNOTATION: "([^"\n]*)"$', text, re.M)
    require(annotations and all(a == ANNOTATION or re.fullmatch(
        r'vcs_gen_start:row=[0-3],b=[0-9]+:vcs_gen_end:' + re.escape(ANNOTATION), a) for a in annotations),
        'Foreign/malformed native annotation')
    return records


def baseline_contract(old, new, state, manifest):
    require(manifest['baseline'] == str(OLD) and manifest['baseline_seal'] == OLD_SHA and
            state['coverage_admitted'] is True and state['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY' and
            state['aggregate_passed'] == 732 and new['tests'][:-1] == old['tests'] and
            len(new['tests']) == len(set(new['tests'])) == 732 and new['design'] == old['design'],
            'Not exact731->732 ancestry/design')
    changes = []
    for metric, scopes in old['metrics'].items():
        require(set(scopes) == set(new['metrics'][metric]), 'Baseline scopes differ')
        for scope, row in scopes.items():
            other = new['metrics'][metric][scope]
            require((row['width'], row['checksum']) == (other['width'], other['checksum']), 'Metric shape changed')
            a, b = int(row['bits'], 16), int(other['bits'], 16)
            require(a & ~b == 0, 'Coverage loss')
            if a != b:
                changes.append(dict(scope=scope, metric=metric, gain=bin(b ^ a).count('1')))
    require(Counter({m: sum(c['gain'] for c in changes if c['metric'] == m) for m in old['metrics']}) ==
            Counter(state['raw_delta']), 'Actual raw delta differs')
    return changes


def evidence():
    pins = {}
    def pin(path, expected=None):
        path = Path(path).absolute()
        require(path.resolve() == path and not path.is_symlink() and path.is_file(), 'Aliased/missing input')
        value = digest(path)
        require(expected is None or value == expected, 'Pin drift: ' + str(path))
        require(str(path) not in pins or pins[str(path)] == value, 'Pin collision')
        pins[str(path)] = value
        return path
    original = json.loads(pin(PARENT, PARENT_SHA).read_bytes())
    for path, expected in original['pins'].items():
        pin(path, expected)
    def products(directory, seal):
        manifest = json.loads(pin(directory / 'admission-manifest.json', seal).read_bytes())
        require(manifest['output'] == str(directory), 'Manifest output alias')
        for path, expected in manifest['output_pins'].items():
            require(Path(path).parent == directory, 'Foreign output pin')
            pin(path, expected)
        return manifest, json.loads((directory/'combined-bits.json').read_bytes())
    _, old = products(OLD, OLD_SHA)
    manifest, latest = products(BASE, BASE_SHA)
    state = json.loads((BASE/'status.json').read_bytes())
    changes = baseline_contract(old, latest, state, manifest)
    require((BASE/'combined-inputs.txt').read_text().splitlines() == [str(DESIGN), *latest['tests']],
            'Exact732 membership order differs')
    build = json.loads(pin(BUILD).read_bytes())
    sources = dict(adapter=ROOT/'hardware/src/vlsu/qbs/qbs_block_adapter.sv',
                   payload=ROOT/'hardware/src/vlsu/qbs/qbs_payload_buffer.sv',
                   engine=ROOT/'hardware/src/vlsu/qbs/qbs_compute_engine.sv')
    texts = {k: pin(path, build[str(path)]).read_text() for k, path in sources.items()}
    contract = source_contract(**texts)
    induction = induction_check()
    design = compiled.Design(DESIGN)
    for rel, expected in latest['design'].items():
        pin(design.db / rel, expected)
    for rel in ('shape/cond.verilog.shape.xml', 'auxiliary/verilog.sourceinfo.xml'):
        pin(design.db / rel)
    candidates, guards, scopes = inventory(design, old, latest, original)
    native_groups = groups(candidates, guards)
    fixture_records = native.parse_records(pin(FIXTURE).read_bytes().decode('ascii'))
    require(len(fixture_records) == 24, 'Historical native grammar fixture differs')
    for module in (compiled, lexical, native):
        pin(Path(module.__file__).resolve())
    pin(Path(sys.modules[compiled.Design.__module__].__file__).resolve())
    for path in (SCRIPT, TEST, SCRIPT.with_name('lzc_native_records.py'), SCRIPT.with_name('closure_point_inventory.py')):
        pin(path)
    return dict(schema='QBS_SIDE1792_PROOF_NATIVE_PLAN_732_V1', status=STATUS, pins=pins,
        parent_review=str(PARENT), parent_review_sha256=PARENT_SHA, parent_execution_provenance='PARENT_AGENT_INDEPENDENT_EXECUTION',
        baseline=str(BASE), baseline_seal=BASE_SHA, actual731_to732_changes=changes,
        source_contract=contract, boolean_induction=induction, sources={k: str(v) for k,v in sources.items()},
        source_proof=original['proof'], candidates=candidates, candidate_count=1792,
        protected_condition_count=41214, retained_target_group_vectors=1792,
        scope_protection=scopes, native_groups=native_groups,
        native_plan=dict(status='HOLD_NOT_DISCOVERED', historical_EL_is_new_scope_evidence=False,
            historical_grammar_fixture=str(FIXTURE), annotation=ANNOTATION,
            stages=['initial-empty', 'actual-native-full-condition-inventory', 'before-protection-audit',
                    'singleton-selection', 'selected-protection-audit', 'first-export-exact1792-gate',
                    'reset-empty-protection-audit', 'reload-first', 'reloaded-protection-audit',
                    'second-export-exact1792-gate', 'final-global-reset-empty-protection-audit'],
            identities='Observe Condition metadata plus expression/checksum/width and actual vector ID/name; compiled IDs/raw positions are NOT GUI selectors. Missing/ambiguous discovery is HOLD.',
            protection='Full41214 condition complement and1792 neighboring vectors retained; dynamic mask/plane/offset, all byte_valid and slot priorities untouched. Other scopes/metrics protected by exact EL population and final global-empty reset.',
            launch_supported=False, EL_created=False, singleton_runner_prepared=False),
        native_qualified=False, aggregate_application=False, waiver_approval=False,
        EDA_started=False, RTL_changed=False, exclusions_applied=False)


def verify(path, seal):
    require(re.fullmatch(r'[a-f0-9]{64}', seal or '') and digest(path) == seal, 'External proof seal differs')
    artifact = json.loads(path.read_bytes())
    require(artifact == evidence(), 'Current proof/plan reproduction differs')
    print('VERIFY_PASS_NATIVE_HOLD_NOT_APPLIED')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'verify'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal')
    args = parser.parse_args()
    output = args.output.absolute()
    require(output.parent == OUT and output.resolve() == output and not output.is_symlink(), 'Direct fresh out required')
    if args.command == 'verify':
        verify(output/'proof-native-plan.json', args.seal)
        return
    require(not output.exists(), 'Existing output protected')
    record = evidence()
    output.mkdir()
    with (output/'proof-native-plan.json').open('x') as stream:
        json.dump(record, stream, indent=2, sort_keys=True); stream.write('\n')
    seal = digest(output/'proof-native-plan.json')
    with (output/'status.json').open('x') as stream:
        json.dump(dict(status=STATUS, seal=seal, EDA_started=False, exclusions_applied=False), stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(output=str(output), seal=seal, pins=len(record['pins']),
                         candidates=1792, protected=41214, native_qualified=False)))


if __name__ == '__main__':
    main()
