#!/usr/bin/env python3
"""Direct-owned original-vs-RVV V decode, native numeric and protocol acceptance."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT/'verification/akv/paired_heads'))
sys.path.insert(0, str(ROOT/'verification/akv/paired_heads/contexts'))
import attention_run as s
from run_context import Execution
from check_value_decode import check_log


def checked_build(build):
    report = s.read_json(build/'build.json')
    s.require(report.get('state') == 'BUILT_NOT_EXECUTED' and report.get('execution') == 'NOT_RUN' and
              report.get('post_pins_match') is True and report.get('trials') == 8 and
              report.get('profiles') == ['q8_0', 'q4_0'] and report.get('elements_per_trial') == 32768 and
              report.get('boundary_elements') == 3584, 'Wrong V-decode build')
    s.require(s.digest(build/'source-pins.json') == report['source_pins_sha256'], 'Build receipt drift')
    pins = s.read_json(build/'source-pins.json')
    s.merge_pins(pins, report['artifact_sha256'])
    s.require(pins.get(report['elf']) == report['elf_sha256'] == s.digest(Path(report['elf'])), 'ELF drift')
    image, accepted = s.checked_image(ROOT/'verification/out/qbacc-soc-accept-20261023-02', Path(report['simv']))
    s.require(image == report['accepted_image_pins'], 'Accepted image differs')
    s.merge_pins(pins, accepted)
    s.merge_pins(pins, s.hashes([build/'build.json', build/'source-pins.json']))
    for path in report['value_paths']:
        s.require(pins.get(path) == s.digest(Path(path)), 'Actual V capture not pinned')
    s.verify_pins(pins)
    return report, image, pins


def run(args):
    s.require(1 <= args.timeout <= 10800, 'Timeout must be 1..10800 seconds')
    build, out = args.build.resolve(strict=True), args.output.resolve()
    s.require(not out.is_relative_to(build), 'Use separate fresh output')
    out.mkdir(parents=True, exist_ok=False)
    work = out/'work'
    work.mkdir()
    owner = Execution(out)
    owner.state.update(build=str(build), timeout_seconds=args.timeout)
    owner.save()
    try:
        report, image, pins = checked_build(build)
        simv, elf = Path(report['simv']), Path(report['elf'])
        files = [Path(__file__), HERE/'check_value_decode.py', HERE/'test_value_decode_check.py',
                 HERE/'test_value_decode_run.py', ROOT/'verification/akv/paired_heads/contexts/run_context.py',
                 ROOT/'verification/akv/paired_heads/contexts/context_spec.py',
                 ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
                 *s.script_files(), Path(sys.executable).resolve()]
        s.merge_pins(pins, s.hashes(files))
        s.verify_pins(pins)
        owner.state.update(simv=str(simv), elf=str(elf))
        s.atomic_json(out/'source-pins.json', pins)
        receipt = s.digest(out/'source-pins.json')

        def identity():
            s.require(s.digest(out/'source-pins.json') == receipt, 'Worker receipt drift')
            s.verify_pins(pins)
            s.require(s.hashes(s.image_files(simv)) == image, 'Execution image drift')

        def manifest(stage):
            owner.execute([sys.executable, '-B', '-m', 'ara_verify.vcs_source_manifest', '--output',
                simv.parent/'vcs_source_manifest.json', '--check'], out/(stage+'.log'), 300, stage.upper())

        identity()
        manifest('manifest-before')
        owner.execute(['bash', ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh', simv.parent, elf],
                      out/'image-contract.log', 180, 'IMAGE_CONTRACT')
        identity()
        if args.preflight_only:
            result = dict(state='PREFLIGHT_PASS_NOT_RUN', elf_sha256=report['elf_sha256'])
        else:
            log, trace = work/'run.vcs.log', work/'vector_trace.csv'
            owner.execute([simv, '-no_save', '-l', log, '+PRELOAD='+str(elf), '+TESTCASE=quant_value_decode',
                '+NO_FSDB', '+NO_INSTR_TRACE', '+VECTOR_TRACE='+str(trace),
                '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000'],
                work/'console.log', args.timeout, 'RUNNING')
            result = check_log(log.read_text(), [Path(p).read_bytes() for p in report['value_paths']])
            owner.execute([sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events',
                '--require-backend', '--require-axi', '--require-axi-write', '--vector-trace', trace,
                '--log', log, '--simv', simv, '--elf', elf, '--output', work/'uvm_result.json'],
                work/'checker.log', 600, 'CHECKING')
            s.check_result(work/'uvm_result.json', report['elf_sha256'], image)
            uvm = s.read_json(work/'uvm_result.json')
            s.require(uvm['log_sha256'] == s.digest(log) and uvm['vector_trace_sha256'] == s.digest(trace),
                      'Independent protocol inputs mismatch')
            manifest('manifest-after')
            identity()
            result.update(state='PASS', simulator_exit_code=0, post_pins_match=True,
                elf_sha256=report['elf_sha256'], source_pins_sha256=receipt,
                independent_protocol_checked=True, evidence_sha256=s.hashes([log, trace,
                    work/'uvm_result.json', out/'source-pins.json', out/'manifest-before.log',
                    out/'manifest-after.log', out/'image-contract.log']))
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=10800)
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()
    def interrupted(signum, _frame):
        raise InterruptedError(f'Signal {signum}')
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    run(args)


if __name__ == '__main__':
    main()
