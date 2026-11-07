#!/usr/bin/env python3
"""Bounded real Attention phase observation, with an uninstrumented ABBA control."""
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
import check_output_phase as checker

BUILD = RUNS/'e2e_output_phase_build_20261106_02'
BUILD_SHA = 'e8683a23c40f956d0276a1f125d35f2414795462d13a27ad8a7492cb2bee7446'
ELF_SHA = '557ac6aa65f219260b4da09fd591cef6c453f57e56d6fbb165597b32b7582011'
GUARD = ROOT/'verification/akv/quantized_kv/prefill/early_guard.py'


def inputs():
    pins = {}
    bind(pins,BUILD/'build.json',BUILD_SHA)
    program=json.loads((BUILD/'build.json').read_text())
    require(program['state']=='OUTPUT_PHASE_ELF_BUILT_NOT_EXECUTED' and
            program['elf_sha256']==ELF_SHA and not program['target_executed'] and
            not program['performance_measured'] and program['simulation_count']==0 and
            program['baseline']=='output_tile_original_object' and
            program['candidate']=='output_tile_observation_only_clone' and
            (program['heads'],program['dim'],program['visible'],program['trials'])==(6,128,128,4) and
            (program['reused_objects'],program['rebuilt_objects'])==(16,2) and
            program['binding_nested_in_qk'] and program['internal_timestamps_per_probed_call']==46 and
            program['quantitative_phase_interpretation_requires_measured_overhead_at_most']==0.05,
            'Wrong phase observation build/scope')
    bind(pins,BUILD/'source-pins.json',program['source_pins_sha256'])
    for group in (json.loads((BUILD/'source-pins.json').read_text()),program['artifacts']):
        for path,sha in group.items():bind(pins,path,sha)
    elf=Path(program['elf']);bind(pins,elf,ELF_SHA)
    golden=Path(program['golden']);require(str(golden.resolve()) in pins,'Independent golden not pinned')
    soc_root=RUNS/'e2e_physical_wide_soc128_20261106_01'
    bind(pins,soc_root/'result.json',SOC_HASH[128])
    soc=json.loads((soc_root/'result.json').read_text())
    require(soc['state']=='PHYSICAL_WIDE_SOC_BUILT_NOT_EXECUTED' and soc['width']==128 and
            soc['post_pins_match'],'Wrong accepted physical platform')
    bind(pins,soc_root/'source-pins.json',soc['source_pins_sha256'])
    for group in (json.loads((soc_root/'source-pins.json').read_text()),soc['artifacts'],soc['image_pins']):
        for path,sha in group.items():bind(pins,path,sha)
    for module in tuple(sys.modules.values()):
        path=getattr(module,'__file__',None)
        if path and Path(path).is_file() and any(Path(path).resolve().is_relative_to(r) for r in (ROOT,VERIFY)):
            bind(pins,path)
    for path in (Path(__file__),HERE/'test_run_output_phase.py',HERE/'test_output_phase.py',GUARD,
                 Path(sys.executable),*(VERIFY/'verification/ara_verify').glob('*.py')):bind(pins,path)
    gate=acceptance_gate(pins)
    return dict(program=program,elf=elf,golden=golden,soc=soc,
                loads=elf_admission(elf.read_bytes(),16),gate=gate),pins


