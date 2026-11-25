#!/usr/bin/env python3
"""Queries0..63 batch64 compact checker: SDK evaluation, not production dispatch."""
import argparse
from collections import Counter
import csv
import math
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode = True
from contract import (ORDER, CONST_FIELDS, require, sha, read, save, verify, module,
                      real_fixture, constant_bytes, elf_blob, work)

RAW_FIELDS = set(('seq id command success fault validation_fault validation_error read_fault context_ready '
    'busy_cycles full refill load release v2_full v2_refill v2_row_load v2_column_load v2_column_panel '
    'v2_logical_column v2_k_view_bank_cycles v2_bank_conflict_cycles v2_rejected q_external_bytes '
    'kv_external_bytes replay_bytes replay_backpressure_cycles read_ranges translations ar r_beats '
    'read_payload_bytes store_wait_cycles read_backpressure_cycles read_outstanding_occ_sum '
    'read_outstanding_max read_outstanding_full_cycles').split())
AGGREGATES = RAW_FIELDS-set('seq id command success fault validation_fault validation_error read_fault context_ready'.split())
SUMMARY_FIELDS = AGGREGATES | set('records success_records fault_records validation_fault_records'.split())


def fields(line, prefix):
    pairs = line[len(prefix):].split()
    require(pairs and all(re.fullmatch('[a-z0-9_]+=[0-9]+',v) for v in pairs), 'Raw field syntax')
    parsed = dict(v.split('=') for v in pairs)
    require(len(parsed) == len(pairs), 'Duplicate raw field')
    return {k:int(v) for k,v in parsed.items()}


def numerical(text, gold, c):
    require(len(gold) >= 256, 'Independent golden prefix extent')
    cap = (f'PFC_CAP first={c["first"]} queries={c["queries"]} d=128 heads=2 kvheads=1 capacity=256 '
           f'outputs={c["outputs"]} printed=64 trials=4 pair_pv=1 atol=3b83126f rtol=3b03126f')
    records = [v for v in text.splitlines() if v.startswith('PFC_')]
    require(len(records) == 10 and records[0] == cap and records[-1] == 'PFC_DONE calls=4 errors=0', 'Compact record schema/count')
    expected = struct.unpack('<64f',gold[:256])
    rows = []
    for trial,mode in enumerate(ORDER):
        require(records[1+2*trial] == f'PFC_BEGIN trial={trial} mode={mode}', 'ABBA order')
        m = re.fullmatch(r'PFC_RESULT trial=([0-3]) mode=([01]) begin=([0-9]+) end=([0-9]+) '
            r'checked=([0-9]+) nonfinite=0 tolerance_errors=0 fcsr=([0-9]+) vcsr=5 vstart=0 guards=128 '
            r'input_bytes=([0-9]+) input_hash=([0-9a-f]{16}) output_hash=([0-9a-f]{16}) '
            r'repeat_errors=0 errors=0 hex=([0-9a-f]{512})',records[2+2*trial])
        require(m is not None, 'Numerical/check/CSR/guard/input failure')
        t,arm,begin,end,checked,fc,nbytes = map(int,m.groups()[:7])
        require((t,arm,checked,nbytes) == (trial,mode,c['outputs'],c['input_bytes']) and
                0 < begin < end and (not rows or rows[-1]['end'] < begin) and fc <= 31 and
                int(m[8],16) == c['input_hash'], 'Shape/full-check extent/timing/flags/input identity')
        bits = tuple(int(m[10][i:i+8],16) for i in range(0,512,8))
        values = struct.unpack('<64f',struct.pack('<64I',*bits))
        for actual,golden in zip(values,expected):
            require(math.isfinite(actual) and math.isfinite(golden) and
                    abs(actual-golden) <= .004+.002*abs(golden), 'Independent printed-value/gold mismatch')
        prior = next((r for r in rows if r['mode'] == mode),None)
        require(prior is None or (fc,bits,m[9]) == (prior['fcsr'],prior['bits'],prior['output_hash']), 'Same-mode flags/output repeat')
        rows.append(dict(trial=trial,mode=mode,begin=begin,end=end,cycles=end-begin,
                         checked=checked,fcsr=fc,bits=bits,output_hash=m[9]))
    return rows


