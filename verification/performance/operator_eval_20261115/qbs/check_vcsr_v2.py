#!/usr/bin/env python3
"""Scoped offline VCSR correction; never changes original worker evidence."""
import argparse
import ast
import csv
import json
import math
from pathlib import Path
import re
import subprocess
import struct
import sys

sys.dont_write_bytecode = True
import check as predecessor

HERE = Path(__file__).resolve().parent
PREDECESSOR_SHA256 = 'b3f305ed42022c193470a36abfc22d38497cfc9fd8abdc3e1595665f984651f2'
DEFAULT_AUDIT_PINS = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/operator_qbs_prepare_20261115_vcsr_contract_01/source-pins.json')
require = predecessor.require
digest = predecessor.digest
fields = predecessor.fields
monitor_reports = predecessor.monitor_reports
PHASES = predecessor.PHASES
TIMES = predecessor.TIMES

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
            require(r['vcsr'] == 2 and r['vstart'] == 0 and r['quant_fcsr'] & ~3 == 0,
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


def verify_parser_delta():
    old = HERE / 'check.py'
    require(digest(old) == PREDECESSOR_SHA256, 'Sealed predecessor checker drift')
    old_tree = ast.parse(old.read_text())
    new_tree = ast.parse(Path(__file__).read_text())
    old_fn = next(n for n in old_tree.body if isinstance(n, ast.FunctionDef) and n.name == 'parse_log')
    new_fn = next(n for n in new_tree.body if isinstance(n, ast.FunctionDef) and n.name == 'parse_log')
    old_source = ast.get_source_segment(old.read_text(), old_fn)
    expected = old_source.replace("r['vcsr'] == r['vstart'] == 0", "r['vcsr'] == 2 and r['vstart'] == 0")
    require(old_source != expected and ast.dump(ast.parse(expected).body[0]) == ast.dump(new_fn),
            'Successor changed a gate other than the single VCSR predicate')


def verify_build(directory):
    directory = Path(directory).resolve()
    path = directory if directory.name == 'build.json' else directory / 'build.json'
    b = json.loads(path.read_text())
    require(b['state'] == 'BUILT_NOT_EXECUTED' and b['post_pins_match'] is True and
            b['reused_objects'] == 0 and b['rtl_executed'] is False, 'Untrusted original build')
    require(digest(b['elf']) == b['elf_sha256'], 'Original ELF drift')
    pins_path = Path(b['source_pins'])
    require(digest(pins_path) == b['source_pins_sha256'], 'Original build inventory drift')
    pins = json.loads(pins_path.read_text())
    require(pins.get(str(HERE / 'check.py')) == PREDECESSOR_SHA256, 'Wrong predecessor in original build')
    outer = path.parent / 'runner-source-pins.json'
    outer_pins = json.loads(outer.read_text())
    require(outer_pins.get(str(path)) == digest(path) and
            outer_pins.get(str(pins_path)) == digest(pins_path), 'Original runner build/inventory pins mismatch')
    for inventory in (pins, outer_pins):
        for file, sha in inventory.items():
            require(digest(file) == sha, 'Original code/image/artifact pin drift: ' + file)
    return b, path, {**pins, **outer_pins, str(outer): digest(outer)}


def disassembly(text):
    instructions, symbols, current = {}, {}, None
    for line in text.splitlines():
        symbol = re.fullmatch(r'([0-9a-f]+) <([^>]+)>:', line)
        if symbol:
            current = symbol[2]
            symbols.setdefault(current, [])
            continue
        match = re.match(r'\s*([0-9a-f]+):\s+([0-9a-f]{4}(?:[0-9a-f]{4})?)\s+(.+)', line)
        if match:
            pc, instruction = int(match[1],16), int(match[2],16)
            require(pc not in instructions, 'Duplicate disassembled PC')
            instructions[pc] = instruction
            if current is not None:
                symbols[current].append(pc)
    require('quantize_row_q8_K' in symbols and 'eval_trial' in symbols, 'ELF workload symbols missing')
    return instructions, symbols


def csr_write(instruction):
    if instruction & 127 != 0x73:
        return None
    funct3 = (instruction >> 12) & 7
    source = (instruction >> 15) & 31
    if funct3 in (1,5) or (funct3 in (2,3,6,7) and source != 0):
        return (instruction >> 20) & 4095
    return None


def is_saturating(instruction):
    return instruction & 127 == 0x57 and ((instruction >> 12) & 7) in (0,3,4) and (
        instruction >> 26) & 63 in (0x20,0x21,0x22,0x23,0x27,0x2e,0x2f)


def elf_proof(build, pins):
    tools = [Path(p) for p in pins if p.endswith('/riscv64-unknown-elf-objdump')]
    require(len(tools) == 1, 'Original pinned objdump missing/ambiguous')
    command = [str(tools[0]), '-d', build['elf']]
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=120)
    instructions, symbols = disassembly(process.stdout.decode())
    quant = set(symbols['quantize_row_q8_K'])
    trial = set(symbols['eval_trial'])
    writes = [(pc,instructions[pc]) for pc in quant if csr_write(instructions[pc]) in (9,10,15)]
    require(len(writes) == 1 and writes[0][1] == 0x00a0d073, 'Not the exact quantizer VXRM=RNE write')
    require(not any(csr_write(instructions[pc]) in (9,10,15) for pc in trial),
            'Trial explicitly overwrites VCSR after quantization')
    markers = sorted(pc for pc in trial if instructions[pc] == 0xc0002073)
    require(len(markers) == 2, 'Original ELF lacks the exact commit-marker pair')
    stamps = [pc for pc in trial if instructions[pc] & 0xfffff07f == 0xc0002073 and
              (instructions[pc] >> 7) & 31]
    # The native compiler duplicates a stamp on an admission-error path.
    # Retired success paths below must still match exactly six raw timestamps.
    require(len(stamps) >= 6, 'Original trial lacks six rdcycle stamp candidates')
    proof = dict(elf_sha256=build['elf_sha256'], quant_symbol='quantize_row_q8_K',
        vxrm_write_pc=f'{writes[0][0]:016x}', vxrm_write_insn='00a0d073',
        vxrm=1, expected_vcsr=2, expected_vxsat=0,
        marker_pcs=[f'{pc:016x}' for pc in markers],
        rdcycle_stamp_candidate_pcs=[f'{pc:016x}' for pc in sorted(stamps)],
        pinned_objdump=str(tools[0]), pinned_objdump_sha256=digest(tools[0]),
        disassembly_sha256=__import__('hashlib').sha256(process.stdout).hexdigest())
    return proof, instructions, quant, trial, set(stamps), markers


