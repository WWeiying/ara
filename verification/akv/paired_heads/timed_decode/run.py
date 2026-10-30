#!/usr/bin/env python3
"""Direct-owned, bounded timed Decode on explicit baseline or unified images."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
from timed_spec import HERE, ROOT, IMAGE_GATE, s, original_run, own_files
sys.path.insert(0, str(HERE))
from build import checked_build
from timed_check import check_log

sys.path.insert(0, str(ROOT/'verification/akv/shared_reader_integration'))
from run_handoff import checked_soc

Execution = original_run.Execution
STORAGE = 'shared_reader_unified_q2_kv32_v1'


def select_image(args, report, baseline_image):
    if args.variant == 'baseline':
        s.require(args.soc_build is None, 'Baseline cannot override its accepted image')
        simv = Path(report['simv'])
        image, pins = s.checked_image(IMAGE_GATE, simv)
        s.require(image == baseline_image, 'Baseline accepted image mismatch')
        return simv, image, pins, dict(variant='baseline', accepted_gate=str(IMAGE_GATE))
    s.require(args.variant == 'unified' and args.soc_build is not None, 'Unified requires checked SoC build')
    directory = args.soc_build.resolve(strict=True)
    soc, snapshot, pins, image = checked_soc(directory)
    s.require(snapshot.get('storage_variant') == STORAGE, 'Not the unified storage snapshot')
    return Path(soc['simv']), image, pins, dict(variant='unified', soc_build=str(directory),
        snapshot_sha256=soc['snapshot_sha256'], storage_variant=snapshot['storage_variant'])


def run(args):
    s.require(type(args.timeout) is int and 1 <= args.timeout <= 10800, 'Timeout must be 1..10800 seconds')
    build, out = args.build.resolve(strict=True), args.output.resolve()
    s.require(not out.is_relative_to(build) and (args.soc_build is None or
              not out.is_relative_to(args.soc_build.resolve())), 'Independent fresh output required')
    out.mkdir(parents=True, exist_ok=False)
    work = out/'work'
    work.mkdir()
    owner = Execution(out)
    owner.state.update(kind='timed_decode', variant=args.variant, build=str(build), timeout_seconds=args.timeout)
    owner.save()
    try:
        report, baseline_image, pins = checked_build(build)
        simv, image, extra, image_receipt = select_image(args, report, baseline_image)
        s.merge_pins(pins, extra)
        s.merge_pins(pins, s.hashes(own_files()))
        elf = Path(report['elf'])
        owner.state.update(simv=str(simv), elf=str(elf), image_identity=image_receipt)
        owner.save()
        s.atomic_json(out/'source-pins.json', pins)
        receipt = s.digest(out/'source-pins.json')

        def identity():
            s.require(s.digest(out/'source-pins.json') == receipt, 'Worker receipt drift')
            s.verify_pins(pins)
            s.require(s.hashes(s.image_files(simv)) == image, 'Image inventory drift')

        def manifest(stage):
            owner.execute([sys.executable, '-B', '-m', 'ara_verify.vcs_source_manifest', '--output',
                           simv.parent/'vcs_source_manifest.json', '--check'],
                          out/(stage+'.log'), 300, stage.upper())

        identity()
        manifest('manifest-before')
        owner.execute(['bash', ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
                       simv.parent, elf, 'akv_v2'], out/'image-contract.log', 180, 'IMAGE_CONTRACT')
        identity()
        if args.preflight_only:
            manifest('manifest-after')
            identity()
            result = dict(state='PREFLIGHT_PASS_NOT_RUN', elf_sha256=report['elf_sha256'],
                          image_identity=image_receipt, post_pins_match=True, source_pins_sha256=receipt)
        else:
            log, trace, protocol = (work/name for name in ('run.vcs.log', 'vector_trace.csv', 'uvm_result.json'))
            owner.execute([simv, '-no_save', '-l', log, '+PRELOAD='+str(elf),
                           '+TESTCASE=akv_timed_decode_'+args.variant, '+NO_FSDB', '+NO_INSTR_TRACE',
                           '+AKV_PERF', '+AKV_SUMMARY', '+VECTOR_TRACE='+str(trace),
                           '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000'],
                          work/'console.log', args.timeout, 'RUNNING')
            result = check_log(log.read_text())
            owner.execute([sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events',
                           '--require-backend', '--require-axi', '--require-axi-write',
                           '--vector-trace', trace, '--log', log, '--simv', simv, '--elf', elf,
                           '--output', protocol], work/'checker.log', 600, 'CHECKING')
            s.check_result(protocol, report['elf_sha256'], image)
            proof = s.read_json(protocol)
            s.require(proof['log_sha256'] == s.digest(log) and
                      proof['vector_trace_sha256'] == s.digest(trace), 'Protocol input drift')
            manifest('manifest-after')
            identity()
            result.update(kind='timed_decode', image_identity=image_receipt, simulator_exit_code=0,
                          post_pins_match=True, independent_protocol_checked=True,
                          elf_sha256=report['elf_sha256'], source_pins_sha256=receipt,
                          model_execution=False, production_promoted=False,
                          complete_operator_performance_accepted=False,
                          evidence_sha256=s.hashes([log, trace, protocol, out/'source-pins.json',
                              out/'manifest-before.log', out/'manifest-after.log', out/'image-contract.log',
                              work/'console.command.json', work/'checker.command.json']))
        s.atomic_json(out/'result.json', result)
        owner.state['state'] = result['state']
        return result
    except BaseException as exc:
        state = 'TIMEOUT' if isinstance(exc, subprocess.TimeoutExpired) else 'INTERRUPTED' if isinstance(exc, InterruptedError) else 'FAIL'
        owner.state.update(state=state, error=repr(exc))
        s.atomic_json(out/'result.json', dict(state=state, error=repr(exc)))
        raise
    finally:
        owner.state.update(child_pid=None, finished=datetime.now(timezone.utc).isoformat())
        owner.save()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--variant', choices=('baseline', 'unified'), required=True)
    parser.add_argument('--soc-build', type=Path)
    parser.add_argument('--timeout', type=int, default=10800)
    parser.add_argument('--preflight-only', action='store_true')
    def interrupted(signum, _frame):
        raise InterruptedError(f'Signal {signum}')
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    run(parser.parse_args())