def activity(text, c):
    expected = work(c)
    all_rows, counts, current = [], [], None
    summaries = []
    for line in text.splitlines():
        if line.startswith('PFC_BEGIN '):
            require(current is None and len(counts) < 4, 'Activity trial nesting')
            current = []
        elif line.startswith('[QBS_PERF]') or line.startswith('[RESIDENT_'):
            raise ValueError('Unexpected QBS/Resident work')
        elif line.startswith('[AKV_PERF] '):
            require(current is not None and not summaries, 'AKV outside measured full call')
            r = fields(line,'[AKV_PERF] ')
            require(set(r) == RAW_FIELDS and r['seq'] == len(all_rows)+1 and r['id'] in range(8), 'AKV field schema/sequence')
            want = expected if ORDER[len(counts)] else []
            require(len(current) < len(want) and all(r[k] == v for k,v in want[len(current)].items()), 'Native command/payload schedule')
            command = r['command']
            require(r['success'] == 1 and all(r[k] == 0 for k in
                ('fault','validation_fault','validation_error','read_fault','v2_rejected')) and
                r['busy_cycles'] > 0 and r['context_ready'] == int(command != 3), 'Native completion/fault')
            flags = dict(full=0,refill=0,load=int(command == 2),release=int(command == 3),
                v2_full=int(command == 4),v2_refill=int(command == 5),v2_row_load=int(command == 2),
                v2_column_load=int(command == 6),v2_column_panel=int(command == 6),
                v2_logical_column=4*int(command == 6))
            require(all(r[k] == v for k,v in flags.items()) and r['read_payload_bytes'] ==
                    r['q_external_bytes']+r['kv_external_bytes']+64*int(command == 4), 'Panel4/pairedPV/traffic geometry')
            all_rows.append(r); current.append(r)
        elif line.startswith('[AKV_PERF_SUMMARY] '):
            r = fields(line,'[AKV_PERF_SUMMARY] ')
            require(set(r) == SUMMARY_FIELDS, 'AKV summary schema')
            summaries.append(r)
        elif line.startswith('PFC_RESULT '):
            require(current is not None and len(current) == (len(expected) if ORDER[len(counts)] else 0), 'Missing native work')
            counts.append(len(current)); current = None
        elif '[AKV_PERF' in line:
            raise ValueError('Malformed AKV record')
    require(current is None and len(counts) == 4 and len(summaries) == 1, 'Incomplete work/summary')
    total = {k:(max(r[k] for r in all_rows) if k == 'read_outstanding_max' else sum(r[k] for r in all_rows))
             for k in AGGREGATES}
    total.update(records=len(all_rows),success_records=len(all_rows),fault_records=0,validation_fault_records=0)
    require(summaries == [total], 'Raw summary differs from actual command records')
    return dict(records_per_trial=counts,summary=total)


def roi(commit, report, rows, parsed):
    ranges = report['elf_ranges']
    starts = {bounds[0]:name for name,bounds in ranges.items() if name != 'main'}
    markers = report['roi_marker_pcs']; reads = report['roi_read_pcs']
    previous, active, index = -1, False, 0
    counts = Counter(); all_counts = Counter(); values = []
    last_stop = -1
    with Path(commit).open(newline='') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames and {'cycle','event','pc','insn','rd_wdata','trap'} <= set(reader.fieldnames), 'Commit schema')
        for r in reader:
            require(None not in r and all(v is not None for v in r.values()), 'Malformed/truncated commit record')
            cycle = int(r['cycle']); require(cycle >= previous, 'Commit ordering'); previous = cycle
            if r['event'] != 'retire': continue
            require(int(r['trap']) == 0, 'Architectural trap')
            pc,insn = int(r['pc'],16),int(r['insn'],16)
            if insn == 0xc0002073:
                require(index < 4 and pc == markers[int(active)], 'Unbound/extra ROI marker')
                if not active:
                    counts,values = Counter(),[]
                    require(cycle > last_stop, 'Overlapping ROI')
                    active = True
                else:
                    require(counts == Counter(compact_full_prefill=1,
                            **({'akv_attention_execute_v2_prefill_native':1} if ORDER[index] else {})) and
                            values == [rows[index]['begin'],rows[index]['end']], 'ROI entries/rdcycle stamps mismatch')
                    active = False; index += 1; last_stop = cycle
                continue
            if pc in starts:
                word = parsed['words'][pc]
                require(insn == (word if word & 3 == 3 else word & 0xffff), 'Entry instruction not ELF-bound')
                name = starts[pc]
                require(active == (name in ('compact_full_prefill','akv_attention_execute_v2_prefill_native')), 'Numerical audit inside ROI or kernel outside ROI')
                all_counts[name] += 1
                if active: counts[name] += 1
            if pc in reads:
                require(active and pc == reads[len(values)] and len(values) < 2 and
                        insn == parsed['words'][pc], 'Unbound/out-of-order cycle read')
                values.append(int(r['rd_wdata'],16))
    require(not active and index == 4 and all_counts == Counter(compact_full_prefill=4,
        akv_attention_execute_v2_prefill_native=2,compact_audit_all=4,compact_validate_all=4), 'Incomplete ROI/whole-output audit calls')
    return dict(markers=8,entries=dict(all_counts),all_numerical_audits_outside_roi=True)


