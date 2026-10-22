"""Frozen original16 reference and strict M6 runtime identity; no build path."""
import importlib.util
import re
import sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
REF=HERE.parent/'zero_stride_e64_m2_original16_prepare01'
G=HERE.parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
sys.path.insert(0,str(REF))
source=load('zero16_frozen_source',REF/'observer.py')
sys.path.insert(0,str(G/'gather_repair05'))
sys.path.insert(0,str(REF))
from newscope import CAP,ALLOC,VTYPE,CHECKS,LMUL,SNAPSHOT_HIGH_OFFSET
import regression as common
read,sha,require=common.read,common.sha,source.require
NAME='zero_stride_e64_m2_original16'
HISTORICAL='rvv_fault_replay_strided_zero_stride_e64_m2'
READY_SHA=common.sha(REF/'READY02.json')
IMAGE=Path('/home/wangwy/fpga_runs/current_board_memory_candidate07/campaign/image')
IMAGE_SHA=common.sha(IMAGE/'image.json')
VETO=re.compile(common.BAD.pattern+r'|ZERO_STRIDE_ORIGINAL16_FAIL|BOARD_REPLAY_MISMATCH|\b(?:FAIL|FAILED|ABORT|MISMATCH)\b',re.I)

def reference_pins():
    require(sha(REF/'READY02.json')==READY_SHA,'Reference READY drift')
    r=read(REF/'READY02.json');p=read(r['evidence_pins'])
    require(sha(Path(r['evidence_pins']))==r['evidence_pins_sha256'] and len(p)==r['pin_count'],'All individually pinned source evidence')
    require(r['status']=='SOURCE_AND_REFERENCE_READY_NOT_DUT' and r['actual_child_returncode']==0 and
            r['firmware_instructions']>0 and r['scalar_checks']==CHECKS and r['scope']['cap']==CAP and r['scope']['lmul']==LMUL and r['scope']['cases']==16 and
            r['scope']['faults']==12,'Original continuous16 source/reference scope')
    common.base.verify_pins(p)
    return {**p,str(REF/'READY02.json'):READY_SHA,str(REF/'evidence_pins02.json'):r['evidence_pins_sha256']}

def specification():
    require(sha(REF/'READY02.json')==READY_SHA,'READY pin')
    r=read(REF/'READY02.json');elf=Path(r['soc_elf'])
    require(sha(elf)==r['soc_elf_sha256'],'Original SoC ELF drift')
    s=read(REF/'software01/soc.symbols.json');code=source.disassemble((REF/'software01/soc.dis').read_text())
    windows={name:source.window(code,s[name],count) for name,count in (('capacity',3),('replay_0',10),('replay_1',10))}
    proof=read(REF/'software01/source_proof.json')['backends']['soc']
    for name,pcs in windows.items():require([f'{code[p]:08x}' for p in pcs]==proof['helpers'][name]['encodings'],'Actual helper bytes '+name)
    bootstrap=source.window(code,s['mx_bootstrap'],8)
    require([code[p] for p in bootstrap][4:7]==[0xcdb1f057,0x0207f407,0x0205f427],'Original bootstrap')
    stores=[p for p in sorted(code) if s['replay_exit']<=p<s['check'] and code[p]&0x707f==0x3023]
    require(len(stores)==1 and code[stores[0]+4]==0xa001 and 'tohost' not in s,'CTRL exit/park')
    return dict(symbols=s,code={str(k):v for k,v in code.items()},windows=windows,bootstrap=bootstrap,
                exit_store=stores[0],park=stores[0]+4,elf=str(elf),elf_sha256=sha(elf),
                checks=CHECKS,cases=16,faults=12,ecalls=16,outputs=16*CAP,guards=32,memory_words=16384)

def runtime_case(case):
    require(case['id']==NAME and case['original_name']==HISTORICAL,'Historical/runtime name')
    return dict(case,original_name=NAME)

def console_gate(text):
    require(not VETO.search(text),'Raw failure marker')
    require(text.splitlines().count('ZERO_STRIDE_ORIGINAL16_PASS cases=16 faults=12 errors=0')==1,'Full16 console oracle')
    require('Core Test *** SUCCESS *** (tohost = 0)' in text and '$finish' in text,'Actual successful finish')

def artifacts(result,case,ledger,spec,validator):
    import csv_check
    require(result.status=='PASS' and type(result.returncode) is int and result.returncode==0 and
            result.name==NAME and not result.reason,'Actual PASS/numeric0 prerequisite')
    common.check_artifacts(result,runtime_case(case),ledger)
    root=result.artifact_dir
    child=read(root/'child_outcome.unvalidated.json');monitor=read(root/'monitor_outcome.unvalidated.json')
    require(child['status']=='PASS' and child['returncode']==0 and child['name']==NAME and
            child['architectural_acceptance'] is False,'Durable child outcome')
    require(type(monitor['returncode']) is int and monitor['returncode']==0 and not monitor['timed_out'] and
            not monitor['failure_seen'] and not monitor['abort_set'] and monitor['architectural_acceptance'] is False,'Actual monitor outcome')
    for rec in (child,monitor):
        require(rec['elapsed_s']==result.elapsed_s and rec['command_sha256']==sha(root/'command.json'),'Outcome identity')
    for name in ('console.log','work/run.vcs.log'):console_gate((root/name).read_text())
    generic=validator(root/'commit_trace.csv')
    require(generic['cvx_exception_count']==12 and generic['architecture_request_count']>0 and
            generic['backend_uop_alloc_count']==generic['backend_uop_done_count']>0,'Full12 exceptions / backend completion')
    strict=csv_check.analyze(root/'commit_trace.csv',spec)
    common.save(root/'terminal_original16.json',strict)
    require(strict['status']=='PASS_ORIGINAL16_FULL_ORACLE',str(strict))
    require((strict['rows'],strict['retired'],strict['last_cycle'])==
            (generic['rows'],generic['retire_count'],generic['last_cycle']),'CSV counts agree')
    return dict(generic=generic,strict=strict,csv_sha256=sha(root/'commit_trace.csv'),
                frozen_image='M7_MASK_DRAIN_DESCRIPTOR_GUARD',linux_stall_closed=False,
                actual_vector_write_payload_in_RVFI=False)

