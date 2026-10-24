#!/usr/bin/env python3
"""Bounded same-ELF Attention ABBA, only after focused RTL and image acceptance.

Run this foreground owner under systemd; no prerequisite polling or detachment.
--preflight-only checks inputs without launching VCS. Never rebuilds an image.
"""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'verification/qbs'))
from run_half_scale_soc import atomic_json, digest, hashes, image_files, script_files, check_result
from run_tile_context_engine import run_command
from run_refill_overlap_probe import numeric_fields, PERF_FIELDS, SUMMARY_FIELDS, COUNTERS

BEGIN = re.compile(r'AKV_QK_TRIAL_BEGIN trial=([0-3]) panel4=([01])')
END = re.compile(r'AKV_QK_ATTENTION trial=([0-3]) panel4=([01]) native=1 kv=128 outputs=1536 '
                 r'cycles=([1-9][0-9]*) fcsr=3 vcsr=5 checksum=a7bc111334389dea errors=0')
SUITE = 'AKV_QK_ABBA_PASS trials=4 outputs_per_trial=1536 bytewise_equal=1 guards=1'
TERMINAL = 'Core Test *** SUCCESS *** (tohost = 0)'
MODES = (0, 1, 1, 0)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def unique_pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'Duplicate JSON field: ' + key)
        result[key] = value
    return result


def read_json(path):
    return json.loads(Path(path).read_text(), object_pairs_hook=unique_pairs,
                      parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))


def commands(mode):
    # Two KV heads, each FULL -> QK/PV -> REFILL -> QK/PV -> RELEASE.
    tile = [6] * (32 if mode else 128) + [2] * 64
    return ([4] + tile + [5] + tile + [3]) * 2


def totals(rows):
    result = {k: (max(r[k] for r in rows) if k == 'read_outstanding_max' else
                  sum(r[k] for r in rows)) for k in COUNTERS}
    result.update(records=len(rows), success_records=len(rows), fault_records=0,
                  validation_fault_records=0)
    return result


def check_record(r, command, mode, seq):
    column = int(command == 6)
    count = column * (4 if mode else 1)
    expected = dict(seq=seq, command=command, success=1, fault=0, validation_fault=0,
        validation_error=0, read_fault=0, context_ready=int(command != 3), full=0, refill=0,
        load=int(command == 2), release=int(command == 3), v2_full=int(command == 4),
        v2_refill=int(command == 5), v2_row_load=int(command == 2), v2_column_load=column,
        v2_column_panel=column*mode, v2_logical_column=count, v2_k_view_bank_cycles=column*8,
        v2_bank_conflict_cycles=0, v2_rejected=0,
        q_external_bytes=1536 if command == 4 else 0,
        kv_external_bytes=32768 if command in (4, 5) else 0,
        replay_bytes=256 if command == 2 else 128*count,
        read_ranges={4: 135, 5: 128}.get(command, 0),
        read_payload_bytes={4: 34368, 5: 32768}.get(command, 0))
    require(all(r[k] == v for k, v in expected.items()), f'Command {seq} work/lifecycle/fault mismatch')
    require(r['id'] < 8 and r['busy_cycles'] > 0 and r['read_outstanding_max'] <= 2,
            'VID/cycle/outstanding bound')
    require(r['translations'] == 0, 'Unexpected translated workload')
    if command in (4, 5):
        require(r['ar'] >= r['read_ranges'] and r['r_beats'] >= r['ar'] and
                r['read_outstanding_max'] > 0, 'Missing FULL/REFILL reads')
    else:
        require(all(r[k] == 0 for k in ('ar', 'r_beats', 'read_outstanding_occ_sum',
                    'read_outstanding_max', 'read_outstanding_full_cycles')), 'Local command read traffic')