def check(build, run, log):
    build,run,log = Path(build).resolve(strict=True),Path(run).resolve(strict=True),Path(log).resolve(strict=True)
    report = read(build/'build.json')
    require(report['state'] == 'BUILT_NOT_EXECUTED' and report['schema'] == 'prefill-prefix64-v2' and
            report['dispatch_allowed'] and report['sdk_overlays'] == {}, 'Unreleased/unready build')
    require(sha(build/'source-pins.json') == report['source_pins_sha256'], 'Pin receipt identity')
    verify(read(build/'source-pins.json')); verify(report['artifacts'])
    require(sha(report['elf']) == report['elf_sha256'] and log.is_relative_to(run), 'ELF/log identity')
    require(report['forced_sdk_api'] is True and report['production_dispatch_verified'] is False and
            report['actual_ggml_dispatch'] is False and report['runtime_admission'] is False,
            'SDK evaluation must not be relabeled as production dispatch')
    data,c = real_fixture(report['fixture']['queries'])
    require(report['fixture'] == c, 'Dimensions/constants not real-capture-derived')
    raw = Path(report['elf']).read_bytes()
    parsed = module(build/'inputs/elf_reader.py','compact_checker_elf').contract(raw)
    require(elf_blob(raw,parsed,'compact_contract',len(CONST_FIELDS)*8) == constant_bytes(c), 'ELF numeric/dimension contract')
    symbols = dict(query='llama_input_a_start',key='llama_input_b_start',value='llama_input_c_start',
                   mask='llama_input_d_start',golden='llama_golden_start')
    for role,blob in data.items():
        require(elf_blob(raw,parsed,symbols[role],len(blob)) == blob, 'ELF not exact real capture: '+role)
    require(parsed['symbols']['fixture_end']['address']-parsed['symbols']['fixture_begin']['address'] == c['input_bytes'] and
            elf_blob(raw,parsed,'fixture_begin',c['input_bytes']) == b''.join(data.values()), 'ELF full input hash extent/layout')
    addresses = {name:parsed['symbols'][name]['address'] for name in
                 ('output_before','llama_attention_output_start','llama_attention_output_end','output_after')}
    require(addresses['output_before']+64 == addresses['llama_attention_output_start'] and
            addresses['llama_attention_output_start']+c['outputs']*4 == addresses['llama_attention_output_end'] ==
            addresses['output_after'], 'ELF full output/guard extents')
    cfg = elf_blob(raw,parsed,'llama_case_config',80)
    require(struct.unpack('<20I',cfg) == (0,0,7,0,128,c['queries'],2,256,1,0,0,0,0,0,0x3db504f3,0,0,0,0,0), 'ELF actual operator configuration')
    text = log.read_text(errors='strict')
    terminal = 'Core Test *** SUCCESS *** (tohost = 0)'
    require(text.splitlines().count(terminal) == 1 and text.count('Core Test') == 1 and
            text.index('PFC_DONE calls=4 errors=0') < text.index(terminal), 'Missing/early terminal')
    require(not re.search(r'Fatal:|Error:|Error-|\b(?:FAIL|FAILED|TIMEOUT)\b',text,re.I), 'Failure text')
    for line in text.splitlines():
        if re.match(r'\s*UVM_(ERROR|FATAL)\b',line):
            require(re.fullmatch(r'\s*UVM_(ERROR|FATAL)\s*:\s*0\s*',line), 'UVM failure')
    rows = numerical(text,data['golden'],c)
    arithmetic = activity(text,c)
    entry = roi(run/'commit.csv',report,rows,parsed)
    cycle_means = [sum(r['cycles'] for r in rows if r['mode'] == mode)/2 for mode in (0,1)]
    return dict(state='PASS',metrics=dict(trials=[{k:v for k,v in r.items() if k != 'bits'} for r in rows],
        baseline_cycles=cycle_means[0],native_cycles=cycle_means[1],speedup=cycle_means[0]/cycle_means[1],
        target_values_checked_per_trial=c['outputs'],independent_raw_values_per_trial=64,
        unprinted_values='Checked on target against immutable real gold; not independently reconstructed from a hash',
        arithmetic=arithmetic,roi=entry,independent_fflags_gold=False,fflags_contract=report['fflags_contract'],
        query_count_threshold_satisfied=True,batch64_sdk_evaluation=True,forced_sdk_api=True,
        production_dispatch_verified=False,actual_ggml_dispatch=False,runtime_admission=False,
        raw_monitor_records=[v for v in text.splitlines() if v.startswith(('[PERF]','[LLM_PERF]'))],
        protocol_and_image='Parent independent gates required',whole_model=False),
        elf_sha256=sha(report['elf']),log_sha256=sha(log),commit_sha256=sha(run/'commit.csv'))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    for name in ('build','run','log','result'): p.add_argument('--'+name,type=Path,required=True)
    a = p.parse_args()
    try:
        result = check(a.build,a.run,a.log)
    except Exception as exc:
        result = dict(state='FAIL',error=str(exc))
    save(a.result,result)
    raise SystemExit(result['state'] != 'PASS')
