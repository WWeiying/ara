#!/usr/bin/env python3
"""Public-entry paired VCS inquiry only after independently replayed benefit."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
import signal
import subprocess
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/akv/paired_heads'))
sys.path.insert(0,str(ROOT/'verification/akv/paired_heads/contexts'))
import attention_run as s
from run_context import Execution
from audit_attention import checked_attention
from check_common_attention import check_log


def checked_build(build):
    report=s.read_json(build/'build.json')
    s.require(report.get('state')=='COMMON_ENTRY_BUILT_NOT_EXECUTED' and
        report.get('execution')=='NOT_RUN' and report.get('post_pins_match') is True and
        report.get('common_entry') is True and report.get('mapping_timed') is True and
        report.get('admission_timed') is True and report.get('heads')==6 and
        report.get('head_dim')==report.get('visible_tokens')==128 and
        report.get('expected_commands')==16 and report.get('trials')==4 and
        report.get('outputs_per_trial')==768 and report.get('kv_head')==0 and
        report.get('exact_scale_bits')=='3db504f3' and report.get('kind') in ('q8_0','q4_0'),
        'Wrong public-entry build')
    s.require(s.digest(build/'source-pins.json')==report['source_pins_sha256'],'Build receipt drift')
    pins=s.read_json(build/'source-pins.json'); s.merge_pins(pins,report['artifact_sha256'])
    s.require(pins.get(report['elf'])==report['elf_sha256']==s.digest(Path(report['elf'])),'ELF drift')
    s.merge_pins(pins,s.hashes([build/'build.json',build/'source-pins.json']))
    s.verify_pins(pins)
    return report,pins


def run(args):
    s.require(1<=args.timeout<=10800,'Bound must be 1..10800 seconds')
    build,prior,out=args.build.resolve(strict=True),args.prerequisite.resolve(strict=True),args.output.resolve()
    s.require(not out.is_relative_to(build) and not out.is_relative_to(prior),'Use separate outputs')
    out.mkdir(parents=True,exist_ok=False); work=out/'work'; work.mkdir()
    owner=Execution(out); owner.state.update(build=str(build),prerequisite=str(prior)); owner.save()
    try:
        report,pins=checked_build(build)
        old,image,previous,parsed=checked_attention(prior)
        s.require(report['kind']==old['kind'] and report['accepted_image_pins']==image and
            Path(report['original_build'])==Path(s.read_json(prior/'status.json')['build']),
            'Public entry must match the accepted original inquiry')
        s.merge_pins(pins,previous)
        own=[Path(__file__),HERE/'audit_attention.py',HERE/'check_common_attention.py',
            HERE/'test_common_attention.py',HERE/'test_common_attention_run.py',
            ROOT/'verification/akv/paired_heads/contexts/run_context.py',
            ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',*s.script_files(),
            Path(sys.executable).resolve()]
        s.merge_pins(pins,s.hashes(own)); s.verify_pins(pins)
        s.atomic_json(out/'source-pins.json',pins); receipt=s.digest(out/'source-pins.json')
        owner.state.update(elf=report['elf'],simv=report['simv'],kind=report['kind'])
        s.atomic_json(out/'prerequisite-audit.json',dict(state='INDEPENDENTLY_REPLAYED',
            prerequisite=str(prior),speedup=parsed['speedup'],sums=parsed['sums'],
            result_sha256=s.digest(prior/'result.json')))
        if parsed['speedup']<=1.0:
            result=dict(state='NO_BENEFIT_NOT_RUN',prior_functionally_passed=True,
                prior_speedup=parsed['speedup'],execution='NOT_RUN')
        else:
            simv,elf=Path(report['simv']),Path(report['elf'])
            def identity():
                s.require(s.digest(out/'source-pins.json')==receipt,'Worker receipt drift')
                s.verify_pins(pins)
                s.require(s.hashes(s.image_files(simv))==image,'Image inventory drift')
            def manifest(stage):
                owner.execute([sys.executable,'-B','-m','ara_verify.vcs_source_manifest','--output',
                    simv.parent/'vcs_source_manifest.json','--check'],out/(stage+'.log'),300,stage.upper())
            identity(); manifest('manifest-before')
            owner.execute(['bash',ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',simv.parent,elf],
                out/'image-contract.log',180,'IMAGE_CONTRACT')
            identity()
            log,trace=work/'run.vcs.log',work/'vector_trace.csv'
            owner.execute([simv,'-no_save','-l',log,'+PRELOAD='+str(elf),'+TESTCASE=quant_common_attention',
                '+NO_FSDB','+NO_INSTR_TRACE','+QBS_PERF','+VECTOR_TRACE='+str(trace),
                '+ARA_CONTRACT_TRACE_LIMIT=2000000','+ARA_UVM_TRACE_LIMIT=2000000'],
                work/'console.log',args.timeout,'RUNNING')
            data=ROOT/'verification/out/akv-quantkv-host-capture-20261024-01'/(
                'capture-k-'+report['kind']+'-v-q8_0')/'decode/block'
            result=check_log(log.read_text(),int(report['kind']=='q4_0'),
                (data/'kqv_out-0.bin').read_bytes(),(ROOT/'hardware/src/vlsu/vlsu.sv').read_text())
            owner.execute([sys.executable,'-B','-m','ara_verify.uvm_dut','--require-events','--require-backend',
                '--require-axi','--require-axi-write','--vector-trace',trace,'--log',log,'--simv',simv,
                '--elf',elf,'--output',work/'uvm_result.json'],work/'checker.log',600,'CHECKING')
            s.check_result(work/'uvm_result.json',report['elf_sha256'],image)
            uvm=s.read_json(work/'uvm_result.json')
            s.require(uvm['log_sha256']==s.digest(log) and uvm['vector_trace_sha256']==s.digest(trace),
                      'Protocol input mismatch')
            manifest('manifest-after'); identity()
            result.update(state='PASS',simulator_exit_code=0,post_pins_match=True,
                independent_protocol_checked=True,elf_sha256=report['elf_sha256'],source_pins_sha256=receipt,
                evidence_sha256=s.hashes([log,trace,work/'uvm_result.json',out/'source-pins.json',
                    out/'prerequisite-audit.json',out/'manifest-before.log',out/'manifest-after.log',
                    out/'image-contract.log']))
        s.atomic_json(out/'result.json',result); owner.state['state']=result['state']
    except BaseException as exc:
        state='TIMEOUT' if isinstance(exc,subprocess.TimeoutExpired) else 'INTERRUPTED' if isinstance(exc,InterruptedError) else 'FAIL'
        owner.state.update(state=state,error=repr(exc))
        s.atomic_json(out/'result.json',dict(state=state,error=repr(exc))); raise
    finally:
        owner.state.update(child_pid=None,finished=datetime.now(timezone.utc).isoformat()); owner.save()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('build','prerequisite','output'): parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--timeout',type=int,default=10800)
    args=parser.parse_args()
    def interrupted(signum,_frame): raise InterruptedError(f'Signal {signum}')
    for sig in (signal.SIGTERM,signal.SIGINT): signal.signal(sig,interrupted)
    run(args)


if __name__=='__main__': main()