def parse_commit(path, build, result, proof_data):
    proof, instructions, quant, trial_pcs, stamp_pcs, markers = proof_data
    frames, frame = [], None
    expected_order, previous_cycle, last_vcsr_write = 0, -1, None
    required = {'cycle','event','order','pc','insn','rd','rd_wdata','trap'}
    with Path(path).open(newline='') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames is not None and required <= set(reader.fieldnames), 'Commit schema mismatch')
        for row in reader:
            cycle = int(row['cycle'])
            require(cycle >= previous_cycle, 'Commit cycle moved backwards')
            previous_cycle = cycle
            if row['event'] != 'retire':
                continue
            order, pc, insn = int(row['order']), int(row['pc'],16), int(row['insn'],16)
            require(order == expected_order, 'Retire order discontinuity')
            expected_order += 1
            write = csr_write(insn)
            if pc == markers[0]:
                require(insn == 0xc0002073 and frame is None and len(frames) < 2, 'Bad/extra open marker')
                require(last_vcsr_write is not None and last_vcsr_write['insn'] == 0x00f05073,
                        'Missing original pre-trial VCSR=0 reset')
                frame = dict(trial=len(frames), open_cycle=cycle, open_order=order,
                    quant_writes=[], stamps=[], fcsr_reads=[], vcsr_reads=[], vstart_reads=[])
            elif pc == markers[1]:
                require(insn == 0xc0002073 and int(row['trap']) == 0 and frame is not None, 'Bad/orphan close marker')
                frame.update(close_cycle=cycle,close_order=order,commit_marker_cycles=cycle-frame['open_cycle'])
                frames.append(frame)
                frame = None
            elif insn == 0xc0002073 and frame is not None:
                raise ValueError('Unexpected commit ROI marker')
            if frame is not None:
                require(int(row['trap']) == 0, 'Trap inside trial')
                require(pc in instructions and instructions[pc] == insn, 'Committed instruction differs from measured ELF')
                if write in (9,10,15):
                    require(pc in quant and insn == 0x00a0d073, 'Unexpected VCSR write inside trial')
                    frame['quant_writes'].append(dict(pc=f'{pc:016x}',cycle=cycle,order=order))
                if is_saturating(insn):
                    require(pc in quant, 'Post-quantization saturating operation can alter VXSAT')
                if pc in stamp_pcs:
                    frame['stamps'].append(int(row['rd_wdata'],16))
                if pc in trial_pcs and insn & 127 == 0x73 and ((insn >> 12) & 7) == 2 and (
                        (insn >> 15) & 31) == 0:
                    csr = insn >> 20
                    key = {3:'fcsr_reads',15:'vcsr_reads',8:'vstart_reads'}.get(csr)
                    if key:
                        frame[key].append(int(row['rd_wdata'],16))
            if write in (9,10,15):
                last_vcsr_write = dict(insn=insn,pc=pc,cycle=cycle)
    require(frame is None and len(frames) == 2, 'Incomplete commit trial evidence')
    for frame,record in zip(frames,result['metrics']['trials']):
        r = record['csr']
        require(len(frame['quant_writes']) == build['case']['m']*8, 'Missing/extra retired quantizer VXRM writes')
        require(frame['stamps'] == [r[f't{i}'] for i in range(6)], 'Commit/software trial stamps do not align')
        require(frame['fcsr_reads'] == [r['quant_fcsr'],r['fcsr']] and
                frame['vcsr_reads'] == [2] and frame['vstart_reads'] == [0],
                'Commit/UART flags or VCSR/VSTART snapshot mismatch')
        frame['reported_software_cycles'] = record['total_cycles']
        monitor = result['metrics']['commit_roi_monitor']
        frame['console_monitor_cycles'] = monitor['trials'][frame['trial']]['total_cycles'] if monitor['available'] else None
    return dict(state='ELF_COMMIT_VCSR_PRESERVATION_CHECKED', static=proof, trials=frames,
        scope='Exact retired quantizer writes, no other VCSR writes or saturating operations within each trial, timestamp/CSR alignment; not independent whole-SoC protocol acceptance')


