#!/usr/bin/env python3
"""Replay the unchanged accepted Register-PV ELF on retirement RTL."""
import argparse
import importlib.util
from pathlib import Path
import signal
import sys
from run_ordinary import checked_review, archive_baseline_integer, runtime, ROOT

CHECKER=ROOT/'verification/akv/quantized_kv/register_pv/check_native.py'
spec=importlib.util.spec_from_file_location('retirement_register_check',CHECKER)
checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)


def run(args):
    s=runtime.s;out=args.output.resolve()
    s.require(out.is_relative_to(ROOT/'verification/out') and not out.exists(),'Fresh output required')
    out.mkdir();work=out/'work';work.mkdir();owner=runtime.Execution(out)
    owner.env['PYTHONPATH']=str(ROOT/'verification');owner.env['PYTHONDONTWRITEBYTECODE']='1'
    result=dict(state='PREFLIGHT',performance_measured=False)
    try:
        baseline=ROOT/'verification/out/register-guarded-q4-vcs-20261028-01'
        old=s.read_json(baseline/'result.json')
        s.require(old['state']=='PASS' and old['post_pins_match'] is True,'Historical acceptance')
        pins=s.read_json(baseline/'source-pins.json')
        changed=str(ROOT/'hardware/src/vlsu/qbs/qbs_profile_engine_int.sv')
        expected='576304613df34547c7d80b04739a4a0164febd719cfcbc463d6465db6d966978'
        s.require(pins.get(changed)==expected,'Only reviewed historical RTL admitted')
        archive_baseline_integer()
        del pins[changed]
        pins[str(ROOT/'verification/out/qbs-retire-historical-integer-20261029-01/qbs_profile_engine_int.sv')]=expected
        s.verify_pins(pins)
        soc,current,image=checked_review(args.soc_build,args.expected_soc_sha256)
        s.merge_pins(pins,current)
        build=ROOT/'verification/out/register-guarded-q4-build-20261028-01'
        report=s.read_json(build/'build.json');elf=Path(report['elf'])
        s.require(report.get('early_entry_guard') is True and report.get('register_pv') is True
            and report['elf_sha256']==old['elf_sha256']==s.digest(elf),'Unchanged guarded ELF')
        golden=ROOT/'verification/out/quant-prefill-capture-20261028-01/q4_0/prefill/block/kqv_out-0.bin'
        s.merge_pins(pins,s.hashes([baseline/'result.json',baseline/'source-pins.json',CHECKER,Path(__file__)]))
        for module in tuple(sys.modules.values()):
            name=getattr(module,'__file__',None)
            if name and Path(name).is_file() and Path(name).resolve().is_relative_to(ROOT):
                s.merge_pins(pins,s.hashes([Path(name).resolve()]))
        s.atomic_json(out/'source-pins.json',pins);simv=Path(soc['simv'])
        def identity():
            s.verify_pins(pins);runtime.verify_current(soc,image,pins)
        identity()
        if args.execute:
            owner.execute(['bash',ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',simv.parent,elf],
                out/'image-contract.log',180,'IMAGE_CONTRACT')
            owner.execute([simv,'-no_save','-l',work/'run.vcs.log','+PRELOAD='+str(elf),
                '+TESTCASE=register_retirement_regression','+NO_FSDB','+NO_INSTR_TRACE',
                '+VECTOR_TRACE='+str(work/'vector_trace.csv'),'+ARA_CONTRACT_TRACE_LIMIT=2000000',
                '+ARA_UVM_TRACE_LIMIT=2000000'],work/'console.log',10800,'RUNNING')
            measured=checker.check_log((work/'run.vcs.log').read_text(),golden.read_bytes(),1)
            owner.execute([sys.executable,'-B','-m','ara_verify.uvm_dut','--require-events',
                '--require-backend','--require-axi','--require-axi-write','--vector-trace',work/'vector_trace.csv',
                '--log',work/'run.vcs.log','--simv',simv,'--elf',elf,'--output',work/'uvm_result.json'],
                work/'checker.log',600,'CHECKING')
            protocol=s.read_json(work/'uvm_result.json')
            s.require(protocol['status']=='PASS' and not protocol.get('issues'),'Protocol failure')
            result.update(state='PASS',measured=measured,performance_measured=True)
        else:result['state']='PREFLIGHT_NOT_RUN'
        identity();result.update(post_pins_match=True,elf_sha256=report['elf_sha256'],
            source_pins_sha256=s.digest(out/'source-pins.json'),
            admitted_rtl_change=changed,historical_rtl_sha256=expected,current_rtl_sha256=s.digest(Path(changed)))
    except BaseException as exc:
        result.update(state='FAIL',error=repr(exc));raise
    finally:
        s.atomic_json(out/'result.json',result);owner.state.update(state=result['state'],child_pid=None);owner.save()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--soc-build',type=Path,required=True)
    parser.add_argument('--expected-soc-sha256',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    def interrupted(sig,_frame):raise InterruptedError(f'Signal {sig}')
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,interrupted)
    run(args)
