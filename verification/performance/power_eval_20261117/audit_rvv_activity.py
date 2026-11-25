#!/usr/bin/env python3
"""Offline power-only admission and complete-loop window selection for baseline RVV."""
import argparse
from collections import Counter
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
RTL = OUT/'power_rtl_20261117_baseline_01'
CAMPAIGN = OUT/'power_precheck_20261117_baseline_02'
CC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


v6 = load(HERE/'q4_m4_dut_fail_v6.py', 'rvv_scoped_protocol')
old = v6.old
require, sha, save = old.require, old.sha, old.save


def scan(path, footer, token):
    source, source_line, sources = v6.v5.source_proof(RTL)
    event = (r'UVM_ERROR '+re.escape(str(source))+r'\('+str(source_line)+
             r'\) @ ([0-9]+): uvm_test_top \[CVXIF/DUT_FAIL\] real Ara program did not report success')
    kept, classified, counts = [], [], Counter()
    h = hashlib.sha256()
    total = kept_bytes = line_number = 0
    with path.open('rb') as stream:
        while True:
            raw = stream.readline(65537)
            if not raw:
                break
            total += len(raw)
            line_number += 1
            require(len(raw) <= 65536 and total <= 1 << 30, 'Raw log resource bound')
            h.update(raw)
            line = raw.decode().rstrip('\r\n')
            require('\0' not in line and not re.search(
                r'(?i)(Error[-:]|Fatal:|Assertion failed|\$(?:fatal|error)|\bTIMEOUT\b|\bTIMED OUT\b)', line),
                'Simulator failure at line '+str(line_number))
            if line.startswith(footer): counts['footer'] += 1
            if line == '--- UVM Report Summary ---': counts['report'] += 1
            if line == 'Core Test *** FAILED *** (tohost = 1)':
                require(counts['footer'] == 1, 'Early EOC')
                counts['eoc'] += 1
            elif 'Core Test' in line or re.search(r'\bFAILED\b', line):
                raise ValueError('Unexpected completion')
            match = re.fullmatch(event, line)
            if match:
                require(counts['eoc'] == 1 and not counts['report'], 'DUT_FAIL order')
                counts['event'] += 1
                classified.append(dict(line=line_number, kind='EXPECTED_NUMERIC_DUT_FAIL', raw=line))
                continue
            if re.fullmatch(r'\s*UVM_ERROR\s*:\s*1\s*', line):
                require(counts['report'] == counts['event'] == 1, 'Error summary scope')
                counts['summary'] += 1
                classified.append(dict(line=line_number, kind='ERROR_SUMMARY_ONE_DUT_FAIL', raw=line))
                continue
            if re.search(r'\bUVM_(ERROR|FATAL)\b', line):
                require(re.fullmatch(r'\s*UVM_FATAL\s*:\s*0\s*', line), 'Unexpected UVM error')
                counts['fatal_zero'] += 1
            if '[CVXIF/DUT_FAIL]' in line:
                require(re.fullmatch(r'\[CVXIF/DUT_FAIL\]\s+1', line), 'Unknown DUT_FAIL diagnostic')
                counts['id'] += 1
            if token in line or 'Core Test' in line or '[QBS_PERF]' in line:
                kept_bytes += len(raw)
                require(kept_bytes <= 262144, 'Actual semantic record bound')
                kept.append(line)
    require(all(counts[k] == 1 for k in ('footer','report','eoc','event','summary','fatal_zero','id')),
            'Numerical DUT_FAIL inventory')
    return '\n'.join(kept)+'\n', dict(raw_sha256=h.hexdigest(), raw_bytes=total, raw_lines=line_number,
        expected_numerical_failure_records=classified, all_raw_lines_checked=True,
        synthesized_records=False), sources


def float32(bits):
    return struct.unpack('<f', struct.pack('<I', bits))[0]


def fnv64(data):
    value = 14695981039346656037
    for byte in data:
        value = ((value ^ byte) * 1099511628211) & ((1 << 64)-1)
    return value


