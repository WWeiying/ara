#!/usr/bin/env python3
"""Numerics, preserved flags/guards, actual paths/work. Parent checks protocol/image."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
from contract import (HERE, REV, SDK_OVERLAYS, FORBIDDEN, MODES, LEGACY, GEOMETRY, ELF,
                      require, save, sha, verify, load, resident_commands)

SCHEMAS = {
    'CALL':set('trial mode d heads kvheads tokens begin returned end initial_fcsr initial_vcsr initial_vstart fcsr vcsr vstart groups errors'.split()),
    'GROUP':set('trial group first_head rows q k v output'.split()),
    'MEMORY':set('trial query_hash guard_hash guard_bytes'.split()),
    'OUT':{'trial','index','bits'}, 'DATA':{'bytes','hash'}, 'DONE':{'calls','errors'},
}
HEX = {'q','k','v','output','query_hash','guard_hash','bits','hash'}


def receipt(directory):
    directory = Path(directory).resolve(strict=True)
    m = json.loads((directory/'build.json').read_text())
    require(m['schema'] == 'current-rtl-attention-firmware-v1' and
            m['state'] == 'BUILT_NOT_EXECUTED' and m['post_pins_match'] is True and
            m['sdk_commit'] == REV and set(m['sdk_overlays']) == set(SDK_OVERLAYS) and
            FORBIDDEN not in m['sdk_overlays'] and m['dirty_asm_excluded'] is True and
            not m['rtl_executed'] and not m['target_executed'], 'Firmware contract mismatch')
    require(sha(directory/'source-pins.json') == m['source_pins_sha256'] and
            sha(m['elf']) == m['elf_sha256'], 'Firmware identity drift')
    verify(json.loads((directory/'source-pins.json').read_text()))
    verify(m['artifacts'])
    require({str(p):sha(p) for p in directory.rglob('*') if p.is_file() and p.name != 'build.json'} ==
            m['artifacts'], 'Artifact membership drift')
    return m


def numerical(text, fixture):
    records = []
    for line in text.splitlines():
        if 'OP_ATTN_' not in line: continue
        match = re.fullmatch(r'OP_ATTN_([A-Z]+) (.+)',line)
        require(match is not None and match[1] in SCHEMAS, 'Malformed/unknown Attention record')
        pairs = [part.split('=') for part in match[2].split()]
        require(all(len(p)==2 for p in pairs) and len({p[0] for p in pairs}) == len(pairs) and
                {p[0] for p in pairs} == SCHEMAS[match[1]], 'Firmware field schema')
        for key,value in pairs:
            require(re.fullmatch('[0-9a-fA-F]+' if key in HEX else '[0-9]+',value), 'Firmware integer syntax')
        records.append((match[1],{k:int(v,16 if k in HEX else 10) for k,v in pairs}))
    cursor = 0

    def take(tag):
        nonlocal cursor
        require(cursor < len(records) and records[cursor][0] == tag, 'Missing/out-of-order '+tag)
        value = records[cursor][1]
        cursor += 1
        return value

    c, expected, last, elapsed = fixture['case'], fixture['result'], 0, []
    rows = c['heads']//c['kv_heads']
    for trial,mode in enumerate(fixture['order']):
        r = take('CALL')
        want = dict(trial=trial,mode=mode,d=c['dimension'],heads=c['heads'],kvheads=c['kv_heads'],
            tokens=c['tokens'],initial_fcsr=c['initial_flags'],initial_vcsr=0,initial_vstart=0,
            fcsr=expected['expected_fcsr'],vcsr=0,vstart=0,groups=c['kv_heads'],errors=0)
        require(all(r[k] == v for k,v in want.items()), 'Call shape/status/CSR/flags mismatch')
        require(last < r['begin'] < r['returned'] < r['end'], 'Incomplete/overlapping full-call stamps')
        last = r['end']
        elapsed.append(dict(trial=trial,mode=MODES[mode],rdcycle_total=r['end']-r['begin'],
                            returned_cycles=r['returned']-r['begin'],final_drain_cycles=r['end']-r['returned']))
        groups = []
        for group in range(c['kv_heads']):
            g = take('GROUP')
            require({k:g[k] for k in ('trial','group','first_head','rows')} ==
                    dict(trial=trial,group=group,first_head=group*rows,rows=rows), 'Group offset/shape mismatch')
            require(all(g[k] > 0 and g[k] % 64 == 0 for k in ('q','k','v','output')), 'Group alignment')
            if group:
                require(all(g[k]-groups[0][k] == group*stride for k,stride in
                    (('q',rows*256),('output',rows*512),('k',c['capacity']*256),('v',c['capacity']*256))),
                    'Double/missing global group offset')
            groups.append(g)
        require(take('MEMORY') == dict(trial=trial,**fixture['memory']), 'Input query/guards/inactive region changed')
        for index,bits in enumerate(expected['bits']):
            require(take('OUT') == dict(trial=trial,index=index,bits=bits), 'Independent raw F32 mismatch')
    require(take('DATA') == dict(bytes=fixture['data_bytes'],hash=fixture['data_hash']), 'Full input/golden mutation')
    require(take('DONE') == dict(calls=len(fixture['order']),errors=0) and cursor == len(records),
            'Missing/duplicate/extra terminal record')
    return elapsed


def expected_work(fixture):
    c, legacy, signatures = fixture['case'], [], []
    rows, d = c['heads']//c['kv_heads'], c['dimension']
    fields = 'v2_full v2_refill v2_row_load v2_column_load v2_column_panel v2_logical_column full refill load release q_external_bytes kv_external_bytes replay_bytes'.split()

    def command(code, **values):
        legacy.append(dict.fromkeys(fields,0) | dict(command=code) | values)

    for arm in fixture['order']:
        if arm == 0: continue
        for group in range(c['kv_heads']):
            for start in range(0,c['tokens'],64):
                t = min(64,c['tokens']-start)
                command(4 if start == 0 else 5,v2_full=int(start == 0),v2_refill=int(start != 0),
                        q_external_bytes=rows*d*2 if start == 0 else 0,kv_external_bytes=t*d*4)
                if arm == 2:
                    for mode in ('QK','PV'):
                        signatures += [0x0605705b if mode == 'QK' else 0x0485705b]*((rows+1)//2)
                    continue
                if rows == 6 and d == 128:
                    panel = c['tokens'] >= 128
                    for i in range(32 if panel else 128):
                        command(6,v2_column_load=1,v2_column_panel=int(panel),
                                v2_logical_column=4 if panel else 1,replay_bytes=t*2*(4 if panel else 1))
                        signatures.append(([0x0205785b,0x02057a5b] if panel else
                                           [0x0005745b,0x000574db])[i % 2])
                    for _ in range(t):
                        command(2,v2_row_load=1,load=1,replay_bytes=d*2)
                        signatures.append(0x0205375b)
                    continue
                for base in range(0,rows,2):
                    panel = rows >= 2 and base+1 < rows
                    for _ in range(d//4 if panel else d):
                        command(6,v2_column_load=1,v2_column_panel=int(panel),
                                v2_logical_column=4 if panel else 1,replay_bytes=t*2*(4 if panel else 1))
                        signatures.append(0x0205745b if panel else 0x0005745b)
                for base in range(0,rows,2):
                    for _ in range(t):
                        command(2,v2_row_load=1,load=1,replay_bytes=d*2)
                        signatures.append({64:0x0005345b,96:0x0405345b,128:0x0205345b}[d])
            command(3,release=1)
    return legacy, signatures


def legacy_work(text, fixture):
    old = load(LEGACY,'attention_legacy_fields')
    expected, _ = expected_work(fixture)
    rows, summaries, totals = [], [], Counter()
    for line in text.splitlines():
        if line.startswith('[AKV_PERF] '):
            require(not summaries and len(rows) < len(expected), 'Unexpected AKV command')
            r = old.parse_fields(line[len('[AKV_PERF] '):],old.PERF_FIELDS)
            require(r['seq'] == len(rows)+1 and all(r[k] == v for k,v in expected[len(rows)].items()),
                    'AKV command/payload/work mismatch at '+str(len(rows)+1))
            require(r['success'] == 1 and r['busy_cycles'] > 0 and all(r[k] == 0 for k in
                ('fault','validation_fault','validation_error','read_fault','v2_rejected')), 'AKV command fault')
            require(r['context_ready'] == int(r['command'] != 3) and r['read_payload_bytes'] ==
                    r['q_external_bytes']+r['kv_external_bytes']+64*r['v2_full'], 'Context/payload accounting')
            for key in old.SUMMARY_FIELDS-{'records','success_records','fault_records','validation_fault_records'}:
                totals[key] = max(totals[key],r[key]) if key == 'read_outstanding_max' else totals[key]+r[key]
            rows.append(r)
        elif line.startswith('[AKV_PERF_SUMMARY] '):
            summaries.append(old.parse_fields(line[len('[AKV_PERF_SUMMARY] '):],old.SUMMARY_FIELDS))
        elif '[AKV_PERF' in line:
            raise ValueError('Malformed AKV probe')
    summary = dict(totals,records=len(expected),success_records=len(expected),fault_records=0,validation_fault_records=0)
    require(len(rows) == len(expected) and summaries == [summary], 'Missing/duplicate/inconsistent AKV summary')
    return dict(commands=len(rows),summary=summary)


def resident_work(text, fixture):
    g = load(GEOMETRY,'attention_work_geometry')
    expected = resident_commands(fixture['case'],fixture['order'])
    completed, lanes = [], {}
    for line in text.splitlines():
        if not line.startswith('[RESIDENT_'): continue
        m = re.fullmatch(r'\[RESIDENT_(QK|PV)_(LANE|PERF)\] (.+)',line)
        require(m is not None and len(completed) < len(expected), 'Unknown/extra resident probe')
        c = expected[len(completed)]
        require(m[1] == c['mode'], 'Resident QK/PV ordering')
        shape, r = g.geometry(c), g.parse_fields(m[3])
        if m[2] == 'LANE':
            fields = set('lane vid tokens elements heads issued returned writes flags error'.split())
            if c['mode'] == 'QK': fields.add('dimensions')
            require(set(r) == fields, 'Resident lane fields')
            lane = r['lane']
            require(lane in range(4) and lane not in lanes and shape['writes'][lane], 'Duplicate/inactive lane')
            want = dict(tokens=c['tokens'],elements=shape['elements'][lane],heads=c['heads'],
                issued=shape['fma'][lane],returned=shape['fma'][lane],writes=len(shape['writes'][lane]),error=0)
            if c['mode'] == 'QK': want['dimensions'] = c['dimension']
            require(all(r[k] == v for k,v in want.items()) and r['flags'] in range(32) and
                    r['vid'] in range(8), 'Resident lane accepted/returned/write counts')
            lanes[lane] = r
            continue
        require(set(r) == set(shape['counts'])|{'seq','vid','cycles','flags','error'} and
                all(r[k] == v for k,v in shape['counts'].items()) and r['seq'] == len(completed)+1 and
                r['vid'] in range(8) and r['cycles'] > 0 and r['error'] == 0, 'Resident terminal geometry')
        require(set(lanes) == {i for i in range(4) if shape['writes'][i]}, 'Missing active resident lane')
        flags = 0
        for lane in lanes.values():
            require(lane['vid'] == r['vid'], 'Resident lane VID')
            flags |= lane['flags']
        first = c['group']*(fixture['case']['heads']//fixture['case']['kv_heads'])+c['base']
        phase = [s['fflags'] for s in fixture['result']['stages'] if s['mode'] == c['mode'] and
                 s['tile'] == c['tile'] and s['head'] in range(first,first+c['heads'])]
        require(len(phase) == c['heads'], 'Missing independent command flag reference')
        expected_flags = 0
        for value in phase: expected_flags |= value
        require(flags == r['flags'] == expected_flags, 'Independent resident arithmetic flags')
        completed.append(dict(command=c,terminal=r))
        lanes = {}
    require(len(completed) == len(expected) and not lanes, 'Incomplete resident work')
    return completed


def vector_work(path, fixture):
    g = load(GEOMETRY,'attention_vector_geometry')
    expected = resident_commands(fixture['case'],fixture['order'])
    signatures, completed, seen, live = [], [], set(), {}
    previous, config, index = -1, 0, 0
    with Path(path).open(newline='') as stream:
        reader = csv.DictReader(stream)
        fields = set('cycle event arch_seq vid lane source insn use_vd vd eew vl vstart addr be wdata nr_lanes vlen_bits'.split())
        require(reader.fieldnames and len(set(reader.fieldnames)) == len(reader.fieldnames) and
                fields <= set(reader.fieldnames), 'Vector CSV schema')
        for r in reader:
            require(None not in r and all(v is not None for v in r.values()), 'Malformed vector CSV row')
            cycle, event = int(r['cycle']), r['event']
            require(cycle >= previous and (r['nr_lanes'],r['vlen_bits']) == ('4','1024'), 'Vector cycle/configuration drift')
            previous = cycle
            if event == 'config':
                require(config == 0 and cycle == 0 and not signatures, 'Duplicate/late vector configuration')
                config += 1
                continue
            require(config == 1 and event in ('alloc','write','done'), 'Unknown vector event')
            insn = int(r['insn'],16)
            if event == 'alloc' and insn & 0x707f in (0x305b,0x705b): signatures.append(insn)
            if insn not in (0x0605705b,0x0485705b): continue
            key = int(r['arch_seq']),int(r['vid'])
            if event == 'alloc':
                require(key not in seen and not live and index < len(expected), 'Duplicate/overlapping resident allocation')
                shape = g.geometry(expected[index])
                require(insn == shape['opcode'], 'Resident opcode order')
                live[key] = dict(shape=shape,writes=set(),begin=cycle)
                seen.add(key)
                index += 1
            require(key in live, 'Unowned resident vector event')
            entry, shape = live[key], live[key]['shape']
            require(insn == shape['opcode'] and tuple(int(r[k]) for k in ('use_vd','vd','eew','vl','vstart')) ==
                    (1,0,shape['eew'],shape['vl'],0), 'Resident vector metadata')
            if event == 'write':
                lane,addr = int(r['lane']),int(r['addr'])
                require(lane in range(4) and addr in shape['writes'][lane] and int(r['source']) == 4 and
                        int(r['be'],16) == shape['writes'][lane][addr] and
                        re.fullmatch('[0-9a-fA-F]{16}',r['wdata']) and (lane,addr) not in entry['writes'],
                        'Illegal/duplicate resident VRF write')
                entry['writes'].add((lane,addr))
            elif event == 'done':
                require(entry['writes'] == {(lane,addr) for lane in range(4) for addr in shape['writes'][lane]},
                        'Incomplete resident VRF result')
                completed.append(dict(vid=key[1],writes=len(entry['writes']),cycles=cycle-entry['begin']))
                del live[key]
    require(config == 1 and not live and len(completed) == len(expected) and
            signatures == expected_work(fixture)[1], 'Incomplete/wrong native/resident opcode signature')
    return completed


def entries(path, build):
    fixture, ranges = build['fixture'], build['elf_ranges']
    c, order = fixture['case'], fixture['order']
    groups, tiles, pairs = c['kv_heads'], (c['tokens']+63)//64, (c['heads']//c['kv_heads']+1)//2
    want = dict(attention_full_call=len(order),akv_decode_execute=2*len(order),
        attention_rvv_group=order.count(0)*groups,attention_rvv_pack=order.count(0)*groups*tiles,
        attention_rvv_qk_pair=order.count(0)*groups*tiles*pairs,
        attention_rvv_pv_pair=order.count(0)*groups*tiles*pairs,
        akv_attention_execute_v2_native_auto=order.count(1)*groups,
        akv_experimental_attention_execute_v2_native=order.count(2)*groups,
        akv_experimental_resident_qk_prepared=order.count(2)*groups*tiles*pairs,
        akv_experimental_resident_pv_compact=order.count(2)*groups*tiles*pairs)
    elf = load(ELF,'attention_entry_elf').contract(Path(build['elf']).read_bytes())
    starts = {ranges[name][0]:name for name in want}
    counts, previous, markers = Counter(), -1, 0
    with Path(path).open(newline='') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames and {'cycle','event','pc','insn','trap'} <= set(reader.fieldnames), 'Commit CSV schema')
        for r in reader:
            require(None not in r and all(v is not None for v in r.values()), 'Malformed commit CSV')
            cycle = int(r['cycle'])
            require(cycle >= previous, 'Commit cycle order')
            previous = cycle
            if r['event'] != 'retire': continue
            require(int(r['trap']) == 0, 'Architectural trap')
            pc, insn = int(r['pc'],16),int(r['insn'],16)
            if insn == 0xc0002073: markers += 1
            if pc in starts:
                word = elf['words'][pc]
                require(insn == (word if word & 3 == 3 else word & 0xffff), 'Entry PC/instruction not ELF-bound')
                counts[starts[pc]] += 1
    require(dict(counts) == want, 'Actual SDK/leaf/RVV entry counts mismatch: '+str(dict(counts)))
    require(markers == 2*len(order), 'Missing/extra total-ROI monitor markers')
    return dict(counts=want,monitor_markers=markers)


def check(build, log, vector, commit):
    m = receipt(build)
    text = Path(log).read_text()
    old = load(LEGACY,'attention_severity')
    old.classify_simulator(text)
    measured = numerical(text,m['fixture'])
    akv = legacy_work(text,m['fixture'])
    resident = resident_work(text,m['fixture'])
    writes = vector_work(vector,m['fixture'])
    require(all(a['terminal']['vid'] == b['vid'] and a['terminal']['result_words'] == b['writes']
                for a,b in zip(resident,writes)), 'Resident perf/vector disagreement')
    actual = entries(commit,m)
    f = m['fixture']
    monitor = [line for line in text.splitlines() if line.startswith(('[LLM_METRIC]','[PERF]'))]
    return dict(state='PASS',metrics=dict(case=f['case']['id'],trials=measured,
        bitexact_output_values=len(f['result']['bits'])*len(f['order']),
        expected_fcsr=f['result']['expected_fcsr'],akv=akv,resident=resident,actual_entries=actual,
        qk_scalar_fmas_per_call=f['case']['heads']*f['case']['tokens']*f['case']['dimension'],
        pv_scalar_fmas_per_call=f['case']['heads']*f['case']['tokens']*f['case']['dimension'],
        monitor_records=monitor,monitor_cycles_are_not_rdcycle_roi=True,
        primary_model_performance_eligible=f['primary_model_performance_eligible'],
        rvv_speedup_primary_eligible=False,baseline=m['baseline_classification']),
        protocol_checked=False,image_checked=False,performance_acceptance=False,
        scope=m['scope'],build_sha256=sha(Path(build)/'build.json'),
        evidence_sha256={str(p):sha(p) for p in (log,vector,commit)})


def main():
    parser = argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    for name in ('build','log','vector','commit','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args = parser.parse_args()
    try:
        result = check(args.build,args.log,args.vector,args.commit)
    except Exception as exc:
        result = dict(state='FAIL',error=str(exc),performance_acceptance=False)
    save(args.output,result)
    print(json.dumps({k:v for k,v in result.items() if k != 'metrics'}))
    return result['state'] != 'PASS'


if __name__ == '__main__':
    raise SystemExit(main())