def check_log(text):
    trials, records, group, summary = [], [], [], None
    active, suite_seen, terminal_seen = False, False, False
    severity = set()
    for line in text.splitlines():
        require(not re.search(r'Fatal:|Error:|\b(?:FAIL|FAILED|TIMEOUT)\b', line, re.I), 'Failure text')
        if 'UVM_ERROR' in line or 'UVM_FATAL' in line:
            match = re.fullmatch(r'(UVM_ERROR|UVM_FATAL)\s*:\s*0', line)
            require(match is not None and match[1] not in severity, 'UVM error/fatal/duplicate summary')
            severity.add(match[1])
        if 'Core Test' in line:
            require(line == TERMINAL and suite_seen and not terminal_seen, 'Malformed/premature core terminal')
            terminal_seen = True
        if 'QBS_PERF' in line and not line.startswith('Command:'):
            raise ValueError('Unexpected QBS execution')
        if 'AKV_PERF' in line and not line.startswith('Command:'):
            if line.startswith('[AKV_PERF] '):
                require(active and not suite_seen, 'Command outside trial')
                mode = MODES[len(trials)]
                sequence = commands(mode)
                require(len(group) < len(sequence), 'Extra command')
                r = numeric_fields(line[len('[AKV_PERF] '):], PERF_FIELDS)
                check_record(r, sequence[len(group)], mode, len(records)+1)
                records.append(r)
                group.append(r)
            elif line.startswith('[AKV_PERF_SUMMARY] '):
                require(suite_seen and not active and summary is None, 'Premature/duplicate summary')
                summary = numeric_fields(line[len('[AKV_PERF_SUMMARY] '):], SUMMARY_FIELDS)
            else:
                raise ValueError('Unknown/malformed AKV metric prefix')
        if 'AKV_QK_' in line:
            begin, end = BEGIN.fullmatch(line), END.fullmatch(line)
            if begin:
                i = len(trials)
                require(not active and not suite_seen and i < 4 and
                        (int(begin[1]), int(begin[2])) == (i, MODES[i]), 'Trial order/nesting')
                active, group = True, []
            elif end:
                i = len(trials)
                require(active and (int(end[1]), int(end[2])) == (i, MODES[i]) and
                        len(group) == len(commands(MODES[i])), 'Incomplete/wrong trial')
                t = totals(group)
                wanted = dict(records=390 if MODES[i] else 774, v2_full=2, v2_refill=2, release=2,
                    v2_row_load=256, v2_column_load=128 if MODES[i] else 512,
                    v2_column_panel=128 if MODES[i] else 0, v2_logical_column=512,
                    v2_k_view_bank_cycles=1024 if MODES[i] else 4096,
                    q_external_bytes=3072, kv_external_bytes=131072, replay_bytes=131072,
                    read_ranges=526, read_payload_bytes=134272)
                require(all(t[k] == v for k, v in wanted.items()), 'Trial totals')
                trials.append(dict(trial=i, panel4=MODES[i], cycles=int(end[3]), fcsr=3, vcsr=5,
                    checksum='a7bc111334389dea', derived_hardware_totals=t))
                active = False
            elif line == SUITE:
                require(not active and len(trials) == 4 and not suite_seen, 'Premature/duplicate suite marker')
                suite_seen = True
            else:
                raise ValueError('Unknown/malformed program marker')
    require(not active and suite_seen and terminal_seen and len(records) == 2328 and
            severity == {'UVM_ERROR', 'UVM_FATAL'}, 'Incomplete final evidence')
    require(summary == totals(records), 'Raw final summary does not conserve per-command counters')
    traffic = ('ar', 'r_beats', 'q_external_bytes', 'kv_external_bytes', 'replay_bytes',
               'read_ranges', 'read_payload_bytes')
    require(all(len({t['derived_hardware_totals'][k] for t in trials}) == 1 for k in traffic),
            'Same-ELF external/replay traffic changed between modes')
    sums = {str(m): sum(t['cycles'] for t in trials if t['panel4'] == m) for m in (0, 1)}
    return dict(state='PASS', trials=trials, raw_hardware_summary=summary, sums=sums,
        attention_speedup=sums['0']/sums['1'], cycle_reduction_percent=100*(1-sums['1']/sums['0']),
        scope='Same-ELF real Decode Attention, QK PANEL4 only; refill overlap OFF; not full model timing',
        accounting='Trial totals derived directly from records; only the raw final summary is hardware-emitted.')


def merge_pins(pins, extra):
    for path, value in extra.items():
        require(path not in pins or pins[path] == value, 'Conflicting pin: ' + path)
        require(re.fullmatch('[0-9a-f]{64}', value) is not None, 'Invalid pin')
        pins[path] = value


def verify_pins(pins):
    require(hashes(map(Path, pins)) == pins, 'Source/image/evidence pin drift')


def checked_build(build):
    report = read_json(build/'build.json')
    require(report['state'] == 'BUILT_NOT_EXECUTED' and all(report.get(k) == v for k, v in
        dict(effective_kv=128, outputs=1536, head_dim=128, q_heads=12, kv_heads=2,
             refill_overlap=False).items()), 'Not the reviewed fresh build schema/shape')
    pins = {}
    for name, field in [('manifest.json', 'manifest_sha256'), ('artifacts.json', 'artifacts_sha256')]:
        require(digest(build/name) == report[field], 'Build receipt drift: ' + name)
        merge_pins(pins, read_json(build/name))
    elf = Path(report['elf']).resolve(strict=True)
    require(digest(elf) == report['elf_sha256'] and pins.get(str(elf)) == report['elf_sha256'], 'ELF identity')
    merge_pins(pins, hashes([build/'build.json', build/'manifest.json', build/'artifacts.json']))
    verify_pins(pins)
    return report, pins