def run(output,timeout,execute):
    out=output.absolute()
    require(out==out.resolve() and out.is_relative_to(RUNS) and 1<=timeout<=10800,
            'Fresh sole-verification directory and at most three-hour simulation required')
    out.mkdir(parents=True,exist_ok=False);work=out/'work';work.mkdir()
    pins,commands={},[]
    result=dict(state='PREPARING',child_pid=None,phase_observation_measured=False,
                whole_model=False,optimization_speedup_claim=False,synthesis_run=False,
                exact_elf_spike_executed=False)
    def save():(out/'status.json').write_text(json.dumps(result,indent=2)+'\n')
    def command(argv,label,limit):
        argv=list(map(str,argv));bind(pins,argv[0]);verify_pins(pins)
        result['state']=label;commands.append(dict(label=label,argv=argv,timeout_seconds=limit));save()
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
        config,pins=inputs();soc,elf=config['soc'],config['elf']
        result.update(elf=str(elf),elf_sha256=ELF_SHA,simv=soc['simv'],image_pins=soc['image_pins'],
                      build_result_sha256=BUILD_SHA,preload_segments=config['loads'],
                      prerequisite_result_sha256=config['gate'])
        verify_pins(pins);(out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        if execute:
            spec=importlib.util.spec_from_file_location('output_phase_early_guard',GUARD)
            guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
            def save_guard(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
            with guard.EarlyGuard(SimpleNamespace(out=out,state=result),work/'running.log',save_guard):
                command([soc['simv'],'-no_save','-l',work/'run.vcs.log','+PRELOAD='+str(elf),
                    '+TESTCASE=output_phase_observation','+NO_FSDB','+NO_INSTR_TRACE','+QBS_PERF',
                    '+VECTOR_TRACE='+str(work/'vector_trace.csv'),'+ARA_CONTRACT_TRACE_LIMIT=2000000',
                    '+ARA_UVM_TRACE_LIMIT=2000000'],'RUNNING',timeout)
            require(not (out/'early-failure.json').exists(),'Early architectural/protocol failure')
            text=(work/'run.vcs.log').read_text()
            result['platform']=check_platform(text,128)
            result['measured']=checker.check(text,config['golden'].read_bytes())
            command([sys.executable,'-B','-m','ara_verify.uvm_dut','--require-events','--require-backend',
                    '--require-axi','--require-axi-write','--vector-trace',work/'vector_trace.csv',
                    '--log',work/'run.vcs.log','--simv',soc['simv'],'--elf',elf,
                    '--output',work/'uvm_result.json'],'PROTOCOL',600)
            p=json.loads((work/'uvm_result.json').read_text())
            require(p['status']=='PASS' and p['elf_sha256']==ELF_SHA and
                    p['log_sha256']==digest(work/'run.vcs.log') and
                    p['vector_trace_sha256']==digest(work/'vector_trace.csv') and
                    p['sim_image_sha256']==soc['image_pins'],'Independent protocol identity/check differs')
            result.update(state='REAL_ATTENTION_PHASE_OBSERVATION_RTL_PASS',
                phase_observation_measured=True,independent_protocol_checked=True,
                quantitative_phase_fractions_allowed=result['measured']['quantitative_phase_fractions_allowed'])
        else:result['state']='REAL_ATTENTION_PHASE_OBSERVATION_PREFLIGHT_NOT_RUN'
        verify_pins(pins)
        result.update(post_pins_match=True,source_pins_sha256=digest(out/'source-pins.json'),
            limits=['Real captured Qwen2.5 GQA6 D128 visible128 complete calls, not Qwen3 or whole-model timing',
                    'Observation-only clone; all results and CSR must match original Output-Tile bits',
                    'Coefficient time includes expf and recurrence; PV includes value decode and accumulation',
                    'Binding is nested in QK; other recorded phases are exclusive',
                    'More than five percent paired complete-call perturbation forbids quantitative phase fractions',
                    'Flat physical RAM, no Linux/MMU, PPA, default-backend promotion or new optimization speedup'])
    except BaseException as exc:
        result.update(state='FAIL',error=repr(exc));raise
    finally:
        save();(out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        result['artifacts']={str(p):digest(p) for p in (*work.glob('*.log'),work/'vector_trace.csv',
            work/'uvm_result.json',out/'source-pins.json',out/'commands.json',out/'early-failure.json') if p.is_file()}
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--timeout',type=int,default=10800);p.add_argument('--execute-reviewed',action='store_true')
    def stop(sig,_frame):raise InterruptedError('Signal '+str(sig))
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,stop)
    a=p.parse_args();run(a.output,a.timeout,a.execute_reviewed)
