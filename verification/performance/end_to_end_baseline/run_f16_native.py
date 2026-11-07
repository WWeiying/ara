#!/usr/bin/env python3
"""Bounded default-F16 native phase measurement on the accepted physical SoC."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from types import SimpleNamespace

from audit import digest, require, verify_pins
from prepare_wide_soc import ROOT, VERIFY, RUNS, HERE
from continue_wide_soc import SOC_HASH
from run_supply_sdk import bind, acceptance_gate
from run_wide_soc_smoke import elf_admission, check_platform
import check_f16_native as checker

GUARD=ROOT/'verification/akv/quantized_kv/prefill/early_guard.py'


def accept_program(program):
    wanted=dict(state='REAL_QWEN3_F16_PHASE_ELF_BUILT_NOT_EXECUTED',post_pins_match=True,
        target_executed=False,performance_measured=False,rtl_changed=False,whole_model=False,
        order=[0,1,1,0],trials=8,outputs_checked=66560,q_heads=2,kv_heads=1,head_dim=128,
        prefill_queries=64,decode_visible=137,pair_heads_enabled=True,pair_pv_enabled=True,
        timing_includes_csr_completion=True,decode_preparation_included=True,
        probe_perturbation_limit=.05,default_runtime_promoted=False)
    require(all(program.get(k)==v for k,v in wanted.items()),'Native F16 program identity/scope differs')


def inputs(build,sha):
    build=build.resolve(strict=True)
    require(build.is_relative_to(RUNS) and len(sha)==64,'Explicit sole-verification build identity required')
    pins={};bind(pins,build/'build.json',sha)
    program=json.loads((build/'build.json').read_text());accept_program(program)
    bind(pins,build/'source-pins.json',program['source_pins_sha256'])
    for group in (json.loads((build/'source-pins.json').read_text()),program['artifacts']):
        for path,value in group.items():bind(pins,path,value)
    elf=Path(program['elf']);bind(pins,elf,program['elf_sha256'])
    soc_root=RUNS/'e2e_physical_wide_soc128_20261106_01'
    bind(pins,soc_root/'result.json',SOC_HASH[128])
    soc=json.loads((soc_root/'result.json').read_text())
    require(soc['state']=='PHYSICAL_WIDE_SOC_BUILT_NOT_EXECUTED' and soc['width']==128 and
            soc['post_pins_match'],'Wrong physical platform')
    bind(pins,soc_root/'source-pins.json',soc['source_pins_sha256'])
    for group in (json.loads((soc_root/'source-pins.json').read_text()),soc['artifacts'],soc['image_pins']):
        for path,value in group.items():bind(pins,path,value)
    for module in tuple(sys.modules.values()):
        path=getattr(module,'__file__',None)
        if path and Path(path).is_file() and any(Path(path).resolve().is_relative_to(r) for r in (ROOT,VERIFY)):
            bind(pins,path)
    for path in (Path(__file__),GUARD,HERE/'test_run_f16_native.py',HERE/'test_f16_native_check.py',
                 Path(sys.executable),*(VERIFY/'verification/ara_verify').glob('*.py')):bind(pins,path)
    gate=acceptance_gate(pins)
    return dict(program=program,elf=elf,soc=soc,gate=gate,loads=elf_admission(elf.read_bytes(),16)),pins


def run(build,sha,output,timeout,execute):
    out=output.absolute()
    require(out==out.resolve() and out.is_relative_to(RUNS) and 1<=timeout<=10800,
            'Fresh sole-verification output and at most three-hour simulation required')
    out.mkdir(parents=True,exist_ok=False);work=out/'work';work.mkdir()
    pins={};commands=[]
    result=dict(state='PREPARING',child_pid=None,whole_model=False,performance_measured=False,
                optimization_speedup_claim=False,synthesis_run=False,exact_elf_spike_executed=False)
    def save():(out/'status.json').write_text(json.dumps(result,indent=2)+'\n')
    def command(argv,label,limit):
        argv=list(map(str,argv));bind(pins,argv[0]);verify_pins(pins)
        commands.append(dict(label=label,argv=argv,timeout_seconds=limit));result['state']=label;save()
        env=dict(os.environ,PATH='/usr/bin:/bin',PYTHONPATH=str(VERIFY/'verification'),
                 PYTHONDONTWRITEBYTECODE='1',LC_ALL='C',READELF='/usr/bin/readelf')
        with (work/(label.lower()+'.log')).open('xb') as stream:
            child=subprocess.Popen(argv,cwd=work,env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
            result['child_pid']=child.pid;save()
            try:code=child.wait(timeout=limit)
            except BaseException:
                os.killpg(child.pid,signal.SIGKILL);child.wait();raise
        result['child_pid']=None;commands[-1]['returncode']=code
        require(code==0,label+' failed');verify_pins(pins)
    try:
        config,pins=inputs(build,sha);soc,elf=config['soc'],config['elf']
        result.update(elf=str(elf),elf_sha256=config['program']['elf_sha256'],simv=soc['simv'],
            image_pins=soc['image_pins'],build_result_sha256=sha,preload_segments=config['loads'],
            prerequisite_result_sha256=config['gate'])
        verify_pins(pins);(out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        if execute:
            spec=importlib.util.spec_from_file_location('f16_native_early_guard',GUARD)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            def save_guard(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
            with module.EarlyGuard(SimpleNamespace(out=out,state=result),work/'running.log',save_guard):
                command([soc['simv'],'-no_save','-l',work/'run.vcs.log','+PRELOAD='+str(elf),
                    '+TESTCASE=qwen3_f16_native_phase','+NO_FSDB','+NO_INSTR_TRACE','+AKV_PERF','+AKV_SUMMARY',
                    '+VECTOR_TRACE='+str(work/'vector_trace.csv'),'+ARA_CONTRACT_TRACE_LIMIT=2000000',
                    '+ARA_UVM_TRACE_LIMIT=2000000'],'RUNNING',timeout)
            require(not (out/'early-failure.json').exists(),'Early architectural/protocol failure')
            text=(work/'run.vcs.log').read_text()
            result['platform']=check_platform(text,128)
            result['measured']=checker.check(text)
            command([sys.executable,'-B','-m','ara_verify.uvm_dut','--require-events','--require-backend',
                '--require-axi','--require-axi-write','--vector-trace',work/'vector_trace.csv',
                '--log',work/'run.vcs.log','--simv',soc['simv'],'--elf',elf,
                '--output',work/'uvm_result.json'],'PROTOCOL',600)
            protocol=json.loads((work/'uvm_result.json').read_text())
            require(protocol['status']=='PASS' and protocol['elf_sha256']==config['program']['elf_sha256'] and
                    protocol['log_sha256']==digest(work/'run.vcs.log') and
                    protocol['vector_trace_sha256']==digest(work/'vector_trace.csv') and
                    protocol['sim_image_sha256']==soc['image_pins'],'Independent protocol identity differs')
            result.update(state='REAL_QWEN3_F16_PHASE_RTL_PASS',performance_measured=True,
                independent_protocol_checked=True,
                quantitative_phase_fractions_allowed=result['measured']['quantitative_phase_fractions_allowed'])
        else:result['state']='REAL_QWEN3_F16_PHASE_PREFLIGHT_NOT_RUN'
        verify_pins(pins)
        result.update(post_pins_match=True,source_pins_sha256=digest(out/'source-pins.json'),limits=[
            'One real Qwen3 KV group, genuine Decode visible137 and native-sized first64 Prefill queries',
            'Materialized subset layout and SDK calls; excludes full GGML admission, locking and entire-model execution',
            'Unchanged native arithmetic versus observation-only clone; no new acceleration measured',
            'Every output checked on target; external record contains per-query fingerprints, not every individual word',
            'Barrier cycles overlap exclusive phases and include useful pending work; never add or subtract as pure overhead',
            'Reject quantitative phase fractions when either paired perturbation exceeds five percent',
            'Flat physical memory, not translated Linux, PPA or FPGA acceptance'])
    except BaseException as exc:
        result.update(state='FAIL',error=repr(exc));raise
    finally:
        save();(out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        result['artifacts']={str(p):digest(p) for p in (*work.glob('*.log'),work/'vector_trace.csv',
            work/'uvm_result.json',out/'source-pins.json',out/'commands.json',out/'early-failure.json') if p.is_file()}
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,required=True)
    p.add_argument('--build-sha256',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--timeout',type=int,default=10800);p.add_argument('--execute-reviewed',action='store_true')
    def stop(sig,_frame):raise InterruptedError('Signal '+str(sig))
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,stop)
    a=p.parse_args();run(a.build,a.build_sha256,a.output,a.timeout,a.execute_reviewed)
