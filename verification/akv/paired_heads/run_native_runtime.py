#!/usr/bin/env python3
"""Run stateless native candidate only after independently accepted KV256."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
from native_runtime_check import CASES, check_log
import attention_run as s

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0,str(HERE/'contexts'))
import run_context as context
import check_context


def checked_build(build):
    report = s.read_json(build/'build.json')
    s.require(report.get('state') == 'BUILT_NOT_EXECUTED' and report.get('execution') == 'NOT_RUN' and
        report.get('post_pins_match') is True and report.get('canonical_modified') is False and
        report.get('cases') == CASES and report.get('runs') == 12 and
        report.get('expected_commands') == 3680,'Wrong native-candidate build')
    s.require(s.digest(build/'source-pins.json') == report['source_pins_sha256'],'Build pins receipt drift')
    pins = s.read_json(build/'source-pins.json')
    s.merge_pins(pins,report['artifact_sha256'])
    s.require(pins.get(report['elf']) == report['elf_sha256'] == s.digest(Path(report['elf'])),
              'Candidate ELF identity mismatch')
    image,accepted = s.checked_image(ROOT/'verification/out/qbacc-soc-accept-20261023-02',Path(report['simv']))
    s.require(image == report['accepted_image_pins'],'Accepted image mismatch')
    s.merge_pins(pins,accepted)
    s.merge_pins(pins,s.hashes([build/'build.json',build/'source-pins.json']))
    s.verify_pins(pins)
    return report,image,pins


def checked_prerequisite(path,image):
    status,result = s.read_json(path/'status.json'),s.read_json(path/'result.json')
    s.require(status.get('state') == result.get('state') == 'PASS' and
        status.get('child_pid') is None and result.get('simulator_exit_code') == 0 and
        result.get('post_pins_match') is True and status.get('running_exit_code') == 0,
        'KV256 prerequisite not actual checked terminal PASS')
    build = Path(status['build']).resolve(strict=True)
    report,build_pins = check_context.checked_build(build)
    s.require(report['visible_kv'] == 256 and report['accepted_image_pins'] == image and
        status['elf'] == report['elf'] and status['simv'] == report['simv'],'Wrong KV256 build/image')
    pins = s.read_json(path/'source-pins.json')
    s.require(all(pins.get(p) == h for p,h in build_pins.items()),'Prerequisite build not pinned')
    s.require(pins.get(str(Path(context.__file__).resolve())) == s.digest(Path(context.__file__)),
              'Prerequisite worker not pinned')
    s.merge_pins(pins,result['evidence_sha256'])
    s.verify_pins(pins)
    parsed = context.checked_output(path/'checking',report,image,
                                    path/'work/run.vcs.log',path/'work/vector_trace.csv')
    s.require(all(result.get(k) == v for k,v in parsed.items()),'KV256 raw/accepted result mismatch')
    s.merge_pins(pins,s.hashes([path/'status.json',path/'result.json']))
    return pins,dict(path=str(path),result_sha256=s.digest(path/'result.json'),sums=parsed['sums'])


def run(args):
    s.require(1 <= args.timeout <= 10800,'Timeout must be 1..10800 seconds')
    build,prerequisite = args.build.resolve(strict=True),args.prerequisite.resolve(strict=True)
    out = args.output.resolve()
    s.require(not out.is_relative_to(build) and not out.is_relative_to(prerequisite),'Use independent fresh output')
    out.mkdir(parents=True,exist_ok=False)
    work = out/'work'
    work.mkdir()
    owner = context.Execution(out)
    owner.state.update(build=str(build),prerequisite=str(prerequisite),timeout_seconds=args.timeout)
    owner.save()
    try:
        report,image,pins = checked_build(build)
        if not args.build_preflight_only:
            previous,receipt = checked_prerequisite(prerequisite,image)
            s.merge_pins(pins,previous)
        else:
            receipt = dict(state='NOT_CHECKED_BUILD_PREFLIGHT_ONLY')
        files = [Path(__file__),HERE/'native_runtime_check.py',HERE/'native_runtime_test.py',
            HERE/'run_native_runtime_test.py',HERE/'contexts/run_context.py',
            HERE/'contexts/check_context.py',HERE/'contexts/context_spec.py',HERE/'threeway_run.py',
            HERE/'threeway_build.py',HERE/'attention_run.py',ROOT/'verification/akv/run_after_verified_gate.py',
            ROOT/'verification/akv/run_qk_panel4_abba.py',ROOT/'verification/akv/run_refill_overlap_probe.py',
            ROOT/'verification/qbs/run_tile_context_engine.py',*s.script_files(),Path(sys.executable).resolve(),
            ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh']
        s.merge_pins(pins,s.hashes(files))
        simv,elf = Path(report['simv']),Path(report['elf'])
        owner.state.update(simv=str(simv),elf=str(elf))
        s.atomic_json(out/'source-pins.json',pins)
        pin_hash = s.digest(out/'source-pins.json')
        def identity():
            s.require(s.digest(out/'source-pins.json') == pin_hash,'Worker pin receipt changed')
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
        if args.build_preflight_only:
            result = dict(state='BUILD_PREFLIGHT_PASS_NOT_RUN',prerequisite=receipt)
        else:
            log,trace = work/'run.vcs.log',work/'vector_trace.csv'
            owner.execute([simv,'-no_save','-l',log,'+PRELOAD='+str(elf),'+TESTCASE=akv_native_pair_runtime',
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
                uvm['vector_trace_sha256'] == s.digest(trace),'UVM input identity mismatch')
            manifest('manifest-after')
            identity()
            result.update(prerequisite=receipt,simulator_exit_code=0,post_pins_match=True,
                source_pins_sha256=pin_hash,elf_sha256=report['elf_sha256'],
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
    p.add_argument('--build-preflight-only',action='store_true')
    args = p.parse_args()
    def interrupted(signum,_frame):
        raise InterruptedError(f'Signal {signum}')
    for sig in (signal.SIGTERM,signal.SIGINT):
        signal.signal(sig,interrupted)
    run(args)


if __name__ == '__main__':
    main()