def attention_numeric(text, m, build):
    ap = load(HERE/'prepare_attention.py', 'rvv_attention_schema')
    schemas = ap.checker()
    records = []
    for line in text.splitlines():
        if not line.startswith('OP_ATTN_'): continue
        match = re.fullmatch(r'OP_ATTN_([A-Z]+) (.+)', line)
        require(match and match[1] in schemas.SCHEMAS, 'Attention record syntax')
        pairs = [p.split('=') for p in match[2].split()]
        require(all(len(p) == 2 for p in pairs) and len({p[0] for p in pairs}) == len(pairs) and
                {p[0] for p in pairs} == schemas.SCHEMAS[match[1]], 'Attention schema')
        row = {}
        for key, value in pairs:
            require(re.fullmatch('[0-9a-fA-F]+' if key in schemas.HEX else '[0-9]+', value), 'Attention integer')
            row[key] = int(value, 16 if key in schemas.HEX else 10)
        records.append((match[1], row))
    cursor = 0
    def take(tag):
        nonlocal cursor
        require(cursor < len(records) and records[cursor][0] == tag, 'Attention record order/count')
        value = records[cursor][1]
        cursor += 1
        return value
    f = m['fixture']
    require(f['order'] == [0,0] and f['printed_values'] == 256, 'Full ordinary-memory RVV outputs required')
    model_raw = (build/'inputs/model_golden.bin').read_bytes()
    model = struct.unpack('<256f', model_raw)
    trials, errors, last_end = [], 0, 0
    for t in range(2):
        r = take('CALL')
        expected = dict(trial=t, mode=0, d=128, heads=2, kvheads=1, tokens=137,
            initial_fcsr=8, initial_vcsr=0, initial_vstart=0,
            fcsr=f['result']['expected_fcsr'], vcsr=0, vstart=0, groups=1)
        require(all(r[k] == v for k,v in expected.items()) and last_end < r['begin'] < r['returned'] < r['end'],
                'Attention shape/flags/CSR/time contract')
        last_end = r['end']
        group = take('GROUP')
        require(all(group[k] == v for k,v in dict(trial=t,group=0,first_head=0,rows=2).items()) and
                all(group[k] > 0 and group[k] % 64 == 0 for k in ('q','k','v','output')), 'Attention group')
        require(take('MEMORY') == dict(trial=t, **f['memory']), 'Attention query/guards/inactive bytes changed')
        check = take('CHECK')
        require(check['trial'] == t and check['values'] == 256 and check['model_errors'] == 0, 'Target all-output check')
        bits, max_abs, max_model, bit_errors = [], 0.0, 0.0, 0
        for i, golden_bits in enumerate(f['result']['bits']):
            out = take('OUT')
            require(out['trial'] == t and out['index'] == i and 0 <= out['bits'] <= 0xffffffff, 'Output identity')
            value, golden = float32(out['bits']), float32(golden_bits)
            require(all(math.isfinite(v) for v in (value, golden, model[i])), 'Nonfinite attention output/golden')
            delta = abs(value-golden)
            require(delta <= 0.0002+0.0002*abs(golden), 'Independent attention tolerance')
            require(abs(value-model[i]) <= 0.003+0.02*abs(model[i]), 'Original model tolerance')
            max_abs = max(max_abs, delta)
            max_model = max(max_model, abs(value-model[i]))
            bit_errors += out['bits'] != golden_bits
            bits.append(out['bits'])
        require(fnv64(struct.pack('<256I', *bits)) == check['output_hash'], 'Actual all-output fingerprint')
        require(r['errors'] == bit_errors and bit_errors > 0, 'Not solely strict bitwise numerical failure')
        errors += r['errors']
        trials.append(dict(**r, finite_outputs=256, bitwise_differences=bit_errors,
                           max_abs=max_abs, max_model_abs=max_model))
    require(take('DATA') == dict(bytes=f['data_bytes'], hash=f['data_hash']), 'Attention captured input/golden mutation')
    require(take('DONE') == dict(calls=2, errors=errors) and cursor == len(records), 'Attention footer')
    return dict(state='POWER_ELIGIBLE', strict_numerical_state='FAIL', finite_outputs=512,
        trials=trials, independent_atol=0.0002, independent_rtol=0.0002,
        original_model_atol=0.003, original_model_rtol=0.02, output_values_checked=512,
        memory_guards_unchanged=True, no_extra_flags=True, hash_only_acceptance=False)


