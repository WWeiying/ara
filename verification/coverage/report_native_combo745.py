"""One frozen-design745 report: qualified combo03 plus FP16 and queue directions."""
import argparse
import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path
from types import FunctionType, SimpleNamespace

import report_c910_combo742_v3 as inherited
import queue_constant_native_v2 as queue
from report_scope_ancestors import report_ancestors

old = inherited.prior.prior
life, require = old.life, old.require
HERE = Path(__file__).resolve().parent
TCL = Path(__file__).with_suffix('.tcl')
REFERENCE = life.OUT / 'qualified-native-combo-full742-agent-20261007-03'
REFERENCE_SEAL = '1b8664a6b467b09fec2142b10f6077dfca26dbb03752265b970f820ff9dfe66a'
BASE = life.OUT / 'gap115-offline-admitted-745-agent-20261007-01'
BASE_SEAL = '965ec298fcd169b9a184367893ddfad7b080c75ac71e85fad72fe4977cf7b5b6'
FP16 = life.OUT / 'c910-fp16-additional8-native742-agent-20261007-01'
FP16_SEAL = '813681de69115ed7011d75f74a340d2b7b062afeb38e21165f72e362278d6fc8'
RECEIPT_SEAL = 'dcc0141bb263628ed024380e53bca144ef85169a031b348fdc765dee9bc04832'
QUEUE = life.OUT / 'queue-constant-native-744-agent-20261007-03'
STAGES = ('raw', 'applied', 'reset', 'reloaded', 'final')
QN = queue.namespace()


def csv_rows(path, delimiter=','):
    with path.open() as stream:
        return list(csv.reader(stream, delimiter=delimiter))