def checked_prerequisite(path, image):
    status, result = read_json(path/'status.json'), read_json(path/'result.json')
    require(status.get('state') == 'PASS' and result.get('state') == 'PASS' and
            status.get('child_pid') is None, 'Focused RTL prerequisite not terminal PASS; do not launch')
    numeric = result.get('numeric', {})
    require(numeric.get('state') == 'PASS' and all(numeric.get(k) == v for k, v in
        dict(pairs=8, runs=16, outputs=3240, tailwords=2904).items()), 'Wrong focused numeric gate')
    design = {p: v for p, v in image.items() if Path(p).name not in ('simulator.conf', 'vcs_source_manifest.json')}
    require(result.get('sim_image_sha256') == design, 'Focused gate used another image')
    evidence = result['evidence_sha256']
    verify_pins(evidence)
    for name in ('pins-before.json', 'pins-after.json'):
        require(str(path/name) in evidence, 'Missing focused source provenance')
    pins = read_json(path/'pins-before.json')
    require(pins == read_json(path/'pins-after.json'), 'Focused source pins changed')
    verify_pins(pins)
    merge_pins(pins, evidence)
    merge_pins(pins, hashes([path/'status.json', path/'result.json']))
    return pins


def checked_image(gate, simv):
    result, status = read_json(gate/'result.json'), read_json(gate/'status.json')
    require(result.get('state') == 'PASS' and result.get('neighbors') == 2 and
            result.get('probe', {}).get('state') == 'PASS' and
            result['probe'].get('commands') == 13 and status.get('state') == 'PASS' and
            status.get('child_pid') is None and Path(status['simv']).resolve() == simv,
            'QBACC image acceptance mismatch')
    pins = dict(result['evidence_sha256'])
    require(str(gate/'image-pins.json') in pins, 'Acceptance lacks image evidence')
    verify_pins(pins)
    image = hashes(image_files(simv))
    require(image == read_json(gate/'image-pins.json'), 'Accepted image changed')
    manifest = read_json(simv.parent/'vcs_source_manifest.json')
    require(manifest['schema_version'] == 1 and Path(manifest['repo_root']).resolve() == ROOT,
            'Wrong source manifest schema/root')
    source = unique_pairs((r['path'], r['sha256']) for r in manifest['files'])
    merge_pins(pins, source)
    merge_pins(pins, image)
    merge_pins(pins, hashes([gate/'status.json', gate/'result.json']))
    verify_pins(pins)
    return image, pins


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('build', 'prerequisite', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
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
            require(run_command(command, log, timeout, env, started) == 0, 'Command failed: '+log.name)
        finally:
            state['child_pid'] = None
            save()
    save()
    try:
        build, gate, prerequisite = (p.resolve(strict=True) for p in (args.build, args.gate, args.prerequisite))
        simv = (args.integration/'build/sim/simv').resolve(strict=True)
        report, pins = checked_build(build)
        image, accepted = checked_image(gate, simv)
        merge_pins(pins, accepted)
        merge_pins(pins, checked_prerequisite(prerequisite, image))
        contract = ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh'
        merge_pins(pins, hashes([Path(__file__).resolve(), HERE/'test_qk_panel4_abba.py',
            HERE/'run_refill_overlap_probe.py', ROOT/'verification/qbs/run_tile_context_engine.py',
            *script_files(), contract, Path(sys.executable).resolve()]))
        verify_pins(pins)
        atomic_json(out/'source-pins.json', pins)
        pin_receipt_hash = digest(out/'source-pins.json')
        elf = Path(report['elf'])
        def manifest_check(label):
            run([sys.executable, '-B', '-m', 'ara_verify.vcs_source_manifest', '--output',
                 simv.parent/'vcs_source_manifest.json', '--check'], out/(label+'.log'), 300)
        manifest_check('manifest-before')
        run(['bash', contract, simv.parent, elf, 'akv_v2'], out/'image-contract.log', 180)
        verify_pins(pins)
        if args.preflight_only:
            state['state'] = 'PREFLIGHT_PASS_NOT_RUN'
            atomic_json(out/'result.json', dict(state=state['state'], source_pins_sha256=pin_receipt_hash))
            return
        state.update(state='RUNNING', simv=str(simv), elf=str(elf))
        save()
        log, trace = work/'run.vcs.log', work/'vector_trace.csv'
        run([simv, '-no_save', '-l', log, '+PRELOAD='+str(elf), '+TESTCASE=akv_qk_panel4_abba',
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
        require(uvm['log_sha256'] == digest(log) and uvm['vector_trace_sha256'] == digest(trace),
                'UVM log/trace identity mismatch')
        manifest_check('manifest-after')
        verify_pins(pins)
        require(hashes(image_files(simv)) == image and digest(out/'source-pins.json') == pin_receipt_hash,
                'Image/pin receipt drift')
        result['evidence_sha256'] = hashes([log, trace, work/'commit_trace.csv', work/'uvm_result.json',
                                            out/'source-pins.json', prerequisite/'result.json', gate/'result.json'])
        atomic_json(out/'result.json', result)
        state['state'] = 'PASS'
    except BaseException as exc:
        state.update(state='FAIL', error=repr(exc))
        raise
    finally:
        state['child_pid'] = None
        save()


if __name__ == '__main__':
    main()
