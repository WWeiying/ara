#!/usr/bin/env python3
"""Bounded real quantized-KV Attention, gated by independently replayed QK batch."""
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
from run_batch_qk import prepare as prepare_batch
from check_batch_qk import check_log as batch_check
from check_attention import check_log


def checked_prerequisite(path):
    status, result = s.read_json(path/'status.json'), s.read_json(path/'result.json')
    s.require(status.get('state') == result.get('state') == 'PASS' and
              status.get('child_pid') is None and result.get('post_pins_match') is True and
              result.get('simulator_exit_code') == 0, 'Require checked terminal multioutput QK PASS')
    report, image, pins, keys, oracle, previous = prepare_batch(Path(status['build']), Path(status['prerequisite']))
    s.require(status['elf'] == report['elf'] and status['simv'] == report['simv'], 'Prerequisite ELF/image drift')
    s.require(s.digest(path/'source-pins.json') == result['source_pins_sha256'], 'Prerequisite receipt drift')
    run_pins = s.read_json(path/'source-pins.json')
    s.require(all(run_pins.get(p) == h for p, h in pins.items()), 'Prerequisite omitted inputs')
    s.merge_pins(run_pins, result['evidence_sha256'])
    s.verify_pins(run_pins)
    log, trace = path/'work/run.vcs.log', path/'work/vector_trace.csv'
    parsed = batch_check(log.read_text(), [p.read_bytes() for p in keys], oracle,
                         (ROOT/'hardware/src/vlsu/vlsu.sv').read_text(), previous)
    s.require(all(result.get(k) == v for k, v in parsed.items() if k != 'state'), 'Prerequisite raw replay differs')
    s.check_result(path/'work/uvm_result.json', report['elf_sha256'], image)
    uvm = s.read_json(path/'work/uvm_result.json')
    s.require(uvm['log_sha256'] == s.digest(log) and uvm['vector_trace_sha256'] == s.digest(trace),
              'Prerequisite protocol inputs mismatch')
    s.merge_pins(run_pins, s.hashes([path/'result.json', path/'status.json']))
    return image, run_pins