def dict_rows(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


def records(text, c):
    fp_scopes = {i['scope'] for i in c['fp16_config']['instances']}
    q_scopes = {i['scope'] for i in c['queue_config']['instances']}
    base_scopes = {i['scope'] for i in c['c910_config']['instances']}
    base_scopes |= {g['scope'] for g in c['toggle_groups'] if g['policy'] != 'fp16'}
    require(not fp_scopes & (q_scopes | base_scopes) and not q_scopes & base_scopes,
            'Cross-policy scope overlap')
    parts = dict(prior=[], fp16=[], queue=[])
    for block in re.split(r'(?m)(?=^CHECKSUM:)', text):
        if not block:
            continue
        scopes = re.findall(r'(?m)^INSTANCE: *(\S+)$', block)
        require(len(scopes) == 1, 'Unbound native block')
        family = 'fp16' if scopes[0] in fp_scopes else 'queue' if scopes[0] in q_scopes else 'prior'
        parts[family].append(block)
    return json.loads(json.dumps(dict(
        original=old.records(''.join(parts['prior']), c),
        fp16=old.c910.parse_el(''.join(parts['fp16']), c['fp16_config']),
        queue=QN['parse_el'](''.join(parts['queue']), c['queue_config']))))


def receipt_pins(result, receipt):
    require(receipt['status'] == 'EXACT_ADDITIONAL8_NATIVE_QUALIFIED_NOT_APPLIED' and
            receipt['original_capture_result']['sha256'] == FP16_SEAL,
            'FP16 receipt identity differs')
    overrides = receipt['pin_ledger']['overrides']
    path = str(FP16 / 'worker.log')
    require(set(overrides) == {path}, 'Unexpected postterminal override')
    data = Path(path).read_bytes()
    prefix, sep, last = data.rstrip(b'\n').rpartition(b'\n')
    require(sep and hashlib.sha256(prefix + b'\n').hexdigest() == result['pins'][path] and
            json.loads(last) == receipt['pin_ledger']['exact_append'], 'Postterminal append differs')
    return life.merge_pins({k: v for k, v in result['pins'].items() if k != path},
                           receipt['pins'])


def hierarchy(rows):
    report_ancestors(rows, {old.base.observer.SYSTEM})
    stack, selected = [], []
    pattern = re.compile(r'(?:^|\.)(?:i_system|i_ara|i_ara_sequencer|i_segment_sequencer|'
                         r'i_ara_dispatcher|i_dispatcher|i_vlsu|i_qbs_engine|i_compute_engine|'
                         r'i_fp_accumulator|i_akv_engine|i_ariane|i_mmu|i_ptw|i_load_unit|'
                         r'i_store_unit|i_wt_dcache|i_cva6|i_vmfpu|i_valu|i_operand_queues_stage|'
                         r'operand_queue_\w+|i_operand_queue_\w+|i_wt_dcache_ctrl|'
                         r'i_store_load_lookahead|i_lookahead)(?:$|\[)')
    for row in rows:
        depth = int(row['Depth'])
        stack = stack[:depth] + [row['Name']]
        scope = '.'.join(stack)
        if scope.startswith(old.base.observer.SYSTEM) and pattern.search(scope):
            selected.append(dict(scope=scope, name=row['Name']))
    require(selected and len({r['scope'] for r in selected}) == len(selected), 'No unique module roots')
    require(any('i_vmfpu' in r['scope'] for r in selected) and
            any('i_ptw' in r['scope'] for r in selected), 'Missing key hierarchy')
    return selected


def prepare(out):
    require(out.parent == life.OUT and not out.exists(), 'Fresh agent output required')
    ref = life.read_bound(REFERENCE / 'qualification.json', REFERENCE_SEAL)
    require(ref['status'] == 'FULL742_QUALIFIED_NATIVE_UNION_REPORT_VERIFIED' and ref['population'] == 742,
            'Prior combo not qualified')
    c = life.read_bound(REFERENCE / 'config.json', ref['config_seal'])
    book = life.read_bound(BASE / 'admission-manifest.json', BASE_SEAL)
    require(book['schema'] == 'GAP115_INDEPENDENT_AXI745_ADMISSION_V1' and book['explicit_parent_authorized'],
            'Wrong formal745 schema')
    pins = life.merge_pins(book['input_pins'], book['output_pins'])
    bits = life.read_bound(BASE / 'combined-bits.json', pins[str(BASE / 'combined-bits.json')])
    state = life.read_bound(BASE / 'status.json', pins[str(BASE / 'status.json')])
    require(state['coverage_admitted'] is True and state['aggregate_passed'] == 745,
            'Not admitted745')
    ledger = (BASE / 'combined-inputs.txt').read_text().splitlines()
    require(len(bits['tests']) == len(set(bits['tests'])) == 745 and
            ledger == [c['input_ledger'][0], *bits['tests']] and
            bits['tests'][:742] == c['input_ledger'][1:], '745 prefix/design/member mismatch')
    pins = old.chain.merge_inventories(pins, c['pins'], ref['output_pins'],
             {str(REFERENCE / 'qualification.json'): REFERENCE_SEAL,
              str(BASE / 'admission-manifest.json'): BASE_SEAL})
    fq = life.read_bound(FP16 / 'capture-result.json', FP16_SEAL)
    receipt = life.read_bound(FP16 / 'postterminal-receipt.json', RECEIPT_SEAL)
    require(fq['objects'] == 1264 and fq['protected_local_objects'] == 416 and fq['semantic_reload'] and
            fq['finalreset'] and fq['non_target_exclusions'] == 0, 'FP16 qualification incomplete')
    fc = life.read_bound(FP16 / 'config.json', fq['config_seal'])
    require(old.c910.parse_el((FP16 / 'first.el').read_text(), fc) ==
            old.c910.parse_el((FP16 / 'second.el').read_text(), fc), 'FP16 reload differs')
    qq = json.loads((QUEUE / 'capture-result.json').read_bytes())
    require(qq['status'] == 'QUEUE_CONSTANT_EXACT_NATIVE_BIT_DIRECTION_ROUNDTRIP_PASS' and
            qq['objects'] == 108 and qq['bit_directions'] == 312 and
            qq['initial_X_excluded'] is False and qq['usage_d_excluded'] is False and
            qq['semantic_reload'] and qq['global_final_empty'] and qq['all_non_targets_protected'],
            'Queue qualification incomplete')
    qt = json.loads((QUEUE / 'terminal.json').read_bytes())
    require(qt['returncode'] == 0 and qt['timeout'] is False and len(qt['actual_dve']) == 1,
            'Queue actual terminal identity unqualified')
    qc = life.read_bound(QUEUE / 'config.json', qq['pins'][str(QUEUE / 'config.json')])
    require(QN['parse_el']((QUEUE / 'first.el').read_text(), qc) ==
            QN['parse_el']((QUEUE / 'second.el').read_text(), qc), 'Queue reload differs')
    pins = old.chain.merge_inventories(pins, receipt_pins(fq, receipt), qq['pins'],
            {str(FP16 / 'postterminal-receipt.json'): RECEIPT_SEAL,
             str(QUEUE / 'capture-result.json'): life.digest(QUEUE / 'capture-result.json')})
    selected = []
    for vdb in ledger:
        for test in sorted((Path(vdb) / 'snps/coverage/db/testdata').glob('*')):
            if test.is_dir():
                selected.append(str(Path(vdb).with_suffix('') / test.name))
    require(len(selected) == len(set(selected)) == 745, 'Ambiguous actual745 test selection')
    config = dict(c, output=str(out), schema='QUALIFIED_NATIVE_COMBO745_V1',
                  successor_entry=str(Path(__file__).resolve()), input_ledger=ledger,
                  expected_selected=selected, admission_seal=BASE_SEAL,
                  fp16_config=fc, queue_config=qc, population=745,
                  original_reference_seal=REFERENCE_SEAL, official_denominator_verified=False)
    combined = (REFERENCE / 'applied.el').read_text() + (FP16 / 'first.el').read_text() + (QUEUE / 'first.el').read_text()
    config['toggle_groups'] = list(c['toggle_groups'])
    atom = old.base.capture.tcl_atom
    selection = (REFERENCE / 'selection.tcl').read_text()
    for index, instance in enumerate(fc['instances']):
        tree = old.native_tree(FP16 / ('native_before_%d.tsv' % index))
        targets = [s['name'] + '[%d:%d]' % (s['left'], s['right']) for s in instance['signals']]
        names = [r[2] for r in tree]
        require(all(names.count(t) == 1 for t in targets), 'FP16 native target absent')
        number = len(config['toggle_groups'])
        config['toggle_groups'].append(dict(policy='fp16', scope=instance['scope'], index=index,
            targets=targets, protected=[n for n in names if n not in targets], reference=[list(r) for r in tree]))
        selection += 'lappend combo_groups [list %s %d [list %s]]\n' % (
            atom(instance['scope']), number, ' '.join(atom(n) for n in names))
    config['expected_union'] = records(combined, config)
    config['queue_references'] = []
    selection += 'set qc_instances {}\n'
    for index, instance in enumerate(qc['instances']):
        rows = csv_rows(QUEUE / ('native_before_%d.tsv' % index), '\t')
        require(rows[0] == ['handle', 'path', 'meta', 'name', 'column1', 'column2'] and
                all(len(r) == 6 for r in rows[1:]), 'Malformed queue inventory')
        config['queue_references'].append([r[1:4] for r in rows[1:]])
        selection += 'lappend qc_instances [list %s [list %s]]\n' % (
            atom(instance['scope']), ' '.join(atom(s['native_label']) for s in instance['signals']))
    rows = dict_rows(REFERENCE / 'summary.csv.partial')
    config['hierarchy_roots'] = hierarchy(rows)
    selection += 'set report745_roots {}\n'
    for root in config['hierarchy_roots']:
        selection += 'lappend report745_roots [list %s %s]\n' % (atom(root['scope']), atom(root['name']))
    deps = [Path(__file__).resolve(), TCL, Path(__file__).with_name('test_report_native_combo745.py'),
            Path(queue.__file__), HERE / 'queue_constant_native.tcl', HERE / 'report_scope_ancestors.py',
            HERE / 'report_c910_combo742_v3.py', HERE / 'report_c910_combo742_v3.tcl']
    pins = old.chain.merge_inventories(pins, {str(p): life.digest(p) for p in deps})
    life.check(pins)
    out.mkdir()
    for name, text in [('inputs.txt', '\n'.join(ledger) + '\n'), ('combined.el', combined),
                       ('selection.tcl', selection)]:
        with (out / name).open('x') as stream:
            stream.write(text)
        pins[str(out / name)] = life.digest(out / name)
    config['pins'] = pins
    life.save(out / 'config.json', config)
    print(json.dumps(dict(status='PREPARED_NO_DVE', seal=life.digest(out / 'config.json'),
                          population=745, hierarchy_roots=len(config['hierarchy_roots']))), flush=True)


def verify(out, seal):
    c = life.read_bound(out / 'config.json', seal)
    require(c['schema'] == 'QUALIFIED_NATIVE_COMBO745_V1' and c['population'] == 745 and
            c['successor_entry'] == str(Path(__file__).resolve()), 'Wrong successor family')
    for index, reference in enumerate(c['queue_references']):
        require(reference and len(reference) == len({tuple(r) for r in reference}), 'Ambiguous queue complement')
        for stage in ('before', 'selected', 'reset', 'reloaded', 'final'):
            rows = csv_rows(out / ('native_%s_%d.tsv' % (stage, index)), '\t')
            require(rows[0] == ['handle', 'path', 'meta', 'name', 'column1', 'column2'] and
                    all(len(r) == 6 for r in rows[1:]) and [r[1:4] for r in rows[1:]] == reference,
                    'Queue target/protected complement differs')
    reports = {}
    for stage in STAGES:
        rows = dict_rows(out / ('modules_' + stage + '.csv'))
        require([(r['Scope'], r['Name']) for r in rows] ==
                [(r['scope'], r['name']) for r in c['hierarchy_roots']] and
                all(r['Token'] == r['Scope'] and r['GUIPath'] == r['Name'] and r['Stage'] == stage for r in rows),
                'Module root identity/order differs')
        reports[stage] = {r['Scope']: {m: r[m] for m in old.base.native.METRICS} for r in rows}
    require(reports['raw'] == reports['reset'] == reports['final'] and
            reports['applied'] == reports['reloaded'], 'Module raw/reset/reload differs')
    def save(path, data):
        require(path == out / 'qualification.json', 'Unexpected inherited result write')
        data.update(status='FULL745_QUALIFIED_NATIVE_UNION_REPORT_VERIFIED', population=745,
                    c910_objects=2528, queue_objects=108, queue_directions=312,
                    fp16_additional_objects=1264, module_reports=reports,
                    admission_seal=BASE_SEAL, integration_scope_not_new_RTL_signoff=True)
        life.save(path, data)
    ns = dict(old.verify.__globals__, records=records,
              life=SimpleNamespace(**{**vars(life), 'save': save}))
    FunctionType(old.verify.__code__, ns)(out, seal)


def run(out, seal):
    def popen(*args, **kwargs):
        env = dict(kwargs['env'], DVE_REVIEWED_WAIVERS=str(TCL))
        return subprocess.Popen(*args, **dict(kwargs, env=env))
    ns = dict(old.base.run.__globals__, verify=verify,
              subprocess=SimpleNamespace(**{**vars(subprocess), 'Popen': popen}))
    FunctionType(old.base.run.__code__, ns)(out, seal)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'check', 'run', 'verify'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal')
    args = parser.parse_args()
    out = args.output.resolve()
    if args.mode == 'prepare':
        prepare(out)
    else:
        require(args.seal, 'Exact config seal required')
        if args.mode == 'check':
            c = life.read_bound(out / 'config.json', args.seal)
            require(c['schema'] == 'QUALIFIED_NATIVE_COMBO745_V1', 'Wrong config schema')
            life.check(c['pins'])
            require(records((out / 'combined.el').read_text(), c) == c['expected_union'], 'Union drift')
            print('EXACT745_PREPARED_CHECK_PASS_NO_DVE')
        else:
            (run if args.mode == 'run' else verify)(out, args.seal)
