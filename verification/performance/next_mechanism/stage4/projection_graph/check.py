#!/usr/bin/env python3
"""Complete SDK-chain checks; protocol/image acceptance remains independent."""
import argparse
import csv
import importlib.util
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
_spec=importlib.util.spec_from_file_location('stage4_chain_check_contract',HERE/'contract.py')
c=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(c)

PHASES=tuple('phase_'+x+'_cycles' for x in
    ('setup','activation','weight','compute','overlap','drain','scheduler','commit','fault','terminal'))
TRIAL_FIELDS=set('id candidate tag admit prep execute total queries hits misses stores producers compared copied retained fcsr vcsr vstart output_hash packed_hash errors'.split())


def fields(text,hexadecimal=()):
    result={}
    for token in text.split():
        c.require(token.count('=')==1,'Malformed record field')
        key,value=token.split('=')
        c.require(key not in result and re.fullmatch('[a-z_]+',key) is not None,
                  'Duplicate/invalid record key')
        c.require(re.fullmatch('[0-9a-f]+' if key in hexadecimal else '[0-9]+',value) is not None,
                  'Invalid unsigned field')
        result[key]=int(value,16 if key in hexadecimal else 10)
    return result


def command_work(row,index):
    part=0 if index%64<48 else 1 if index%64<56 else 2
    weight=32*6*(210 if part==1 else 144)
    want=dict(seq=index+1,m=4,n=32,vlen=1024,lanes=4,success=1,fault=0,
        validation_fault=0,validation_error=0,read_fault=0,weight_bytes=weight,
        activation_bytes=7008,payload_bytes=16+weight+7008,tiles=48,
        useful_pairs=196608,pair_capacity=196608,dot_active_cycles=6144,
        accumulator_updates=768,activation_access=0,context_fill_count=0,
        context_reuse_count=0,context_reuse_block_count=0,context_read_bytes=0,
        activation_axi_bytes_saved=0,context_replay_cycles=0,
        context_replay_compute_overlap_cycles=0,context_validation_fault_count=0)
    c.require(all(row.get(k)==v for k,v in want.items()),'Command order/shape/work/fault mismatch')
    c.require(all(k in row for k in PHASES) and sum(row[k] for k in PHASES)==row['busy_cycles']>0,
              'Exclusive engine phase partition')
    c.require(row['busy_cycles']>=row['dot_active_cycles'],'Dot issue cycles exceed command lifetime')


