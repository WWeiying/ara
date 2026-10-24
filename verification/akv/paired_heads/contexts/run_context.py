#!/usr/bin/env python3
"""Direct-owned bounded KV256 worker; prerequisite must already be terminal PASS.

Use run_after_verified_gate.py for pidfd waiting, not this worker. Its default
KV128 prerequisite build is the sealed threeway-build-20261023-01. No checksum
or positive-speedup requirement crosses from that different capture to KV256.
"""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
from context_spec import HERE, ROOT, shared as s
from check_context import checked_build, check_log
import threeway_run as prior

PRIOR_BUILD = ROOT/'verification/out/akv-paired-heads-threeway-build-20261023-01'
IMAGE_GATE = ROOT/'verification/out/qbacc-soc-accept-20261023-02'


def checked_prerequisite(path, build, image):
    status, result = s.read_json(path/'status.json'), s.read_json(path/'result.json')
    s.require(status.get('state') == result.get('state') == 'PASS' and
              'child_pid' in status and status['child_pid'] is None,
              'KV128 prerequisite is not checked terminal PASS; no wait/retry')
    report, build_pins, _ = prior.checked_build(build)
    s.require(report['accepted_image_pins'] == image and status['elf'] == report['elf'] and
              status['simv'] == report['simv'], 'Prerequisite build/ELF/image mismatch')
    pins = s.read_json(path/'source-pins.json')
    s.require(all(pins.get(p) == h for p,h in build_pins.items()), 'Prerequisite does not pin its typed KV128 build')
    worker = Path(prior.__file__).resolve()
    s.require(pins.get(str(worker)) == s.digest(worker), 'Unpinned prerequisite worker')
    log, trace, uvm_path = (path/'work'/n for n in ('run.vcs.log','vector_trace.csv','uvm_result.json'))
    evidence = result['evidence_sha256']
    s.require(all(str(p) in evidence for p in (log,trace,uvm_path,path/'source-pins.json')),
              'Missing prerequisite protocol evidence')
    s.merge_pins(pins,evidence)
    s.verify_pins(pins)
    s.check_result(uvm_path,report['elf_sha256'],image)
    uvm = s.read_json(uvm_path)
    s.require(uvm['log_sha256'] == s.digest(log) and uvm['vector_trace_sha256'] == s.digest(trace),
              'Prerequisite UVM evidence mismatch')
    parsed = prior.check_log(log.read_text())
    s.require(all(result.get(k) == v for k,v in parsed.items()), 'Prerequisite result/raw replay mismatch')
    s.merge_pins(pins,s.hashes([path/'status.json',path/'result.json']))
    return pins, dict(path=str(path),build=str(build),result_sha256=s.digest(path/'result.json'),
        sums=parsed['sums'],contract='Functional PASS only; no positive-speedup or cross-capture checksum requirement')


