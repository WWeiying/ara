#!/usr/bin/env python3
"""One offline recheck of immutable raw evidence, never a simulator launcher."""
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import checker
from adapter import NAME, HISTORICAL_NAME, runtime_case

require, read, sha = checker.require, checker.read, checker.sha
PLAN_SHA = 'e3bbb288f69f8f0cc0a24491125e0bb327e04d3edbaa3eb46837bb2c153e0940'


@dataclass
class ControlFlowReconstructedResult:
    # These are explicit derivations, NOT a replacement for persisted TestResult.
    name: str
    artifact_dir: Path
    elapsed_s: float  # wall-window upper proxy, not recovered monotonic elapsed
    returncode: int = 0  # implied by executed prior gate, NOT directly persisted
    status: str = 'PASS'  # base runner before postcheck, NOT the batch status
    reason: str = ''


def main():
    out = HERE/'audit01'
    require(not out.exists(), 'Fresh offline record only; no retries/overwrite')
    out.mkdir()
    started = time.time()
    report = dict(status='OFFLINE_RECHECK_NOT_COMPLETED', original_batch_status='NOT_PASS',
                  no_simulator=True, original_raw_metadata_modified=False,
                  direct_persisted_child_returncode=None, direct_persisted_child_elapsed_s=None,
                  process_service_acceptance=False)
    try:
        old = HERE.parent/'prepared01'
        root = old/'replay/tests'/NAME
        require(sha(old/'plan.json') == PLAN_SHA, 'Original plan drift')
        plan, complete, metadata, launch = [read(old/p) for p in
            ('plan.json', 'complete.json', 'replay/run.json', 'launch.json')]
        require(complete['status'] == 'NOT_PASS' and complete['aborted'] is True and
                complete['results'][0]['returncode'] is None and
                complete['results'][0]['reason'] == 'ValueError: Command provenance mismatch' and
                metadata['status'] == 'INTERRUPTED' and metadata['status_counts'] == {'ERROR': 1},
                'Unexpected original failure record')
        pins = dict(plan['pins'])
        pins.update(launch['approval_pins'])
        original_files = [old/p for p in ('plan.json', 'complete.json', 'launch.json', 'service.log',
            'replay/run.json', 'replay/summary.json', 'replay/summary.csv', 'replay/junit.xml',
            'dryrun_check.json', 'dryrun/tests/'+NAME+'/command.json')]
        original_files += [p for p in root.rglob('*') if p.is_file()]
        pins.update({str(p): sha(p) for p in original_files})
        checker.common.base.verify_pins(pins)
        require(plan['pins'][str(checker.HERE/'checker.py')] == sha(checker.HERE/'checker.py'),
                'Actual sealed checker drift')
        ledger, repo, _ = checker.common.image_context(Path(plan['image']))
        require(sha(Path(plan['image'])/'image.json') == plan['image_sha256'], 'Image ledger drift')
        case = plan['case']
        runtime = runtime_case(case)
        command = read(root/'command.json')
        def expected(testcase):
            return dict(cwd=str(root/'work'), command=[ledger['simv'], '-l', 'run.vcs.log',
                '+ntb_random_seed=1', '+PRELOAD='+str(root/'input.elf'), '+TESTCASE='+testcase,
                '+NO_FSDB', '+COMMIT_TRACE='+str(root/'commit_trace.csv')])
        require(command == expected(NAME), 'Runtime command not exact authorized runner command')
        previous = expected(HISTORICAL_NAME)
        differences = [dict(index=i, actual=a, old_expected=b)
                       for i, (a,b) in enumerate(zip(command['command'], previous['command'])) if a != b]
        require(len(differences) == 1 and differences[0]['index'] == 5, 'Not solely TESTCASE mismatch')
        require(checker.specification(Path(case['elf'])) == plan['spec'], 'Actual ELF specification drift')
        runner = repo/'verification/ara_verify/runner.py'
        require(plan['pins'][str(runner)] == sha(runner), 'Frozen runner identity')
        require(read(root/'trace_summary.json')['status'] == 'VALID', 'Missing rc-gated trace summary')
        wall_window = (datetime.fromisoformat(metadata['completed_at']) -
                       datetime.fromisoformat(metadata['created_at'])).total_seconds()
        require(0 < wall_window < case['timeout_s'], 'Recorded enclosing wall window exceeds budget')
        reconstructed = ControlFlowReconstructedResult(NAME, root, wall_window)
        from ara_verify.trace import validate_trace
        # Only copied runtime metadata is adapted. Raw rows and strict oracle are untouched.
        checked = checker.artifacts(reconstructed, runtime, ledger, plan['spec'], validate_trace)
        require(checked['generic'] == {k:v for k,v in read(root/'trace_summary.json').items()
                                     if k != 'status'}, 'Fresh generic trace differs from persisted summary')
        checker.common.base.verify_pins(pins)
        require(sha(old/'plan.json') == PLAN_SHA, 'Late plan drift')
        report.update(status='ACCEPTED_ARCHITECTURAL_ORIGINAL265_ONLY_PROCESS_PROVENANCE_QUALIFIED',
            scope=dict(calls=265,predecessors=264,result_bits=4240,guards=530,flags=265,vstart=265,
                       full_original_parent=False,direct_vector_payload=False),
            original_plan_sha256=PLAN_SHA, original_plan_pins_checked=len(plan['pins']),
            all_evidence_pins_checked=len(pins), pins_unchanged=True,
            command_difference=differences, seed_matches=True,
            historical_source_name=HISTORICAL_NAME,runtime_name=NAME,
            inferred_child_returncode=0,
            inference_basis=['postcheck entered only after parent returned PASS',
                'check_artifacts line198 required numeric rc0 and bounded elapsed before line212 mismatch',
                'frozen runner wrote VALID trace_summary only after numeric rc0/no observed failure'],
            elapsed_evidence=dict(exact_monotonic_s=None, enclosing_recorded_wall_window_s=wall_window,
                vcs_cpu_s=1225.070,cpu_is_not_wall=True,
                use_in_legacy_check='explicit wall-window proxy; monotonic bound implied by prior executed gate'),
            original_run_metadata=metadata, original_complete=complete,
            service_exit='NOT_QUERIED_NOT_RECOVERED; wrapper status is not child exit',
            checker_result=checked, evidence_pins=pins,
            recovery_code_pins={str(HERE/n):sha(HERE/n) for n in
                                ('adapter.py','offline.py','test_host.py','host01.json')})
    except BaseException as error:
        report.update(status='OFFLINE_RECHECK_FAILED_NOT_ACCEPTED',
                      error=f'{type(error).__name__}: {error}')
    finally:
        report['offline_elapsed_s'] = time.time()-started
        with (out/'finding.json').open('x') as stream:
            json.dump(report, stream, indent=2)
            stream.write('\n')
    print(report['status'], flush=True)
    return 0 if report['status'].startswith('ACCEPTED_ARCHITECTURAL_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