def check_log(text,oracle):
    c.require(text.count('Core Test *** SUCCESS ***')==1,'Missing/duplicate firmware success')
    c.require(not re.search(r'(?im)(?:^\s*(?:Error[-:]|Fatal:)|Assertion failed|\$fatal|STAGE4_CHAIN_FAIL|\bTIMEOUT\b)',text),
              'Simulator/firmware failure')
    for line in text.splitlines():
        if re.match(r'\s*UVM_(ERROR|FATAL)\b',line):
            c.require(re.fullmatch(r'\s*UVM_(ERROR|FATAL)\s*:\s*0\s*',line) is not None,'UVM failure')
    scope='STAGE4_CHAIN_SCOPE trials=4 m=4 k=1536 q=1536 v=256 key=256 cache_both=1 parallel_both=1 full_ggml=0'
    trials,perf=[],[]
    seen_scope=done=False
    for line in text.splitlines():
        if line.startswith('[QBS_PERF] '):
            c.require(seen_scope and not done and len(perf)<256,'Out-of-scope/extra native work')
            row=fields(line[len('[QBS_PERF] '):])
            command_work(row,len(perf));perf.append(row)
        elif line.startswith('STAGE4_CHAIN_SCOPE '):
            c.require(not seen_scope and not trials and not perf and line==scope,'Scope/strong baseline mismatch')
            seen_scope=True
        elif line.startswith('STAGE4_CHAIN_TRIAL '):
            row=fields(line[len('STAGE4_CHAIN_TRIAL '):],('output_hash','packed_hash'))
            i=len(trials)
            c.require(seen_scope and not done and i<4 and set(row)==TRIAL_FIELDS and len(perf)==(i+1)*64,
                      'Trial record schema/order/work count')
            want=dict(id=i,candidate=c.ORDER[i],tag=3+c.ORDER[i],queries=3,hits=2,misses=1,
                stores=1,producers=1,compared=49152,copied=45600,retained=0,
                fcsr=17,vcsr=5,vstart=0,errors=0,output_hash=oracle['output_hash'],packed_hash=oracle['packed_hash'])
            c.require(all(row[k]==v for k,v in want.items()),'Producer/cache/CSR/raw-output mismatch')
            c.require(all(row[k]>0 for k in ('admit','prep','execute')) and
                      0<=row['total']-sum(row[k] for k in ('admit','prep','execute'))<=4096,
                      'Complete-call timing partition')
            busy=sum(p['busy_cycles'] for p in perf[i*64:(i+1)*64])
            c.require(busy<=row['execute'],'Engine busy exceeds complete execute interval')
            trials.append(dict(row,native_busy=busy,execute_remainder=row['execute']-busy))
        elif line.startswith('STAGE4_CHAIN_DONE '):
            c.require(not done and len(trials)==4 and fields(line[len('STAGE4_CHAIN_DONE '):])==
                      dict(trials=4,commands=256,outputs_per_trial=8192,errors=0),'Incomplete/duplicate terminal')
            done=True
        elif line.startswith('STAGE4_CHAIN_'):
            raise ValueError('Unknown SDK-chain record')
    c.require(seen_scope and done and len(trials)==4 and len(perf)==256,'Incomplete SDK-chain evidence')
    for i in range(64):
        # Arithmetic work cannot change when only the CPU cold producer changes.
        keys=('fp_uop_issue','accumulator_updates','useful_pairs','pair_capacity','dot_active_cycles')
        c.require(all(all(perf[t*64+i].get(k)==perf[i].get(k) for k in keys) for t in range(1,4)),
                  'Arithmetic work differs across producer arms')
    means={name:{field:sum(trials[i][field] for i in ids)/2 for field in
                 ('admit','prep','execute','native_busy','execute_remainder','total')}
           for name,ids in (('accepted_parallel_cache',(0,3)),('preflight',(1,2)))}
    return dict(state='SDK_CHAIN_LOG_CHECKED',trials=trials,means=means,
        complete_call_speedup=means['accepted_parallel_cache']['total']/means['preflight']['total'],
        preparation_speedup=means['accepted_parallel_cache']['prep']/means['preflight']['prep'],
        commands=256,outputs_checked_by_target=32768,independent_oracle_hashes_checked=True,
        full_ggml=False,whole_model=False,scope=c.SCOPE,performance_acceptance=False)


def check_vector(path):
    live,completed={},[]
    last=-1;configured=False
    required=set('cycle event arch_seq vid insn use_vd vd eew vl vstart nr_lanes vlen_bits lane source addr be wdata'.split())
    with Path(path).open(newline='') as stream:
        reader=csv.DictReader(stream)
        c.require(reader.fieldnames and len(reader.fieldnames)==len(set(reader.fieldnames)) and required<=set(reader.fieldnames),
                  'Vector trace schema')
        for row in reader:
            c.require(None not in row and all(v is not None for v in row.values()),'Malformed vector row')
            cycle=int(row['cycle']);event=row['event']
            c.require(cycle>=last and (row['nr_lanes'],row['vlen_bits'])==('4','1024'),'Vector cycle/config drift')
            last=cycle
            if event=='config':
                c.require(not configured and cycle==0 and not live and not completed,'Duplicate/late vector configuration')
                configured=True;continue
            c.require(configured and event in ('alloc','write','done'),'Unexpected/reset vector event')
            word=int(row['insn'],16)
            if word&127!=0x5b or word==0x0005155b: continue
            c.require(word==0x06b5045b,'Unexpected custom instruction or QBACC')
            key=int(row['arch_seq']),int(row['vid'])
            c.require(tuple(int(row[k]) for k in ('use_vd','vd','eew','vl','vstart'))==(1,8,2,128,0),
                      'M4 allocation geometry')
            if event=='alloc':
                c.require(key not in live and key not in completed and key[0]>0 and key[1] in range(8),
                          'Duplicate/invalid QBS allocation')
                live[key]=set()
            else:
                c.require(key in live,'Unowned QBS result/completion')
                if event=='write':
                    lane,address=int(row['lane']),int(row['addr'])
                    c.require(lane in range(4) and address in range(32,48) and int(row['source'])==4 and
                              int(row['be'],16)==255 and re.fullmatch('[0-9a-fA-F]{16}',row['wdata']) is not None,
                              'Wrong architectural result write')
                    c.require((lane,address) not in live[key],'Duplicate QBS result word')
                    live[key].add((lane,address))
                else:
                    c.require(live[key]=={(lane,address) for lane in range(4) for address in range(32,48)},
                              'Incomplete QBS result bytes')
                    completed.append(key);del live[key]
    c.require(configured and not live and len(completed)==256,'Missing/extra QBS work')
    return dict(commands=256,result_bytes=131072,alloc_write_done_checked=True)


