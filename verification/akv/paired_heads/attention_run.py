#!/usr/bin/env python3
"""Bounded build03 derived-GQA2 ABBA worker; no build and no prerequisite polling.

Run foreground under a direct-owned systemd service. Generic AKV OFF is NOT
ordinary RVV; this is a mechanism comparison, not production deployment proof.
"""
import argparse
import os
from pathlib import Path
import re
import signal
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))
from run_qk_panel4_abba import (checked_image, merge_pins, verify_pins, read_json,
                               require, totals)
from run_half_scale_soc import atomic_json, digest, hashes, image_files, script_files, check_result
from run_tile_context_engine import run_command
from run_refill_overlap_probe import numeric_fields, PERF_FIELDS, SUMMARY_FIELDS

MODES = (0, 1, 1, 0)
SUBSET = 'AKV_PAIR_SUBSET source=qwen25_kv128 qheads=0,1,6,7 kvheads=0,1 outputs=512 derived=1'
BEGIN = re.compile(r'AKV_PAIR_TRIAL_BEGIN trial=([0-3]) paired=([01])')
END = re.compile(r'AKV_PAIR_ATTENTION trial=([0-3]) paired=([01]) admitted_groups=([02]) '
                 r'native=1 kv=128 outputs=512 cycles=([1-9][0-9]*) fcsr=([0-9]+) vcsr=5 '
                 r'checksum=([0-9a-f]{16}) guardbytes=384 errors=0')
SUITE = 'AKV_PAIR_ABBA_PASS trials=4 outputs_per_trial=512 bytewise_equal=1 guards=1 derived_subset=1'
TERMINAL = 'Core Test *** SUCCESS *** (tohost = 0)'
EXPECTED = dict(trials=4, modes=[0, 1, 1, 0], outputs_per_trial=512, commands=3864,
    off=dict(commands=1542, column_load=1024, column_panel=0, row_load=512, replay_bytes=262144),
    on=dict(commands=390, column_load=128, column_panel=128, row_load=256, replay_bytes=131072),
    per_trial=dict(v2_full=2, v2_refill=2, release=2, q_external_bytes=1024,
                   kv_external_bytes=131072, read_payload_bytes=132224, read_ranges=518))


def commands(mode):
    tile = [6]*(32 if mode else 256) + [2]*(64 if mode else 128)
    return ([4] + tile + [5] + tile + [3])*2


SEQUENCES = tuple(commands(m) for m in (0, 1))


def check_record(row, command, mode, seq):
    col, pv = int(command == 6), int(command == 2)
    logical = col*(4 if mode else 1)
    expected = dict(seq=seq, command=command, success=1, fault=0, validation_fault=0,
        validation_error=0, read_fault=0, context_ready=int(command != 3),
        full=0, refill=0, load=pv, release=int(command == 3), v2_full=int(command == 4),
        v2_refill=int(command == 5), v2_row_load=pv, v2_column_load=col,
        v2_column_panel=col*mode, v2_logical_column=logical, v2_k_view_bank_cycles=8*col,
        v2_bank_conflict_cycles=0, v2_rejected=0, translations=0,
        q_external_bytes=512 if command == 4 else 0,
        kv_external_bytes=32768 if command in (4, 5) else 0,
        replay_bytes=128*logical+256*pv,
        read_ranges={4: 131, 5: 128}.get(command, 0),
        read_payload_bytes={4: 33344, 5: 32768}.get(command, 0))
    require(all(row[k] == v for k, v in expected.items()), f'Command {seq}: work/sequence/fault mismatch')
    require(row['id'] < 8 and row['busy_cycles'] > 0 and row['read_outstanding_max'] <= 2,
            'Invalid VID/cycles/outstanding count')
    if command in (4, 5):
        require(row['ar'] >= row['read_ranges'] and row['r_beats'] >= row['ar'] and
                row['read_outstanding_max'] > 0, 'Missing FULL/REFILL traffic')
    else:
        require(all(row[k] == 0 for k in ('ar', 'r_beats', 'read_outstanding_occ_sum',
                    'read_outstanding_max', 'read_outstanding_full_cycles')), 'Unexpected local-command AXI reads')


