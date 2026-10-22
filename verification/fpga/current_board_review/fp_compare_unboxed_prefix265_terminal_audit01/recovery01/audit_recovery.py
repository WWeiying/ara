"""One authorized architectural data audit; never repairs old process metadata."""
import csv
from datetime import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
A = HERE.parent
PREPARED_SHA = 'ff5f57910afda05b9eb34ca8551459523fffa952b0282cb4563d1f9a9a9af444'
COMPLETE_SHA = '54d4d1a6b91e5de466a777a9d02fc12e2bb3180288ebfc64ec3bcbca448d3b04'
STATUS = 'ARCHITECTURAL_RESULT_ACCEPTED_PROCESS_METADATA_ERROR'


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''): h.update(b)
    return h.hexdigest()


def read(p): return json.loads(Path(p).read_text())


def save(p, data):
    with Path(p).open('x') as f: json.dump(data, f, indent=2); f.write('\n')


def main():
    assert __debug__ and sys.argv[1:] == ['--authorize-one-offline-recovery']
    assert not (HERE/'invocation.json').exists(), 'One invocation only; no retry'
    started = time.monotonic()
    save(HERE/'invocation.json', dict(pid=os.getpid(), argv=[sys.executable, '-B', *sys.argv],
        started=time.time(), script_sha256=sha(__file__), authorization_sha256=sha(HERE/'AUTHORIZATION.md'),
        prepared_sha256=PREPARED_SHA, complete_sha256=COMPLETE_SHA, allowed_csv_parses=1))
    print('RECOVERY_AUDIT_PID', os.getpid(), flush=True)
    try:
        assert sha(A/'prepared.json') == PREPARED_SHA
        prepared = read(A/'prepared.json')
        for p, h in prepared['static_pins'].items(): assert sha(p) == h, ('frozen auditor drift', p)
        sys.path.insert(0, str(A))
        spec = importlib.util.spec_from_file_location('frozen_unboxed_audit', A/'audit.py')
        audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)
        plan, _, gold, checker, Observer = audit.static_identity()
        P, NAME = audit.P, audit.NAME
        root = P/'replay/tests'/NAME
        assert sha(P/'complete.json') == COMPLETE_SHA
        old = read(P/'complete.json'); run = read(P/'replay/run.json'); summary = read(P/'replay/summary.json')
        assert old['status'] == 'NOT_PASS' and old['plan_sha256'] == audit.PLAN_SHA
        assert old['aborted'] is True and old['pins_unchanged'] is False
        assert type(old['retries']) is int and old['retries'] == 0 and old['error'] == 'ValueError: Sticky abort'
        assert summary == old['results'] and len(summary) == 1
        result = summary[0]
        assert result == dict(name=NAME, kind='app', status='ERROR', returncode=None, elapsed_s=0.0,
            reason='ValueError: Command provenance mismatch', artifact_dir=str(root))
        assert run['status'] == 'INTERRUPTED' and run['status_counts'] == {'ERROR': 1} and run['tests'] == [NAME]
        assert run['jobs'] == run['seed'] == 1 and run['timeout_s'] == 5400
        assert run['commit_trace'] is True and run['code_coverage'] is False and run['input_snapshots'] is True
        assert run['contract_monitor'] is False and run['probe_kinds'] == []
        assert datetime.fromisoformat(run['completed_at']) > datetime.fromisoformat(run['created_at'])
        assert not (root/'strict_prefix.json').exists(), 'Unexpected producer specialized report'
        assert not (P/'complete.tmp').exists()
        veto_files = [str(p) for p in P.rglob('*') if p.is_file() and re.search(r'first[ _-]?(?:failure|error)|abort|cancel|timeout', p.name, re.I)]
        assert not veto_files, ('Additional failure evidence', veto_files)
        image = Path(plan['image']); ledger = read(image/'image.json')
        assert sha(image/'image.json') == audit.IMAGE_SHA and run['simv'] == ledger['simv']
        snapshot = Path(ledger['snapshot'])/'snapshot.json'; snap = read(snapshot)
        assert sha(snapshot) == plan['snapshot_sha256'] == ledger['snapshot_sha256']
        assert snap['state'] == 'SEALED' and len(snap['files']) == 539 and len(ledger['files']) == 66
        assert sha(image/'_build/vcs/simulator.conf') == ledger['configuration_sha256'] == '6aaa87d2cdbabde8aee6baebad81dc7109d08361f788e799a44420f7cd037785'
        assert sha(image/'_build/vcs/vcs_source_manifest.json') == ledger['manifest_sha256']
        pins = dict(prepared['static_pins']); audit.add(pins, plan['pins']); audit.add(pins, ledger['files'])
        audit.add(pins, {str(Path(snap['root'])/p): h for p, h in snap['files'].items()})
        launch = read(P/'launch.json'); audit.add(pins, launch['approval_pins'])
        assert launch['plan_sha256'] == audit.PLAN_SHA and launch['started'] <= old['finished'] < launch['started']+6600
        owner = launch['owner']; prop = owner['properties']
        assert prop['Id'] == audit.UNIT and prop['MainPID'] == str(owner['pid']) and int(prop['MainPID']) > 0
        assert (prop['LoadState'], prop['ActiveState'], prop['SubState']) == ('loaded', 'active', 'running')
        assert prop['Restart'] == 'no' and prop['KillMode'] == 'control-group' and prop['RuntimeMaxUSec'] == '1h 50min'
        assert prop['ControlGroup'].endswith('/'+audit.UNIT) and prop['ControlGroup'] in [l.split(':', 2)[-1] for l in owner['cgroup'].splitlines()]
        argv = run['invocation']
        assert argv[:2] == [str(audit.R/'replay.py'), 'run'] and '--authorize-run' in argv
        assert argv[argv.index('--plan-sha256')+1] == audit.PLAN_SHA
        rp, rh = argv[argv.index('--parent-review')+1], argv[argv.index('--parent-review-sha256')+1]
        audit.add(pins, {rp: rh}); review = read(rp)
        assert review['decision'] == 'AUTHORIZE_UNBOXED_ORIGINAL265_ONCE' and review['plan_sha256'] == audit.PLAN_SHA
        assert review['unit'] == audit.UNIT and review['budget_risk_accepted'] is True and review['reference_ready_sha256'] == audit.READY_SHA
        for key in ('reference_audit', 'reference_review'):
            e = review[key]; audit.add(pins, {e['path']: e['sha256']})
        reference = read(review['reference_audit']['path'])
        assert reference['status'] == 'ACCEPTED_SOURCE_REFERENCE_ONLY_NOT_DUT' and reference['ready_sha256'] == audit.READY_SHA
        case = plan['case']
        assert case['id'] == NAME and case['original_name'] == 'rvv_fp_compare_unboxed_unmasked_e16_mf4'
        assert sha(root/'input.elf') == case['sha256'] == sha(case['elf'])
        assert read(root/'inputs.json')['binary'] == dict(source=case['elf'], path=str(root/'input.elf'), sha256=case['sha256'])
        assert read(root/'inputs.json')['simv'] == dict(path=ledger['simv'], image_sha256=ledger['files'])
        actual_command = read(root/'command.json')
        assert actual_command == dict(command=[ledger['simv'], '-l', 'run.vcs.log', '+ntb_random_seed=1',
            '+PRELOAD='+str(root/'input.elf'), '+TESTCASE='+NAME, '+NO_FSDB', '+COMMIT_TRACE='+str(root/'commit_trace.csv')], cwd=str(root/'work'))
        evidence = [P/'complete.json', P/'launch.json', P/'service.log', P/'replay/run.json', P/'replay/summary.json',
                    P/'replay/junit.xml', A/'prepared.json', HERE/'AUTHORIZATION.md', Path(__file__), HERE/'invocation.json',
                    A/'recovery_review01/evidence.json', A/'recovery_review01/REVIEW.md']
        evidence += [root/n for n in ('input.elf', 'inputs.json', 'command.json', 'console.log', 'work/run.vcs.log', 'commit_trace.csv', 'trace_summary.json')]
        for p in evidence: audit.add(pins, {str(p): sha(p)})
        audit.verify(pins)
        save(HERE/'pins_before.json', pins)
        for path in (root/'console.log', root/'work/run.vcs.log'):
            text = path.read_text(); checker.console_gate(text)
            assert not re.search(r'first[ _-]?(?:error|failure)|\b(?:TIMEOUT|CANCELLED|FATAL)\b', text, re.I)
        observer = Observer(plan['spec'], gold)
        with (root/'commit_trace.csv').open(newline='') as stream:
            strict = checker.source.audit(checker.convert(observer.rows(csv.DictReader(stream))), plan['spec'])
        generic = observer.finish()
        assert strict['retired'] == generic['retire_count'] and strict['helper_instructions'] == 4587
        assert strict['actual_initialization_stores'] == 76850
        assert strict['target_calls'] == 265 and strict['full_result_bit_checks'] == 4240 and strict['guard_checks'] == 530
        assert strict['returned_vstart_zero'] == strict['returned_flags_checked'] == 265
        assert strict['unused_helper_retirements'] == 0 and strict['full_reference_vectors'] is False
        assert dict(generic, status='VALID') == read(root/'trace_summary.json')
        audit.verify(pins)
        assert not (root/'strict_prefix.json').exists() and read(P/'complete.json') == old
        save(HERE/'verified_pins.json', pins)
        save(HERE/'result.json', dict(status=STATUS, architectural_result_accepted=True, process_metadata_accepted=False,
            original_batch_preserved=True, old_complete=old, old_run_status=run['status'], child_returncode=None,
            child_returncode_evidence='UNKNOWN_PERSISTED_NUMERIC; rc0 inferred only from sealed code path',
            outer_service_returncode=None, child_elapsed_s=None, observed_vcs_CPU_seconds=1225.070,
            plan_sha256=audit.PLAN_SHA, complete_sha256=COMPLETE_SHA, prepared_sha256=PREPARED_SHA,
            image_sha256=audit.IMAGE_SHA, elf_sha256=case['sha256'], csv_sha256=pins[str(root/'commit_trace.csv')],
            generic=generic, strict=strict, observer=observer.evidence(), actual_command=actual_command,
            pins_verified=len(pins), full_plan_pins=len(plan['pins']), evidence_pins=len(evidence), pins_pre_post_unchanged=True,
            csv_parses=1, reference_used_as_DUT_evidence=False, full_parent_acceptance=False,
            original_Linux_ELF_replay=False, no_guest_execution=True, audit_seconds=time.monotonic()-started))
        print(STATUS, sha(HERE/'result.json'), flush=True)
    except BaseException as error:
        save(HERE/'not_accepted.json', dict(status='NOT_ACCEPTED_NO_RETRY', firstcause=repr(error),
            complete_sha256=COMPLETE_SHA, elapsed_s=time.monotonic()-started))
        raise


if __name__ == '__main__': main()
