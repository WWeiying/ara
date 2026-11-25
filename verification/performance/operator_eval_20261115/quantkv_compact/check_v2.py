#!/usr/bin/env python3
"""Compact quantKV checker; no simulator entry point or synthetic timing."""
import argparse
from collections import Counter
import csv
import math
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode=True
from contract import ORDER,require,read,save,sha,verify,module,captured,elf_blob


def numerical(text,golden,kind,count):
    lines=[x for x in text.splitlines() if x.startswith(('PREFILL_','QKC_'))]
    require(len(lines)==15 and lines[0]==f'PREFILL_CAP q4={int(kind=="q4_0")} rows=8 d=128 first_query=16 tokens=20 trials=4' and
        lines[1]==f'QKC_INITIAL bytes={count} checked={count} first_fail=-1 state_errors=0' and
        lines[-1]=='PREFILL_SUITE_PASS','Missing/extra compact records / initial comparison')
    require(len(golden)==163840,'Original full golden extent')
    gold=struct.unpack('<64f',golden[131072:131328]); rows=[]
    for t,m in enumerate(ORDER):
        require(lines[2+t*3]==f'PREFILL_BEGIN trial={t} shared={m}' and lines[3+t*3]==
            f'QKC_BYTES trial={t} bytes={count} checked={count} first_fail=-1 state_errors=0','Incomplete byte traversal / order / state mutation')
        r=re.fullmatch(r'PREFILL_RESULT trial=([0-3]) shared=([01]) cycles=([1-9][0-9]*) commands=4 values=([0-9]+) '
            r'fcsr=([0-9]+) vcsr=5 vstart=0 checked=1024 first_fail=-1 guards=384 errors=0 hex=([0-9a-f]{512})',lines[4+t*3])
        require(r is not None and (int(r[1]),int(r[2]),int(r[4]))==(t,m,20 if m else 74) and int(r[5])<=31,
            'All-output gold/count/guard/flag/path failure')
        bits=tuple(int(r[6][i:i+8],16) for i in range(0,512,8))
        values=struct.unpack('<64f',struct.pack('<64I',*bits))
        for actual,expected in zip(values,gold):
            require(math.isfinite(actual) and math.isfinite(expected) and
                abs(actual-expected)<=2e-5+2e-5*abs(expected),'Independent raw golden mismatch')
        require(not rows or (bits,int(r[5]))==(rows[0]['bits'],rows[0]['fcsr']),'Cross-arm exact bits/flags differ')
        rows.append(dict(trial=t,shared=m,cycles=int(r[3]),fcsr=int(r[5]),bits=bits))
    return rows


def entry_instruction(parsed,pc):
    word=parsed['words'][pc]
    return word if word&3==3 else word&0xffff


def roi(path,r,rows,parsed):
    lo,hi=r['elf_ranges']['quantkv_compare_bytes']; qbs=r['elf_ranges']['qbs_native_execute_command'][0]
    printf=r['elf_ranges']['printf_'][0]; markers=r['roi_marker_pcs']; reads=r['roi_read_pcs']
    active=False; trial=0; calls=0; values=[]; batches=[]; previous=-1
    with Path(path).open(newline='') as stream:
        reader=csv.DictReader(stream)
        require(reader.fieldnames and {'cycle','event','pc','insn','rd_wdata','trap'}<=set(reader.fieldnames),'Commit schema')
        for v in reader:
            require(None not in v and all(x is not None for x in v.values()),'Truncated commit row')
            cycle=int(v['cycle']); require(cycle>=previous,'Commit order'); previous=cycle
            if v['event']!='retire': continue
            require(int(v['trap'])==0,'Architectural trap')
            pc,insn=int(v['pc'],16),int(v['insn'],16)
            if insn==0xc0002073:
                require(trial<4 and pc==markers[int(active)],'ROI marker PC/count')
                if not active: active=True; calls=0; values=[]
                else:
                    require(calls==4 and len(values)==2 and values[1]-values[0]==rows[trial]['cycles'],'ROI work/rdcycle mismatch')
                    active=False; trial+=1
                continue
            if pc==lo:
                require(not active and insn==entry_instruction(parsed,pc),'Byte comparator inside ROI / unbound entry'); batches.append([])
            if lo<=pc<hi and (insn&0x000ff07f)==0x2073:
                # CSRRS with rs1=x0, funct3=2; read the three preserved CSRs.
                csr=insn>>20
                if csr in (3,15,8):
                    require(batches and not active,'Unowned comparator CSR snapshot'); batches[-1].append((csr,int(v['rd_wdata'],16)))
            if pc==qbs:
                require(active and insn==entry_instruction(parsed,pc),'QBS outside ROI'); calls+=1
            if pc==printf: require(not active,'Printf inside ROI')
            if pc in reads:
                require(active and len(values)<2 and pc==reads[len(values)] and insn==entry_instruction(parsed,pc),'Cycle-read binding/order')
                values.append(int(v['rd_wdata'],16))
    require(not active and trial==4 and len(batches)==5,'Incomplete ROI or byte-check count')
    for i,b in enumerate(batches):
        require(len(b)==6 and [x[0] for x in b]==[3,15,8,3,15,8] and b[:3]==b[3:] and b[2][1]==0,
                'Comparator modified FCSR/VCSR/VSTART')
        if i: require([x[1] for x in b[:3]]==[rows[i-1]['fcsr'],5,0],'Original post-call flag snapshot changed')
    return dict(markers=8,qbs_calls=16,complete_byte_comparisons=5,comparator_arch_state_preserved=True)


