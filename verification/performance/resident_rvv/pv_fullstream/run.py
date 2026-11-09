#!/usr/bin/env python3
"""Prepare-only by default: frozen source/context/FP/final-ack successor gate."""
import argparse
import difflib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
CONTEXT = OUT/'resident_pv_context_fp_agent_20261108_01'
IMPORT = OUT/'resident_pv_import_agent_20261108_01'
LOCAL = ('run.py', 'test_run.py', 'tb.sv', 'source_harness.svh',
         'akv_resident_pv_cluster.sv', 'README.md')
SOURCE_KEYS = ('id', 'guard', 'words', 'cmdpops', 'sentinels', 'latency', 'source_first',
               'import_done', 'reader_done', 'last_fp', 'last_ack', 'transaction_done', 'final_drain',
               'first_write', 'gap_start', 'gap_cycles', 'tail_release', 'cancel_cycle', 'cancel_terminal', 'cancel_wait',
               'writes', 'error', 'credit_stalls', 'skew', 'coefficient_stalls')


def module(path):
    spec = importlib.util.spec_from_file_location('frozen_'+path.parent.name+'_'+path.stem, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def context_inputs():
    return HERE/'context' if (HERE/'context').is_dir() else CONTEXT/'inputs'


def import_inputs():
    return HERE/'import' if (HERE/'import').is_dir() else IMPORT/'inputs'


def helpers():
    context = module(context_inputs()/'run.py')
    return context, context.upstream(), module(import_inputs()/'run.py')


def check_cluster(original, candidate):
    port = '  input logic abort_i,\n'
    connection = '.lane_result_valid_i(lane_result_valid)'
    if original.count(port) != 1 or original.count(connection) != 1:
        raise ValueError('Unexpected accepted cluster structure')
    wanted = original.replace(port, port+'  input logic commit_permit_i,\n').replace(
        connection, '.lane_result_valid_i(lane_result_valid & {4{commit_permit_i || commit_authorized_o}})')
    if candidate != wanted:
        raise ValueError('Cluster diff exceeds the two authorized changes')


def guard_selection(inputs, expected, helper):
    # Repeat the accepted real T9 group. No SoftFloat recomputation or body edits.
    source = expected['mapping'][2]
    if (source['source'], source['elements'], source['heads'], source['tokens']) != (2, 32, 2, 9):
        raise ValueError('Accepted real guard record changed')
    generator = module(inputs/'upstream/corpus.py')
    records = generator.records((generator.BASE/'vectors/vectors.txt').read_text(),
        json.loads((generator.BASE/'vectors/vectors.json').read_text())['cases_by_id'])
    result = dict(cases=3, lanes=[], groups=[], context=[], mapping=[],
                  real_groups=1, real_lane_cases=4)
    texts = [f'50565531 3\n' for _ in range(4)]
    for cid in range(3):
        result['mapping'].append(dict(source, id=cid, no_stalls=0, guard=cid+1))
        flags = 0
        for lane, name in enumerate(source['names']):
            record = records[name]
            header = record['header'][:]
            header[0] = str(cid)
            texts[lane] += ' '.join(header)+'\n'+'\n'.join(record['body'])+'\n'
            row = next(r for r in expected['lanes'] if r['id'] == 2 and r['lane'] == lane)
            row = dict(row, id=cid)
            flags |= row['flags']
            if cid == 1:
                row.update(writes=0, acks=0)
            result['lanes'].append(row)
        result['groups'].append(dict(id=cid, flags=0 if cid == 1 else flags))
        result['context'].append(dict(expected['context'][2], id=cid))
    files = {f'lane{l}.txt': text for l, text in enumerate(texts)}
    files['schedule.txt'] = ''.join(f'{cid} 2 0 0\n' for cid in range(3))
    return result, files


def expected_bundle(inputs, context, helper):
    normal = context.check_selected(inputs, helper)
    guard, files = guard_selection(inputs, normal, helper)
    return dict(normal=normal, guard=guard), files


def check_source(text, expected, helper, guard=False):
    rows = helper.parse_rows(text, 'PV_FULLSTREAM_CASE', SOURCE_KEYS)
    if [r['id'] for r in rows] != list(range(expected['cases'])):
        raise ValueError('Missing/duplicate/out-of-order source receipts')
    for row in rows:
        cid = row['id']
        cancel = guard and cid == 1
        writes = sum(r['writes'] for r in expected['lanes'] if r['id'] == cid)
        fixed = dict(guard=cid+1 if guard else 0, words=96, cmdpops=4, sentinels=4,
                     latency=100, writes=writes, error=int(cancel))
        if any(row[k] != v for k, v in fixed.items()):
            raise ValueError('Source/commit exact count or status mismatch')
        if not (0 < row['source_first'] < row['import_done'] < row['transaction_done'] < row['final_drain'] and
                row['source_first'] < row['last_fp'] < row['transaction_done'] and
                row['source_first'] < row['reader_done'] < row['transaction_done']):
            raise ValueError('Source/FP/transaction interval order')
        if cancel:
            if row['first_write'] or row['last_ack'] or row['writes']:
                raise ValueError('Cancelled source gap committed architecture')
        elif not (max(row['last_fp'], row['import_done'], row['reader_done']) < row['first_write'] <= row['last_ack'] < row['transaction_done']):
            raise ValueError('Commit bypassed source/FP drain or final acknowledgements')
        if guard and cid in (0, 1):
            if not (row['last_fp'] <= row['gap_start'] < row['tail_release'] < row['import_done'] and
                    row['gap_cycles'] >= 12 and row['tail_release']-row['gap_start'] >= 12):
                raise ValueError('Missing delayed-tail authorization/cancel proof')
        elif any(row[k] for k in ('gap_start', 'gap_cycles', 'tail_release', 'cancel_cycle')):
            raise ValueError('Unexpected guard event in normal/reuse transaction')
        if cancel:
            if not (row['gap_start']+12 <= row['cancel_cycle'] < row['cancel_terminal'] and
                    row['cancel_terminal']+12 <= row['tail_release'] and row['cancel_wait'] >= 12):
                raise ValueError('Cancelled cluster terminal did not wait for source drain')
        elif any(row[k] for k in ('cancel_cycle', 'cancel_terminal', 'cancel_wait')):
            raise ValueError('Unexpected cancelled terminal')
    if any(sum(r[k] for r in rows) <= 0 for k in ('credit_stalls', 'skew', 'coefficient_stalls')):
        raise ValueError('Missing real queue backpressure/skew coverage')
    return rows


def check_log(text, expected, context, helper, guard=False):
    if guard:
        checked = helper.check_log(text, expected, 0)
        pressure = helper.parse_rows(text, 'PV_RETURN_STALL', ('id', 'lane', 'cycles'))
        if pressure != [dict(id=i, lane=l, cycles=2) for i in range(3) for l in range(4)]:
            raise ValueError('Missing explicit adapter-visible return backpressure')
        checked['return_backpressure'] = pressure
        rows = helper.parse_rows(text, 'PV_CONTEXT_CASE', tuple(expected['context'][0]))
        total = dict(cases=3, **{k: sum(r[k] for r in expected['context'])
                                for k in ('reads', 'coefficients', 'fills', 'latency')})
        if rows != expected['context'] or helper.parse_rows(text, 'PV_CONTEXT_PASS', tuple(total)) != [total]:
            raise ValueError('Guard context exact numerical transport changed')
        # The cancelled case deliberately has no architectural write timestamps.
        # All original FMA/stream/native/return checks still execute in the TB.
        times = helper.parse_rows(text, 'PV_CONTEXT_TIME', context.TIME_KEYS)
        if [r['id'] for r in times] != [0, 2]:
            raise ValueError('Guard success/reuse timing records missing')
        checked.update(context=rows, context_totals=total, times=times)
    else:
        checked = context.check_log(text, expected, helper)
    source = check_source(text, expected, helper, guard)
    for timing in checked['times']:
        row = source[timing['id']]
        if (row['source_first'] <= timing['launch'] or row['last_fp'] != timing['last_return'] or
                row['reader_done'] != timing['reader_done'] or
                row['last_ack'] != timing['last_ack'] or row['first_write'] != timing['first_write'] or
                row['final_drain'] != timing['drain']):
            raise ValueError('Source and accepted FP timing ledgers disagree')
    measured = []
    for row in expected['mapping']:
        if row['no_stalls']:
            s = source[row['id']]
            measured.append(dict(id=row['id'], source=row['source'],
                source_to_import_done=s['import_done']-s['source_first']+1,
                source_to_last_fp=s['last_fp']-s['source_first']+1,
                source_to_final_ack=s['last_ack']-s['source_first']+1,
                source_to_transaction_done=s['transaction_done']-s['source_first']+1))
    return dict(**checked, source=source, real_no_injected_stall_intervals=measured)


def admit(base, image_name, helper, context):
    report = json.loads((base/'report.json').read_text())
    if report.get('state') != 'PASS' or not report.get('post_pins_match') or not report.get('post_image_match'):
        raise ValueError('Predecessor not identity-checked PASS: '+str(base))
    source = json.loads((base/'source-pins.json').read_text())
    image = json.loads((base/image_name).read_text())
    pins = {}
    for bundle in (source, report['artifacts'], image):
        helper.verify(bundle)
        context.merge(pins, bundle)
    for name in ('report.json', 'source-pins.json', image_name):
        pins[str(base/name)] = helper.sha(base/name)
    return source, pins


def write_pin(path, text, pins, helper):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        stream.write(text)
    path.chmod(0o444)
    pins[str(path)] = helper.sha(path)


def artifact_pins(out, helper):
    names = ('expected.json', 'selection.json', 'prepared.json', 'source-pins.json',
             'source-pins-before.json', 'source-pins-after.json', 'cluster.diff', 'tb.diff',
             'prepare-tests.log', 'work/commands.json', 'work/tests.log', 'work/compile.log',
             'work/normal.log', 'work/guard.log', 'work/image-pins.json')
    return {str(out/name): helper.sha(out/name) for name in names if (out/name).is_file()}


def prepare(out):
    context, helper, importer = helpers()
    out.mkdir(exist_ok=False)
    inputs = out/'inputs'
    inputs.mkdir()
    cpins, pins = admit(CONTEXT, 'work/image-pins.json', helper, context)
    ipins, inherited = admit(IMPORT, 'image-pins.json', helper, context)
    context.merge(pins, inherited)
    accepted = context.check_selected(CONTEXT/'inputs', helper)
    context.check_log((CONTEXT/'work/run.log').read_text(), accepted, helper)
    importer.check_log((IMPORT/'run.log').read_text())
    helper.verify_directories(json.loads((CONTEXT/'selection.json').read_text())['include_directories'])
    for base, label, bundle in ((CONTEXT, 'context', cpins), (IMPORT, 'import', ipins)):
        for name, digest in sorted(bundle.items()):
            path = Path(name)
            if path.is_relative_to(base/'inputs'):
                helper.copy_pin(path, inputs/label/path.relative_to(base/'inputs'), pins, digest)
    expected, guard_files = expected_bundle(inputs/'context', context, helper)
    for relative in (*importer.SOURCES, importer.HEADER, *importer.CONTRACTS):
        name = str(importer.FROZEN/relative)
        if cpins.get(name) != ipins.get(name) or name not in ipins:
            raise ValueError('Import/context frozen production disagreement: '+relative)
    for name in LOCAL:
        helper.copy_pin(HERE/name, inputs/name, pins)
    original = (inputs/'context/upstream/akv_resident_pv_cluster.sv').read_text()
    check_cluster(original, (inputs/'akv_resident_pv_cluster.sv').read_text())
    importer.check_command_contract((inputs/'import'/importer.CONTRACTS[0]).read_text(),
                                    (inputs/'source_harness.svh').read_text())
    for name in ('lane0.txt', 'lane1.txt', 'lane2.txt', 'lane3.txt', 'schedule.txt'):
        helper.copy_pin(inputs/'context'/name, inputs/'normal'/name, pins)
    for name, content in guard_files.items():
        write_pin(inputs/'guard'/name, content, pins, helper)
    # Copy the admitted production/header closure; never fall back to live RTL.
    filelist = (inputs/'context/sources.f').read_text()
    selected, directories = helper.frozen_filelist(filelist, cpins)
    remap = {}
    for name, digest in selected.items():
        path = Path(name)
        relative = path.relative_to(helper.FROZEN_SOURCE) if path.is_relative_to(helper.FROZEN_SOURCE) else Path('production/vmfpu.sv')
        destination = inputs/'frozen'/relative
        helper.copy_pin(path, destination, pins, digest)
        remap[name] = str(destination)
    snapshot_dirs = {str(inputs/'frozen'/Path(name).relative_to(helper.FROZEN_SOURCE)):
                     sorted(remap[p] for p in files) for name, files in directories.items()}
    lines = []
    for line in filelist.splitlines():
        if line.startswith('+incdir+'):
            line = '+incdir+'+str(inputs/'frozen'/Path(line[8:]).relative_to(helper.FROZEN_SOURCE))
        elif line.startswith('/'):
            line = remap[line]
        elif line == '+define+TARGET_VERILATOR':
            continue
        lines.append(line)
    lines.append('+incdir+'+str(inputs))
    write_pin(inputs/'sources.f', '\n'.join(lines)+'\n', pins, helper)
    for name, old, new in (
        ('cluster.diff', original, (inputs/'akv_resident_pv_cluster.sv').read_text()),
        ('tb.diff', (inputs/'context/tb.sv').read_text(), (inputs/'tb.sv').read_text())):
        write_pin(out/name, ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                  fromfile='accepted01/'+name.removesuffix('.diff'), tofile='pv_fullstream/'+name.removesuffix('.diff'))), pins, helper)
    vcs = shutil.which('vcs')
    if not vcs:
        raise ValueError('Host VCS not found')
    branch = subprocess.check_output(['git', '-C', str(OUT.parents[1]), 'branch', '--show-current'], text=True).strip()
    if branch != 'ara_dsa_signoff_integration':
        raise ValueError('Wrong signoff branch')
    config = dict(vcs=vcs, signoff_branch=branch, include_directories=snapshot_dirs,
                  wall_time_seconds=540, normal_cases=66, guard_cases=3, parent_review_required=True,
                  accepted_context=str(CONTEXT), accepted_import=str(IMPORT),
                  source_model='four production queues, one-cycle responses, controlled stalls; not VRF arbitration')
    helper.save(out/'expected.json', expected)
    helper.save(out/'selection.json', config)
    for path in (out/'expected.json', out/'selection.json', Path(vcs).resolve()):
        pins[str(path)] = helper.sha(path)
    helper.verify(pins)
    helper.verify_directories(snapshot_dirs)
    helper.save(out/'source-pins.json', pins)
    helper.save(out/'source-pins-before.json', pins)
    importer.command([sys.executable, '-B', str(inputs/'test_run.py')], inputs,
                     out/'prepare-tests.log', time.monotonic()+90)
    helper.verify(pins)
    helper.save(out/'prepared.json', dict(state='PREPARED_NOT_EXECUTED', normal_cases=66,
        guard_cases=3, numerical_fmas=36976, guard_fmas=1728, numerical_writes=2544,
        guard_writes=128, parent_review_required=True, host_tests_pass=True))


