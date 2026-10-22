"""One original negative-stride single: immutable reference, no build path."""
import importlib.util
import re
import sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
REF=HERE.parent/'negative_stride_load_original01'
G=HERE.parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module
source=load('negative_stride_frozen_observer',REF/'observer.py')
sys.path.insert(0,str(G/'gather_repair05'))
import regression as common
read,sha,require=common.read,common.sha,source.require
NAME='negative_stride_load_e16_m1_u1_s0_b3_m2_f0_g3'
HISTORICAL='rvv_small_fault_strided_negative_stride_e16_m1_u1_s0_b3_m2_f0_g3'
READY_SHA='d20a279ff09bbad626141a386a12160634b0ad36ca82ff6da661c1c7ddcc4d52'
VETO=re.compile(common.BAD.pattern+r'|NEGATIVE_STRIDE_SINGLE_FAIL|BOARD_REPLAY_MISMATCH|\b(?:FAILED|FAIL|ABORT|MISMATCH)\b',re.I)

def specification():
    require(sha(REF/'READY.json')==READY_SHA,'Frozen reference READY drift')
    r=read(REF/'READY.json');elf=Path(r['soc_elf'])
    require(sha(elf)==r['soc_elf_sha256'],'Original SoC ELF drift')
    symbols=read(REF/'software01/soc.symbols.json')
    code=source.disassemble((REF/'software01/soc.dis').read_text())
    helper=source.window(code,symbols['replay_0'],10)
    unused=source.window(code,symbols['replay_1'],10)
    capacity=source.window(code,symbols['capacity'],3)
    require([f'{code[p]:08x}' for p in helper]==read(REF/'software01/source_proof.json')['backend']['soc']['helpers']['replay_0']['encodings'],'Original helper code drift')
    end=symbols['check'];exits=[p for p in sorted(code) if symbols['replay_exit']<=p<end]
    store,=[p for p in exits if code[p]&0x707f==0x3023]
    park=store+4
    require(code[park]==0xa001 and 'tohost' not in symbols,'SoC CTRL/park contract')
    return dict(symbols=symbols,code={str(k):v for k,v in code.items()},helper=helper,unused=unused,
                capacity=capacity,exit_store=store,park=park,elf=str(elf),elf_sha256=sha(elf),
                checks=17274,output_elements=64,guards=2,memory_bytes=8192)

def runtime_case(case):
    require(case['id']==NAME and case['original_name']==HISTORICAL,'Historical/runtime identity')
    return dict(case,original_name=NAME)

def console_gate(text):
    require(not VETO.search(text),'Raw failure marker')
    require(text.splitlines().count('NEGATIVE_STRIDE_SINGLE_PASS')==1,'Missing/duplicate single oracle')
    require('Core Test *** SUCCESS *** (tohost = 0)' in text and '$finish' in text,'Missing actual successful finish')

def artifacts(result,case,ledger,spec,validator):
    import csv_check
    require(result.status=='PASS' and result.returncode==0 and result.name==NAME and not result.reason,'Actual child not PASS/0')
    common.check_artifacts(result,runtime_case(case),ledger)
    root=result.artifact_dir;child=read(root/'child_outcome.unvalidated.json')
    require(child['name']==NAME and child['returncode']==0 and child['status']=='PASS' and
            child['architectural_acceptance'] is False and child['elapsed_s']==result.elapsed_s and
            child['command_sha256']==sha(root/'command.json'),'Durable unvalidated child outcome')
    monitor=read(root/'monitor_outcome.unvalidated.json')
    require(monitor['returncode']==0 and type(monitor['returncode']) is int and
            not monitor['timed_out'] and not monitor['failure_seen'] and not monitor['abort_set'] and
            monitor['elapsed_s']==result.elapsed_s and monitor['command_sha256']==sha(root/'command.json') and
            monitor['architectural_acceptance'] is False,'Actual monitored numeric outcome')
    for p in (root/'console.log',root/'work/run.vcs.log'):console_gate(p.read_text())
    generic=validator(root/'commit_trace.csv')
    require(generic['cvx_exception_count']==1 and generic['architecture_request_count']>0 and
            generic['backend_uop_alloc_count']==generic['backend_uop_done_count']>0,'CVX/arch/uop completion contract')
    strict=csv_check.analyze(root/'commit_trace.csv',spec)
    require(strict['status']=='PASS_NEGATIVE_STRIDE_FULL_SINGLE',str(strict))
    require((strict['rows'],strict['retired'],strict['last_cycle'])==
            (generic['rows'],generic['retire_count'],generic['last_cycle']),'Independent CSV counts')
    return dict(generic=generic,strict=strict,csv_sha256=sha(root/'commit_trace.csv'),
                scope='One source-derived Sv39 single, not Linux or parent96',
                child_outcome_sha256=sha(root/'child_outcome.unvalidated.json'),
                monitor_outcome_sha256=sha(root/'monitor_outcome.unvalidated.json'))
