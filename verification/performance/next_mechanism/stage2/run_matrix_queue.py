#!/usr/bin/env python3
"""Fresh queue=0/16 engine gate against immutable historical matched images."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import time

sys.dont_write_bytecode = True
import check_matrix_v2 as checker

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = checker.ORIGINAL.parent
HISTORICAL = OUT / 'stage2_matrix_qwen3_vcs_20261109_01'
COMPUTE = Path('hardware/src/vlsu/qbs/qbs_compute_engine.sv')
FIFO = Path('hardware/deps/common_cells/src/fifo_v3.sv')
LOCAL = ('run_matrix_queue.py', 'matrix_queue_probe.sv', 'matrix_queue_vectors.c', 'test_matrix_queue.py')
PROBE = '''
  localparam int Stage2QueueDepth = `STAGE2_QUEUE_DEPTH;
  defparam dut.i_engine.i_compute_engine.IntegerResultQueueDepth = Stage2QueueDepth;
`define QUEUE_DUT dut.i_engine.i_compute_engine
  stage2_matrix_queue_probe #(.QueueDepth(Stage2QueueDepth)) queue_probe (
    .clk_i(clk), .rst_ni(rst_n), .command_fire_i(command_valid && command_ready),
    .success_i(success_valid), .fault_i(fault_valid),
    .m_i(`QUEUE_DUT.m_q), .n_i(`QUEUE_DUT.n_q), .profile_i(`QUEUE_DUT.weight_profile_q),
    .k_blocks_i(`QUEUE_DUT.k_blocks_q), .seeded_i(`QUEUE_DUT.seeded_q),
    .enabled_i(`QUEUE_DUT.integer_queue_enabled), .push_i(`QUEUE_DUT.integer_queue_push),
    .pop_i(`QUEUE_DUT.integer_queue_pop), .occupancy_i(32'(`QUEUE_DUT.integer_queue_occupancy)),
    .data_i(`QUEUE_DUT.integer_result_data), .data_o(`QUEUE_DUT.fp_request_data),
    .fp_valid_i(`QUEUE_DUT.fp_request_valid), .fp_ready_i(`QUEUE_DUT.fp_request_ready),
    .final_drain_i(`QUEUE_DUT.phase_drain_o), .fault_drain_i(`QUEUE_DUT.fault_i),
    .start_valid_i(`QUEUE_DUT.integer_start_valid), .start_ready_i(`QUEUE_DUT.integer_start_ready),
    .contexts_i(`QUEUE_DUT.i_profile_engine_int.context_valid_q),
    .result_pending_i((|`QUEUE_DUT.i_profile_engine_int.result_pending_q[0]) ||
                      (|`QUEUE_DUT.i_profile_engine_int.result_pending_q[1])),
    .fp_occupancy_i(`QUEUE_DUT.i_fp_accumulator.entry_occupancy)
  );
`undef QUEUE_DUT
'''


def check_queue_log(text, depth):
    old = checker.legacy()
    def rows(prefix):
        result = [old.fields(line) for line in text.splitlines() if line.startswith(prefix + ' ')]
        if any(not isinstance(v, int) or v < 0 for row in result for v in row.values()):
            raise ValueError('Non-numeric queue probe')
        return result
    commands, resets, done = rows('STAGE2_QUEUE_COMMAND'), rows('STAGE2_QUEUE_RESET'), rows('STAGE2_QUEUE_DONE')
    command_keys = set('seq depth enabled m n profile kb success fault enq deq fp_accept max_occ full decoupled start_overlap final_drain fault_drain start_blocked ctx0 ctx1 ctx2 ctx3 pending fp_full queue_full'.split())
    if any(set(row) != command_keys for row in commands) or any(set(row) != set('seq enq deq flushed'.split()) for row in resets) or any(set(row) != set('commands enq deq resets reset_flushed depth'.split()) for row in done):
        raise ValueError('Malformed queue record schema')
    if len(done) != 1 or not commands:
        raise ValueError('Missing queue terminal/work records')
    terminal, = done
    if terminal['commands'] != len(commands) or terminal['resets'] != len(resets) or terminal['depth'] != depth:
        raise ValueError('Queue terminal geometry')
    if {r['seq'] for r in commands + resets} != set(range(1, len(commands) + len(resets) + 1)):
        raise ValueError('Missing/duplicate queue command/reset')
    for row in commands:
        enabled = int(depth > 0 and (row['m'], row['profile']) == (8, 1))
        if row['depth'] != depth or row['enabled'] != enabled or row['enq'] != row['deq'] or row['max_occ'] > depth:
            raise ValueError('Queue work/drain accounting')
        if row['success'] + row['fault'] != 1:
            raise ValueError('Ambiguous queue command terminal')
        if row['success'] and (row['fp_accept'] != row['m'] * row['n'] * row['kb'] or row['enq'] != enabled * row['fp_accept']):
            raise ValueError('Queue changed successful FP work')
        if sum(row[f'ctx{i}'] for i in range(4)) != row['start_blocked']:
            raise ValueError('Context-start blocked classification')
        if not enabled and any(row[k] for k in ('enq', 'deq', 'max_occ', 'full', 'decoupled', 'start_overlap', 'final_drain', 'fault_drain')):
            raise ValueError('Non-cooperative/fallback path used FIFO')
    for row in resets:
        if row['enq'] - row['deq'] != row['flushed']:
            raise ValueError('Reset FIFO ledger')
    for key in ('enq', 'deq'):
        if sum(r[key] for r in commands + resets) != terminal[key]:
            raise ValueError('Lost queue counts across commands/reset')
    if terminal['enq'] != terminal['deq'] + terminal['reset_flushed'] or sum(r['flushed'] for r in resets) != terminal['reset_flushed']:
        raise ValueError('Undrained FIFO work')
    return dict(commands=commands, totals=terminal)


def prepare(out):
    old = checker.legacy()
    if out.parent != OUT:
        raise ValueError('Use a new direct signoff out child')
    historical_report = json.loads((HISTORICAL / 'report.json').read_text())
    if historical_report['state'] != 'PASS' or not historical_report['source_image_data_post_match']:
        raise ValueError('Historical matched engine baseline not PASS')
    out.mkdir(exist_ok=False)
    snapshot, pins = out / 'inputs', {}

    def copy(source, target, expected=None):
        digest = checker.sha(source)
        if expected is not None and digest != expected:
            raise ValueError('Archived baseline identity drift: ' + str(source))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if checker.sha(target) != digest:
            raise ValueError('Copy race: ' + str(source))
        pins[str(source)] = pins[str(target)] = digest

    original_manifest = json.loads((checker.ORIGINAL / 'source-pins.json').read_text())
    archived = {p: h for p, h in original_manifest.items() if Path(p).is_relative_to(checker.ORIGINAL)}
    old.verify(archived)
    pins.update(archived)
    for source in sorted((checker.ORIGINAL / 'inputs').rglob('*')):
        if source.is_file():
            rel = source.relative_to(checker.ORIGINAL / 'inputs')
            if rel != COMPUTE:
                copy(source, snapshot / rel, original_manifest[str(source)])
    # Only this fresh production module differs from the historical composition.
    copy(ROOT / COMPUTE, snapshot / COMPUTE)
    copy(ROOT / FIFO, snapshot / FIFO)
    local = snapshot / HERE.relative_to(ROOT)
    for name in LOCAL:
        copy(HERE / name, local / name)
    copy(HISTORICAL / 'inputs' / HERE.relative_to(ROOT) / 'check_matrix_v2.py', local / 'check_matrix_v2.py')
    copy(checker.ORIGINAL / 'matrix_engine.sv', out / 'matrix_engine.sv')
    bench = (checker.ORIGINAL / 'matrix_tb.sv').read_text()
    adapted = old.once(bench, '  qbs_engine_composed #(\n', PROBE + '  qbs_engine_composed #(\n')
    if old.once(adapted, PROBE, '') != bench:
        raise ValueError('Original checker changed')
    (out / 'matrix_tb.sv').write_text(adapted)
    historical_images = json.loads((checker.ORIGINAL / 'report.json').read_text())['images']
    for arm, image in historical_images.items():
        for source, digest in image.items():
            copy(Path(source), out / 'historical_images' / arm / Path(source).relative_to(checker.ORIGINAL / arm), digest)
    for path in (HISTORICAL / 'report.json', HISTORICAL / 'source-pins.json', HISTORICAL / 'source-pins-after.json'):
        pins[str(path)] = checker.sha(path)
    prior_selection = json.loads((HISTORICAL / 'selection.json').read_text())
    vectors = {}
    for view, slices in prior_selection['vectors'].items():
        for name, data in slices.items():
            source = Path(data['candidate'])
            target = out / f'{view}_{name}.txt'
            copy(source, target)
            vectors[f'{view}_{name}'] = str(target)
    for name in ('synthetic', 'context'):
        copy(checker.ORIGINAL / f'{name}_candidate.txt', out / f'{name}.txt')
        vectors[name] = str(out / f'{name}.txt')
    deadline = time.monotonic() + 180
    cc, vcs = shutil.which('cc'), shutil.which('vcs')
    if not cc or not vcs:
        raise ValueError('Host C compiler and VCS required')
    program = out / 'matrix_queue_vectors'
    old.command([cc, '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror', '-pedantic', '-ffp-contract=off', '-frounding-math',
                 '-I' + str(snapshot / 'apps/common'), local / 'matrix_queue_vectors.c',
                 snapshot / 'verification/qbs/qbs_ref.c', '-lm', '-o', program], out, out / 'oracle-build.log', deadline)
    original = out / 'minimal_original.txt'
    old.command([program, original], out, out / 'oracle-run.log', deadline)
    updated, _ = old.candidate_vector(original.read_text())
    (out / 'minimal.txt').write_text(updated)
    vectors['minimal'] = str(out / 'minimal.txt')
    filelist = (checker.ORIGINAL / 'sources.f').read_text().replace(str(checker.ORIGINAL / 'inputs'), str(snapshot))
    filelist = filelist.replace(str(checker.ORIGINAL / 'matrix_engine.sv'), str(out / 'matrix_engine.sv')).replace(str(checker.ORIGINAL / 'matrix_tb.sv'), str(out / 'matrix_tb.sv'))
    (out / 'sources.f').write_text(filelist + str(snapshot / FIFO) + '\n' + str(local / 'matrix_queue_probe.sv') + '\n')
    old.save(out / 'historical-baseline.json', dict(label='historical matched engine baseline, not current live root',
             accepted_report=str(HISTORICAL / 'report.json'), source_archive=str(checker.ORIGINAL / 'inputs'),
             images=historical_images, archived_source_pins=archived,
             accepted_paired_cycles=historical_report['paired_cycles'],
             old_live_root_audit_reused=False))
    old.save(out / 'selection.json', dict(local=str(local), vcs=vcs, vectors=vectors, timeout_seconds=7200,
             configurations=[0, 16], historical=str(HISTORICAL), scope='engine_not_soc',
             queue_entry_bits=140, numerical_expectations_changed=False))
    old.command([sys.executable, '-B', local / 'test_matrix_queue.py', '--prepared', out], out, out / 'host-tests.log', deadline, 60)
    for path in (Path(vcs).resolve(), Path(cc).resolve(), Path(sys.executable).resolve(), *out.glob('*')):
        if path.is_file():
            pins[str(path)] = checker.sha(path)
    old.verify(pins)
    old.save(out / 'source-pins.json', pins)
    old.save(out / 'prepared.json', dict(state='PREPARED_NOT_EXECUTED', frozen_runner=str(local / 'run_matrix_queue.py'),
             source_pins_sha256=checker.sha(out / 'source-pins.json'), baseline='historical matched engine baseline',
             fresh_depths=[0, 16]))
    print(local / 'run_matrix_queue.py', flush=True)


def execute(out):
    old = checker.legacy()
    config = json.loads((out / 'selection.json').read_text())
    if Path(__file__).resolve() != Path(config['local']) / 'run_matrix_queue.py':
        raise ValueError('Use frozen worker')
    pins = json.loads((out / 'source-pins.json').read_text())
    deadline = time.monotonic() + config['timeout_seconds']
    report = dict(state='FAIL', runs={}, images={}, baseline='historical matched engine baseline', retries=0)
    try:
        old.verify(pins)
        for depth in config['configurations']:
            work = out / f'q{depth}'
            work.mkdir(exist_ok=False)
            argv = [config['vcs'], '-full64', '-sverilog', '-timescale=1ns/1ps', '-j4', '+lint=TFIPC-L',
                    '-top', 'qbs_engine_tb', '-o', 'simv', '+define+STAGE2_COOPERATIVE_WAVES=1',
                    f'+define+STAGE2_QUEUE_DEPTH={depth}', '-f', out / 'sources.f']
            old.save(work / 'compile-command.json', list(map(str, argv)))
            old.save(out / 'status.json', dict(state='RUNNING', phase='compile', depth=depth))
            print(f'STAGE2_QUEUE_COMPILING depth={depth}', flush=True)
            old.command(argv, work, work / 'compile.log', deadline)
            report['images'][str(depth)] = old.image_pins(work)
            if str(work / 'simv') not in report['images'][str(depth)]:
                raise ValueError('Missing fresh image')
            old.save(work / 'image-pins.json', report['images'][str(depth)])
            old.verify(pins)
        order = ['minimal', *[f'{view}_{name}' for view in ('attn_q', 'ffn_gate') for name, *_ in old.SLICES], 'context', 'synthetic']
        for suite in order:
            for depth in config['configurations']:
                work = out / f'q{depth}'
                vector = Path(config['vectors'][suite])
                argv = [work / 'simv', '-no_save', '+QBS_COMMAND_VECTOR_FILE=' + str(vector)]
                if suite != 'synthetic':
                    argv += ['+QBS_FUNCTIONAL_ONLY', '+QBS_FP_PROBE']
                if suite == 'context':
                    argv += ['+QBS_CONTEXT_SUITE']
                old.verify(pins)
                old.verify(report['images'][str(depth)])
                old.save(work / f'{suite}-command.json', list(map(str, argv)))
                old.save(out / 'status.json', dict(state='RUNNING', phase=suite, depth=depth))
                print(f'STAGE2_QUEUE_RUNNING {suite} depth={depth}', flush=True)
                old.command(argv, work, work / f'{suite}.log', deadline, 900)
                text = (work / f'{suite}.log').read_text()
                result = checker.check_log(text, old.vectors(vector.read_text()), 1, suite)
                result['queue'] = check_queue_log(text, depth)
                old.verify(pins)
                old.verify(report['images'][str(depth)])
                report['runs'][f'{suite}_q{depth}'] = result
                old.save(out / 'progress.json', report)
                print(f'STAGE2_QUEUE_CHECKED {suite} depth={depth}', flush=True)
        historical = json.loads((HISTORICAL / 'report.json').read_text())
        for view in ('attn_q', 'ffn_gate'):
            for name, *_ in old.SLICES:
                current = report['runs'][f'{view}_{name}_q0']
                if current['cycles'] != historical['runs'][f'{view}_{name}_candidate']['cycles']:
                    raise ValueError('Fresh queue=0 did not reproduce historical cooperative timing')
        eligible = [row for key, result in report['runs'].items() if key.endswith('_q16') for row in result['queue']['commands'] if row['enabled']]
        for field in ('decoupled', 'start_overlap', 'final_drain', 'fault_drain'):
            if sum(row[field] for row in eligible) == 0:
                raise ValueError('Missing actual queue effect/drain coverage: ' + field)
        report['paired_cycles'] = {view: {str(depth): {m: sum(report['runs'][f'{view}_{m}{half}_q{depth}']['cycles'][0] for half in ('a', 'b'))
                                      for m in ('m4', 'm8')} for depth in config['configurations']} for view in ('attn_q', 'ffn_gate')}
        old.verify(pins)
        for image in report['images'].values():
            old.verify(image)
        old.save(out / 'source-pins-after.json', pins)
        report.update(state='PASS', source_image_post_match=True, fresh_q0_matches_historical=True,
                      scope='engine_not_soc; no SoC/CPU/model acceptance')
    except Exception as exc:
        report['error'] = str(exc)
    report['artifacts'] = {str(p): checker.sha(p) for p in out.rglob('*') if p.is_file() and
                           p.suffix in ('.log', '.json') and p.name not in ('report.json', 'status.json', 'service.log')}
    old.save(out / 'report.json', report)
    old.save(out / 'status.json', dict(state=report['state'], error=report.get('error'), report=str(out / 'report.json')))
    print('STAGE2_QUEUE_' + report['state'] + ' ' + str(out / 'report.json'), flush=True)
    return int(report['state'] != 'PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if args.execute:
        raise SystemExit(execute(args.output.resolve()))
    prepare(args.output.resolve())