def verify_audit_pins(path):
    pins = json.loads(Path(path).read_text())
    for file in (Path(__file__).resolve(),HERE/'test_vcsr_v2.py',HERE/'check.py'):
        require(pins.get(str(file)) == digest(file), 'Successor checker/test/predecessor not in audit pins')
    for file,sha in pins.items():
        require(digest(file) == sha, 'Successor audit source drift: '+file)
    return pins


def audit_run(log, directory, commit, original_result, audit_pins_path):
    verify_parser_delta()
    audit_pins = verify_audit_pins(audit_pins_path)
    build,build_path,pins = verify_build(directory)
    log,commit,original_result = map(Path,(log,commit,original_result))
    identities = {str(p):digest(p) for p in (log,commit,original_result,build_path,Path(audit_pins_path))}
    failure = json.loads(original_result.read_text())
    require(failure.get('state') == 'FAIL' and failure.get('error') == 'Vector CSR/quantization exception contract',
            'Original numerical FAIL receipt missing or has a different failure; do not relabel it')
    data = build_path.parent/'data'
    packed = 'expected_q8.bin' if build['case']['backend']=='rvv' else 'expected_packed.bin'
    arguments = (log.read_text(),build,(data/'expected.bin').read_bytes(),
                 (data/'expected_q8.bin').read_bytes(),(data/packed).read_bytes())
    result = parse_log(*arguments)
    try:
        predecessor.parse_log(*arguments)
    except ValueError as error:
        require(str(error) == failure['error'], 'Original checker failure was not solely its VCSR predicate')
    else:
        raise ValueError('Original checker unexpectedly passes; not the scoped correction')
    proof_data = elf_proof(build,pins)
    proof = parse_commit(commit,build,result,proof_data)
    for inventory in (pins,audit_pins,identities):
        for file,sha in inventory.items():
            require(digest(file)==sha, 'Input changed during scoped audit: '+file)
    result['state'] = 'PASS'
    result.update(audit_kind='SCOPED_VCSR_CORRECTION',audit_state='SCOPED_VCSR_AUDIT_PASS',
        original_worker_reclassified=False,original_numerical_state='FAIL',
        original_numerical_receipt=str(original_result),original_numerical_sha256=identities[str(original_result)],
        original_checker_sha256=PREDECESSOR_SHA256, successor_checker_sha256=digest(__file__),
        audit_source_pins_sha256=digest(audit_pins_path),build=str(build_path),build_sha256=digest(build_path),
        log=str(log),log_sha256=digest(log),commit=str(commit),commit_sha256=digest(commit),
        vcsr_evidence=proof,correction_scope='Only final VCSR=0 predicate corrected to VCSR=2; raw log/ELF/images/source pins unchanged; all other predecessor gates identical')
    result['metrics']['scope'] = 'Scoped corrected workload audit only; original worker remains FAIL; parent protocol/image audit still required'
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--build',required=True,type=Path)
    p.add_argument('--log',type=Path)
    p.add_argument('--commit',type=Path)
    p.add_argument('--original-result',type=Path)
    p.add_argument('--audit-pins',type=Path,default=DEFAULT_AUDIT_PINS)
    p.add_argument('--preflight',action='store_true')
    p.add_argument('--output',required=True,type=Path)
    a = p.parse_args()
    require(not a.output.exists(),'Refusing to overwrite audit evidence')
    try:
        verify_parser_delta()
        if a.preflight:
            build,build_path,pins = verify_build(a.build)
            proof = elf_proof(build,pins)[0]
            result = dict(state='VCSR_AUDIT_STATIC_PREFLIGHT_ONLY',rtl_executed=False,
                          original_worker_reclassified=False,build=str(build_path),elf_proof=proof)
        else:
            require(a.log is not None and a.audit_pins is not None,'--log and --audit-pins required')
            commit = a.commit or a.log.parent/'commit.csv'
            original = a.original_result or a.log.parent/'numerical.json'
            result = audit_run(a.log,a.build,commit,original,a.audit_pins)
    except (ValueError,KeyError,OSError,TypeError,subprocess.SubprocessError) as error:
        a.output.write_text(json.dumps(dict(state='SCOPED_VCSR_AUDIT_FAIL',error=str(error)),indent=2)+'\n')
        raise SystemExit(str(error)) from error
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(result['state'])


if __name__ == '__main__':
    main()