def m1_numeric(text, m):
    raw_records = [old.old.fields(line,'OPR_RAW ',('kind','hex')) for line in text.splitlines()
                   if line.startswith('OPR_RAW ')]
    records = [(line.split()[0], old.old.fields(line, line.split()[0]+' ', ('id','kind')))
               for line in text.splitlines() if line.startswith('OPR_') and not line.startswith('OPR_RAW ')]
    require(len(records) == 12, 'M1 record count')
    cursor = 0
    def take(tag):
        nonlocal cursor
        require(records[cursor][0] == tag, 'M1 record order')
        r = records[cursor][1]
        cursor += 1
        return r
    require(take('OPR_META') == dict(id=m['build_id'],m=1,n=64,k=2048,profile=1,ap=1,kb=8,ab=292,
                                    rvv=1,trials=2,policy=1), 'M1 metadata')
    trials, errors, diagnostics = [], 0, {}
    for raw in raw_records:
        require(set(raw) == {'trial','kind','offset','hex'} and raw['trial'] in (0,1) and
                raw['kind'] in ('Q8','PACK') and re.fullmatch(r'(?:[0-9a-f]{2}){1,16}',raw['hex']),
                'M1 failure diagnostic schema')
        key = (raw['trial'],raw['kind'])
        require(key not in diagnostics,'Duplicate M1 diagnostic')
        diagnostics[key] = raw
    require(set(diagnostics) == {(t,k) for t in range(2) for k in ('Q8','PACK')}, 'Missing failure diagnostics')
    for t in range(2):
        r = take('OPR_TRIAL')
        require(set(r) == set('trial status commands quant_fcsr quant_vcsr fcsr vcsr vstart'.split()) |
                {'t%d' % i for i in range(6)}, 'M1 trial schema')
        require(r['trial'] == t and r['status'] == r['commands'] == r['vstart'] == 0 and
                r['quant_fcsr'] & ~3 == 0 and r['quant_vcsr'] == r['vcsr'] == 2 and
                r['fcsr'] in (t*8,t*8|1), 'M1 SDK/flags/CSR')
        stamps = [r['t%d'%i] for i in range(6)]
        require(all(0 <= a < b < 1 << 64 for a,b in zip(stamps,stamps[1:])) and
                (not trials or r['t0'] > trials[-1]['t5']), 'M1 time bounds')
        checks = []
        for kind in ('Q8','PACK','OUT','GUARD'):
            c, gold = take('OPR_CHECK'), m['comparisons'][kind]
            require(set(c) == set('trial kind count mismatches first expected_hash actual_hash raw_differences first_actual first_expected'.split())
                    and c['trial'] == t and c['kind'] == kind, 'M1 comparison schema')
            raw = Path(gold['path']).read_bytes()
            require(old.fnv(raw) == gold['expected_hash'] == c['expected_hash'] and c['count'] == gold['count'] and
                    len(raw) == c['count']*(4 if kind == 'OUT' else 1) and
                    0 <= c['actual_hash'] <= 0xffffffff and 0 <= c['raw_differences'] <= c['count'], 'M1 golden identity')
            if kind in ('OUT','GUARD'):
                require(c['mismatches'] == c['first_actual'] == c['first_expected'] == 0 and
                        c['first'] == 0xffffffff, 'M1 nonfinite/out-of-tolerance output or bad guards')
                if kind == 'GUARD':
                    require(c['actual_hash'] == c['expected_hash'] and not c['raw_differences'], 'M1 guard bytes')
            else:
                require(0 < c['mismatches'] == c['raw_differences'] <= c['count'] and 0 <= c['first'] < c['count'] and
                        0 <= c['first_actual'] <= 255 and c['first_expected'] == raw[c['first']], 'M1 strict byte differences')
                diagnostic = diagnostics[t,kind]
                actual_bytes = bytes.fromhex(diagnostic['hex'])
                require(diagnostic['offset'] == c['first'] and actual_bytes[0] == c['first_actual'] and
                        len(actual_bytes) == min(16,len(raw)-c['first']), 'M1 raw/target diagnostic binding')
                errors += 1
            checks.append(c)
        trials.append(dict(**r, checks=checks))
    require(take('OPR_DONE') == dict(errors=errors) and errors == 4, 'M1 error cause inventory')
    return dict(state='POWER_ELIGIBLE',strict_numerical_state='FAIL',trials=trials,
        finite_outputs=128, output_values_checked=128, atol=0.0002, rtol=0.0002,
        tolerance_proof='Pinned exhaustive finite/tolerance comparator covers every output; max error was not logged',
        max_abs_not_recorded=True, memory_guards_unchanged=True, hash_only_acceptance=False)


