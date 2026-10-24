#!/usr/bin/env python3
"""Direct-owned, bounded numerical inquiry on a sealed accepted VCS image."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import shutil
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/akv/paired_heads/contexts'))
from run_context import Execution
import attention_run as s
from check_rvv_qbs import HostOracle, check_transcript, check_work


def prepare(build):
    report = s.read_json(build/'build.json')
    s.require(report.get('state') == 'BUILT_NOT_EXECUTED' and
              report.get('execution') == 'NOT_RUN' and report.get('post_pins_match') is True and
              report.get('profiles') == ['q8_0','q4_0'] and report.get('heads') == [0,1] and
              report.get('query_heads') == [0,6] and report.get('tokens') == [0,63,64,127] and
              report.get('expected_commands') == 16 and report.get('query_exports') == 4 and
              report.get('query_bytes_per_export') == 136, 'Wrong numerical inquiry build')
    s.require(s.digest(build/'source-pins.json') == report['source_pins_sha256'], 'Build receipt drift')
    pins = s.read_json(build/'source-pins.json')
    s.merge_pins(pins,report['artifact_sha256'])
    s.require(pins.get(report['elf']) == report['elf_sha256'] == s.digest(Path(report['elf'])), 'ELF drift')
    s.verify_pins(pins)
    image,accepted = s.checked_image(ROOT/'verification/out/qbacc-soc-accept-20261023-02',Path(report['simv']))
    s.require(image == report['accepted_image_pins'], 'Accepted image mismatch')
    s.merge_pins(pins,accepted)
    # The original capture paths are already pinned by the sealed build.
    keys = []
    for kind in ('q8_0','q4_0'):
        candidates = [Path(p) for p in pins if
            p.endswith('/capture-k-'+kind+'-v-q8_0/decode/block/attn_k_input-0.bin')]
        s.require(len(candidates) == 1, 'Ambiguous/unpinned real K source')
        keys.append(candidates[0])
    # Preserve argv[0]: a gcc-named ccache symlink must not be invoked as ccache.
    cc = Path(shutil.which('gcc')).absolute()
    s.require(cc.is_file(), 'Missing host C compiler')
    files = [build/'build.json',build/'source-pins.json',Path(__file__),HERE/'check_rvv_qbs.py',
        HERE/'host_score.c',HERE/'test_rvv_qbs_check.py',HERE/'test_rvv_qbs_run.py',
        ROOT/'verification/qbs/qbs_ref.c',ROOT/'verification/qbs/qbs_ref.h',ROOT/'apps/common/qbs_abi.h',
        ROOT/'hardware/src/vlsu/vlsu.sv',ROOT/'hardware/src/vlsu/qbs/qbs_engine.sv',
        ROOT/'hardware/src/vlsu/qbs/qbs_compute_engine.sv',
        ROOT/'hardware/src/vlsu/qbs/qbs_profile_engine_int.sv',
        ROOT/'verification/akv/paired_heads/contexts/run_context.py',
        ROOT/'verification/akv/paired_heads/contexts/check_context.py',
        ROOT/'verification/akv/paired_heads/contexts/context_spec.py',
        ROOT/'verification/akv/paired_heads/attention_run.py',
        ROOT/'verification/akv/run_qk_panel4_abba.py',ROOT/'verification/akv/run_refill_overlap_probe.py',
        ROOT/'verification/qbs/run_tile_context_engine.py',*s.script_files(),cc,cc.resolve(),
        Path('/usr/bin/gcc').resolve(strict=True),Path(sys.executable).resolve(),
        ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh']
    s.merge_pins(pins,s.hashes(files))
    s.verify_pins(pins)
    return report,image,pins,keys,cc


def run(args):
    s.require(1 <= args.timeout <= 10800, 'Timeout must be 1..10800 seconds')
    build,out = args.build.resolve(strict=True),args.output.resolve()
    s.require(not out.is_relative_to(build), 'Output must be outside sealed build')
    out.mkdir(parents=True,exist_ok=False)
    work = out/'work'
    work.mkdir()
    owner = Execution(out)
    owner.state.update(build=str(build),timeout_seconds=args.timeout)
    owner.save()
    try:
        report,image,pins,keys,cc = prepare(build)
        simv,elf = Path(report['simv']),Path(report['elf'])
        owner.state.update(simv=str(simv),elf=str(elf))
        library = out/'host_score.so'
        owner.execute([cc,'-std=gnu11','-O2','-shared','-fPIC','-fno-fast-math',
            '-ffp-contract=off','-frounding-math','-I'+str(ROOT),HERE/'host_score.c',
            ROOT/'verification/qbs/qbs_ref.c','-lm','-o',library],out/'host-build.log',120,'HOST_BUILD')
        oracle = HostOracle(library)
        s.merge_pins(pins,s.hashes([library]))
        s.atomic_json(out/'source-pins.json',pins)
        receipt = s.digest(out/'source-pins.json')
        def identity():
            s.require(s.digest(out/'source-pins.json') == receipt, 'Worker pins receipt drift')
            s.verify_pins(pins)
            s.require(s.hashes(s.image_files(simv)) == image, 'Image inventory drift')
        def manifest(stage):
            owner.execute([sys.executable,'-B','-m','ara_verify.vcs_source_manifest','--output',
                simv.parent/'vcs_source_manifest.json','--check'],out/(stage+'.log'),300,stage.upper())
        identity()
        manifest('manifest-before')
        owner.execute(['bash',ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
            simv.parent,elf],out/'image-contract.log',180,'IMAGE_CONTRACT')
        identity()
        if args.preflight_only:
            result = dict(state='PREFLIGHT_PASS_NOT_RUN',elf_sha256=report['elf_sha256'])
        else:
            log,trace = work/'run.vcs.log',work/'vector_trace.csv'
            owner.execute([simv,'-no_save','-l',log,'+PRELOAD='+str(elf),'+TESTCASE=quant_kv_rvv_qbs',
                '+NO_FSDB','+NO_INSTR_TRACE','+QBS_PERF','+VECTOR_TRACE='+str(trace),
                '+ARA_CONTRACT_TRACE_LIMIT=2000000','+ARA_UVM_TRACE_LIMIT=2000000'],
                work/'console.log',args.timeout,'RUNNING')
            text = log.read_text()
            result = check_transcript(text,[p.read_bytes() for p in keys],oracle)
            result['hardware_work'] = check_work(text,(ROOT/'hardware/src/vlsu/vlsu.sv').read_text())
            owner.execute([sys.executable,'-B','-m','ara_verify.uvm_dut','--require-events',
                '--require-backend','--require-axi','--require-axi-write','--vector-trace',trace,
                '--log',log,'--simv',simv,'--elf',elf,'--output',work/'uvm_result.json'],
                work/'checker.log',600,'CHECKING')
            s.check_result(work/'uvm_result.json',report['elf_sha256'],image)
            uvm = s.read_json(work/'uvm_result.json')
            s.require(uvm['log_sha256'] == s.digest(log) and
                      uvm['vector_trace_sha256'] == s.digest(trace), 'UVM input identity')
            manifest('manifest-after')
            identity()
            result.update(state='PASS',simulator_exit_code=0,post_pins_match=True,
                elf_sha256=report['elf_sha256'],source_pins_sha256=receipt,
                evidence_sha256=s.hashes([log,trace,work/'uvm_result.json',library,
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
    a = p.parse_args()
    def interrupted(signum,_frame):
        raise InterruptedError(f'Signal {signum}')
    for sig in (signal.SIGTERM,signal.SIGINT):
        signal.signal(sig,interrupted)
    run(a)


if __name__ == '__main__':
    main()
