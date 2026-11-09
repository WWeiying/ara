#!/usr/bin/env python3
"""Prepare a sealed context/reader/production-VMFPU numerical successor."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
FP = OUT / 'resident_pv_cluster_fp_20261108_02'
READER = OUT / 'resident_pv_reader_gate_20261108_02'
LOCAL = ('run.py', 'test_run.py', 'tb.sv', 'README.md')


def module(path):
    spec = importlib.util.spec_from_file_location('frozen_' + path.stem, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def upstream():
    return module((HERE/'upstream' if (HERE/'upstream').is_dir() else FP/'inputs')/'run.py')


def merge(pins, more):
    for name, digest in more.items():
        if name in pins and pins[name] != digest:
            raise ValueError('Conflicting input pin: ' + name)
        pins[name] = digest


def admission(base, helper, pins):
    receipt = json.loads((base/'report.json').read_text())
    if receipt['state'] != 'PASS':
        raise ValueError('Admission is not PASS: ' + str(base))
    source = json.loads((base/'source-pins.json').read_text())
    image_file = base/('shared0/image-pins.json' if base == FP else 'image-pins.json')
    image = json.loads(image_file.read_text())
    for bundle in (receipt['artifacts'], source, image):
        helper.verify(bundle)
        merge(pins, bundle)
    merge(pins, {str(base/'report.json'): helper.sha(base/'report.json')})
    if base == FP:
        config = json.loads((base/'selection.json').read_text())
        helper.verify_directories(config['include_directories'])
        expected = helper.validate_corpus(base/'inputs')
        helper.check_log((base/'shared0/run.log').read_text(), expected, 0)
    elif not receipt.get('post_image_match') or not receipt.get('post_pins_match'):
        raise ValueError('Reader admission lacks identity checks')
    return source


def require_broadcast(records):
    first = records[0]['header']
    elements, heads, tokens, rounding = map(int, first[1:5])
    if elements not in (16, 24, 32):
        raise ValueError('Unsupported partial per-lane elements: ' + str(elements))
    words = elements//4
    packets = []
    for record in records:
        header = record['header']
        if header[1:5] != first[1:5] or int(header[5]) != 0:
            raise ValueError('Unequal/non-normal shape')
        ns, np, no, nc = map(int, header[8:12])
        if (ns, np, no, nc) != (words*heads, tokens*(words+1), words*heads*tokens, words*heads):
            raise ValueError('Unexpected original body counts')
        data = [line.split() for line in record['body'][ns:ns+np]]
        if any(int(kind) != int(i % (words+1) != 0) for i, (kind, _) in enumerate(data)):
            raise ValueError('Packet order changed')
        packets.append([int(value, 16) for _, value in data])
    for token in range(tokens):
        coeffs = [lane[token*(words+1)] for lane in packets]
        if len(set(coeffs)) != 1 or coeffs[0] >> 32:
            raise ValueError('Unequal or wider-than-32-bit broadcast coefficients')


def selection(inputs, helper):
    # The accepted checker validates ALL 68 groups against original SoftFloat
    # bytes first. Selection below only remaps headers, never arithmetic bodies.
    helper.validate_corpus(inputs)
    generator = module(inputs/'corpus.py')
    metadata = json.loads((generator.BASE/'vectors/vectors.json').read_text())
    records = generator.records((generator.BASE/'vectors/vectors.txt').read_text(), metadata['cases_by_id'])
    manifest = json.loads((inputs/'corpus.json').read_text())
    chosen, rejected = [], []
    for group in manifest['groups']:
        if group['elements'] in (1, 3, 31):
            rejected.append(dict(source=group['id'], elements=group['elements'],
                                 reason='unsupported partial per-lane shape; no padding'))
            continue
        if group['elements'] not in (16, 24, 32):
            raise ValueError('Unexpected source geometry')
        names = group['source_names']
        variants = [names] if group['id'] < 3 else [[name]*4 for name in dict.fromkeys(names)]
        for variant, lane_names in enumerate(variants):
            require_broadcast([records[name] for name in lane_names])
            chosen.append(dict(source=group['id'], variant=variant, no_stalls=0, names=lane_names))
    if len(chosen) != 63 or len(rejected) != 35:
        raise ValueError('Unexpected supported/rejected source selection')
    chosen += [dict(row, no_stalls=1) for row in chosen[:3]]
    texts = [f'50565531 {len(chosen)}\n' for _ in range(4)]
    expected = dict(cases=len(chosen), lanes=[], groups=[], context=[], mapping=[],
                    excluded=rejected, real_groups=3, real_lane_cases=12)
    for cid, item in enumerate(chosen):
        flags = 0
        h = records[item['names'][0]]['header']
        elements, heads, tokens, rm = map(int, h[1:5])
        for lane, name in enumerate(item['names']):
            record = records[name]
            header = record['header'][:]
            header[0] = str(cid)
            texts[lane] += ' '.join(header)+'\n'+'\n'.join(record['body'])+'\n'
            ns, np, no, nc = map(int, header[8:12])
            f = int(header[12], 16)
            flags |= f
            expected['lanes'].append(dict(id=cid, lane=lane, seeds=ns, packets=np,
                                         issued=no, returned=no, writes=nc, acks=nc, flags=f))
        expected['groups'].append(dict(id=cid, flags=flags))
        expected['mapping'].append(dict(id=cid, **item, elements=elements, heads=heads, tokens=tokens, rm=rm))
        reads = tokens*(elements//4)
        expected['context'].append(dict(id=cid, source=item['source'], variant=item['variant'],
            no_stalls=item['no_stalls'], reads=reads, coefficients=tokens, values=reads,
            fills=4*reads, latency=reads))
    schedule = ''.join(f"{r['id']} {r['source']} {r['variant']} {r['no_stalls']}\n" for r in expected['mapping'])
    return expected, {**{f'lane{l}.txt': text for l, text in enumerate(texts)}, 'schedule.txt': schedule}


TIME_KEYS = ('id', 'launch', 'first_coeff', 'first_read', 'last_read', 'first_fma', 'last_fma',
             'last_return', 'coeff_span', 'fma_span', 'first_seed', 'last_seed', 'first_write',
             'last_write', 'last_ack', 'reader_done', 'cluster_done', 'drain', 'stream_stalls')
LANE_TIME_KEYS = ('id', 'lane', 'ready_stalls', 'preowner_stalls', 'owned_stalls', 'owned_cycles', 'native_cycles')


def check_context(text, expected, helper):
    rows = helper.parse_rows(text, 'PV_CONTEXT_CASE', tuple(expected['context'][0]))
    if rows != expected['context']:
        raise ValueError('Reader/context case ledger mismatch')
    want_total = dict(cases=expected['cases'], **{key: sum(r[key] for r in rows)
                       for key in ('reads', 'coefficients', 'fills', 'latency')})
    if helper.parse_rows(text, 'PV_CONTEXT_PASS', tuple(want_total)) != [want_total]:
        raise ValueError('Reader/context total ledger mismatch')
    times = helper.parse_rows(text, 'PV_CONTEXT_TIME', TIME_KEYS)
    lanes = helper.parse_rows(text, 'PV_CONTEXT_LANE_TIME', LANE_TIME_KEYS)
    starts = helper.parse_rows(text, 'PV_CONTEXT_START', ('id', 'owned', 'gate', 'ready'))
    firsts = helper.parse_rows(text, 'PV_CONTEXT_FIRST_FMA', ('id', 'owned', 'gate', 'ready'))
    ids = list(range(expected['cases']))
    if any([r['id'] for r in data] != ids for data in (times, starts, firsts)) or (
            [(r['id'], r['lane']) for r in lanes] != [(i, l) for i in ids for l in range(4)]):
        raise ValueError('Missing/duplicate/out-of-order diagnostic record')
    for t, row, start, first in zip(times, rows, starts, firsts):
        if not (t['launch'] < t['first_coeff'] < t['first_read'] <= t['last_read'] <= t['reader_done'] < t['cluster_done'] < t['drain'] and
                t['first_coeff'] <= t['first_fma'] <= t['last_fma'] <= t['last_return'] <= t['first_write'] <= t['last_write'] <= t['last_ack'] <= t['cluster_done'] and
                t['launch'] < t['first_seed'] <= t['last_seed'] <= t['last_fma'] and
                t['coeff_span'] == t['last_return']-t['first_coeff']+1 and
                t['fma_span'] == t['last_return']-t['first_fma']+1):
            raise ValueError('Invalid diagnostic interval/order')
        if any(r[k] > 15 for r in (start, first) for k in ('owned', 'gate', 'ready')):
            raise ValueError('Bad ownership/gate snapshot')
        if row['no_stalls'] and (start['gate'] != 15 or first['gate'] != 15):
            raise ValueError('Diagnostic replay injected gate stall')
    for lane in lanes:
        if (lane['ready_stalls'] != lane['preowner_stalls']+lane['owned_stalls'] or
                min(lane['owned_cycles'], lane['native_cycles']) <= 0):
            raise ValueError('Invalid ownership/native interval counters')
    return dict(context=rows, context_totals=want_total, times=times, lane_times=lanes,
                coefficient_start=starts, first_fma_state=firsts)


def check_log(text, expected, helper):
    return dict(**helper.check_log(text, expected, 0), **check_context(text, expected, helper))


def check_selected(inputs, helper):
    expected, files = selection(inputs/'upstream', helper)
    for name, wanted in files.items():
        if (inputs/name).read_text() != wanted:
            raise ValueError('Selected original body/header remap changed: '+name)
    return expected


def prepare(out):
    helper = upstream()
    out.mkdir(exist_ok=False)
    inputs = out/'inputs'
    inputs.mkdir()
    pins = {}
    fp_pins = admission(FP, helper, pins)
    reader_pins = admission(READER, helper, pins)
    # Copy only explicit accepted inputs. Inherited live docs stay pinned, too.
    names = ('run.py', 'test_run.py', 'test_corpus.py', 'corpus.py', 'corpus.json',
             'lane0.txt', 'lane1.txt', 'lane2.txt', 'lane3.txt', 'sources.f', 'README.md',
             'tb.sv', 'adapter.sv', 'vmfpu_baseline.sv', 'akv_resident_pv_lane.sv',
             'akv_resident_pv_group.sv', 'resident_payload_fanout.sv', 'akv_resident_pv_cluster.sv')
    for name in names:
        source = FP/'inputs'/name
        helper.copy_pin(source, inputs/'upstream'/name, pins, fp_pins[str(source)])
    source = READER/'inputs/akv_resident_pv_reader.sv'
    helper.copy_pin(source, inputs/source.name, pins, reader_pins[str(source)])
    for name in LOCAL:
        helper.copy_pin(HERE/name, inputs/name, pins)
    # All context dependencies must be identical to the reader's admitted chain.
    for name, digest in reader_pins.items():
        if name.startswith(str(helper.FROZEN_SOURCE)+'/') and fp_pins.get(name) != digest:
            raise ValueError('Reader/FP frozen dependency disagreement: '+name)
    selected, directories = helper.frozen_filelist((inputs/'upstream/sources.f').read_text(), fp_pins)
    merge(pins, selected)
    expected, files = selection(inputs/'upstream', helper)
    # TARGET_VERILATOR is an unused inherited define, not a tool invocation.
    # Remove it for the VCS successor, as in the accepted reader gate.
    files['sources.f'] = ''.join(line+'\n' for line in (inputs/'upstream/sources.f').read_text().splitlines()
                                 if line != '+define+TARGET_VERILATOR')
    for name, value in files.items():
        with (inputs/name).open('x') as stream:
            stream.write(value)
        (inputs/name).chmod(0o444)
        pins[str(inputs/name)] = helper.sha(inputs/name)
    helper.save(out/'expected.json', expected)
    vcs = shutil.which('vcs')
    if not vcs:
        raise ValueError('Host VCS missing')
    import subprocess
    branch = subprocess.check_output(['git', '-C', str(OUT.parents[1]), 'branch', '--show-current'], text=True).strip()
    if branch != 'ara_dsa_signoff_integration':
        raise ValueError('Wrong signoff branch')
    config = dict(vcs=vcs, shared_fma=0, compile_seconds=600, simulation_seconds=180,
                  include_directories=directories, signoff_branch=branch,
                  admitted_fp=str(FP), admitted_reader=str(READER), parent_review_required=True)
    helper.save(out/'selection.json', config)
    for path in (out/'expected.json', out/'selection.json', Path(vcs).resolve()):
        pins[str(path)] = helper.sha(path)
    helper.verify(pins)
    helper.save(out/'source-pins.json', pins)
    helper.save(out/'source-pins-before.json', pins)
    helper.save(out/'prepared.json', dict(state='PREPARED_NOT_EXECUTED', cases=expected['cases'],
        issued=sum(r['issued'] for r in expected['lanes']), parent_review_required=True))


def artifacts(out, helper):
    # Explicit closed-file allowlist: never hash service stdout, whatever its name.
    names = ('expected.json', 'selection.json', 'prepared.json', 'source-pins.json',
             'source-pins-before.json', 'source-pins-after.json', 'work/commands.json',
             'work/tests.log', 'work/compile.log', 'work/run.log', 'work/image-pins.json',
             'work/image-pins-after.json')
    return {str(out/name): helper.sha(out/name) for name in names if (out/name).is_file()}


def execute(out):
    helper = upstream()
    pins = json.loads((out/'source-pins.json').read_text())
    config = json.loads((out/'selection.json').read_text())
    inputs, work = out/'inputs', out/'work'
    work.mkdir(exist_ok=False)
    report = dict(state='FAIL', scope='Context/reader/four production VMFPUs; local diagnostics only',
                  complete_call_speedup=False, production_vrf_import=False, shared_fma=0)
    try:
        helper.verify(pins)
        helper.verify_directories(config['include_directories'])
        expected = check_selected(inputs, helper)
        if expected != json.loads((out/'expected.json').read_text()):
            raise ValueError('Prepared selection changed')
        compile_cmd = [config['vcs'], '-full64', '-sverilog', '-timescale=1ns/1ps',
            '-top', 'resident_pv_context_fp_tb', '-j8', '-o', 'simv', '+define+SIMULATION',
            '+define+ARA_SHARED_SIMD_MUL', '+define+RESIDENT_TEST_SHARED_FMA=0',
            '-f', str(inputs/'sources.f'), *[str(inputs/'upstream'/name) for name in (
                'vmfpu_baseline.sv', 'akv_resident_pv_lane.sv', 'adapter.sv',
                'akv_resident_pv_group.sv', 'resident_payload_fanout.sv', 'akv_resident_pv_cluster.sv')],
            str(inputs/'akv_resident_pv_reader.sv'), str(inputs/'tb.sv')]
        sim_cmd = [str(work/'simv'), '-no_save', '+CORPUS='+str(inputs)]
        test_cmd = [sys.executable, '-B', str(inputs/'test_run.py')]
        helper.save(work/'commands.json', dict(tests=test_cmd, compile=compile_cmd, run=sim_cmd))
        helper.command(test_cmd, inputs, work/'tests.log', 60)
        print('PV_CONTEXT_FP_COMPILING '+str(out), flush=True)
        helper.command(compile_cmd, work, work/'compile.log', config['compile_seconds'])
        helper.verify(pins)
        helper.verify_directories(config['include_directories'])
        image = {str(p): helper.sha(p) for p in (work/'simv.daidir').rglob('*') if p.is_file()}
        image[str(work/'simv')] = helper.sha(work/'simv')
        helper.save(work/'image-pins.json', image)
        print('PV_CONTEXT_FP_RUNNING '+str(out), flush=True)
        text = helper.command(sim_cmd, work, work/'run.log', config['simulation_seconds'])
        checked = check_log(text, expected, helper)
        helper.verify(pins)
        helper.verify(image)
        helper.verify_directories(config['include_directories'])
        helper.save(out/'source-pins-after.json', pins)
        helper.save(work/'image-pins-after.json', image)
        report.update(state='PASS', post_pins_match=True, post_image_match=True, **checked)
    except Exception as exc:
        report['error'] = str(exc)
    report['artifacts'] = artifacts(out, helper)
    helper.save(out/'report.json', report)
    print('PV_CONTEXT_FP_'+report['state']+' '+str(out/'report.json'), flush=True)
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
            parser.error('Execution requires parent review and the frozen runner')
        return execute(out)
    prepare(out)
    print('PV_CONTEXT_FP_PREPARED_NOT_EXECUTED '+str(out), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