def check_entries(path,entries):
    by_pc={row['pc']:(name,row['insn']) for name,row in entries.items()}
    c.require(set(entries)==set(c.ENTRIES) and len(by_pc)==3,'Incomplete/aliased entry binding')
    expected=[]
    for arm in c.ORDER:
        expected.extend([c.ENTRIES[arm]]+[c.ENTRIES[2]]*64)
    actual=[];last=-1
    with Path(path).open(newline='') as stream:
        reader=csv.DictReader(stream)
        c.require(reader.fieldnames and len(reader.fieldnames)==len(set(reader.fieldnames)) and
                  {'cycle','event','pc','insn','trap'}<=set(reader.fieldnames),'Commit schema')
        for row in reader:
            c.require(None not in row and all(v is not None for v in row.values()),'Malformed commit row')
            cycle=int(row['cycle']);c.require(cycle>=last,'Commit cycle order');last=cycle
            if row['event']!='retire': continue
            c.require(int(row['trap'])==0,'Unexpected architectural trap')
            pc=int(row['pc'],16)
            if pc in by_pc:
                name,word=by_pc[pc]
                c.require(int(row['insn'],16)==word,'ELF entry instruction mismatch')
                actual.append(name)
    c.require(actual==expected,'Missing/extra/misordered actual producer/native entries')
    return dict(counts={name:actual.count(name) for name in c.ENTRIES},
                abba_producer_then_native64=True,elf_pc_insn_bound=True)


def checked_build(directory):
    directory=Path(directory).resolve(strict=True)
    record=json.loads((directory/'build.json').read_text())
    c.require(record['state']=='BUILT_NOT_EXECUTED' and record['scope']==c.SCOPE and
              record['llama_commit']==c.LLAMA_COMMIT and record['sdk_commit']==c.SDK_COMMIT and
              record['baseline']=='da56 packed parallel-sums + exact-byte cache, tag3' and
              record['candidate']=='new preflight cold producer only, tag4','Wrong build/source/baseline scope')
    c.require(c.sha(directory/'source-pins.json')==record['source_pins_sha256'] and
              c.sha(record['elf'])==record['elf_sha256'],'Build inventory/ELF changed')
    c.verify(json.loads((directory/'source-pins.json').read_text()));c.verify(record['artifacts'])
    actual={str(p):c.sha(p) for p in directory.rglob('*') if p.is_file() and p!=directory/'build.json'}
    c.require(actual==record['artifacts'],'Incomplete/extra build artifact inventory')
    raw=(directory/'ordered_golden.bin').read_bytes();packed=(directory/'inputs/data/activation_q8k_m4.bin').read_bytes()
    c.require(len(raw)==32768 and c.fnv(raw)==record['oracle']['output_hash'] and
              c.fnv(packed)==record['oracle']['packed_hash'],'Independent numerical oracle changed')
    c.require(record['entry_contract']==c.entry_contract(record['elf'],directory/'inputs/elf_reader.py') and
              record['expected_entries']==dict(zip(c.ENTRIES,(2,2,256))) and
              record['roi_included']==list(c.ROI_INCLUDED) and record['roi_excluded']==list(c.ROI_EXCLUDED),
              'ELF execution/ROI contract changed')
    return record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    for name in ('build','log','vector','commit'): parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();build=checked_build(args.build)
    result=check_log(args.log.read_text(),build['oracle'])
    result['vector_work']=check_vector(args.vector)
    result['actual_entries']=check_entries(args.commit,build['entry_contract'])
    result['protocol_checked']=False
    result['post_image_checked']=False
    print(json.dumps(result,indent=2))
