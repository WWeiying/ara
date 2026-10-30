#!/usr/bin/env python3
"""Bounded real Prefill-slice worker gated by accepted native F32 PV."""
import argparse
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
from prefill_slice_check import check_log
from prefill_slice_data import load as capture_slice

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
spec = importlib.util.spec_from_file_location('prefill_slice_f32_leaf_check',HERE/'rtl_check.py')
leaf_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(leaf_check)
sys.path.insert(0,str(HERE.parent/'contexts'))
from run_context import Execution
import attention_run as s


def inputs(build,previous):
    report = s.read_json(build/'build.json')
    s.require(report.get('state') == 'BUILT_NOT_EXECUTED' and report.get('execution') == 'NOT_RUN' and
        report.get('post_pins_match') is True and report.get('expected_commands') == [3552,3138,3138,3552] and
        report.get('trials') == 4 and report.get('outputs_per_trial') == 2304,'Invalid slice build')
    s.require(s.digest(build/'source-pins.json') == report['source_pins_sha256'],'Build receipt drift')
    pins = s.read_json(build/'source-pins.json')
    s.merge_pins(pins,report['artifact_sha256'])
    s.require(pins.get(report['elf']) == report['elf_sha256'] == s.digest(Path(report['elf'])),'Wrong ELF')
    data,capture_pins = capture_slice()
    s.require(all(pins.get(p) == h for p,h in capture_pins.items()),'Capture provenance not pinned')
    s.require(all((build/(name+'.bin')).read_bytes() == blob for name,blob in data.items()),'Slice data drift')
    image,accepted = s.checked_image(ROOT/'verification/out/qbacc-soc-accept-20261023-02',Path(report['simv']))
    s.require(image == report['accepted_image_pins'],'Image drift')
    s.merge_pins(pins,accepted)
    status,result = s.read_json(previous/'status.json'),s.read_json(previous/'result.json')
    s.require(status.get('state') == result.get('state') == 'PASS' and status.get('child_pid') is None and
              status.get('running_exit_code') == result.get('simulator_exit_code') == 0 and
              result.get('post_pins_match') is True,'F32 PV prerequisite not checked terminal PASS')
    old_build = Path(status['build'])
    old_report = s.read_json(old_build/'build.json')
    s.require(old_report.get('state') == 'BUILT_NOT_EXECUTED' and
        old_report.get('post_pins_match') is True and old_report.get('expected') == leaf_check.EXPECTED and
        s.digest(old_build/'source-pins.json') == old_report['source_pins_sha256'],
        'Invalid F32 leaf build receipt')
    old_build_pins = s.read_json(old_build/'source-pins.json')
    s.merge_pins(old_build_pins,old_report['artifact_sha256'])
    s.require(old_build_pins.get(old_report['elf']) == old_report['elf_sha256'] ==
        s.digest(Path(old_report['elf'])),'Leaf ELF mismatch')
    s.merge_pins(old_build_pins,s.hashes([old_build/'build.json',old_build/'source-pins.json']))
    s.require(old_report['accepted_image_pins'] == image and status['elf'] == old_report['elf'] and status['simv'] == report['simv'],
              'Wrong leaf prerequisite image/build')
    old_pins = s.read_json(previous/'source-pins.json')
    s.require(all(old_pins.get(p) == h for p,h in old_build_pins.items()),'Leaf build not pinned')
    s.merge_pins(old_pins,result['evidence_sha256'])
    log,trace,uvm_file = (previous/'work'/name for name in ('run.vcs.log','vector_trace.csv','uvm_result.json'))
    raw = leaf_check.check_log(log.read_text(),old_report['cases'],(Path(status['build'])/'golden.bin').read_bytes())
    s.require(all(result.get(k) == v for k,v in raw.items()),'Leaf raw log mismatch')
    s.check_result(uvm_file,old_report['elf_sha256'],image)
    uvm = s.read_json(uvm_file)
    s.require(uvm['log_sha256'] == s.digest(log) and uvm['vector_trace_sha256'] == s.digest(trace),
              'Leaf protocol evidence mismatch')
    s.merge_pins(pins,old_pins)
    s.merge_pins(pins,s.hashes([previous/'status.json',previous/'result.json',build/'build.json',
        build/'source-pins.json',Path(__file__),HERE/'test_run_prefill_slice.py',HERE/'prefill_slice_check.py',
        HERE/'test_prefill_slice_check.py',HERE/'prefill_slice_data.py',HERE/'rtl_run.py',HERE/'rtl_check.py',
        HERE.parent/'contexts/run_context.py',HERE.parent/'contexts/check_context.py',HERE.parent/'contexts/context_spec.py',
        HERE.parent/'threeway_run.py',HERE.parent/'threeway_build.py',HERE.parent/'native_runtime_check.py',
        HERE.parent/'attention_run.py',ROOT/'verification/akv/run_qk_panel4_abba.py',
        ROOT/'verification/akv/run_refill_overlap_probe.py',ROOT/'verification/qbs/run_tile_context_engine.py',
        *s.script_files(),Path(sys.executable).resolve(),ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh']))
    s.verify_pins(pins)
    return report,image,pins


def run(args):
    s.require(1 <= args.timeout <= 10800,'Timeout must be 1..10800 seconds')
    build,previous = args.build.resolve(strict=True),args.prerequisite.resolve(strict=True)
    out = args.output.resolve()
    s.require(not out.is_relative_to(build) and not out.is_relative_to(previous),'Use separate fresh output')
    out.mkdir(parents=True,exist_ok=False)
    work = out/'work'
    work.mkdir()
    owner = Execution(out)
    owner.state.update(build=str(build),prerequisite=str(previous),timeout_seconds=args.timeout)
    owner.save()
    try:
        report,image,pins = inputs(build,previous)
        simv,elf = Path(report['simv']),Path(report['elf'])
        owner.state.update(simv=str(simv),elf=str(elf))
        s.atomic_json(out/'source-pins.json',pins)
        receipt = s.digest(out/'source-pins.json')
        def identity():
            s.require(s.digest(out/'source-pins.json') == receipt,'Worker receipt drift')
            s.verify_pins(pins)
            s.require(s.hashes(s.image_files(simv)) == image,'Image inventory drift')
        def manifest(stage):
            owner.execute([sys.executable,'-B','-m','ara_verify.vcs_source_manifest','--output',
                simv.parent/'vcs_source_manifest.json','--check'],out/(stage+'.log'),300,stage.upper())
        identity()
        manifest('manifest-before')
        owner.execute(['bash',ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
            simv.parent,elf,'akv_v2'],out/'image-contract.log',180,'IMAGE_CONTRACT')
        identity()
        if args.preflight_only:
            result = dict(state='PREFLIGHT_PASS_NOT_RUN',elf_sha256=report['elf_sha256'])
        else:
            log,trace = work/'run.vcs.log',work/'vector_trace.csv'
            owner.execute([simv,'-no_save','-l',log,'+PRELOAD='+str(elf),'+TESTCASE=akv_prefill_pv_slice',
                '+NO_FSDB','+NO_INSTR_TRACE','+AKV_PERF','+AKV_SUMMARY','+VECTOR_TRACE='+str(trace),
                '+ARA_CONTRACT_TRACE_LIMIT=2000000','+ARA_UVM_TRACE_LIMIT=2000000'],
                work/'console.log',args.timeout,'RUNNING')
            result = check_log(log.read_text())
            owner.execute([sys.executable,'-B','-m','ara_verify.uvm_dut','--require-events',
                '--require-backend','--require-axi','--require-axi-write','--vector-trace',trace,
                '--log',log,'--simv',simv,'--elf',elf,'--output',work/'uvm_result.json'],
                work/'checker.log',600,'CHECKING')
            s.check_result(work/'uvm_result.json',report['elf_sha256'],image)
            uvm = s.read_json(work/'uvm_result.json')
            s.require(uvm['log_sha256'] == s.digest(log) and
                uvm['vector_trace_sha256'] == s.digest(trace),'Protocol input identity')
            manifest('manifest-after')
            identity()
            result.update(simulator_exit_code=0,post_pins_match=True,elf_sha256=report['elf_sha256'],
                source_pins_sha256=receipt,prerequisite_result_sha256=s.digest(previous/'result.json'),
                evidence_sha256=s.hashes([log,trace,work/'uvm_result.json',out/'source-pins.json',
                    out/'manifest-before.log',out/'manifest-after.log',out/'image-contract.log']))
        s.atomic_json(out/'result.json',result)
        owner.state['state'] = result['state']
        return result
    except BaseException as exc:
        state = 'TIMEOUT' if isinstance(exc,subprocess.TimeoutExpired) else 'INTERRUPTED' if isinstance(exc,InterruptedError) else 'FAIL'
        owner.state.update(state=state,error=repr(exc))
        s.atomic_json(out/'result.json',dict(state=state,error=repr(exc)))
        raise
    finally:
        owner.state.update(child_pid=None,finished=datetime.now(timezone.utc).isoformat())
        owner.save()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('build','prerequisite','output'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--timeout',type=int,default=10800)
    p.add_argument('--preflight-only',action='store_true')
    args = p.parse_args()
    def interrupted(signum,_frame):
        raise InterruptedError(f'Signal {signum}')
    for sig in (signal.SIGTERM,signal.SIGINT):
        signal.signal(sig,interrupted)
    run(args)


if __name__ == '__main__':
    main()
