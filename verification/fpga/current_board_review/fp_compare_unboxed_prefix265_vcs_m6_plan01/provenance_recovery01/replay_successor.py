#!/usr/bin/env python3
"""Narrow successor: historical/runtime split and durable unvalidated outcome.

prepare/dryrun do not launch. run retains the old explicit parent authorization,
image/source/pin, resource, service ownership, timeout and no-retry gates.
"""
import importlib.util
from pathlib import Path
import shlex
import sys
from types import SimpleNamespace

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import checker
from adapter import runtime_case, successor_checked_runner

spec = importlib.util.spec_from_file_location('sealed_unboxed_replay', HERE.parent/'replay.py')
legacy = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = legacy
spec.loader.exec_module(legacy)
original_validate = legacy.validate
UNIT = 'ara-fp-unboxed-original265-m6-02.service'


def artifacts(result, case, ledger, spec, validator):
    return checker.artifacts(result, runtime_case(case), ledger, spec, validator)


def validate(data, image):
    original_validate(data, image)
    checker.require(data['pins'].get(str(Path(__file__).resolve())) == checker.sha(Path(__file__)),
                    'Successor executable drift')
    checker.require(data['pins'].get(str(HERE/'adapter.py')) == checker.sha(HERE/'adapter.py'),
                    'Successor runtime/outcome adapter drift')


def prepare(image, out, reserved):
    require, common = checker.require, checker.common
    require(not out.exists(), 'Fresh successor plan only')
    pins = legacy.reference_inputs()
    ledger, repo, _ = common.image_context(image)
    require(checker.sha(image/'image.json') == legacy.IMAGE_SHA, 'Exact original M6 image required')
    pins.update(common.image_pins(image, ledger, repo))
    case, scope = legacy.scope()
    runtime_case(case)  # Assert the actual historical/runtime identities without changing case.
    host = checker.read(HERE/'host01.json')
    require(host['status'] == 'PASS_HOST_ONLY' and host['tests'] == 5 and
            host['errors'] == host['failures'] == 0, 'Metadata/outcome Host gates')
    common.base.verify_pins(host['pins'])
    for module in list(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path and Path(path).is_file() and Path(path).resolve().is_relative_to(checker.HERE.parents[3]):
            pins[str(Path(path).resolve())] = checker.sha(Path(path))
    for name in ('adapter.py','replay_successor.py','test_host.py','host01.json','README.md'):
        pins[str(HERE/name)] = checker.sha(HERE/name)
    require(type(reserved) is int and 0 <= reserved <= 24, 'Unused reservations only')
    common.base.verify_pins(pins)
    out.mkdir()
    common.save(out/'plan.json', dict(status='PREPARED_NOT_RUN', image=str(image),
        image_sha256=legacy.IMAGE_SHA, snapshot_sha256=ledger['snapshot_sha256'],
        case=case, spec=scope, pins=pins, jobs=1, timeout_s=legacy.TIMEOUT,
        service_timeout_s=legacy.OUTER, unit=UNIT, reserved_slots=reserved,
        no_build=True, no_retry=True, no_fsdb=True, reference_ready_sha256=checker.READY_SHA,
        independent_reference_acceptance='EXISTING_AUDIT_REQUIRES_NEW_PLAN_AUTHORIZATION_AT_RUN',
        runtime_testcase=case['id'], historical_source_name=case['original_name'],
        unvalidated_outcome_before_postcheck=True,
        prior_run='PRESERVED_NOT_PASS_NOT_A_RETRY_AUTHORIZATION',
        launch_requirements=['new_parent_planSHA_authorization','pinned_reference_audit_review',
                             'direct_service_owner','runtime_resources'],
        resource_snapshot=None, resource_check_deferred_to_authorized_run=True))
    digest = checker.sha(out/'plan.json')
    command = [sys.executable, str(Path(__file__).resolve()), 'run', '--image', str(image),
        '--out', str(out), '--plan-sha256', digest, '--authorize-run',
        '--parent-review', 'NEW_PARENT_REVIEW_JSON', '--parent-review-sha256', 'NEW_REVIEW_SHA256']
    service = ['systemd-run','--user','--unit='+UNIT,'--property=RuntimeMaxSec='+str(legacy.OUTER),
        '--property=KillMode=control-group','--property=Restart=no',
        '--property=WorkingDirectory='+str(HERE),
        '--property=StandardOutput=append:'+str(out/'service.log'),
        '--property=StandardError=append:'+str(out/'service.log'),*command]
    common.save(out/'ready.json', dict(status='PREPARED_NOT_ADMITTED_NO_DUT', plan_sha256=digest,
        command=command, service_command=shlex.join(service), pins=len(pins), vcs_started=False))
    print('PREPARED_NOT_ADMITTED_NO_DUT', digest)


# Bind both fixes to the actual frozen execution path, without editing its files.
legacy.HERE = HERE
legacy.UNIT = UNIT
legacy.prepare = prepare
legacy.validate = validate
legacy.worker.HERE = HERE
legacy.worker.UNIT = UNIT
legacy.worker.validate = validate
legacy.worker.checked_runner = successor_checked_runner
legacy.worker.checker = SimpleNamespace(VETO=checker.VETO, artifacts=artifacts)

if __name__ == '__main__':
    raise SystemExit(legacy.main())
