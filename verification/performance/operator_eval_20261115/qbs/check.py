#!/usr/bin/env python3
"""Independent fail-closed workload check; parent owns image and protocol gates."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PHASES = tuple('phase_' + p + '_cycles' for p in
               ('setup', 'activation', 'weight', 'compute', 'overlap', 'drain',
                'scheduler', 'commit', 'fault', 'terminal'))
TIMES = ('quant', 'pack', 'admit', 'execute', 'drain')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def fields(line, prefix, strings=()):
    result = {}
    for token in line[len(prefix):].split():
        require(token.count('=') == 1, 'Malformed field')
        key, value = token.split('=')
        require(key and value and key not in result, 'Duplicate/empty field')
        if key in strings:
            result[key] = value
        else:
            require(re.fullmatch(r'[0-9]+', value), 'Nondecimal field: ' + key)
            result[key] = int(value)
    return result


def monitor_reports(text):
    reports, current = [], None
    raw = []
    for line in text.splitlines():
        if not line.startswith(('[PERF]', '[LLM_METRIC]')):
            continue
        raw.append(line)
        if line == '[PERF] ==== Performance Report Start ====':
            require(current is None, 'Nested monitor report')
            current = {}
        elif line == '[PERF] ==== Performance Report End ====':
            require(current is not None, 'Orphan monitor report end')
            reports.append(current)
            current = None
        elif current is not None:
            match = re.fullmatch(r'\[PERF\]\s+([^:]+):\s*([0-9]+(?:\.[0-9]+)?)\s*', line)
            if match:
                key, value = match.groups()
                key = key.strip()
                require(key not in current, 'Duplicate monitor metric')
                current[key] = float(value) if '.' in value else int(value)
    require(current is None and len(reports) in (0, 2), 'Incomplete/extra monitor trial reports')
    for r in reports:
        require(r.get('total_cycles', 0) > 0, 'Empty monitor ROI')
    return dict(available=bool(reports), trials=reports, raw_lines=raw,
                semantics='Commit-marker ROI, including marker and CSR snapshot overhead; distinct from issue-side rdcycle boundaries')


def parse_log(text, build, expected, q8_expected, packed_expected):
    c, plan = build['case'], build['plan']
    m, n = c['m'], c['n']
    native = c['backend'] == 'native'
    commands = plan['commands'] if native else []
    require(len(expected) == 4*m*n and len(q8_expected) == len(packed_expected) == m*8*292,
            'Golden dimensions')
    require(text.count('Core Test *** SUCCESS ***') == 1, 'Missing/duplicate firmware success')
    perf, trials, raw = [], [], {}
    meta = done = None
    for line in text.splitlines():
        if re.match(r'\s*UVM_(?:ERROR|FATAL)\b', line):
            require(re.fullmatch(r'\s*UVM_(?:ERROR|FATAL)\s*:\s*0\s*', line), 'UVM error')
        require(not re.search(r'(?i)(?:^\s*(?:Error[-:]|Fatal:)|Assertion failed|\$fatal|\bTIMEOUT\b|\bTIMED OUT\b)', line),
                'Simulation error/timeout')
        if line.startswith('[QBS_PERF] '):
            require(native and meta is None and len(perf) < 2*len(commands), 'Unexpected native work')
            p = fields(line, '[QBS_PERF] ')
            require(p['seq'] == len(perf)+1, 'Command sequence mismatch')
            require(p['success'] == 1 and all(p[k] == 0 for k in
                    ('fault', 'validation_fault', 'validation_error', 'read_fault',
                     'context_validation_fault_count')), 'Native command failure')
            require(sum(p[k] for k in PHASES) == p['busy_cycles'] > 0 and
                    p['phase_fault_cycles'] == 0, 'Nonexclusive/incomplete engine phases')
            require(p['probe_compute_without_dot_issue_cycles'] + p['dot_active_cycles'] ==
                    p['phase_compute_cycles'] + p['phase_overlap_cycles'], 'Compute accounting')
            perf.append(p)
        elif line.startswith('OPQ_META '):
            require(meta is None and done is None and len(perf) == 2*len(commands), 'Duplicate/early metadata')
            meta = fields(line, 'OPQ_META ', ('id',))
            require(meta == dict(id=build['build_id'], m=m, n=n, k=2048, profile=c['profile'],
                                 rvv=int(not native), trials=2), 'Build/scope mismatch')
        elif line.startswith('OPQ_TRIAL '):
            require(meta is not None and done is None and len(trials) < 2, 'Early/late/extra trial')
            r = fields(line, 'OPQ_TRIAL ')
            require(set(r) == {'trial', 'status', 'commands', 'context', 'eligible', 'coop',
                    'quant_fcsr', 'fcsr', 'vcsr', 'vstart', *(f't{i}' for i in range(6))}, 'Trial schema')
            t = len(trials)
            eligible = int(native and plan['context_eligible'])
            context = int(eligible and c['reuse'] != 'direct')
            require(r['trial'] == t and r['status'] == 0 and r['commands'] == len(commands) and
                    r['eligible'] == eligible and r['context'] == context and r['coop'] in (0, 1),
                    'SDK admission/work failure')
            require(native or r['coop'] == 0, 'RVV queried native capability')
            ts = [r[f't{i}'] for i in range(6)]
            require(all(0 <= a < b < 2**64 for a, b in zip(ts, ts[1:])), 'Bad phase boundaries')
            if t:
                require(ts[0] > trials[0]['t5'] and r['coop'] == trials[0]['coop'], 'Overlapping repeat/capability drift')
            require(r['vcsr'] == r['vstart'] == 0 and r['quant_fcsr'] & ~3 == 0,
                    'Vector CSR/quantization exception contract')
            seed = build['flag_seeds'][t]
            if native:
                require(r['fcsr'] == plan['flags'] | seed, 'Missing/new/sticky native flags')
            else:
                require(r['fcsr'] in (seed, seed | 1), 'RVV unexpected exception or lost sticky DZ')
            trials.append(r)
        elif any(line.startswith('OPQ_' + k + ' ') for k in ('GUARD', 'Q8', 'PACK', 'OUT')):
            require(meta is not None and done is None and trials, 'Early/late raw record')
            kind = line.split()[0][4:]
            r = fields(line, 'OPQ_' + kind + ' ', ('hex', 'bits'))
            index_key = 'block' if kind in ('Q8', 'PACK') else 'index'
            value_key = 'bits' if kind == 'OUT' else 'hex'
            limit = m*n if kind == 'OUT' else (10 if kind == 'GUARD' else m*8)
            require(set(r) == {'trial', index_key, value_key} and r['trial'] == len(trials)-1 and
                    0 <= r[index_key] < limit, 'Raw schema/scope')
            key = (kind, r['trial'], r[index_key])
            require(key not in raw, 'Duplicate raw record')
            value = r[value_key]
            width = 8 if kind == 'OUT' else (128 if kind == 'GUARD' else 584)
            require(re.fullmatch('[0-9a-f]{' + str(width) + '}', value), 'Malformed raw bytes')
            index = r[index_key]
            if kind == 'OUT':
                actual_bits = int(value, 16)
                golden_bits = struct.unpack_from('<I', expected, 4*index)[0]
                if native:
                    require(actual_bits == golden_bits, 'Bit-exact output mismatch')
                else:
                    actual = struct.unpack('<f', struct.pack('<I', actual_bits))[0]
                    golden = struct.unpack_from('<f', expected, 4*index)[0]
                    contract = build['numeric_contract']
                    require(math.isfinite(actual) and math.isfinite(golden) and
                            abs(actual-golden) <= contract['rvv_atol'] + contract['rvv_rtol']*abs(golden),
                            'RVV independent tolerance mismatch')
            elif kind == 'GUARD':
                require(value == 'a5'*64, 'Corrupted raw guard')
            else:
                golden = q8_expected if kind == 'Q8' else packed_expected
                require(bytes.fromhex(value) == golden[index*292:(index+1)*292],
                        'Full Q8/packed byte mismatch')
            raw[key] = value
        elif line.startswith('OPQ_DONE '):
            require(done is None and len(trials) == 2, 'Duplicate/early footer')
            done = fields(line, 'OPQ_DONE ')
            require(done == {'errors': 0}, 'Firmware reported failure')
        elif line.startswith('OPQ_'):
            raise ValueError('Unknown workload record')
    wanted = {(kind,t,i) for t in range(2) for kind,limit in
              (('GUARD',10),('Q8',m*8),('PACK',m*8),('OUT',m*n)) for i in range(limit)}
    require(meta is not None and done is not None and len(trials) == 2 and
            set(raw) == wanted and len(perf) == 2*len(commands), 'Incomplete evidence')
    rows = []
    for t,r in enumerate(trials):
        observed = perf[t*len(commands):(t+1)*len(commands)]
        for i,(p,cmd) in enumerate(zip(observed,commands)):
            cm, cn = cmd['m'], cmd['n']
            wb = 144 if c['profile'] == 1 else 210
            require((p['m'],p['n'],p['lanes'],p['vlen']) == (cm,cn,4,1024) and
                    p['weight_bytes'] == cn*8*wb and p['activation_bytes'] == cm*8*292 and
                    p['useful_pairs'] == cm*cn*2048 and p['tiles'] == 8*(cn//4)*(2 if cm > 4 else 1),
                    'Command geometry/work mismatch')
            cooperative = bool(r['coop'] and c['profile'] == 1 and cm == 8)
            capacity = 64 if cooperative else 32
            require(p['pair_capacity'] == capacity*p['dot_active_cycles'] == p['useful_pairs'],
                    'Dot issue capacity mismatch')
            access = 0
            if r['context']:
                if c['reuse'] == 'cross_call':
                    access = (1 if i == 0 else 2) if t == 0 else (3 if i == len(commands)-1 else 2)
                else:
                    access = 1 if cmd['col'] == 0 else (3 if cmd['col']+cn == n else 2)
            require(p['activation_access'] == access and p['context_fill_count'] == int(access == 1) and
                    p['context_reuse_count'] == int(access in (2,3)) and
                    p['activation_axi_bytes_saved'] == (cm*8*292 if access in (2,3) else 0),
                    'Context lifecycle/counter mismatch')
        sw = {key:r[f't{i+1}']-r[f't{i}'] for i,key in enumerate(TIMES)}
        busy = sum(p['busy_cycles'] for p in observed)
        require(busy <= sw['execute'], 'Engine busy exceeds execute ROI')
        rows.append(dict(trial=t, label=('first','repeat')[t], software_cycles=sw,
            total_cycles=r['t5']-r['t0'], native_busy_cycles=busy,
            execute_outside_engine_cycles=sw['execute']-busy,
            engine_phase_cycles={k:sum(p[k] for p in observed) for k in PHASES},
            engine_counters={k:sum(p[k] for p in observed) for k in
                ('weight_bytes','activation_bytes','useful_pairs','pair_capacity','dot_active_cycles',
                 'context_fill_count','context_reuse_count','activation_axi_bytes_saved')},
            csr=r, commands=observed))
    return dict(state='PASS', metrics=dict(case_id=c['id'], backend=c['backend'],
        baseline_kind=c['baseline_kind'], primary_eligible=c['primary_eligible'],
        commit_roi_monitor=monitor_reports(text),
        provenance=c['provenance'], m=m,n=n,k=2048, trials=rows,
        output_values_checked=2*m*n, q8_bytes_checked=2*m*8*292,
        packed_bytes_checked=2*m*8*292, guard_bytes_checked=2*10*64,
        numerical_contract=build['numeric_contract'], whole_model=False,
        protocol_checked=False, current_image_checked=False,
        scope='Workload only; externally pinned parent image/protocol gates required',
        counter_semantics='Exclusive phases partition busy; pair capacity is dot issue capacity, not physical utilization; execute residual includes fences/stores/SDK/stamp overhead'))


def check_run(log_path, build_dir):
    directory = Path(build_dir)
    build_path = directory if directory.name == 'build.json' else directory / 'build.json'
    directory = build_path.parent
    build = json.loads(build_path.read_text())
    require(build['state'] == 'BUILT_NOT_EXECUTED' and build['post_pins_match'] is True and
            build['reused_objects'] == 0 and build['rtl_executed'] is False, 'Untrusted build')
    require(digest(build['elf']) == build['elf_sha256'], 'ELF drift')
    require(digest(build['source_pins']) == build['source_pins_sha256'], 'Pins inventory drift')
    pins = json.loads(Path(build['source_pins']).read_text())
    require(pins.get(str(Path(__file__).resolve())) == digest(__file__), 'Checker not pinned')
    for path,sha in pins.items():
        require(digest(path) == sha, 'Source/artifact drift: ' + path)
    data = directory / 'data'
    packed = 'expected_q8.bin' if build['case']['backend'] == 'rvv' else 'expected_packed.bin'
    result = parse_log(Path(log_path).read_text(), build, (data / 'expected.bin').read_bytes(),
                       (data / 'expected_q8.bin').read_bytes(), (data / packed).read_bytes())
    result.update(build=str(build_path.resolve()), build_sha256=digest(build_path),
                  log=str(Path(log_path).resolve()), log_sha256=digest(log_path),
                  elf_sha256=build['elf_sha256'], source_pins_sha256=build['source_pins_sha256'])
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('--build', required=True, type=Path)
    p.add_argument('--log', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    require(not args.output.exists(), 'Refusing to overwrite checker evidence')
    try:
        result = check_run(args.log, args.build)
    except (ValueError,KeyError,OSError,TypeError) as error:
        args.output.write_text(json.dumps(dict(state='FAIL', metrics={}, error=str(error)), indent=2)+'\n')
        raise SystemExit(str(error)) from error
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    print(result['state'])


if __name__ == '__main__':
    main()