def check(build,run,log):
    build,run,log=Path(build).resolve(strict=True),Path(run).resolve(strict=True),Path(log).resolve(strict=True)
    r=read(build/'build.json'); require(r['state']=='BUILT_NOT_EXECUTED' and r['schema']=='quantkv-compact-v1','Wrong build')
    require(sha(build/'source-pins.json')==r['source_pins_sha256'],'Source receipt identity')
    verify(read(build/'source-pins.json')); verify(r['artifacts'])
    require(sha(r['elf'])==r['elf_sha256'] and log.is_relative_to(run),'ELF/log identity')
    data=captured(r['kind']); payload=b''.join(data.values()); n=len(payload)
    raw=Path(r['elf']).read_bytes(); parsed=module(build/'inputs/elf_reader.py','quantkv_check_elf').contract(raw)
    def address(name): return parsed['symbols'][name]['address']
    require(address('fixture_end')-address('fixture_begin')==n and
        address('quantkv_expected_end')-address('quantkv_expected_begin')==n and
        address('fixture_end')<=address('quantkv_expected_begin') and
        elf_blob(raw,parsed,'fixture_begin',n)==payload and
        elf_blob(raw,parsed,'quantkv_expected_begin',n)==payload,'Complete actual/independent expected byte audit')
    symbols=dict(query='prefill_query',key='prefill_key',value='prefill_value',mask='prefill_mask',golden='prefill_golden')
    for name,blob in data.items(): require(elf_blob(raw,parsed,symbols[name],len(blob))==blob,'Embedded capture byte identity: '+name)
    constants=(0x514b4331,1,int(r['kind']=='q4_0'),n,8,128,136,16,20,1024,64,384,
        struct.unpack('<I',struct.pack('<f',2e-5))[0],0x3db504f3,0x00010100)
    require(r['constants']==list(constants) and elf_blob(raw,parsed,'quantkv_contract',120)==struct.pack('<15Q',*constants) and
        elf_blob(raw,parsed,'prefill_scale',4)==struct.pack('<I',0x3db504f3) and
        elf_blob(raw,parsed,'prefill_q4',4)==struct.pack('<I',int(r['kind']=='q4_0')),'ELF dimensions/tolerance/scale/type')
    text=log.read_text(); terminal='Core Test *** SUCCESS *** (tohost = 0)'
    require(text.splitlines().count(terminal)==1 and text.index('PREFILL_SUITE_PASS')<text.index(terminal),'Completion gate')
    require(not re.search(r'Fatal:|Error:|Error-|\b(?:FAIL|FAILED|TIMEOUT)\b',text,re.I),'Failure text')
    for line in text.splitlines():
        if re.match(r'\s*UVM_(ERROR|FATAL)\b',line): require(re.fullmatch(r'\s*UVM_(ERROR|FATAL)\s*:\s*0\s*',line),'UVM failure')
    rows=numerical(text,data['golden'],r['kind'],n)
    old=module(build/'inputs/ancestor/check.py','quantkv_frozen_work_checker')
    activity=old.activity(text,dict(kind=r['kind']))
    entries=roi(run/'commit.csv',r,rows,parsed)
    means=[sum(v['cycles'] for v in rows if v['shared']==m)/2 for m in (0,1)]
    return dict(state='PASS',metrics=dict(trials=[{k:v for k,v in x.items() if k!='bits'} for x in rows],
        baseline_cycles=means[0],shared_cycles=means[1],speedup=means[0]/means[1],native_records_per_trial=activity,
        roi=entries,fixture_bytes=n,all_fixture_bytes_compared_exactly=True,target_gold_values_per_trial=1024,
        independent_raw_values_per_trial=64,unprinted_values_checked_by_frozen_target_loop=True,
        original_cross_arm_bitexact_and_flag_contract=True,whole_model=False,actual_ggml_dispatch=False),
        elf_sha256=r['elf_sha256'],log_sha256=sha(log),commit_sha256=sha(run/'commit.csv'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    for n in ('build','run','log','result'): p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args()
    try: result=check(a.build,a.run,a.log)
    except Exception as exc: result=dict(state='FAIL',error=str(exc))
    save(a.result,result); raise SystemExit(result['state']!='PASS')
