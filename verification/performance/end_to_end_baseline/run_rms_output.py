#!/usr/bin/env python3
"""Check the norm/output ELF in Spike first, then one bounded VCS ABBA run."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

from audit import digest, require, verify_pins
from prepare_wide_soc import HERE, ROOT, VERIFY, RUNS
from continue_wide_soc import SOC_HASH
from run_supply_sdk import bind, acceptance_gate
from run_wide_soc_smoke import elf_admission, check_platform
from run_decode_rvv_isa import SPIKE, SPIKE_SHA, libraries, spike_command
from run_decode_rvv_rtl import ISA, ISA_SHA
from check_projection_native import fields
import check_rms_output as checker


def inputs(build):
    pins = {}
    bind(pins, build / 'build.json')
    program = json.loads((build / 'build.json').read_text())
    require(program['state'] == 'REAL_FUSED_RMS_VECTOR_OUTPUT_BUILT_NOT_EXECUTED' and
            program['outputs_checked'] == 40960 and program['output_boundary_cases'] == 155 and
            program['recompiled_objects'] == 4 and program['baseline_arithmetic_unchanged'] and
            program['timing_includes_csr_completion'] and not program['rtl_changed'] and
            not program['production_library_changed'], 'Wrong output experiment build')
    bind(pins, build / 'source-pins.json', program['source_pins_sha256'])
    for group in (json.loads((build / 'source-pins.json').read_text()), program['artifacts']):
        for path, sha in group.items(): bind(pins,path,sha)
    elf = Path(program['elf']); bind(pins,elf,program['elf_sha256'])
    loads = elf_admission(elf.read_bytes(),16)
    soc_root = RUNS / 'e2e_physical_wide_soc128_20261106_01'
    bind(pins,soc_root / 'result.json',SOC_HASH[128])
    soc = json.loads((soc_root / 'result.json').read_text())
    require(soc['width'] == 128 and soc['post_pins_match'], 'Wrong actual SoC')
    bind(pins,soc_root / 'source-pins.json',soc['source_pins_sha256'])
    for group in (json.loads((soc_root / 'source-pins.json').read_text()),soc['artifacts'],soc['image_pins']):
        for path,sha in group.items(): bind(pins,path,sha)
    bind(pins,ISA / 'result.json',ISA_SHA)
    isa = json.loads((ISA / 'result.json').read_text())
    plugin = ISA / 'spike_soc_ports.so'; bind(pins,plugin,isa['artifacts'][str(plugin)])
    bind(pins,SPIKE,SPIKE_SHA); isa_pins=json.loads((ISA / 'source-pins.json').read_text())
    bind(pins,ISA / 'source-pins.json',isa['source_pins_sha256'])
    dtc=Path('/usr/bin/dtc').resolve(strict=True); bind(pins,dtc,isa_pins[str(dtc)])
    for name in ('spike-libraries.log','plugin-libraries.log'):
        path = ISA / name; bind(pins,path,isa['artifacts'][str(path)])
        for library in libraries(path.read_text()): bind(pins,library,isa_pins[library])
    data = Path(program['data'])
    for path in (data / 'expected_f32.bin',data / 'decode_expected_f32.bin'):
        bind(pins,path,pins[str(path.resolve())])
    for module in tuple(sys.modules.values()):
        path=getattr(module,'__file__',None)
        if path and Path(path).is_file() and any(Path(path).resolve().is_relative_to(r) for r in (ROOT,VERIFY)):
            bind(pins,path)
    for path in (HERE / 'test_rms_output_check.py',HERE / 'test_rms_norm_output.py',
                 Path(__file__),Path(sys.executable),*(VERIFY / 'verification/ara_verify').glob('*.py')):
        bind(pins,path)
    gate = acceptance_gate(pins)
    return dict(program=program,elf=elf,soc=soc,plugin=plugin,data=data,loads=loads,gate=gate),pins


def run(build, output, execute, timeout):
    out=output.absolute()
    require(out==out.resolve() and out.is_relative_to(RUNS) and 1<=timeout<=10800,'Fresh bounded verification run')
    out.mkdir(parents=True,exist_ok=False); work=out/'work'; work.mkdir()
    pins,commands={},[]
    result=dict(state='PREPARING',child_pid=None,performance_measured=False,whole_model=False,
                rtl_changed=False,production_library_changed=False,synthesis_run=False)
    def save(): (out/'status.json').write_text(json.dumps(result,indent=2)+'\n')
    def command(argv,label,limit,isa=False):
        argv=list(map(str,argv));bind(pins,argv[0]);verify_pins(pins)
        result['state']=label;commands.append(dict(label=label,argv=argv,timeout_seconds=limit));save()
        env={k:v for k,v in os.environ.items() if k!='LD_PRELOAD' and
             (not isa or k not in ('LD_LIBRARY_PATH','CPATH','C_INCLUDE_PATH','CPLUS_INCLUDE_PATH'))}
        env.update(PATH='/usr/bin:/bin',PYTHONPATH=str(VERIFY/'verification'),PYTHONDONTWRITEBYTECODE='1',
                   LC_ALL='C',READELF='/usr/bin/readelf')
        with (work/(label.lower()+'.log')).open('xb') as stream:
            child=subprocess.Popen(argv,cwd=work,env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
            result['child_pid']=child.pid;save()
            try: code=child.wait(timeout=limit)
            except BaseException:
                os.killpg(child.pid,signal.SIGKILL);child.wait();raise
        result['child_pid']=None;commands[-1]['returncode']=code
        require(code==0,label+' failed');verify_pins(pins)
    try:
        config,pins=inputs(build)
        soc,elf,data=config['soc'],config['elf'],config['data']
        result.update(elf=str(elf),elf_sha256=config['program']['elf_sha256'],simv=soc['simv'],
                      image_pins=soc['image_pins'],preload_segments=config['loads'],
                      prerequisite_result_sha256=config['gate'])
        (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        if execute:
            command(spike_command(config['plugin'],elf),'ISA_REFERENCE',120,True)
            text=(work/'isa_reference.log').read_text()
            reference=checker.check(text,(data/'expected_f32.bin').read_bytes(),(data/'decode_expected_f32.bin').read_bytes())
            exit_rows=[fields(line,'SPIKE_SOC_EXIT') for line in text.replace('\r','').splitlines()
                       if line.startswith('SPIKE_SOC_EXIT ')]
            require(len(exit_rows)==1 and set(exit_rows[0])=={'status','uart_bytes'} and
                    exit_rows[0]['status']==0 and exit_rows[0]['uart_bytes']>0,'ISA did not exit successfully')
            result['isa_signature']=checker.signature(reference)
            command([soc['simv'],'-no_save','-l',work/'run.vcs.log','+PRELOAD='+str(elf),
                     '+TESTCASE=rms_guarded_output_abba','+NO_FSDB','+NO_INSTR_TRACE','+QBS_PERF',
                     '+VECTOR_TRACE='+str(work/'vector_trace.csv'),'+ARA_CONTRACT_TRACE_LIMIT=2000000',
                     '+ARA_UVM_TRACE_LIMIT=2000000'],'SIMULATION',timeout)
            text=(work/'run.vcs.log').read_text();result['platform']=check_platform(text,128)
            measured=checker.check(text,(data/'expected_f32.bin').read_bytes(),(data/'decode_expected_f32.bin').read_bytes())
            require(checker.signature(measured)==result['isa_signature'],'RTL differs from ISA numerical/state summary')
            result['activity']=checker.activity((work/'vector_trace.csv').read_text())
            command([sys.executable,'-B','-m','ara_verify.uvm_dut','--require-events','--require-backend',
                     '--require-axi','--require-axi-write','--vector-trace',work/'vector_trace.csv',
                     '--log',work/'run.vcs.log','--simv',soc['simv'],'--elf',elf,
                     '--output',work/'uvm_result.json'],'PROTOCOL',600)
            protocol=json.loads((work/'uvm_result.json').read_text())
            require(protocol['status']=='PASS' and protocol['log_sha256']==digest(work/'run.vcs.log') and
                    protocol['vector_trace_sha256']==digest(work/'vector_trace.csv') and
                    protocol['elf_sha256']==config['program']['elf_sha256'] and
                    protocol['sim_image_sha256']==soc['image_pins'],'Protocol/identity mismatch')
            result.update(state='REAL_FUSED_RMS_VECTOR_OUTPUT_RTL_PASS',measured=measured,
                          performance_measured=True,independent_protocol_checked=True)
        else: result['state']='REAL_FUSED_RMS_VECTOR_OUTPUT_PREFLIGHT_NOT_RUN'
        verify_pins(pins)
        result.update(post_pins_match=True,source_pins_sha256=digest(out/'source-pins.json'),
                      limits=['Existing FP32-square/ordered-FP64 sum and original mean/scale retained',
                              'Normal valid RAM and entry vstart=0; no memory-fault or intermediate-fflags equivalence',
                              'Real complete fused calls only; no model speedup or GGML production promotion'])
    except BaseException as exc:
        result.update(state='FAIL',error=repr(exc));raise
    finally:
        save();(out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        result['artifacts']={str(p):digest(p) for p in (*work.glob('*.log'),work/'vector_trace.csv',
             work/'uvm_result.json',out/'source-pins.json',out/'commands.json') if p.is_file()}
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--timeout',type=int,default=10800);p.add_argument('--execute-reviewed',action='store_true')
    def stop(sig,_frame): raise InterruptedError('Signal '+str(sig))
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,stop)
    a=p.parse_args();run(a.build.resolve(strict=True),a.output,a.execute_reviewed,a.timeout)
