#!/usr/bin/env python3
"""Bounded ordinary RVV / generic AKV / paired AKV same-ELF worker.

Foreground systemd owner only; never polls prerequisites or rebuilds sources.
Ordinary RVV is not the stronger tiled RVV path. No deployment claim.
"""
from enum import Enum
import argparse
import os
from pathlib import Path
import re
import signal
import sys

sys.dont_write_bytecode = True
import attention_run as mechanism
from attention_run import (ROOT, require, read_json, digest, hashes, verify_pins,
    merge_pins, checked_image, image_files, script_files, check_result, atomic_json,
    run_command, numeric_fields, PERF_FIELDS, SUMMARY_FIELDS, check_record, commands, totals)

HERE = Path(__file__).resolve().parent


class Variant(str, Enum):
    RVV = 'rvv'
    GENERIC = 'generic'
    PAIRED = 'paired'


ORDER = (Variant.RVV, Variant.GENERIC, Variant.PAIRED,
         Variant.PAIRED, Variant.GENERIC, Variant.RVV)
SEQUENCES = {v: [] if v == Variant.RVV else commands(int(v == Variant.PAIRED)) for v in Variant}
EXPECTED = dict(trials=6, order=[v.value for v in ORDER], outputs_per_trial=512, commands=3864,
    rvv=dict(commands=0), generic=mechanism.EXPECTED['off'], paired=mechanism.EXPECTED['on'],
    per_native_trial=mechanism.EXPECTED['per_trial'])
SUBSET = ('THREEWAY_SUBSET source=qwen25_kv128 qheads=0,1,6,7 kvheads=0,1 '
          'outputs=512 derived=1 outputbytes=2048')
BEGIN = re.compile(r'THREEWAY_BEGIN trial=([0-5]) variant=(rvv|generic|paired)')
END = re.compile(r'THREEWAY_END trial=([0-5]) variant=(rvv|generic|paired) executed=1 '
    r'native=([01]) admitted_groups=([02]) outputs=512 cycles=([1-9][0-9]*) '
    r'fcsr=([0-9]+) vcsr=5 checksum=([0-9a-f]{16}) guardbytes=384 errors=0')
SUITE = ('THREEWAY_SUITE_PASS trials=6 outputs_per_trial=512 within_variant_exact=1 '
         'generic_paired_exact=1 rvv_tolerance_only=1 guards=1 derived_subset=1')
TERMINAL = mechanism.TERMINAL
HOST_CROP_TESTS = dict(coordinate_words=512, coordinate_bytes=2048, rejected_mutations=3)
CAPTURE_NAMES = dict(input_a='attn_q_input-0.bin', golden='kqv_out-0.bin',
    input_b='attn_k_input-0.bin', input_c='attn_v_input-0.bin', input_d='attn_mask_input-0.bin')


def group_totals(rows):
    # RVV has no AKV records: define zero, including the otherwise empty max.
    return totals(rows) if rows else dict.fromkeys(SUMMARY_FIELDS, 0)


