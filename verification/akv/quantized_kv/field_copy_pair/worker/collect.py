#!/usr/bin/env python3
"""Offline replay/compare of two terminal checked sides; never launch EDA."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run as worker

s = worker.s


def checked_side(directory, side, prepared, image, args, pins, deadline):
    result_path, status_path = directory/'result.json', directory/'status.json'
    result, status = s.read_json(result_path), s.read_json(status_path)
    worker.fields(result, dict(schema='field_copy_pair_side_v1', state='FIELD_COPY_SIDE_CHECKED',
        side=side, revision=worker.REVISIONS[side], execution='SIMULATED_ONCE', simulations_launched=1,
        simulator_exit_code=0, post_pins_match=True, independent_protocol_checked=True,
        output_words_checked=4608, mirrored_calls_checked=6, native_commands_checked=16,
        historical_timing_used=False, performance_acceptance=False,
        review_sha256=args.review_sha256, image_pins=image, soc_build_sha256=worker.accepted.SOC_SHA),
        'terminal '+side)
    worker.fields(status, dict(state='FIELD_COPY_SIDE_CHECKED', side=side, child_pid=None,
                              simulations_launched=1, running_exit_code=0, checking_exit_code=0),
                  'terminal side status')
    program = prepared['programs'][side]
    worker.fields(result, dict(elf=program['elf'], elf_sha256=program['elf_sha256']), 'side ELF')
    receipt = directory/'source-pins.json'
    s.require(s.digest(receipt) == result['source_pins_sha256'], 'Side source receipt drift')
    before = s.read_json(receipt)
    s.require(all(before.get(p) == sha for p, sha in pins.items()), 'Side lacks current reviewed inputs')
    s.verify_pins(before)
    evidence = result['evidence_sha256']
    work = directory/'work'
    required = [receipt, directory/'runtime-environment.json', work/'run.vcs.log', work/'vector_trace.csv',
        work/'uvm_result.json', work/'console.command.json', work/'checker.command.json',
        directory/'manifest-before.command.json', directory/'manifest-after.command.json',
        directory/'image-contract.command.json']
    s.require(all(str(path) in evidence for path in required), 'Incomplete closed side evidence')
    s.verify_pins(evidence)
    s.require(s.digest(directory/'runtime-environment.json') == result['runtime_environment_sha256'] and
              s.read_json(directory/'runtime-environment.json') == result['runtime_environment'], 'Side environment differs')
    simv = Path(status['simv'])
    for log, expected, timeout in ((work/'console.log', worker.simulation_command(simv, Path(program['elf']), work), None),
                                    (work/'checker.log', worker.uvm_command(simv, Path(program['elf']), work), 600)):
        command = s.read_json(log.with_suffix('.command.json'))
        s.require(command['argv'] == list(map(str, expected)) and command['cwd'] == str(work),
                  'Side command or private cwd differs')
        if timeout is None:
            s.require(type(command['timeout_seconds']) is int and 1 <= command['timeout_seconds'] <= 10800,
                      'Side simulator timeout outside bound')
        else:
            s.require(command['timeout_seconds'] == timeout, 'Side checker timeout differs')
    parsed = worker.checked_raw(work, program)
    s.require(parsed == result['raw_replay'], 'Side raw replay differs from saved report')
    worker.independent_protocol(work, program, image)
    s.require(time.monotonic() < deadline, 'Offline collection exceeded 300 seconds')
    closed = dict(before)
    s.merge_pins(closed, evidence)
    s.merge_pins(closed, s.hashes([result_path, status_path]))
    return parsed, result, closed


def collect(args):
    baseline, candidate = worker.path(args.baseline), worker.path(args.candidate)
    s.require(baseline != candidate and not baseline.is_relative_to(candidate) and
              not candidate.is_relative_to(baseline), 'Need independent side outputs')
    output = worker.fresh_output(args.output, [baseline, candidate, worker.PAIR,
        worker.path(args.review).parent, worker.path(args.soc_build)])
    output.mkdir(parents=True)
    deadline = time.monotonic()+300
    result = dict(schema='field_copy_pair_collection_v1', performance_acceptance=False,
                  independent_parent_review_required=True, eda_launched=False)
    try:
        prepared, soc, pins, image, review = worker.prepare_inputs(args)
        evidence = dict(pins)
        reports, side_results = {}, {}
        for side, directory in (('baseline', baseline), ('candidate', candidate)):
            parsed, side_result, closed = checked_side(directory, side, prepared, image, args, pins, deadline)
            worker.fields(side_result, dict(prepared_pair_sha256=review['prepared_pair_sha256'],
                runtime_environment=review['runtime_environment'], soc_build=str(args.soc_build)), 'paired identity')
            s.merge_pins(evidence, closed)
            reports[side], side_results[side] = parsed, side_result
        comparison = worker.comparison.compare(reports['baseline'], reports['candidate'])
        s.require(side_results['baseline']['elf_sha256'] != side_results['candidate']['elf_sha256'],
                  'Both sides substituted the same executable')
        s.verify_pins(evidence)
        s.require(s.hashes(s.image_files(Path(soc['simv']))) == image, 'Post-collection image drift')
        s.require(time.monotonic() < deadline, 'Offline collection exceeded 300 seconds')
        s.atomic_json(output/'input-pins.json', evidence)
        result.update(state='FIELD_COPY_PAIR_CHECKED_PENDING_PARENT_REVIEW', comparison=comparison,
            baseline=str(baseline), candidate=str(candidate), review_sha256=args.review_sha256,
            prepared_pair_sha256=review['prepared_pair_sha256'], image_pins=image,
            source_pins_sha256=s.digest(output/'input-pins.json'), post_pins_match=True,
            fresh_runs_checked=2, output_words_per_binary=4608, cross_binary_word_comparisons=4608,
            total_output_values_read=9216)
        s.atomic_json(output/'result.json', result)
        return result
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc), post_pins_match=False)
        s.atomic_json(output/'result.json', result)
        raise
    finally:
        s.atomic_json(output/'status.json', dict(state=result.get('state'), child_pid=None,
            finished=datetime.now(timezone.utc).isoformat()))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--review-sha256', required=True)
    parser.add_argument('--soc-build', type=Path, default=worker.accepted.SOC_BUILD)
    parser.add_argument('--output', type=Path, required=True)
    collect(parser.parse_args())