def trace(path, elf, expected, anchor, output):
    nm = CC.with_name(CC.name.replace('gcc','nm'))
    proc = subprocess.run([str(nm), '--defined-only', '-n', str(elf)], capture_output=True, text=True, check=True, timeout=30)
    (output/'symbols.log').write_text(proc.stdout)
    symbols = {p[2]:int(p[0],16) for line in proc.stdout.splitlines() if len(p:=line.split()) == 3}
    reader = load(HERE.parent/'resident_rvv/qk_shared/qk_boundary/elf.py', 'rvv_elf')
    parsed = reader.contract(elf.read_bytes())
    entries = {symbols[name]:name for name in expected}
    anchor = symbols[anchor] if isinstance(anchor,str) else anchor
    require(anchor in parsed['words'], 'Window anchor is not executable ELF code')
    counts, anchors, markers, order, previous = Counter(), [], 0, -1, -1
    with path.open(newline='') as stream:
        rows = csv.DictReader(stream)
        require(rows.fieldnames and {'cycle','event','order','pc','insn','trap'} <= set(rows.fieldnames), 'Commit schema')
        for row in rows:
            require(None not in row and all(v is not None for v in row.values()), 'Malformed commit row')
            cycle = int(row['cycle'])
            require(cycle >= previous and int(row['trap']) == 0, 'Commit order/architectural exception')
            previous = cycle
            if row['event'] != 'retire': continue
            require(int(row['order']) == order+1, 'Retire trace gap')
            order += 1
            pc, insn = int(row['pc'],16), int(row['insn'],16)
            if pc in entries or pc == anchor:
                word = parsed['words'][pc]
                require(insn == (word if word & 3 == 3 else word & 0xffff), 'ELF/retire instruction mismatch')
            if pc in entries: counts[entries[pc]] += 1
            if pc == anchor: anchors.append(cycle)
            markers += insn == 0xc0002073
    require(dict(counts) == expected and markers == 4 and len(anchors) >= 3, 'Incomplete/full-work path')
    first, last = anchors[1]+1, anchors[2]+1
    require(2 <= last-first <= 32768, 'Complete-loop window bound')
    return dict(entry_counts=dict(counts), architectural_traps=0, retired=order+1, roi_markers=markers,
        window=dict(first_cycle=first,last_cycle=last,cycles=last-first,anchor_pc=hex(anchor),
            anchor_cycles=anchors[:16], basis='Second complete loop/tile interval in first trial, including waits',
            clock_relation='RTL pre-edge wall_cycle to post-edge gate counter +1; gate PC/phase validation remains required',
            gate_phase_checked=False)), {str(nm):sha(nm),str(Path(reader.__file__)):sha(reader.__file__)}