def check_prepared(out, context, helper):
    inputs = out/'inputs'
    expected, guard = expected_bundle(inputs/'context', context, helper)
    if expected != json.loads((out/'expected.json').read_text()):
        raise ValueError('Prepared expectations changed')
    for name in ('lane0.txt', 'lane1.txt', 'lane2.txt', 'lane3.txt', 'schedule.txt'):
        if (inputs/'normal'/name).read_bytes() != (inputs/'context'/name).read_bytes():
            raise ValueError('Normal accepted body/mapping drift')
    for name, content in guard.items():
        if (inputs/'guard'/name).read_text() != content:
            raise ValueError('Guard original body/mapping drift')
    check_cluster((inputs/'context/upstream/akv_resident_pv_cluster.sv').read_text(),
                  (inputs/'akv_resident_pv_cluster.sv').read_text())
    return expected


def execute(out):
    context, helper, importer = helpers()
    pins = json.loads((out/'source-pins.json').read_text())
    config = json.loads((out/'selection.json').read_text())
    inputs, work = out/'inputs', out/'work'
    work.mkdir(exist_ok=False)
    deadline = time.monotonic()+config['wall_time_seconds']
    report = dict(state='FAIL', scope='Source/import/context/production-VMFPU/final-ack gate only',
                  production_vrf_arbitration=False, soc_acceptance=False)
    try:
        helper.verify(pins)
        helper.verify_directories(config['include_directories'])
        expected = check_prepared(out, context, helper)
        compile_cmd = [config['vcs'], '-full64', '-sverilog', '-timescale=1ns/1ps',
            '-top', 'resident_pv_fullstream_tb', '-j8', '-o', 'simv', '+define+SIMULATION',
            '+define+ARA_SHARED_SIMD_MUL', '+define+RESIDENT_TEST_SHARED_FMA=0',
            '-f', str(inputs/'sources.f'), *[str(inputs/'context/upstream'/name) for name in (
                'vmfpu_baseline.sv', 'akv_resident_pv_lane.sv', 'adapter.sv',
                'akv_resident_pv_group.sv', 'resident_payload_fanout.sv')],
            str(inputs/'akv_resident_pv_cluster.sv'), str(inputs/'context/akv_resident_pv_reader.sv'),
            str(inputs/'import/akv_resident_pv_import.sv'), str(inputs/'tb.sv')]
        commands = dict(tests=[sys.executable, '-B', str(inputs/'test_run.py')], compile=compile_cmd,
            normal=[str(work/'simv'), '-no_save', '+CORPUS='+str(inputs/'normal')],
            guard=[str(work/'simv'), '-no_save', '+CORPUS='+str(inputs/'guard'), '+GUARD_CASES'])
        helper.save(work/'commands.json', commands)
        importer.command(commands['tests'], inputs, work/'tests.log', deadline)
        print('PV_FULLSTREAM_COMPILING', flush=True)
        importer.command(compile_cmd, work, work/'compile.log', deadline)
        helper.verify(pins)
        image = {str(p): helper.sha(p) for p in (work/'simv.daidir').rglob('*') if p.is_file()}
        image[str(work/'simv')] = helper.sha(work/'simv')
        helper.save(work/'image-pins.json', image)
        for mode in ('normal', 'guard'):
            print('PV_FULLSTREAM_RUNNING '+mode, flush=True)
            text = importer.command(commands[mode], work, work/(mode+'.log'), deadline)
            report[mode] = check_log(text, expected[mode], context, helper, mode=='guard')
            helper.verify(pins)
            helper.verify(image)
            helper.verify_directories(config['include_directories'])
        helper.save(out/'source-pins-after.json', pins)
        report.update(state='PASS', post_pins_match=True, post_image_match=True)
    except Exception as exc:
        report['error'] = str(exc)
    report['artifacts'] = artifact_pins(out, helper)
    helper.save(out/'report.json', report)
    print('PV_FULLSTREAM_'+report['state']+' '+str(out/'report.json'), flush=True)
    if 'error' in report:
        print(report['error'], flush=True)
    return int(report['state'] != 'PASS')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--execute-prepared', action='store_true')
    parser.add_argument('--parent-reviewed', action='store_true')
    args = parser.parse_args()
    out = args.output.resolve()
    if out.parent != OUT:
        parser.error('Use a fresh direct signoff output child')
    if args.execute_prepared:
        if not args.parent_reviewed or Path(__file__).resolve() != out/'inputs/run.py':
            parser.error('Execution requires parent approval and frozen runner')
        return execute(out)
    prepare(out)
    print('PV_FULLSTREAM_PREPARED_NOT_EXECUTED '+str(out), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