def prepare_inputs(args):
    report,pins = checked_build(args.build)
    s.require(report['visible_kv'] == 256, 'This worker consumes the real KV256 successor only')
    image,accepted = s.checked_image(args.gate,Path(report['simv']))
    s.require(image == report['accepted_image_pins'], 'Accepted image changed')
    s.merge_pins(pins,accepted)
    prerequisite, receipt = checked_prerequisite(args.prerequisite,args.prerequisite_build,image)
    s.merge_pins(pins,prerequisite)
    files = [Path(__file__),HERE/'test_run_context.py',HERE/'check_context.py',HERE/'context_spec.py',
        Path(prior.__file__),HERE.parent/'threeway_run_test.py',HERE.parent/'attention_run.py',
        HERE.parent.parent/'run_after_verified_gate.py',HERE.parent.parent/'run_qk_panel4_abba.py',
        HERE.parent.parent/'run_refill_overlap_probe.py',ROOT/'verification/qbs/run_tile_context_engine.py',
        ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',*s.script_files(),Path(sys.executable).resolve()]
    s.merge_pins(pins,s.hashes(files))
    s.verify_pins(pins)
    return report,pins,image,receipt


class Execution:
    """Record foreground phases; the existing shared tool owns group cleanup."""
    def __init__(self, out):
        self.out = out
        self.state = dict(state='PREFLIGHT',pid=os.getpid(),child_pid=None,
                          started=datetime.now(timezone.utc).isoformat())
        self.env = dict(os.environ,PYTHONPATH=str(ROOT/'verification'),PYTHONDONTWRITEBYTECODE='1')
        for key in ('LLAMA_ATTN_SIM_L2_BYTES','LD_PRELOAD'):
            self.env.pop(key,None)

    def save(self):
        s.atomic_json(self.out/'status.json',self.state)

    def execute(self, argv, log, timeout, phase):
        argv = list(map(str,argv))
        s.atomic_json(log.with_suffix('.command.json'),dict(argv=argv,cwd=str(log.parent),timeout_seconds=timeout))
        self.state['state'] = phase
        def started(pid):
            self.state['child_pid'] = pid
            if phase == 'RUNNING':
                self.state['simulator_pid'] = pid
            self.save()
        try:
            code = s.run_command(argv,log,timeout,self.env,started)
            self.state[phase.lower()+'_exit_code'] = code
            s.require(code == 0,f'{phase} returned {code}')
        finally:
            self.state['child_pid'] = None
            self.save()


def checked_output(check_dir, report, image, log, trace):
    checked = s.read_json(check_dir/'result.json')
    s.require(checked.get('state') == 'NUMERIC_WORK_AND_UVM_CHECKED' and
              checked.get('post_pins_match') is True and checked['elf_sha256'] == report['elf_sha256'],
              'Context checker not complete or wrong ELF')
    s.require(s.digest(check_dir/'pins.json') == checked['pins_sha256'], 'Checker pins receipt drift')
    s.verify_pins(s.read_json(check_dir/'pins.json'))
    required = (log,trace,check_dir/'uvm_result.json')
    s.require(all(str(p) in checked['evidence_sha256'] for p in required),'Missing checker evidence')
    s.verify_pins(checked['evidence_sha256'])
    s.check_result(check_dir/'uvm_result.json',report['elf_sha256'],image)
    uvm = s.read_json(check_dir/'uvm_result.json')
    s.require(uvm['log_sha256'] == s.digest(log) and uvm['vector_trace_sha256'] == s.digest(trace), 'UVM input identity')
    parsed = check_log(log.read_text(),256)
    s.require(all(checked.get(k) == v for k,v in parsed.items() if k != 'state'), 'Checker result/raw replay mismatch')
    return parsed


def run(args):
    s.require(1 <= args.timeout <= 10800,'Timeout must be 1..10800 seconds')
    for name in ('build','prerequisite','prerequisite_build','gate'):
        setattr(args,name,getattr(args,name).resolve(strict=True))
    out = args.output.resolve()
    s.require(not any(out.is_relative_to(p) for p in (args.build,args.prerequisite,args.prerequisite_build,args.gate)),
              'Use a separate fresh output directory')
    out.mkdir(parents=True,exist_ok=False)
    work = out/'work'
    work.mkdir()
    owner = Execution(out)
    owner.state.update(timeout_seconds=args.timeout,build=str(args.build),prerequisite=str(args.prerequisite))
    owner.save()
    try:
        report,pins,image,receipt = prepare_inputs(args)
        simv,elf = Path(report['simv']),Path(report['elf'])
        owner.state.update(simv=str(simv),elf=str(elf))
        s.atomic_json(out/'source-pins.json',pins)
        pin_receipt = s.digest(out/'source-pins.json')
        def identity():
            s.require(s.digest(out/'source-pins.json') == pin_receipt,'Worker source receipt changed')
            s.verify_pins(pins)
            s.require(s.hashes(s.image_files(simv)) == image,'Execution image inventory changed')
        def manifest(stage):
            owner.execute([sys.executable,'-B','-m','ara_verify.vcs_source_manifest','--output',
                simv.parent/'vcs_source_manifest.json','--check'],out/(stage+'.log'),300,stage.upper())
        identity()
        manifest('manifest-before')
        owner.execute(['bash',ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
            simv.parent,elf,'akv_v2'],out/'image-contract.log',180,'IMAGE_CONTRACT')
        identity()
        if args.preflight_only:
            result = dict(state='PREFLIGHT_PASS_NOT_RUN',prerequisite=receipt,elf_sha256=report['elf_sha256'])
        else:
            log,trace,commit = (work/n for n in ('run.vcs.log','vector_trace.csv','commit_trace.csv'))
            owner.execute([simv,'-no_save','-l',log,'+PRELOAD='+str(elf),'+TESTCASE=akv_context_kv256_threeway',
                '+NO_FSDB','+NO_INSTR_TRACE','+AKV_PERF','+AKV_SUMMARY','+VECTOR_TRACE='+str(trace),
                '+COMMIT_TRACE='+str(commit),'+ARA_CONTRACT_TRACE_LIMIT=2000000','+ARA_UVM_TRACE_LIMIT=2000000'],
                work/'console.log',args.timeout,'RUNNING')
            check_dir = out/'checking'
            owner.execute([sys.executable,'-B',HERE/'check_context.py','--build',args.build,'--log',log,
                '--vector-trace',trace,'--output',check_dir],out/'checker.log',600,'CHECKING')
            result = checked_output(check_dir,report,image,log,trace)
            manifest('manifest-after')
            identity()
            result.update(prerequisite=receipt,elf_sha256=report['elf_sha256'],simulator_exit_code=0,
                post_pins_match=True,source_pins_sha256=pin_receipt,
                evidence_sha256=s.hashes([log,trace,commit,work/'console.log',check_dir/'result.json',
                    check_dir/'uvm_result.json',check_dir/'pins.json',out/'source-pins.json',
                    out/'manifest-before.log',out/'manifest-after.log',out/'image-contract.log',out/'checker.log']))
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
    for name in ('build','output','prerequisite'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--prerequisite-build',type=Path,default=PRIOR_BUILD)
    p.add_argument('--gate',type=Path,default=IMAGE_GATE)
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