def check_log(text, native_identity=None):
    records, trials, group = [], [], []
    active = subset = suite = terminal = False
    summary, severity = None, set()
    for line in text.splitlines():
        require(not re.search(r'Fatal:|Error:|\b(?:FAIL|FAILED|TIMEOUT)\b', line, re.I), 'Failure text')
        if 'UVM_ERROR' in line or 'UVM_FATAL' in line:
            m = re.fullmatch(r'(UVM_ERROR|UVM_FATAL)\s*:\s*0', line)
            require(m is not None and m[1] not in severity, 'UVM failure/duplicate summary')
            severity.add(m[1])
        if 'Core Test' in line:
            require(line == TERMINAL and suite and not terminal, 'Core success missing/duplicate/malformed')
            terminal = True
        if ('QBS_PERF' in line or 'AKV_PAIR_' in line) and not line.startswith('Command:'):
            raise ValueError('Unexpected other workload')
        if 'AKV_PERF' in line and not line.startswith('Command:'):
            if line.startswith('[AKV_PERF] '):
                require(active and not suite, 'Command outside trial')
                variant = ORDER[len(trials)]
                sequence = SEQUENCES[variant]
                require(variant != Variant.RVV and len(group) < len(sequence), 'RVV AKV work/extra command')
                row = numeric_fields(line[len('[AKV_PERF] '):], PERF_FIELDS)
                check_record(row, sequence[len(group)], int(variant == Variant.PAIRED), len(records)+1)
                records.append(row)
                group.append(row)
            elif line.startswith('[AKV_PERF_SUMMARY] '):
                require(suite and not active and summary is None, 'Premature/duplicate hardware summary')
                summary = numeric_fields(line[len('[AKV_PERF_SUMMARY] '):], SUMMARY_FIELDS)
            else:
                raise ValueError('Unknown/malformed AKV metric-prefixed line')
        if 'THREEWAY_' in line:
            begin, end = BEGIN.fullmatch(line), END.fullmatch(line)
            if line == SUBSET:
                require(not subset and not active and not trials, 'Duplicate/misplaced subset')
                subset = True
            elif begin:
                i = len(trials)
                require(subset and not active and not suite and i < 6 and
                        (int(begin[1]), Variant(begin[2])) == (i, ORDER[i]), 'Trial order/nesting')
                active, group = True, []
            elif end:
                i = len(trials)
                require(active and (int(end[1]), Variant(end[2])) == (i, ORDER[i]), 'Trial end/order')
                variant = ORDER[i]
                require(int(end[3]) == int(variant != Variant.RVV) and
                        int(end[4]) == 2*int(variant == Variant.PAIRED), 'Native/admission mismatch')
                require(len(group) == len(SEQUENCES[variant]), 'Incomplete command sequence')
                flags, count = int(end[6]), group_totals(group)
                require(flags <= 31, 'Invalid FCSR flags/FRM')
                require(int(end[5]) >= count['busy_cycles'], 'Cycles below AKV engine busy')
                trials.append(dict(trial=i, variant=variant.value, native=int(end[3]),
                    admitted_groups=int(end[4]), cycles=int(end[5]), fcsr=flags, vcsr=5,
                    checksum=end[7], derived_hardware_totals=count))
                active = False
            elif line == SUITE:
                require(subset and not active and len(trials) == 6 and not suite, 'Premature/duplicate suite')
                suite = True
            else:
                raise ValueError('Unknown/malformed program marker')
    require(subset and suite and terminal and not active and len(records) == 3864 and
            severity == {'UVM_ERROR', 'UVM_FATAL'}, 'Incomplete execution evidence')
    require(summary == totals(records), 'Raw summary differs from record sums/max')
    identities = {}
    for variant in Variant:
        values = {(t['checksum'], t['fcsr'], t['vcsr']) for t in trials if t['variant'] == variant.value}
        require(len(values) == 1, 'Variant repeat bits/status differ')
        identities[variant] = next(iter(values))
    require(identities[Variant.GENERIC] == identities[Variant.PAIRED], 'Generic/paired bits/status differ')
    if native_identity is not None:
        require(identities[Variant.GENERIC] == tuple(native_identity), 'Native differs from accepted mechanism gate')
    native = [t for t in trials if t['native']]
    for field in ('ar', 'r_beats', 'q_external_bytes', 'kv_external_bytes', 'read_ranges', 'read_payload_bytes'):
        require(len({t['derived_hardware_totals'][field] for t in native}) == 1, 'Native external traffic differs')
    sums = {v.value: sum(t['cycles'] for t in trials if t['variant'] == v.value) for v in Variant}
    return dict(state='PASS', trials=trials, raw_hardware_summary=summary, sums=sums,
        paired_speedup_vs_generic=sums['generic']/sums['paired'],
        paired_speedup_vs_ordinary_rvv=sums['rvv']/sums['paired'],
        generic_speedup_vs_ordinary_rvv=sums['rvv']/sums['generic'],
        provenance='Offline Q/golden heads0,1,6,7 subset of Qwen2.5 KV128; NOT Qwen3 capture',
        comparison='Actual ordinary RVV versus generic AKV versus paired AKV; NOT strong tiled RVV',
        numerical='On-chip all512 finite/original tolerance; exact repeats; generic/paired exact; RVV bits/flags may differ',
        accounting='Derived per-trial AKV record sums/max; RVV zero AKV totals are not a fabricated hardware summary',
        scope='Complete same-ELF plan/native or ordinary RVV work; offline crop/checks excluded; not whole-model/deployment acceptance')


