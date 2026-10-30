#!/usr/bin/env python3
"""Bounded F32 PV worker on an existing accepted VCS image."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
from rtl_check import HERE, ROOT, EXPECTED, check_log, require
sys.path.insert(0, str(HERE.parent/'contexts'))
from run_context import Execution
import attention_run as s


def prepare(build):
    # Keep the sealed checker unchanged: its build-only check_pins helper passes
    # a JSON string to digest(Path). Validate the typed receipt here instead.
    report = s.read_json(build/'build.json')
    require(report.get('state') == 'BUILT_NOT_EXECUTED' and
            report.get('execution') == 'NOT_RUN' and report.get('expected') == EXPECTED and
            report.get('post_pins_match') is True, 'Invalid build receipt')
    require(s.digest(build/'source-pins.json') == report['source_pins_sha256'], 'Build receipt drift')
    pins = s.read_json(build/'source-pins.json')
    s.merge_pins(pins, report['artifact_sha256'])
    require(pins.get(report['elf']) == report['elf_sha256'] == s.digest(Path(report['elf'])),
            'Build ELF identity')
    s.verify_pins(pins)
    image, accepted = s.checked_image(ROOT/'verification/out/qbacc-soc-accept-20261023-02',
                                      Path(report['simv']))
    require(image == report['accepted_image_pins'], 'Build/accepted image mismatch')
    s.merge_pins(pins, accepted)
    files = [build/'build.json',build/'source-pins.json',Path(__file__),HERE/'rtl_run_test.py',
        HERE/'rtl_check.py',HERE/'rtl_test.py',HERE.parent/'rtl_check.py',
        HERE.parent/'contexts/run_context.py',HERE.parent/'contexts/check_context.py',
        HERE.parent/'contexts/context_spec.py',HERE.parent/'threeway_run.py',
        HERE.parent/'threeway_build.py',HERE.parent/'attention_run.py',
        ROOT/'verification/akv/run_qk_panel4_abba.py',ROOT/'verification/akv/run_refill_overlap_probe.py',
        ROOT/'verification/qbs/run_tile_context_engine.py',*s.script_files(),
        ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',Path(sys.executable).resolve()]
    s.merge_pins(pins,s.hashes(files))
    s.verify_pins(pins)
    return report,image,pins


def run(args):
    require(1 <= args.timeout <= 10800, 'Timeout must be 1..10800 seconds')
    build = args.build.resolve(strict=True)
    out = args.output.resolve()
    require(not out.is_relative_to(build), 'Output must be outside sealed build')
    out.mkdir(parents=True,exist_ok=False)
    work = out/'work'
    work.mkdir()
    owner = Execution(out)
    owner.state.update(timeout_seconds=args.timeout,build=str(build))
    owner.save()
    try:
        report,image,pins = prepare(build)
        simv,elf = Path(report['simv']),Path(report['elf'])
        owner.state.update(simv=str(simv),elf=str(elf))
        s.atomic_json(out/'source-pins.json',pins)
        receipt = s.digest(out/'source-pins.json')
        def identity():
            require(s.digest(out/'source-pins.json') == receipt,'Worker pins receipt changed')
            s.verify_pins(pins)
            require(s.hashes(s.image_files(simv)) == image,'Image inventory drift')
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
            owner.execute([simv,'-no_save','-l',log,'+PRELOAD='+str(elf),'+TESTCASE=akv_paired_f32_pv',
                '+NO_FSDB','+NO_INSTR_TRACE','+AKV_PERF','+AKV_SUMMARY','+VECTOR_TRACE='+str(trace),
                '+ARA_CONTRACT_TRACE_LIMIT=2000000','+ARA_UVM_TRACE_LIMIT=2000000'],
                work/'console.log',args.timeout,'RUNNING')
            result = check_log(log.read_text(),report['cases'],(build/'golden.bin').read_bytes())
            owner.execute([sys.executable,'-B','-m','ara_verify.uvm_dut','--require-events',
                '--require-backend','--require-axi','--require-axi-write','--vector-trace',trace,
                '--log',log,'--simv',simv,'--elf',elf,'--output',work/'uvm_result.json'],
                work/'checker.log',600,'CHECKING')
            s.check_result(work/'uvm_result.json',report['elf_sha256'],image)
            uvm = s.read_json(work/'uvm_result.json')
            require(uvm['log_sha256'] == s.digest(log) and
                    uvm['vector_trace_sha256'] == s.digest(trace), 'Independent UVM input identity')
            manifest('manifest-after')
            identity()
            result.update(simulator_exit_code=0,post_pins_match=True,elf_sha256=report['elf_sha256'],
                source_pins_sha256=receipt,evidence_sha256=s.hashes([log,trace,work/'uvm_result.json',
                    out/'source-pins.json',out/'manifest-before.log',out/'manifest-after.log',out/'image-contract.log']))
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
    p.add_argument('--build',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
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
