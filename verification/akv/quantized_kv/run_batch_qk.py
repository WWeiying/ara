#!/usr/bin/env python3
"""Bounded all-head QK worker, gated by the independently rechecked M1 inquiry."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
from run_rvv_qbs import s, ROOT, Execution, prepare as prior_prepare, HostOracle, check_transcript, check_work
from check_batch_qk import check_log
from batch_spec import expected

HERE = Path(__file__).resolve().parent
PRIOR_BUILD = ROOT/'verification/out/akv-quantkv-rvv-qbs-build-20261024-01'
PRIOR_RUN = ROOT/'verification/out/akv-quantkv-rvv-qbs-20261024-01'


def checked_prerequisite(path):
    report,image,pins,keys,_ = prior_prepare(PRIOR_BUILD)
    result,status = s.read_json(path/'result.json'),s.read_json(path/'status.json')
    s.require(result.get('state') == status.get('state') == 'PASS' and status['child_pid'] is None and
              result['post_pins_match'] is True and result['simulator_exit_code'] == 0,
              'Require actual terminal M1 inquiry PASS')
    s.require(s.digest(path/'source-pins.json') == result['source_pins_sha256'],'Prior pins receipt drift')
    s.merge_pins(pins,s.read_json(path/'source-pins.json'))
    s.merge_pins(pins,result['evidence_sha256'])
    s.verify_pins(pins)
    log,trace = path/'work/run.vcs.log',path/'work/vector_trace.csv'
    oracle_path = path/'host_score.so'
    s.require(all(str(p) in result['evidence_sha256'] for p in
                  (log,trace,oracle_path,path/'work/uvm_result.json')),'Missing original M1 evidence')
    oracle = HostOracle(oracle_path)
    text = log.read_text()
    parsed = check_transcript(text,[p.read_bytes() for p in keys],oracle)
    s.require(all(result.get(k) == v for k,v in parsed.items() if k != 'state'),'Prior raw numerical mismatch')
    s.require(result['hardware_work'] == check_work(text,(ROOT/'hardware/src/vlsu/vlsu.sv').read_text()),
              'Prior actual work mismatch')
    s.check_result(path/'work/uvm_result.json',report['elf_sha256'],image)
    uvm = s.read_json(path/'work/uvm_result.json')
    s.require(uvm['log_sha256'] == s.digest(log) and uvm['vector_trace_sha256'] == s.digest(trace),
              'Prior UVM input identity')
    previous_queries = {(q['kind'],q['head']*6):bytes.fromhex(q['hex']) for q in parsed['queries']}
    s.merge_pins(pins,s.hashes([path/'result.json',path/'status.json',path/'source-pins.json']))
    return image,pins,keys,oracle,previous_queries


def prepare(build,prerequisite):
    report = s.read_json(build/'build.json')
    s.require(report.get('state') == 'BUILT_NOT_EXECUTED' and report.get('execution') == 'NOT_RUN' and
        report.get('post_pins_match') is True and report.get('profiles') == ['q8_0','q4_0'] and
        report.get('query_heads') == list(range(12)) and report.get('kv_heads') == 2 and
        report.get('visible') == 128 and report.get('capacity') == 256 and
        report.get('expected_commands') == 40 and report.get('expected_outputs') == 3336 and
        report.get('query_exports') == 24,'Wrong all-head batch build')
    s.require(s.digest(build/'source-pins.json') == report['source_pins_sha256'],'Batch build receipt drift')
    pins = s.read_json(build/'source-pins.json')
    s.merge_pins(pins,report['artifact_sha256'])
    s.require(pins.get(report['elf']) == report['elf_sha256'] == s.digest(Path(report['elf'])),'ELF drift')
    s.verify_pins(pins)
    image,prior,keys,oracle,previous_queries = checked_prerequisite(prerequisite)
    s.require(image == report['accepted_image_pins'],'Prior/batch accepted image mismatch')
    s.merge_pins(pins,prior)
    files = [Path(__file__),HERE/'check_batch_qk.py',HERE/'batch_spec.py',HERE/'test_batch_spec.py',
        HERE/'test_batch_check.py',HERE/'test_batch_run.py',HERE/'run_rvv_qbs.py',
        HERE/'check_rvv_qbs.py',ROOT/'verification/akv/paired_heads/contexts/run_context.py',
        ROOT/'verification/akv/paired_heads/contexts/check_context.py',
        ROOT/'verification/akv/paired_heads/contexts/context_spec.py',
        *s.script_files(),Path(sys.executable).resolve()]
    s.merge_pins(pins,s.hashes(files))
    s.verify_pins(pins)
    return report,image,pins,keys,oracle,previous_queries


def run(args):
    s.require(1 <= args.timeout <= 10800,'Timeout must be 1..10800 seconds')
    build,prior,out = args.build.resolve(strict=True),args.prerequisite.resolve(strict=True),args.output.resolve()
    s.require(not out.is_relative_to(build) and not out.is_relative_to(prior),'Use a fresh independent output')
    out.mkdir(parents=True,exist_ok=False)
    work = out/'work'
    work.mkdir()
    owner = Execution(out)
    owner.state.update(build=str(build),prerequisite=str(prior),timeout_seconds=args.timeout)
    owner.save()
    try:
        report,image,pins,keys,oracle,previous_queries = prepare(build,prior)
        simv,elf = Path(report['simv']),Path(report['elf'])
        owner.state.update(simv=str(simv),elf=str(elf))
        s.atomic_json(out/'source-pins.json',pins)
        receipt = s.digest(out/'source-pins.json')
        def identity():
            s.require(s.digest(out/'source-pins.json') == receipt,'Worker pins receipt drift')
            s.verify_pins(pins)
            s.require(s.hashes(s.image_files(simv)) == image,'Image inventory drift')
        def manifest(stage):
            owner.execute([sys.executable,'-B','-m','ara_verify.vcs_source_manifest','--output',
                simv.parent/'vcs_source_manifest.json','--check'],out/(stage+'.log'),300,stage.upper())
        identity()
        manifest('manifest-before')
        owner.execute(['bash',ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
            simv.parent,elf],out/'image-contract.log',180,'IMAGE_CONTRACT')
        identity()
        if args.preflight_only:
            result = dict(state='PREFLIGHT_PASS_NOT_RUN',expected=expected(),elf_sha256=report['elf_sha256'])
        else:
            log,trace = work/'run.vcs.log',work/'vector_trace.csv'
            owner.execute([simv,'-no_save','-l',log,'+PRELOAD='+str(elf),'+TESTCASE=quant_kv_batch_qk',
                '+NO_FSDB','+NO_INSTR_TRACE','+QBS_PERF','+VECTOR_TRACE='+str(trace),
                '+ARA_CONTRACT_TRACE_LIMIT=2000000','+ARA_UVM_TRACE_LIMIT=2000000'],
                work/'console.log',args.timeout,'RUNNING')
            result = check_log(log.read_text(),[p.read_bytes() for p in keys],oracle,
                               (ROOT/'hardware/src/vlsu/vlsu.sv').read_text(),previous_queries)
            owner.execute([sys.executable,'-B','-m','ara_verify.uvm_dut','--require-events',
                '--require-backend','--require-axi','--require-axi-write','--vector-trace',trace,
                '--log',log,'--simv',simv,'--elf',elf,'--output',work/'uvm_result.json'],
                work/'checker.log',600,'CHECKING')
            s.check_result(work/'uvm_result.json',report['elf_sha256'],image)
            uvm = s.read_json(work/'uvm_result.json')
            s.require(uvm['log_sha256'] == s.digest(log) and
                      uvm['vector_trace_sha256'] == s.digest(trace),'UVM input identity')
            manifest('manifest-after')
            identity()
            result.update(state='PASS',simulator_exit_code=0,post_pins_match=True,
                elf_sha256=report['elf_sha256'],source_pins_sha256=receipt,
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
    p.add_argument('--build',type=Path,required=True)
    p.add_argument('--prerequisite',type=Path,default=PRIOR_RUN)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--timeout',type=int,default=10800)
    p.add_argument('--preflight-only',action='store_true')
    a = p.parse_args()
    def interrupted(signum,_frame):
        raise InterruptedError(f'Signal {signum}')
    for sig in (signal.SIGTERM,signal.SIGINT):
        signal.signal(sig,interrupted)
    run(a)


if __name__ == '__main__':
    main()
