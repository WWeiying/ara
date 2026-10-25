#!/usr/bin/env python3
"""Successor H/S/B runner: terminal strided PLUS all four independently checked tail splits."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from verification.akv.quantized_kv.tail_split.scope import HERE, PARENT, ROOT
sys.path.insert(0, str(PARENT))
from run_threeway_attention import checked_build, terminal_inputs
from run_strided_attention import s, Execution, checked_build as checked_strided_build
from check_strided_attention import check_log as check_strided
from check_threeway_attention import check_log
from verification.akv.quantized_kv.tail_split.combine import checked_combined, checked_run, validate_matrix


def checked_tails(directory, target, pins):
    combined = checked_combined(directory)
    inherited = s.read_json(directory / 'source-pins.json')
    records = []
    for name in combined['runs']:
        run = Path(name).resolve(strict=True)
        saved, build, extra = checked_run(run)
        s.require(build['accepted_image_pins'] == target['accepted_image_pins'],
                  'Tail/threeway image differs')
        s.require(inherited.get(str(run / 'result.json')) == s.digest(run / 'result.json') and
                  all(inherited.get(path) == sha for path, sha in extra.items()),
                  'Combined receipt omitted a raw-rechecked split input')
        records.append(saved)
    validate_matrix(records)
    s.require(target['kind'] in ('q4_0', 'q8_0'), 'Unknown target profile')
    s.merge_pins(pins, inherited)
    s.merge_pins(pins, s.hashes([directory / 'result.json', directory / 'source-pins.json']))
    s.verify_pins(pins)
    return dict(run=str(directory), state='ALL_FOUR_RAW_RECHECKED', tail=True,
                acceptance='TAIL_SPLIT_COMBINED_PASS', split_runs=4, commands=24,
                result_sha256=s.digest(directory / 'result.json'))


def prerequisites(strided, tail, report, pins):
    old, inherited, saved, text, _extra = terminal_inputs(
        strided, checked_strided_build, PARENT / 'run_strided_attention.py')
    s.require(old['kind'] == report['kind'] and
              old['accepted_image_pins'] == report['accepted_image_pins'],
              'Strided prerequisite profile/image differs')
    s.require(Path(report['predecessor_strided_build']) ==
              Path(s.read_json(strided / 'status.json')['build']),
              'Three-way build is not derived from this strided comparison')
    capture = ROOT / 'verification/out/akv-quantkv-host-capture-20261024-01' / (
        'capture-k-' + report['kind'] + '-v-q8_0') / 'decode/block'
    raw = check_strided(text, int(report['kind'] == 'q4_0'),
                        (capture / 'kqv_out-0.bin').read_bytes(),
                        (ROOT / 'hardware/src/vlsu/vlsu.sv').read_text())
    s.require(all(saved.get(key) == value for key, value in raw.items()
                  if key not in ('state', 'independent_protocol_checked')),
              'Saved strided prerequisite disagrees with raw evidence')
    s.merge_pins(pins, inherited)
    receipts = [dict(run=str(strided), state='RAW_RECHECKED', tail=False,
                     result_sha256=s.digest(strided / 'result.json'))]
    receipts.append(checked_tails(tail, report, pins))
    s.verify_pins(pins)
    return receipts


def run(args):
    s.require(1 <= args.timeout <= 10800, 'Invalid timeout')
    build, strided, tail = (p.resolve(strict=True) for p in (args.build, args.prerequisite, args.tail_combined))
    out = args.output.resolve()
    s.require(not any(out.is_relative_to(p) or p.is_relative_to(out) for p in (build, strided, tail)),
              'Independent output directory required')
    out.mkdir(parents=True, exist_ok=False)
    work = out / 'work'
    work.mkdir()
    owner = Execution(out)
    owner.state.update(build=str(build), prerequisite=str(strided), tail_combined=str(tail))
    owner.save()
    try:
        report, pins = checked_build(build)
        own = [Path(__file__), HERE / 'test_threeway.py', HERE / 'THREEWAY.md', *s.script_files(),
               Path(sys.executable).resolve()]
        for module in tuple(sys.modules.values()):
            name = getattr(module, '__file__', None)
            if name:
                path = Path(name).resolve()
                if path.is_relative_to(ROOT) and path.is_file():
                    own.append(path)
        s.merge_pins(pins, s.hashes(own))
        s.atomic_json(out / 'preflight-pins.json', pins)
        s.verify_pins(pins)
        receipts = prerequisites(strided, tail, report, pins)
        s.atomic_json(out / 'prerequisite-audit.json', receipts)
        s.merge_pins(pins, s.hashes([out / 'preflight-pins.json', out / 'prerequisite-audit.json']))
        s.atomic_json(out / 'source-pins.json', pins)
        receipt = s.digest(out / 'source-pins.json')
        simv, elf = Path(report['simv']), Path(report['elf'])
        image = report['accepted_image_pins']
        owner.state.update(simv=str(simv), elf=str(elf), kind=report['kind'])

        def identity():
            s.require(s.digest(out / 'source-pins.json') == receipt, 'Worker manifest drift')
            s.verify_pins(pins)
            s.require(s.hashes(s.image_files(simv)) == image, 'Image inventory drift')

        def manifest(stage):
            owner.execute([sys.executable, '-B', '-m', 'ara_verify.vcs_source_manifest', '--output',
                           simv.parent / 'vcs_source_manifest.json', '--check'], out / (stage + '.log'), 300, stage.upper())

        identity()
        manifest('manifest-before')
        owner.execute(['bash', ROOT / 'hardware/scripts/llama_q4km_extract/check-sim-l2.sh', simv.parent, elf],
                      out / 'image-contract.log', 180, 'IMAGE_CONTRACT')
        identity()
        if args.preflight_only:
            s.atomic_json(out / 'result.json', dict(state='PREFLIGHT_ONLY_NOT_EXECUTED',
                          post_pins_match=True, source_pins_sha256=receipt))
            owner.state['state'] = 'PREFLIGHT_ONLY_NOT_EXECUTED'
            return
        log, trace = work / 'run.vcs.log', work / 'vector_trace.csv'
        owner.execute([simv, '-no_save', '-l', log, '+PRELOAD=' + str(elf), '+TESTCASE=quant_threeway_attention',
                       '+NO_FSDB', '+NO_INSTR_TRACE', '+QBS_PERF', '+VECTOR_TRACE=' + str(trace),
                       '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000'],
                      work / 'console.log', args.timeout, 'RUNNING')
        capture = ROOT / 'verification/out/akv-quantkv-host-capture-20261024-01' / (
            'capture-k-' + report['kind'] + '-v-q8_0') / 'decode/block'
        parsed = check_log(log.read_text(), int(report['kind'] == 'q4_0'),
                           (capture / 'kqv_out-0.bin').read_bytes(),
                           (ROOT / 'hardware/src/vlsu/vlsu.sv').read_text())
        owner.execute([sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events', '--require-backend',
                       '--require-axi', '--require-axi-write', '--vector-trace', trace, '--log', log,
                       '--simv', simv, '--elf', elf, '--output', work / 'uvm_result.json'], work / 'checker.log', 600, 'CHECKING')
        s.check_result(work / 'uvm_result.json', report['elf_sha256'], image)
        uvm = s.read_json(work / 'uvm_result.json')
        s.require(uvm['log_sha256'] == s.digest(log) and uvm['vector_trace_sha256'] == s.digest(trace), 'Protocol input drift')
        manifest('manifest-after')
        identity()
        parsed.update(state='PASS', simulator_exit_code=0, post_pins_match=True,
                      independent_protocol_checked=True, elf_sha256=report['elf_sha256'], source_pins_sha256=receipt,
                      evidence_sha256=s.hashes([log, trace, work / 'uvm_result.json', out / 'source-pins.json',
                          out / 'prerequisite-audit.json', out / 'manifest-before.log', out / 'manifest-after.log',
                          out / 'image-contract.log']))
        s.atomic_json(out / 'result.json', parsed)
        owner.state['state'] = 'PASS'
    except BaseException as exc:
        state = 'TIMEOUT' if isinstance(exc, subprocess.TimeoutExpired) else \
                'INTERRUPTED' if isinstance(exc, InterruptedError) else 'FAIL'
        owner.state.update(state=state, error=repr(exc))
        s.atomic_json(out / 'result.json', dict(state=state, error=repr(exc)))
        raise
    finally:
        owner.state.update(child_pid=None, finished=datetime.now(timezone.utc).isoformat())
        owner.save()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ('build', 'prerequisite', 'tail-combined', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=10800)
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()

    def interrupted(sig, _frame):
        raise InterruptedError(f'Signal {sig}')

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    run(args)