def check_log(text):
    records, trials, group = [], [], []
    active = subset = suite = terminal = False
    summary = None
    severity = set()
    for line in text.splitlines():
        require(not re.search(r'Fatal:|Error:|\b(?:FAIL|FAILED|TIMEOUT)\b', line, re.I), 'Failure text')
        if 'UVM_ERROR' in line or 'UVM_FATAL' in line:
            m = re.fullmatch(r'(UVM_ERROR|UVM_FATAL)\s*:\s*0', line)
            require(m is not None and m[1] not in severity, 'UVM error/fatal or duplicate summary')
            severity.add(m[1])
        if 'Core Test' in line:
            require(line == TERMINAL and suite and not terminal, 'Missing/excess/malformed core success')
            terminal = True
        if 'QBS_PERF' in line and not line.startswith('Command:'):
            raise ValueError('Unexpected QBS work')
        if 'AKV_PERF' in line and not line.startswith('Command:'):
            if line.startswith('[AKV_PERF] '):
                require(active and not suite, 'Command outside trial')
                mode = MODES[len(trials)]
                sequence = SEQUENCES[mode]
                require(len(group) < len(sequence), 'Extra trial command')
                row = numeric_fields(line[len('[AKV_PERF] '):], PERF_FIELDS)
                check_record(row, sequence[len(group)], mode, len(records)+1)
                group.append(row)
                records.append(row)
            elif line.startswith('[AKV_PERF_SUMMARY] '):
                require(suite and not active and summary is None, 'Premature/duplicate hardware summary')
                summary = numeric_fields(line[len('[AKV_PERF_SUMMARY] '):], SUMMARY_FIELDS)
            else:
                raise ValueError('Unknown/malformed AKV metric-prefixed line')
        if 'AKV_PAIR_' in line:
            begin, end = BEGIN.fullmatch(line), END.fullmatch(line)
            if line == SUBSET:
                require(not subset and not trials and not active, 'Duplicate/misplaced subset declaration')
                subset = True
            elif begin:
                i = len(trials)
                require(subset and not active and not suite and i < 4 and
                        (int(begin[1]), int(begin[2])) == (i, MODES[i]), 'ABBA order/nesting')
                active, group = True, []
            elif end:
                i = len(trials)
                require(active and (int(end[1]), int(end[2]), int(end[3])) == (i, MODES[i], 2*MODES[i])
                        and len(group) == len(SEQUENCES[MODES[i]]), 'Incomplete/mismatched/admission trial')
                flags = int(end[5])
                require(flags <= 31, 'Invalid FCSR flags/FRM')
                t = totals(group)
                mode = MODES[i]
                variant = EXPECTED['on' if mode else 'off']
                expected = dict(EXPECTED['per_trial'], records=variant['commands'],
                    v2_column_load=variant['column_load'], v2_column_panel=variant['column_panel'],
                    v2_row_load=variant['row_load'], replay_bytes=variant['replay_bytes'],
                    v2_logical_column=512 if mode else 1024,
                    v2_k_view_bank_cycles=1024 if mode else 8192)
                require(all(t[k] == v for k, v in expected.items()), 'Trial geometry/work totals')
                require(int(end[4]) >= t['busy_cycles'], 'Measured cycles smaller than engine busy')
                trials.append(dict(trial=i, paired=mode, admitted_groups=int(end[3]),
                    cycles=int(end[4]), fcsr=flags, vcsr=5, checksum=end[6],
                    derived_hardware_totals=t))
                active = False
            elif line == SUITE:
                require(subset and not active and len(trials) == 4 and not suite, 'Premature/duplicate suite PASS')
                suite = True
            else:
                raise ValueError('Unknown/malformed program marker')
    require(subset and suite and terminal and not active and len(records) == 3864 and
            severity == {'UVM_ERROR', 'UVM_FATAL'}, 'Incomplete execution evidence')
    require(summary == totals(records), 'Raw summary differs from record sums/max')
    require(len({(t['checksum'], t['fcsr'], t['vcsr']) for t in trials}) == 1, 'Output bits/status differ across ABBA')
    external = ('ar', 'r_beats', 'q_external_bytes', 'kv_external_bytes', 'read_ranges', 'read_payload_bytes')
    require(all(len({t['derived_hardware_totals'][k] for t in trials}) == 1 for k in external),
            'External traffic differs across same-ELF modes')
    sums = {str(m): sum(t['cycles'] for t in trials if t['paired'] == m) for m in (0, 1)}
    return dict(state='PASS', trials=trials, raw_hardware_summary=summary, sums=sums,
        attention_speedup=sums['0']/sums['1'], cycle_reduction_percent=100*(1-sums['1']/sums['0']),
        provenance='Derived GQA2 subset of Qwen2.5 KV128 capture: Q heads0,1,6,7; not a Qwen3 Decode capture',
        comparison='Paired ON versus generic AKV OFF mechanism gain only; NOT ordinary RVV or tiled baseline',
        scope='Same-ELF full plan/native Attention including query preparation and admission; not full model timing or deployment acceptance',
        accounting='Per-trial totals derived from actual records; only final raw summary is hardware-emitted.',
        deployment='Keep experimental; ordinary RVV same-subset baseline and benefit gates still required.')


