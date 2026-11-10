#!/usr/bin/env python3
"""Strict three-call arithmetic, actual entry/command, and resident write checks."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import fixture as f

SHARED = f.ROOT/'verification/performance/resident_rvv/qk_shared'
GEOMETRY = SHARED/'full_call/check_work.py'
OLD_CHECK = f.ROOT/'verification/performance/akv_pair_eval/check.py'
ELF_READER = SHARED/'qk_boundary/elf.py'


def build_receipt(directory):
    directory = Path(directory).resolve(strict=True)
    m = json.loads((directory/'build.json').read_text())
    f.require(m.get('state') == 'BUILT_NOT_EXECUTED' and
              m.get('schema') == 'resident-sdk-three-call-v1' and m.get('cases') == list(f.CASES) and
              m.get('target_executed') is False and m.get('rtl_executed') is False and
              m.get('post_pins_match') is True,'Unreviewed SDK firmware')
    f.require(m['source_pins_sha256'] == f.sha(directory/'source-pins.json') and
              m['elf_sha256'] == f.sha(m['elf']),'Software identity changed')
    inventories = [json.loads((directory/'source-pins.json').read_text()),m['artifacts']]
    for pins in inventories:
        for path,digest in pins.items():
            f.require(f.sha(path) == digest,'Input/artifact drift: '+path)
    actual = {str(p):f.sha(p) for p in directory.rglob('*') if p.is_file() and p != directory/'build.json'}
    f.require(actual == m['artifacts'],'Incomplete software inventory')
    return m


SCHEMAS = {
    'CALL':set('trial requested d heads kvheads tokens begin returned end initial_fcsr initial_vcsr initial_vstart fcsr vcsr vstart groups errors'.split()),
    'GROUP':set('trial group first_head rows q k v output'.split()),
    'MEMORY':set('trial query_hash guard_hash guard_bytes'.split()),
    'OUT':set('trial index bits'.split()),
    'DATA':{'bytes','hash'}, 'DONE':{'calls','errors'},
}
HEX = {'q','k','v','output','query_hash','guard_hash','bits','hash'}


def numerical(text,fixture):
    records = []
    for line in text.splitlines():
        if not line.startswith('SDK_ATTENTION_'):
            continue
        match = re.fullmatch(r'SDK_ATTENTION_([A-Z]+) (.+)',line)
        f.require(match is not None and match[1] in SCHEMAS,'Unknown firmware record')
        pairs = [part.split('=') for part in match[2].split()]
        f.require(all(len(p)==2 for p in pairs) and len({p[0] for p in pairs}) == len(pairs) and
                  {p[0] for p in pairs} == SCHEMAS[match[1]],'Firmware field schema')
        values = {key:int(value,16 if key in HEX else 10) for key,value in pairs}
        records.append((match[1],values))
    cursor, outputs, elapsed = 0, [], []

    def take(tag):
        nonlocal cursor
        f.require(cursor < len(records) and records[cursor][0] == tag,'Missing/out-of-order '+tag)
        value = records[cursor][1]
        cursor += 1
        return value

    last = 0
    for trial,c in enumerate(f.CASES):
        r = take('CALL')
        want = dict(trial=trial,requested=c['requested'],d=c['dimension'],heads=c['heads'],
            kvheads=c['kv_heads'],tokens=c['tokens'],initial_fcsr=c['initial_flags'],
            initial_vcsr=0,initial_vstart=0,fcsr=fixture['results'][trial]['expected_fcsr'],
            vcsr=0,vstart=0,groups=c['kv_heads'],errors=0)
        f.require(all(r[k] == v for k,v in want.items()),'Call shape/status/CSR/flags mismatch')
        f.require(last < r['begin'] < r['returned'] < r['end'],'Overlapping/incomplete full call')
        last = r['end']
        elapsed.append(r['end']-r['begin'])
        groups = []
        rows = c['heads']//c['kv_heads']
        for group in range(c['kv_heads']):
            g = take('GROUP')
            f.require({k:g[k] for k in ('trial','group','first_head','rows')} ==
                      dict(trial=trial,group=group,first_head=group*rows,rows=rows),
                      'Decode group/first_head mismatch')
            f.require(all(g[k] > 0 and g[k] % 64 == 0 for k in ('q','k','v','output')),
                      'Group pointer alignment')
            if group:
                f.require(all(g[k]-groups[0][k] == group*stride for k,stride in
                    (('q',rows*256),('output',rows*512),('k',c['capacity']*256),
                     ('v',c['capacity']*256))),'Double/missing decode offset')
            groups.append(g)
        f.require(take('MEMORY') == dict(trial=trial,**fixture['memory'][trial]),
                  'Query/guards/inactive region corruption')
        raw = []
        for index,expected in enumerate(fixture['results'][trial]['bits']):
            r = take('OUT')
            f.require(r == dict(trial=trial,index=index,bits=expected),'Raw F32 numerical mismatch')
            raw.append(r['bits'])
        outputs.append(raw)
    f.require(outputs[0] == outputs[1],'Fallback/candidate original output mismatch')
    f.require(take('DATA') == dict(bytes=fixture['data_bytes'],hash=fixture['data_hash']),
              'Full input readback mismatch')
    f.require(take('DONE') == dict(calls=3,errors=0) and cursor == len(records),'Extra/incomplete terminal')
    return dict(calls=3,output_values=1088,bitexact=True,fflags=[r['expected_fcsr'] for r in fixture['results']],
                full_call_cycles_diagnostic_only=elapsed,performance_baseline=False)


def local_flags(fixture,c):
    case = f.CASES[c['trial']]
    first = c['group']*(case['heads']//case['kv_heads'])+c['base']
    values = [s['fflags'] for s in fixture['results'][c['trial']]['stages']
              if s['head'] in range(first,first+c['heads']) and s['tile'] == c['tile'] and s['mode'] == c['mode']]
    f.require(len(values) == c['heads'],'Missing independent command-local flags')
    flags = 0
    for value in values:
        flags |= value
    return flags


def resident_performance(text,fixture):
    g = f.load(GEOMETRY,'sdk_resident_geometry')
    expected = f.commands()
    rows, lanes = [], {}
    for line in text.splitlines():
        if not line.startswith('[RESIDENT_'):
            continue
        m = re.fullmatch(r'\[RESIDENT_(QK|PV)_(LANE|PERF)\] (.+)',line)
        f.require(m is not None and len(rows)<len(expected),'Unknown/extra resident probe')
        c = expected[len(rows)]
        f.require(m[1] == c['mode'],'Resident pair/stage order')
        shape,r = g.geometry(c),g.parse_fields(m[3])
        if m[2] == 'LANE':
            keys = set('lane vid tokens elements heads issued returned writes flags error'.split())
            if c['mode']=='QK': keys.add('dimensions')
            f.require(set(r) == keys,'Lane probe field contract')
            lane = r['lane']
            f.require(lane in range(4) and lane not in lanes and shape['writes'][lane],
                      'Inactive/duplicate lane')
            want = dict(tokens=c['tokens'],elements=shape['elements'][lane],heads=c['heads'],
                issued=shape['fma'][lane],returned=shape['fma'][lane],writes=len(shape['writes'][lane]),error=0)
            if c['mode']=='QK': want['dimensions']=c['dimension']
            f.require(all(r[k]==v for k,v in want.items()) and 0<=r['flags']<32 and 0<=r['vid']<8,
                      'Lane work mismatch')
            lanes[lane] = r
            continue
        f.require(set(r) == set(shape['counts'])|{'seq','vid','cycles','error','flags'},
                  'Terminal probe field contract')
        f.require(all(r[k]==v for k,v in shape['counts'].items()) and
                  r['seq']==len(rows)+1 and 0<=r['vid']<8 and r['cycles']>0 and r['error']==0,
                  'Resident command geometry mismatch')
        f.require(set(lanes)=={i for i in range(4) if shape['writes'][i]},'Missing active lane')
        flags = 0
        for lane in lanes.values():
            f.require(lane['vid']==r['vid'],'Probe VID mismatch')
            flags |= lane['flags']
        f.require(flags==r['flags']==local_flags(fixture,c),'Independent resident command flags mismatch')
        rows.append(dict(command=c,terminal=r,lanes=lanes))
        lanes = {}
    f.require(len(rows)==22 and not lanes,'Incomplete resident work')
    return rows


def expected_akv():
    old = f.load(OLD_CHECK,'sdk_legacy_fields')
    # Exact original paired native-auto: 32 panel4 reads + T V-row reads/tile.
    one = old.expected_commands()[1046:1283]
    f.require(len(one)==237,'Accepted native command template changed')
    fields = set(one[0])
    result = list(one)
    for c in f.CASES[1:]:
        for group in range(c['kv_heads']):
            for start in range(0,c['tokens'],64):
                r = dict.fromkeys(fields,0)
                r.update(command=4 if start==0 else 5,v2_full=int(start==0),v2_refill=int(start!=0),
                    q_external_bytes=(c['heads']//c['kv_heads'])*c['dimension']*2 if start==0 else 0,
                    kv_external_bytes=min(64,c['tokens']-start)*c['dimension']*4)
                result.append(r)
            r = dict.fromkeys(fields,0)
            r.update(command=3,release=1)
            result.append(r)
    return old,result


def legacy_work(text):
    old,expected = expected_akv()
    rows, summaries, totals = [], [], Counter()
    for line in text.splitlines():
        if line.startswith('[AKV_PERF] '):
            f.require(not summaries and len(rows)<len(expected),'Extra/post-summary AKV work')
            r = old.parse_fields(line[len('[AKV_PERF] '):],old.PERF_FIELDS)
            f.require(r['seq']==len(rows)+1 and all(r[k]==v for k,v in expected[len(rows)].items()),
                      'Native/lifetime command mismatch')
            f.require(r['success']==1 and r['busy_cycles']>0 and all(r[k]==0 for k in
                ('fault','validation_fault','validation_error','read_fault','v2_rejected')),
                'AKV command fault')
            f.require(r['context_ready']==int(r['command']!=3) and r['read_payload_bytes']==
                r['q_external_bytes']+r['kv_external_bytes']+64*r['v2_full'],'Context/payload contract')
            for key in old.SUMMARY_FIELDS-{'records','success_records','fault_records','validation_fault_records'}:
                totals[key] = max(totals[key],r[key]) if key=='read_outstanding_max' else totals[key]+r[key]
            rows.append(r)
        elif line.startswith('[AKV_PERF_SUMMARY] '):
            summaries.append(old.parse_fields(line[len('[AKV_PERF_SUMMARY] '):],old.SUMMARY_FIELDS))
        elif '[AKV_PERF' in line:
            raise ValueError('Malformed AKV probe')
    f.require(len(rows)==len(expected)==247 and summaries==[dict(totals,records=247,
        success_records=247,fault_records=0,validation_fault_records=0)],'AKV summary/work incomplete')
    return dict(commands=247,per_call=[237,4,6],summary=summaries[0])


def vector_work(path):
    g = f.load(GEOMETRY,'sdk_write_geometry')
    expected = f.commands()
    signatures = []
    for t in (64,64,9):
        signatures += [0x0205745b]*32+[0x0205345b]*t
    signatures += [g.geometry(c)['opcode'] for c in expected]
    allocations, completed, live, seen = [], [], {}, set()
    resident_index, last, config = 0,-1,0
    with Path(path).open(newline='') as stream:
        reader = csv.DictReader(stream)
        required = set('cycle event arch_seq vid lane source insn use_vd vd eew vl vstart addr be wdata nr_lanes vlen_bits'.split())
        f.require(reader.fieldnames and len(reader.fieldnames)==len(set(reader.fieldnames)) and
                  required<=set(reader.fieldnames),'Vector trace schema')
        for r in reader:
            f.require(None not in r and all(v is not None for v in r.values()),'Malformed vector row')
            cycle,event = int(r['cycle']),r['event']
            f.require(cycle>=last and (r['nr_lanes'],r['vlen_bits'])==('4','1024'),'Vector config/cycle drift')
            last = cycle
            if event=='config':
                f.require(config==0 and cycle==0 and not seen,'Late/duplicate vector config')
                config += 1
                continue
            f.require(config==1 and event in ('alloc','write','done'),'Unknown/reset vector event')
            insn = int(r['insn'],16)
            if event=='alloc' and insn&0x707f in (0x305b,0x705b):
                allocations.append(insn)
            if insn not in (0x0605705b,0x0485705b):
                continue
            key = int(r['arch_seq']),int(r['vid'])
            if event=='alloc':
                f.require(key not in live and key not in seen and resident_index<len(expected),
                          'Duplicate/extra resident allocation')
                c = expected[resident_index]
                shape = g.geometry(c)
                f.require(insn==shape['opcode'] and not any(e['resident'] for e in live.values()),
                          'Resident command overlap/order')
                # Track each allocation independently; unrelated EEW maintenance
                # is not assumed globally serial and is left to strict protocol.
                live[key] = dict(shape=shape,writes=set(),resident=True,begin=cycle,index=resident_index)
                seen.add(key)
                resident_index += 1
            f.require(key in live,'Unowned resident event')
            entry = live[key]
            shape = entry['shape']
            f.require(insn==shape['opcode'] and tuple(int(r[k]) for k in
                ('use_vd','vd','eew','vl','vstart'))==(1,0,shape['eew'],shape['vl'],0),'Resident allocation metadata')
            if event=='write':
                lane,addr = int(r['lane']),int(r['addr'])
                f.require(lane in range(4) and addr in shape['writes'][lane] and int(r['source'])==4 and
                    int(r['be'],16)==shape['writes'][lane][addr] and
                    re.fullmatch('[0-9a-fA-F]{16}',r['wdata']) is not None and
                    (lane,addr) not in entry['writes'],'Resident write/byte mask/duplicate')
                entry['writes'].add((lane,addr))
            elif event=='done':
                f.require(entry['writes']=={(lane,addr) for lane in range(4) for addr in shape['writes'][lane]},
                          'Incomplete resident VRF writes')
                completed.append(dict(vid=key[1],arch_seq=key[0],writes=len(entry['writes']),
                                      begin=entry['begin'],end=cycle))
                del live[key]
    f.require(config==1 and not live and len(completed)==22 and allocations==signatures,
              'Resident/native opcode signature/work incomplete')
    return completed


def actual_entry(path,elf_path):
    elf = f.load(ELF_READER,'sdk_entry_elf').contract(Path(elf_path).read_bytes())
    names = ('akv_decode_execute','akv_experimental_attention_execute_v2_native')
    starts = {elf['symbols'][name]['address']:name for name in names}
    counts = Counter()
    last = -1
    with Path(path).open(newline='') as stream:
        reader = csv.DictReader(stream)
        f.require(reader.fieldnames and {'cycle','event','pc','insn','trap'}<=set(reader.fieldnames),
                  'Commit trace schema')
        for r in reader:
            f.require(None not in r and all(v is not None for v in r.values()),'Malformed commit row')
            cycle = int(r['cycle'])
            f.require(cycle>=last,'Commit trace order')
            last = cycle
            if r['event']!='retire':
                continue
            f.require(int(r['trap'])==0,'Unexpected architectural trap')
            pc = int(r['pc'],16)
            if pc in starts:
                insn = int(r['insn'],16)
                word = elf['words'][pc]
                f.require(insn == (word if word&3==3 else word&0xffff),'Entry PC/instruction binding')
                counts[starts[pc]] += 1
    f.require(counts==dict(akv_decode_execute=6,akv_experimental_attention_execute_v2_native=4),
              'Actual SDK/decode entry counts mismatch')
    return dict(counts)


def check(build,log,vector,commit):
    m = build_receipt(build)
    text = Path(log).read_text()
    old = f.load(OLD_CHECK,'sdk_console_severity')
    old.classify_simulator(text)
    result = dict(numerical=numerical(text,m['fixture']),legacy_work=legacy_work(text),
        resident_work=resident_performance(text,m['fixture']),vector_work=vector_work(vector),
        actual_entries=actual_entry(commit,m['elf']),protocol_checked=False,
        scope=m['scope'],performance_acceptance=False)
    f.require(all(p['terminal']['vid']==w['vid'] and p['terminal']['result_words']==w['writes']
              for p,w in zip(result['resident_work'],result['vector_work'])),'Probe/vector disagreement')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    for name in ('build','log','vector','commit'):
        parser.add_argument('--'+name,type=Path,required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.build,args.log,args.vector,args.commit),indent=2))