def checked_build(build):
    report = read_json(build/'build.json')
    require(report.get('state') == 'BUILT_NOT_EXECUTED' and report.get('execution') == 'NOT_RUN' and
        report.get('post_pins_match') is True and report.get('expected') == EXPECTED and
        report.get('source_heads') == [0, 1, 6, 7] and report.get('source_kv_heads') == [0, 1] and
        report.get('tolerance') == dict(atol=.004, rtol=.002) and report.get('output_capacity') == 2048 and
        report.get('shared_output_all_paths') is True and report.get('linked_abi_and_all_blob_bytes_verified') is True and
        report.get('host_self_tests') == HOST_CROP_TESTS, 'Wrong threeway build01 schema/geometry/proof')
    receipt = build/'source-pins.json'
    require(report['source_pins'] == str(receipt) and digest(receipt) == report['source_pins_sha256'], 'Source receipt identity')
    pins = read_json(receipt)
    merge_pins(pins, report['artifact_sha256'])
    elf = Path(report['elf']).resolve(strict=True)
    require(pins.get(str(elf)) == report['elf_sha256'] == digest(elf), 'ELF identity')
    proof_path = build/'data-proof.json'
    require(report['artifact_sha256'].get(str(proof_path)) == digest(proof_path), 'Unpinned crop proof')
    proof = read_json(proof_path)
    require(proof.get('state') == 'HOST_DATA_CHECK_PASS' and proof.get('self_test') == HOST_CROP_TESTS and
        proof.get('args') == [128, 1, 4, 256, 2, 0, 0, 0] and proof.get('flag') == 1 and
        proof.get('params') == [.004, .002, report['scale'], 0., 0., 0., 0., 0.] and
        proof.get('config_sha256') == digest(build/'config.bin'), 'Invalid data/config proof')
    capture = Path(report['capture']).resolve(strict=True)/'decode/block'
    capture_pins = {}
    require([c['name'] for c in proof['crops']] == ['input_a', 'golden'] and
            set(proof['unchanged']) == {'input_b', 'input_c', 'input_d'}, 'Wrong crop/unchanged set')
    for crop in proof['crops']:
        source, output = capture/CAPTURE_NAMES[crop['name']], build/(crop['name']+'.bin')
        require(crop['source'] == str(source) and crop['output'] == str(output) and
            crop['source_heads'] == [0, 1, 6, 7] and crop['verified_bytes'] == 2048 and
            crop['source_sha256'] == pins.get(str(source)) == digest(source) and
            crop['sha256'] == pins.get(str(output)) == digest(output), 'Crop source/output identity')
        original, cropped = source.read_bytes(), output.read_bytes()
        require(len(original) == 6144 and len(cropped) == 2048 and
            cropped == b''.join(original[h*512:(h+1)*512] for h in (0, 1, 6, 7)), 'Crop byte mapping')
        capture_pins[str(source)] = digest(source)
    for name, unchanged in proof['unchanged'].items():
        source = capture/CAPTURE_NAMES[name]
        require(unchanged['path'] == str(source) and unchanged['sha256'] == pins.get(str(source)) == digest(source),
                'K/V/mask identity')
        capture_pins[str(source)] = digest(source)
    merge_pins(pins, hashes([build/'build.json', receipt]))
    verify_pins(pins)
    return report, pins, capture_pins