def audit(kind, output):
    require(kind in ('attention','m1','m4') and output.parent == OUT and not output.exists(), 'Fresh audit required')
    if kind == 'm4':
        prior = OUT/'power_q4_m4_dut_fail_20261117_rvv_03'
        result = json.loads((prior/'result.json').read_text())
        require(result['state'] == 'POWER_ELIGIBLE' and not result['full_protocol_pass'], 'Scoped M4 qualification')
        pins = json.loads((prior/'source-pins.json').read_text())
        old.verify(pins)
        old.verify(result['artifacts'])
        run = Path(result['original_run'])
        build = OUT/'power_q4_m4_compact_20261117_rvv_02'
        m = old.receipt(build)
        expected, anchor = dict(eval_trial=2,quantize_row_q8_K=8,q4k_gemm_32x4=4), 0x80002568
    else:
        case_id = 'power_attention_rvv' if kind == 'attention' else 'qwen3_real_decode_attn_q_m1_n64_rvv_x32'
        run = CAMPAIGN/'runs'/case_id
        require(json.loads((run/'result.json').read_text())['state'] == 'FAIL', 'Original FAIL required')
        plan = json.loads((CAMPAIGN/'plan.json').read_text())
        case = next(c for c in plan['cases'] if c['id'] == case_id)
        build = Path(case['checker'][case['checker'].index('--build')+1])
        m = json.loads((build/'build.json').read_text())
        pins = json.loads((CAMPAIGN/'source-pins.json').read_text())
        old.verify(pins)
        old.verify(json.loads(Path(m['source_pins'] if kind == 'm1' else build/'source-pins.json').read_text()))
        if kind == 'attention':
            ap = load(HERE/'prepare_attention.py','activity_attention_receipt')
            m = ap.receipt(build)
            expected = dict(attention_full_call=2,attention_rvv_group=2,attention_rvv_pack=6,
                attention_memory_qk_panel4=6,attention_memory_pv_rotation=6,akv_decode_execute=4)
            anchor = 'attention_rvv_pack'
        else:
            require(sha(m['elf']) == m['elf_sha256'] == case['elf_sha256'], 'M1 ELF identity')
            expected, anchor = dict(projection_trial=2,quantize_row_q8_K=2,q4k_gemv_32=4), 0x800022f8
    elf = Path(m['elf'])
    require(sha(elf) == m['elf_sha256'], 'Firmware identity')
    files = [run/'result.json',run/'run.vcs.log',run/'commit.csv',run/'vector.csv',build/'build.json',
        Path(__file__).resolve(),HERE/'test_audit_rvv_activity.py',RTL/'build.json',RTL/'source-pins.json']
    if kind == 'm4': files.append(prior/'result.json')
    evidence = {str(p):sha(p) for p in files}
    image = json.loads((RTL/'build.json').read_text())
    old.verify(image['image_pins'])
    old.verify(json.loads((RTL/'source-pins.json').read_text()))
    output.mkdir()
    report = dict(state='FAIL',kind=kind,original_worker_reclassified=False,simulations_launched=0,
                  strict_numerical_state='FAIL',full_protocol_pass=False,power_acceptance=False)
    try:
        if kind != 'm4':
            text, classified, sources = scan(run/'run.vcs.log',
                'OP_ATTN_DONE ' if kind == 'attention' else 'OPR_DONE ',
                'OP_ATTN_' if kind == 'attention' else 'OPR_')
            require(classified['raw_sha256'] == evidence[str(run/'run.vcs.log')], 'Log drift')
            save(output/'raw-classification.json', classified)
            numeric = attention_numeric(text,m,build) if kind == 'attention' else m1_numeric(text,m)
            save(output/'numerical-power.json', numeric)
            expected_issues = v6.expected_issues(run/'run.vcs.log', classified)
            env = dict(json.loads((RTL/'plan.json').read_text())['environment'],
                PYTHONPATH=plan['protocol_pythonpath'],PYTHONDONTWRITEBYTECODE='1')
            argv = [sys.executable,'-B','-m','ara_verify.uvm_dut','--require-events','--require-backend',
                '--require-axi','--require-axi-write','--vector-trace',str(run/'vector.csv'),
                '--log',str(run/'run.vcs.log'),'--simv',str(RTL/'sim/simv'),'--elf',str(elf),
                '--output',str(output/'protocol-original.json')]
            with (output/'protocol.log').open('x') as log:
                proc = subprocess.run(argv,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=1200)
            require(proc.returncode == 1, 'Strict protocol FAIL must remain')
            proof = json.loads((output/'protocol-original.json').read_text())
            scoped = v6.check_scope(proof,expected_issues,case,image['image_pins'][str(RTL/'sim/simv')],
                                   evidence[str(run/'run.vcs.log')],evidence[str(run/'vector.csv')])
            save(output/'protocol-scoped.json',scoped)
            pins.update(sources)
        else:
            numeric = dict(reused_power_audit=str(prior),finite_outputs=512,strict_numerical_state='FAIL')
        work, tools = trace(run/'commit.csv',elf,expected,anchor,output)
        pins.update(tools)
        save(output/'window-evidence.json',work)
        old.verify(evidence)
        old.verify(pins)
        report.update(state='POWER_ELIGIBLE',elf=str(elf),elf_sha256=sha(elf),run=str(run),
            firmware_build=str(build),numeric=numeric,work=work,traffic_protocol_checked=True,
            configuration='reconstructed_no_qbs_c910_baseline',historical_byte_identity='UNPROVEN',
            scope='Relative-power activity admission only; strict program/UVM/protocol FAILs remain unchanged')
    except Exception as exc:
        report['error'] = repr(exc)
    pins.update(evidence)
    save(output/'source-pins.json',pins)
    report['artifacts'] = {str(p):sha(p) for p in output.rglob('*') if p.is_file()}
    save(output/'result.json',report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--kind',choices=('attention','m1','m4'),required=True)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    result = audit(a.kind,a.output.resolve())
    print(json.dumps({k:v for k,v in result.items() if k not in ('artifacts','numeric')}))
    return int(result['state'] != 'POWER_ELIGIBLE')


if __name__ == '__main__':
    raise SystemExit(main())
