#!/usr/bin/env python3
"""Independent CSR successor of pinned check.py; raw logs are never rewritten."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PARENT_BUILD_SHA256 = '0036348fcc4a733886e159b482291740915200bb8d94af6c1cec9cfeaef99abc'
PARENT_CHECK_SHA256 = '182c1be66ffff14983e34fdabf86cd3df8d3e60484e004525ed7ca1e1438694f'
CHECKER_API = 'check_run(log_path: Path, build_dir: Path) -> dict'
SUCCESSOR_FILES = ('main_csr_successor.c', 'build_csr_successor.py',
                   'check_successor.py', 'test_csr_successor.py')
CSR_CONTRACT = dict(
    name='q6_decode_quant_rne_preserved_v1',
    before=dict(fcsr=0, vcsr=0, vstart=0),
    quant=dict(fcsr_allowed_mask=3, vcsr=2, vxrm=1, vxsat=0, vstart=0),
    after=dict(fcsr='fcsr_quant', vcsr='vcsr_quant', vxsat=0, vstart=0, vl=32, vtype=208),
    sampling='Quant CSR reads after t1, charged to admission; t0..t4 unchanged',
    post_quant_csr_reset=False)
SUCCESSOR_REASON = (
    'build05 real llama quantize_row_q8_K uses RNE vnclip; quant-disassembly.log:79 '
    'pc 80000a24 is csrwi vxrm,1 (vcsr=2 with vxsat=0). The old final-vcsr=0 '
    'measurement contract was wrong. This new ELF samples quant CSRs and requires '
    'vcsr_quant=2, vstart_quant=0, vcsr_after=vcsr_quant, vstart_after=0; '
    'no algorithm change or post-quant CSR reset. Original errors=2 evidence remains FAIL.')
PHASES = tuple('phase_' + name + '_cycles' for name in (
    'setup', 'activation', 'weight', 'compute', 'overlap', 'drain',
    'scheduler', 'commit', 'fault', 'terminal'))
TIMES = ('prep', 'admit', 'execute', 'drain', 'total')
TRIAL_KEYS = {'trial', 'context', 'status', 'commands', 'plan_errors', 'q8_errors',
              'output_errors', 't0', 't1', 't2', 't3', 't4', *TIMES}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def fields(line, prefix, strings=()):
    require(line.startswith(prefix), 'Record prefix mismatch')
    result = {}
    for token in line[len(prefix):].split():
        require(token.count('=') == 1, 'Malformed field')
        key, value = token.split('=')
        require(key not in result and key and value, 'Duplicate/empty field')
        if key in strings:
            result[key] = value
        else:
            require(re.fullmatch(r'[0-9]+', value) is not None, 'Nondecimal field: ' + key)
            result[key] = int(value)
    return result


def parse_log(text, build_id, expected_q8, expected):
    require(len(expected_q8) == 2336 and len(expected) == 256, 'Golden dimensions')
    perf, trials, q8, output = [], [], {}, {}
    csr, guards, work = {}, {}, {}
    meta = done = None
    for line in text.splitlines():
        if line.startswith('[QBS_PERF]'):
            require(meta is None, 'Native command emitted after timing records')
            p = fields(line, '[QBS_PERF] ')
            require(p['seq'] == len(perf) + 1 and len(perf) < 4, 'Extra/out-of-order command')
            require((p['m'], p['n'], p['vlen'], p['lanes']) == (1, 32, 1024, 4),
                    'Not M1/N32 at the selected VLEN/lanes')
            require((p['success'], p['fault'], p['validation_fault'], p['read_fault'],
                     p['validation_error'], p['context_validation_fault_count']) == (1, 0, 0, 0, 0, 0),
                    'Native execution failed')
            require(p['weight_bytes'] == 32*8*210 and p['activation_bytes'] == 8*292 and
                    p['tiles'] == 64 and p['useful_pairs'] == 32*2048,
                    'Full K/profile2 geometry mismatch')
            require(sum(p[k] for k in PHASES) == p['busy_cycles'] > 0 and
                    p['phase_fault_cycles'] == 0, 'Nonexclusive/incomplete engine phases')
            require(0 < p['useful_pairs'] <= p['pair_capacity'] == 32*p['dot_active_cycles'],
                    'Issue capacity accounting')
            require(p['probe_compute_without_dot_issue_cycles'] + p['dot_active_cycles'] ==
                    p['phase_compute_cycles'] + p['phase_overlap_cycles'], 'Compute accounting')
            perf.append(p)
        elif line.startswith('Q6_DECODE_META'):
            require(meta is None and len(perf) == 4 and done is None, 'Duplicate/early metadata')
            meta = fields(line, 'Q6_DECODE_META ', ('build_id',))
            require(meta == dict(build_id=build_id, m=1, k=2048, n=64, profile=2,
                                 trials=2, q8_bytes=2336, guard_bytes=64), 'Wrong build/scope')
        elif line.startswith('Q6_DECODE_TRIAL'):
            require(meta is not None and done is None and len(trials) < 2, 'Extra/early trial')
            t = fields(line, 'Q6_DECODE_TRIAL ')
            require(set(t) == TRIAL_KEYS and t['trial'] == len(trials), 'Trial schema/order')
            require(t['context'] in (0, 1) and t['status'] == 0 and t['commands'] == 2 and
                    t['plan_errors'] == t['q8_errors'] == t['output_errors'] == 0,
                    'Firmware admission/numerics failure')
            ts = [t['t' + str(i)] for i in range(5)]
            require(all(0 <= ts[i] < ts[i+1] < 2**64 for i in range(4)),
                    'Invalid/unordered phase boundaries')
            require(all(t[name] == ts[i+1]-ts[i] for i, name in enumerate(TIMES[:4])) and
                    t['total'] == ts[-1]-ts[0] == sum(t[k] for k in TIMES[:4]),
                    'Software phase partition mismatch')
            if trials:
                require(t['t0'] > trials[0]['t4'] and t['context'] == trials[0]['context'],
                        'Repeat overlaps or admission changed')
            trials.append(t)
        elif line.startswith('Q6_DECODE_CSR'):
            require(meta is not None and done is None, 'Early/late CSR record')
            r = fields(line, 'Q6_DECODE_CSR ')
            require(set(r) == {'trial', 'fcsr_before', 'vcsr_before', 'vstart_before',
                              'fcsr_quant', 'vcsr_quant', 'vstart_quant',
                              'fcsr_after', 'vcsr_after', 'vstart_after',
                              'vl_after', 'vtype_after'} and
                    r['trial'] == len(trials)-1 and r['trial'] not in csr, 'CSR schema/order')
            require(r['fcsr_before'] == r['vcsr_before'] == r['vstart_before'] == 0 and
                    r['fcsr_quant'] & ~3 == 0 and r['fcsr_after'] == r['fcsr_quant'] and
                    r['vcsr_quant'] == 2 and r['vstart_quant'] == 0 and
                    r['vcsr_after'] == r['vcsr_quant'] and r['vstart_after'] == 0 and
                    r['vl_after'] == 32 and r['vtype_after'] == 208, 'CSR contract failure')
            csr[r['trial']] = r
        elif line.startswith('Q6_DECODE_WORK'):
            require(meta is not None and done is None, 'Early/late work record')
            r = fields(line, 'Q6_DECODE_WORK ')
            t = len(trials)-1
            require(t not in work and r == dict(trial=t, quant_calls=1, plan_calls=1,
                    execute_calls=1, planned_commands=2, k_elements=2048, n_elements=64,
                    guard_errors=0), 'SDK work count/scope mismatch')
            work[t] = r
        elif line.startswith('Q6_DECODE_GUARD'):
            require(meta is not None and done is None, 'Early/late guard record')
            r = fields(line, 'Q6_DECODE_GUARD ', ('hex',))
            require(set(r) == {'trial', 'index', 'hex'} and r['trial'] == len(trials)-1 and
                    0 <= r['index'] < 8, 'Guard schema/scope')
            key = (r['trial'], r['index'])
            require(key not in guards and r['hex'] == 'a5'*64,
                    'Duplicate/corrupted guard bytes')
            guards[key] = r['hex']
        elif line.startswith('Q6_DECODE_Q8'):
            require(meta is not None and done is None, 'Early/late Q8 dump')
            r = fields(line, 'Q6_DECODE_Q8 ', ('hex',))
            require(set(r) == {'trial', 'block', 'hex'} and
                    r['trial'] == len(trials)-1 and 0 <= r['block'] < 8,
                    'Q8 schema/scope')
            key = (r['trial'], r['block'])
            require(key not in q8 and re.fullmatch(r'[0-9a-f]{584}', r['hex']) is not None,
                    'Duplicate/malformed Q8 block')
            value = bytes.fromhex(r['hex'])
            require(value == expected_q8[r['block']*292:(r['block']+1)*292],
                    'Full Q8 byte mismatch (scale/quants/bsums)')
            q8[key] = value
        elif line.startswith('Q6_DECODE_OUT'):
            require(meta is not None and done is None, 'Early/late output')
            r = fields(line, 'Q6_DECODE_OUT ', ('bits',))
            require(set(r) == {'trial', 'index', 'bits'} and r['trial'] == len(trials)-1 and
                    0 <= r['index'] < 64, 'Output schema/scope')
            key = (r['trial'], r['index'])
            require(key not in output and re.fullmatch(r'[0-9a-f]{8}', r['bits']) is not None,
                    'Duplicate/malformed output')
            value = int(r['bits'], 16)
            require(value == struct.unpack_from('<I', expected, 4*r['index'])[0],
                    'Independent bit-exact golden mismatch')
            output[key] = value
        elif line.startswith('Q6_DECODE_DONE'):
            require(done is None and len(trials) == 2, 'Duplicate/early footer')
            done = fields(line, 'Q6_DECODE_DONE ')
            require(done == dict(errors=0, trials=2, commands=4), 'Failed footer')
        elif line.startswith('Q6_DECODE_'):
            raise ValueError('Unknown workload record')
        summary = re.fullmatch(r'\s*UVM_(?:ERROR|FATAL)\s*:\s*([0-9]+)\s*', line)
        if summary:
            require(int(summary[1]) == 0, 'Nonzero UVM failure summary')
        else:
            require(not re.match(r'\s*UVM_(?:ERROR|FATAL)\b', line) and
                    'Fatal:' not in line and 'Error:' not in line and
                    'TIMEOUT' not in line.upper() and 'TIMED OUT' not in line.upper(),
                    'Simulator error/timeout')
    require(meta is not None and done is not None and len(trials) == 2 and len(perf) == 4 and
            set(csr) == set(work) == {0, 1} and
            set(guards) == {(t, g) for t in range(2) for g in range(8)} and
            set(q8) == {(t, b) for t in range(2) for b in range(8)} and
            set(output) == {(t, i) for t in range(2) for i in range(64)}, 'Incomplete evidence')
    rows = []
    for index, t in enumerate(trials):
        commands = perf[2*index:2*index+2]
        accesses = [p['activation_access'] for p in commands]
        require(accesses == ([1, 3] if t['context'] else [0, 0]), 'Context lifecycle mismatch')
        require([p['context_fill_count'] for p in commands] == ([1, 0] if t['context'] else [0, 0]) and
                [p['context_reuse_count'] for p in commands] == ([0, 1] if t['context'] else [0, 0]),
                'Context counter mismatch')
        busy = sum(p['busy_cycles'] for p in commands)
        require(busy <= t['execute'], 'Native busy outside SDK execute ROI')
        partition = dict(preparation=t['prep'], plan_admission=t['admit'],
                         native_engine_busy=busy, sdk_execute_outside_engine= t['execute']-busy,
                         final_drain=t['drain'])
        require(sum(partition.values()) == t['total'], 'Slice partition mismatch')
        rows.append(dict(trial=index, repeat_label=('first', 'repeat')[index], timing=t,
                         csr=csr[index], work=work[index], raw_guard_bytes_checked=8*64,
                         complete_slice_partition_cycles=partition,
                         native_phase_cycles={k: sum(p[k] for p in commands) for k in PHASES},
                         commands=commands))
    return dict(state='PASS', acceptance_scope='Workload scope/output/Q8/CSR/guards/work/timing only',
                performance_measured=True, log_profile_valid=True,
                independent_protocol_checked=False, current_soc_identity_checked=False,
                full_q8_bytes_checked_per_trial=2336, output_values_checked_per_trial=64,
                csr_checked=True, guards_checked=True, work_checked=True,
                trials=rows, warm_claim='First/repeat comparison only; no cache residency claim',
                scope='Real Qwen3 position40 Decode attn_v M1/K2048/N64 slice, not a layer/model',
                counter_semantics='Exclusive engine phases partition busy; issue capacity is not physical lane utilization; execute residual includes SDK, native fences, vsetvli, stores and timestamp boundary cost')


def check_build(path):
    build = json.loads(path.read_text())
    require(build['state'] == 'BUILT_NOT_EXECUTED' and build['performance_measured'] is False and
            build['post_pins_match'] is True and build['reused_objects'] == 0,
            'Untrusted build state')
    require(digest(build['elf']) == build['elf_sha256'], 'Measured ELF changed')
    pins_file = Path(build['source_pins'])
    require(digest(pins_file) == build['source_pins_sha256'], 'Source pins changed')
    pins = json.loads(pins_file.read_text())
    for name, sha in pins.items():
        require(Path(name).is_file() and digest(name) == sha, 'Source/artifact drift: ' + name)
    for name, sha in build['artifacts'].items():
        require(digest(name) == sha, 'Build artifact drift: ' + name)
    require(pins.get(str(Path(__file__).resolve())) == digest(__file__), 'Checker not in sealed pins')
    for name in (*SUCCESSOR_FILES, 'main.c', 'build.py', 'check.py',
                 'host_ref.c', 'test_profile.py', 'README.md'):
        source = HERE / name
        require(pins.get(str(source)) == digest(source), 'Missing helper pin: ' + name)
    require(pins[str(HERE / 'build.py')] == PARENT_BUILD_SHA256 and
            pins[str(HERE / 'check.py')] == PARENT_CHECK_SHA256, 'Predecessor identity mismatch')
    require(build['csr_contract'] == CSR_CONTRACT and
            build['successor_reason'] == SUCCESSOR_REASON, 'Wrong successor CSR contract/reason')
    require(build['parent_builder'] == dict(path=str(HERE / 'build.py'),
                                            sha256=PARENT_BUILD_SHA256),
            'Wrong parent builder')
    require(build['measurement_source'] == str(HERE / 'main_csr_successor.c'),
            'Wrong measurement source')
    require(build['checker_entry'][1:] == [
        '-B', str(HERE / 'check_successor.py'), '--build', str(path.resolve()),
        '--log', '<run.vcs.log>', '--output', '<new authorized output.json>'] and
        Path(build['checker_entry'][0]).resolve() == Path(sys.executable).resolve() and
        build['checker_api'] == CHECKER_API, 'Wrong successor checker entry')
    commands = json.loads((path.parent / 'commands.json').read_text())
    main_commands = [c['argv'] for c in commands if c['label'] == 'compile-main']
    require(len(main_commands) == 1 and main_commands[0].count('-c') == 1 and
            main_commands[0][main_commands[0].index('-c') + 1] ==
            str(HERE / 'main_csr_successor.c'), 'Main compile did not use successor source')
    s = build['capture_scope']
    require((s['phase'], s['position'], s['m'], s['k'], s['n'], s['weight_profile'],
             s['trials'], s['commands_per_trial']) == ('decode', 40, 1, 2048, 64, 2, 2, 2),
            'Wrong build shape')
    return build


def check_run(log_path: Path, build_dir: Path) -> dict:
    """Fail closed; PASS is workload evidence, not protocol/SoC acceptance."""
    log_path, build_dir = Path(log_path), Path(build_dir)
    manifest_path = build_dir / 'build.json'
    checker_path = Path(__file__).resolve()
    checker_sha256 = digest(checker_path)
    build = check_build(manifest_path)
    result = parse_log(log_path.read_text(), build['build_id'],
                       Path(build['q8_expected']).read_bytes(), Path(build['expected']).read_bytes())
    result.update(build=str(manifest_path.resolve()), build_sha256=digest(manifest_path),
                  elf_sha256=build['elf_sha256'], source_pins_sha256=build['source_pins_sha256'],
                  log=str(log_path.resolve()), log_sha256=digest(log_path),
                  checker_identity=dict(path=str(checker_path), sha256=checker_sha256,
                                        entrypoint=CHECKER_API),
                  successor_reason=SUCCESSOR_REASON, csr_contract=CSR_CONTRACT)
    require(digest(checker_path) == checker_sha256, 'Checker identity changed during checking')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--log', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    require(not args.output.exists(), 'Refusing to overwrite evidence')
    result = check_run(args.log, args.build.parent)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(result['state'])


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError) as e:
        raise SystemExit(str(e)) from e