def checked_build(build):
    report = read_json(build/'build.json')
    require(report.get('state') == 'BUILT_NOT_EXECUTED' and report.get('execution') == 'NOT_RUN' and
            report.get('post_pins_match') is True and report.get('expected') == EXPECTED and
            report.get('source_heads') == [0, 1, 6, 7] and report.get('source_kv_heads') == [0, 1] and
            report.get('tolerance') == dict(atol=.004, rtol=.002), 'Wrong build03 schema/geometry')
    require(digest(build/'source-pins.json') == report['source_pins_sha256'], 'Build source receipt drift')
    pins = read_json(build/'source-pins.json')
    merge_pins(pins, report['artifact_sha256'])
    elf = Path(report['elf']).resolve(strict=True)
    require(pins.get(str(elf)) == report['elf_sha256'] and digest(elf) == report['elf_sha256'], 'ELF identity')
    merge_pins(pins, hashes([build/'build.json', build/'source-pins.json']))
    verify_pins(pins)
    return report, pins


def checked_prerequisite(path, image):
    status, result = read_json(path/'status.json'), read_json(path/'result.json')
    require(status.get('state') == result.get('state') == 'PASS' and status.get('child_pid') is None,
            'Focused paired gate not terminal PASS; do not launch or wait')
    numeric = result.get('numeric', {})
    require(numeric.get('state') == 'PASS' and all(numeric.get(k) == v for k, v in
        dict(pairs=3, runs=6, qk_outputs=512, pv_outputs=1152).items()), 'Wrong focused numeric gate')
    hardware = result.get('hardware_totals', {})
    wanted = dict(records=1044, success_records=1044, fault_records=0, validation_fault_records=0,
        v2_full=6, release=6, v2_refill=0, v2_row_load=384, v2_column_load=648,
        v2_column_panel=72, v2_logical_column=864, q_external_bytes=2304,
        kv_external_bytes=147456, read_ranges=786, read_payload_bytes=150144, replay_bytes=196416)
    require(all(hardware.get(k) == v for k, v in wanted.items()), 'Wrong focused command/work gate')
    evidence = result['evidence_sha256']
    log, trace, uvm_path = (path/'work'/n for n in ('run.vcs.log', 'vector_trace.csv', 'uvm_result.json'))
    required = [path/'source-pins.json', log, trace, uvm_path]
    require(all(str(p) in evidence for p in required), 'Missing focused UVM/source evidence')
    verify_pins(evidence)
    pins = read_json(path/'source-pins.json')
    verify_pins(pins)
    elf = Path(status['elf']).resolve(strict=True)
    require(pins.get(str(elf)) == digest(elf) and
            str(Path(status['simv']).resolve()) in image, 'Focused ELF/image identity')
    check_result(uvm_path, digest(elf), image)
    uvm = read_json(uvm_path)
    require(uvm['log_sha256'] == digest(log) and uvm['vector_trace_sha256'] == digest(trace),
            'Focused UVM log/trace identity')
    merge_pins(pins, evidence)
    merge_pins(pins, hashes([path/'status.json', path/'result.json']))
    return pins


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('build', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--prerequisite', type=Path,
        default=ROOT/'verification/out/akv-paired-heads-rtl-run-20261023-01')
    parser.add_argument('--gate', type=Path, default=ROOT/'verification/out/qbacc-soc-accept-20261023-02')
    parser.add_argument('--integration', type=Path, default=ROOT/'verification/out/qbacc-soc-20261023-02')
    parser.add_argument('--timeout', type=int, default=10800)
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()
    require(1 <= args.timeout <= 10800, 'Timeout must be 1..10800 seconds')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    work = out/'work'
    work.mkdir()
    state = dict(state='PREFLIGHT', pid=os.getpid(), child_pid=None, timeout=args.timeout)
    def save():
        atomic_json(out/'status.json', state)
    def started(pid):
        state['child_pid'] = pid
        save()
    def interrupted(signum, _frame):
        raise InterruptedError(f'Signal {signum}')
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    env = dict(os.environ, PYTHONPATH=str(ROOT/'verification'), PYTHONDONTWRITEBYTECODE='1')
    env.pop('LLAMA_ATTN_SIM_L2_BYTES', None)
    env.pop('LD_PRELOAD', None)
    def run(command, log, timeout):
        command = list(map(str, command))
        atomic_json(log.with_suffix('.command.json'), dict(argv=command, cwd=str(log.parent)))
        try:
            require(run_command(command, log, timeout, env, started) == 0, 'Command failed: '+str(log))
        finally:
            state['child_pid'] = None
            save()
    save()
    try:
        build, gate, prerequisite = (p.resolve(strict=True) for p in (args.build, args.gate, args.prerequisite))
        simv = (args.integration/'build/sim/simv').resolve(strict=True)
        report, pins = checked_build(build)
        image, accepted = checked_image(gate, simv)
        require(report['simv'] == str(simv) and report['accepted_image_pins'] == image, 'Build/image mismatch')
        merge_pins(pins, accepted)
        merge_pins(pins, checked_prerequisite(prerequisite, image))
        contract = ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh'
        merge_pins(pins, hashes([Path(__file__).resolve(), HERE/'attention_run_test.py',
            HERE.parent/'run_qk_panel4_abba.py', HERE.parent/'run_refill_overlap_probe.py',
            ROOT/'verification/qbs/run_tile_context_engine.py', *script_files(),
            contract, Path(sys.executable).resolve()]))
        verify_pins(pins)
        atomic_json(out/'source-pins.json', pins)
        receipt_hash = digest(out/'source-pins.json')
        def manifest(stage):
            run([sys.executable, '-B', '-m', 'ara_verify.vcs_source_manifest', '--output',
                 simv.parent/'vcs_source_manifest.json', '--check'], out/(stage+'.log'), 300)
        manifest('manifest-before')
        elf = Path(report['elf'])
        run(['bash', contract, simv.parent, elf, 'akv_v2'], out/'image-contract.log', 180)
        verify_pins(pins)
        if args.preflight_only:
            state['state'] = 'PREFLIGHT_PASS_NOT_RUN'
            atomic_json(out/'result.json', dict(state=state['state'], source_pins_sha256=receipt_hash))
            return
        state.update(state='RUNNING', simv=str(simv), elf=str(elf))
        save()
        log, trace = work/'run.vcs.log', work/'vector_trace.csv'
        run([simv, '-no_save', '-l', log, '+PRELOAD='+str(elf), '+TESTCASE=akv_paired_heads_attention_abba',
             '+NO_FSDB', '+NO_INSTR_TRACE', '+AKV_PERF', '+AKV_SUMMARY',
             '+VECTOR_TRACE='+str(trace), '+COMMIT_TRACE='+str(work/'commit_trace.csv'),
             '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000'],
            work/'console.log', args.timeout)
        state['state'] = 'CHECKING'
        save()
        result = check_log(log.read_text())
        run([sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events', '--require-backend',
             '--require-axi', '--require-axi-write', '--vector-trace', trace, '--log', log,
             '--simv', simv, '--elf', elf, '--output', work/'uvm_result.json'], work/'checker.log', 600)
        check_result(work/'uvm_result.json', report['elf_sha256'], image)
        uvm = read_json(work/'uvm_result.json')
        require(uvm['log_sha256'] == digest(log) and uvm['vector_trace_sha256'] == digest(trace), 'UVM evidence identity')
        manifest('manifest-after')
        verify_pins(pins)
        require(hashes(image_files(simv)) == image and digest(out/'source-pins.json') == receipt_hash, 'Image/receipt drift')
        result['evidence_sha256'] = hashes([log, trace, work/'commit_trace.csv', work/'uvm_result.json',
            out/'source-pins.json', prerequisite/'result.json', gate/'result.json'])
        atomic_json(out/'result.json', result)
        state['state'] = 'PASS'
    except BaseException as exc:
        state.update(state='FAIL', error=repr(exc))
        atomic_json(out/'result.json', dict(state='FAIL', error=repr(exc)))
        raise
    finally:
        state['child_pid'] = None
        save()


if __name__ == '__main__':
    main()