def checked_prerequisite(path, image, capture_pins):
    status, result = read_json(path/'status.json'), read_json(path/'result.json')
    require(status.get('state') == result.get('state') == 'PASS' and status.get('child_pid') is None,
            'Mechanism Attention gate not terminal PASS; do not launch or wait')
    log, trace, uvm_path = (path/'work'/n for n in ('run.vcs.log', 'vector_trace.csv', 'uvm_result.json'))
    evidence = result['evidence_sha256']
    require(all(str(p) in evidence for p in (log, trace, uvm_path, path/'source-pins.json')), 'Missing mechanism evidence')
    verify_pins(evidence)
    pins = read_json(path/'source-pins.json')
    verify_pins(pins)
    require(len(capture_pins) == 5 and all(pins.get(p) == h for p, h in capture_pins.items()), 'Different mechanism inputs/subset')
    elf = Path(status['elf']).resolve(strict=True)
    require(pins.get(str(elf)) == digest(elf) and str(Path(status['simv']).resolve()) in image, 'Mechanism ELF/image identity')
    check_result(uvm_path, digest(elf), image)
    uvm = read_json(uvm_path)
    require(uvm['log_sha256'] == digest(log) and uvm['vector_trace_sha256'] == digest(trace), 'Mechanism UVM evidence identity')
    parsed = mechanism.check_log(log.read_text())
    require(all(result.get(k) == v for k, v in parsed.items()), 'Mechanism result/raw checker mismatch')
    require(parsed['sums']['0'] > parsed['sums']['1'], 'No positive mechanism gate benefit')
    first = parsed['trials'][0]
    identity = (first['checksum'], first['fcsr'], first['vcsr'])
    merge_pins(pins, evidence)
    merge_pins(pins, hashes([path/'status.json', path/'result.json']))
    return pins, identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('build', 'output', 'prerequisite'):
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
            require(run_command(command, log, timeout, env, started) == 0, 'Command failed: '+str(log))
        finally:
            state['child_pid'] = None
            save()
    save()
    try:
        build, gate, prerequisite = (p.resolve(strict=True) for p in (args.build, args.gate, args.prerequisite))
        simv = (args.integration/'build/sim/simv').resolve(strict=True)
        report, pins, capture_pins = checked_build(build)
        image, accepted = checked_image(gate, simv)
        require(report['simv'] == str(simv) and report['accepted_image_pins'] == image, 'Build/image mismatch')
        merge_pins(pins, accepted)
        prior, identity = checked_prerequisite(prerequisite, image, capture_pins)
        merge_pins(pins, prior)
        contract = ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh'
        merge_pins(pins, hashes([Path(__file__).resolve(), HERE/'threeway_run_test.py', HERE/'attention_run.py',
            HERE.parent/'run_qk_panel4_abba.py', HERE.parent/'run_refill_overlap_probe.py',
            ROOT/'verification/qbs/run_tile_context_engine.py', *script_files(), contract, Path(sys.executable).resolve()]))
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
            atomic_json(out/'result.json', dict(state=state['state'], source_pins_sha256=receipt_hash,
                mechanism_native_identity=identity, prerequisite=str(prerequisite)))
            return
        state.update(state='RUNNING', simv=str(simv), elf=str(elf))
        save()
        log, trace = work/'run.vcs.log', work/'vector_trace.csv'
        run([simv, '-no_save', '-l', log, '+PRELOAD='+str(elf), '+TESTCASE=akv_paired_heads_threeway',
             '+NO_FSDB', '+NO_INSTR_TRACE', '+AKV_PERF', '+AKV_SUMMARY',
             '+VECTOR_TRACE='+str(trace), '+COMMIT_TRACE='+str(work/'commit_trace.csv'),
             '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000'], work/'console.log', args.timeout)
        state['state'] = 'CHECKING'
        save()
        result = check_log(log.read_text(), identity)
        run([sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events', '--require-backend',
             '--require-axi', '--require-axi-write', '--vector-trace', trace, '--log', log,
             '--simv', simv, '--elf', elf, '--output', work/'uvm_result.json'], work/'checker.log', 600)
        check_result(work/'uvm_result.json', report['elf_sha256'], image)
        uvm = read_json(work/'uvm_result.json')
        require(uvm['log_sha256'] == digest(log) and uvm['vector_trace_sha256'] == digest(trace), 'UVM evidence identity')
        manifest('manifest-after')
        verify_pins(pins)
        require(hashes(image_files(simv)) == image and digest(out/'source-pins.json') == receipt_hash, 'Image/receipt drift')
        result.update(prerequisite=str(prerequisite), mechanism_native_identity=identity,
            evidence_sha256=hashes([log, trace, work/'commit_trace.csv', work/'uvm_result.json',
                out/'source-pins.json', prerequisite/'result.json', gate/'result.json']))
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