def run(args):
    s.require(1 <= args.timeout <= 10800, 'Timeout must be 1..10800 seconds')
    build, prior, out = args.build.resolve(strict=True), args.prerequisite.resolve(strict=True), args.output.resolve()
    s.require(not out.is_relative_to(build) and not out.is_relative_to(prior), 'Use fresh independent output')
    out.mkdir(parents=True, exist_ok=False)
    work = out/'work'
    work.mkdir()
    owner = Execution(out)
    owner.state.update(build=str(build), prerequisite=str(prior), timeout_seconds=args.timeout)
    owner.save()
    try:
        report = s.read_json(build/'build.json')
        s.require(report.get('state') == 'BUILT_NOT_EXECUTED' and report.get('execution') == 'NOT_RUN' and
                  report.get('post_pins_match') is True and report.get('heads') == 6 and
                  report.get('head_dim') == report.get('visible_tokens') == 128 and
                  report.get('expected_commands') == 16 and report.get('trials') == 4 and
                  report.get('kv_head') == 0 and report.get('outputs_per_trial') == 768 and
                  report.get('exact_scale_bits') == '3db504f3' and
                  report.get('kind') in ('q4_0', 'q8_0'), 'Wrong full Attention build')
        s.require(s.digest(build/'source-pins.json') == report['source_pins_sha256'], 'Build receipt drift')
        pins = s.read_json(build/'source-pins.json')
        s.merge_pins(pins, report['artifact_sha256'])
        simv, elf = Path(report['simv']), Path(report['elf'])
        s.require(pins.get(str(elf)) == report['elf_sha256'] == s.digest(elf), 'ELF drift')
        image, accepted = s.checked_image(ROOT/'verification/out/qbacc-soc-accept-20261023-02', simv)
        s.require(image == report['accepted_image_pins'], 'Image drift')
        s.merge_pins(pins, accepted)
        if not args.preflight_only:
            previous_image, previous_pins = checked_prerequisite(prior)
            s.require(image == previous_image, 'Prerequisite image differs')
            s.merge_pins(pins, previous_pins)
        files = [Path(__file__), HERE/'check_attention.py', HERE/'test_attention_check.py',
                 HERE/'test_attention_source.py', HERE/'run_batch_qk.py', HERE/'check_batch_qk.py',
                 HERE/'batch_spec.py', HERE/'run_rvv_qbs.py', HERE/'check_rvv_qbs.py',
                 ROOT/'verification/akv/paired_heads/contexts/run_context.py',
                 ROOT/'verification/akv/paired_heads/contexts/context_spec.py',
                 *s.script_files(), Path(sys.executable).resolve(), build/'build.json', build/'source-pins.json']
        s.merge_pins(pins, s.hashes(files))
        s.verify_pins(pins)
        owner.state.update(simv=str(simv), elf=str(elf), kind=report['kind'])
        s.atomic_json(out/'source-pins.json', pins)
        receipt = s.digest(out/'source-pins.json')

        def identity():
            s.require(s.digest(out/'source-pins.json') == receipt, 'Worker receipt drift')
            s.verify_pins(pins)
            s.require(s.hashes(s.image_files(simv)) == image, 'Image inventory drift')

        def manifest(stage):
            owner.execute([sys.executable, '-B', '-m', 'ara_verify.vcs_source_manifest', '--output',
                simv.parent/'vcs_source_manifest.json', '--check'], out/(stage+'.log'), 300, stage.upper())

        identity()
        manifest('manifest-before')
        owner.execute(['bash', ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh', simv.parent, elf],
                      out/'image-contract.log', 180, 'IMAGE_CONTRACT')
        identity()
        if args.preflight_only:
            result = dict(state='PREFLIGHT_PASS_NOT_RUN', prerequisite_accepted=False)
        else:
            log, trace = work/'run.vcs.log', work/'vector_trace.csv'
            owner.execute([simv, '-no_save', '-l', log, '+PRELOAD='+str(elf),
                '+TESTCASE=quant_kv_attention', '+NO_FSDB', '+NO_INSTR_TRACE', '+QBS_PERF',
                '+VECTOR_TRACE='+str(trace), '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000'],
                work/'console.log', args.timeout, 'RUNNING')
            data = ROOT/'verification/out/akv-quantkv-host-capture-20261024-01'/(
                'capture-k-'+report['kind']+'-v-q8_0')/'decode/block'
            result = check_log(log.read_text(), int(report['kind'] == 'q4_0'),
                              (data/'kqv_out-0.bin').read_bytes(), (ROOT/'hardware/src/vlsu/vlsu.sv').read_text())
            owner.execute([sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events',
                '--require-backend', '--require-axi', '--require-axi-write', '--vector-trace', trace,
                '--log', log, '--simv', simv, '--elf', elf, '--output', work/'uvm_result.json'],
                work/'checker.log', 600, 'CHECKING')
            s.check_result(work/'uvm_result.json', report['elf_sha256'], image)
            uvm = s.read_json(work/'uvm_result.json')
            s.require(uvm['log_sha256'] == s.digest(log) and uvm['vector_trace_sha256'] == s.digest(trace),
                      'Protocol checker input mismatch')
            manifest('manifest-after')
            identity()
            result.update(state='PASS', simulator_exit_code=0, post_pins_match=True,
                independent_protocol_checked=True, elf_sha256=report['elf_sha256'],
                source_pins_sha256=receipt, evidence_sha256=s.hashes([log, trace, work/'uvm_result.json',
                    out/'source-pins.json', out/'manifest-before.log', out/'manifest-after.log', out/'image-contract.log']))
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
    for name in ('build', 'prerequisite', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
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
