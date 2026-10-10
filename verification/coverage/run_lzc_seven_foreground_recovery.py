"""One explicitly reviewed foreground recovery of the sealed724 pre-EDA worker loss."""
import argparse
import contextlib
import json
import os
from pathlib import Path

import run_lzc_selector_native_seven_policy_v2 as original

frozen, require = original.frozen, original.require
SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_run_lzc_seven_foreground_recovery.py')
OUTPUT = frozen.OUT / 'lzc-selector-native-seven-policy-runtime-v2-724-parent-20261006-01'
SIDECAR = frozen.OUT / 'lzc-seven-foreground-recovery-724-parent-20261006-01'
LAUNCH_SEAL = 'e729bbf04bec7d85d162af00baafffe97dc6f90e41701ddc37210d8ce7665bee'
RUNTIME_SEAL = '2e556f60fc95ace5e71b41483d481cad85e34cdf696e789d85da11d5614bdb36'
CLAIM_SHA = 'a3e6afb4214148e06c1bba7f44c332734cda51c5253aa5dd0f8ab719ba8c9b81'
BACKGROUND_SHA = '520316b55f3ec25831e6b025cecfdd0e4807e78a5392c753fe1db29111d07238'
STATUS_SHA = 'aeeddc59d6bad5df561b89b819a708b43165f490fdd0abfd43c249834988057b'
BLOCKED = ('execution.json', 'live-identity.json', 'live-ready', 'DVEfiles', 'launcher.log',
           'integrity-before.json', 'integrity-after.json', 'capture-result.json', 'applied.el',
           'after-root.el', 'reloaded.el', 'initial-empty.el', 'reset-empty.el', 'final-empty.el',
           'session-final-empty.el', 'selected_tests.txt', 'rooted-metrics.csv', 'gui-contract.tsv',
           'summary_raw.csv', 'summary_applied.csv', 'summary_reset.csv')


def fast_guard():
    require(OUTPUT.resolve() == OUTPUT and not OUTPUT.is_symlink(), 'Aliased original output')
    claim_path, background_path = OUTPUT / original.CLAIM, OUTPUT / 'population-background.json'
    require(frozen.sha(claim_path) == CLAIM_SHA and frozen.sha(background_path) == BACKGROUND_SHA,
            'Frozen original claim/background bytes differ')
    claim, background = [json.loads(p.read_bytes()) for p in (claim_path, background_path)]
    launch = frozen.load_sealed(OUTPUT / original.PLAN, LAUNCH_SEAL)
    runtime = frozen.load_sealed(OUTPUT / 'runtime-plan.json', RUNTIME_SEAL)
    require(claim['mode'] == 'background' and claim['owner_pid'] == 3077991
            and claim['output'] == str(OUTPUT) and claim['launch_plan_sha256'] == LAUNCH_SEAL
            and claim['retries_allowed'] is False, 'Original claim identity differs')
    command = ['/usr/bin/python3', '-B', str(original.SCRIPT), '_background-worker',
               '--output', str(OUTPUT), '--launch-seal', LAUNCH_SEAL]
    require(background['runner_pid'] == 3080799 and background['command'] == command
            and background['cwd'] == str(OUTPUT) and background['launch_plan_sha256'] == LAUNCH_SEAL
            and background['dve_command'] == launch['command'] == runtime['command']
            and not background['actual_dve_pid_confirmed'] and not background['automatic_retry'],
            'Original worker/command binding differs')
    require(launch['config_sha256'] == RUNTIME_SEAL
            and (launch['targets'], launch['protected'], launch['audited'], launch['timeout_seconds']) ==
            (5868, 17702, 23570, 10800), 'Original sealed launch scope differs')
    require(not any(Path('/proc', str(pid)).exists() for pid in (3077991, 3080799)), 'Original PID still exists')
    require(frozen.sha(OUTPUT / 'status.json') == STATUS_SHA
            and json.loads((OUTPUT / 'status.json').read_bytes())['status'] == 'PREPARED_NO_DVE',
            'Original status is not unexecuted PREPARED')
    require((OUTPUT / 'population-runner.log').is_file()
            and (OUTPUT / 'population-runner.log').read_bytes() == b'', 'Original worker diagnostic is not empty')
    require(not any((OUTPUT / name).exists() for name in BLOCKED), 'Existing DVE execution/output: no recovery')
    require(not any(any((OUTPUT / group).iterdir()) for group in (*frozen.GROUPS, 'lzc')),
            'Existing group audit/output: no recovery')
    # Frozen run persists RUNNING and integrity-before before its first Popen.
    # These exact pre-EDA bytes and absent outputs bind this original worker,
    # without depending on visibility of unrelated host processes.
    return launch, runtime


def prepare(sidecar):
    require(sidecar == SIDECAR and sidecar.resolve() == sidecar and not sidecar.exists(), 'Fresh fixed recovery sidecar required')
    launch, _ = fast_guard()
    dependencies = (SCRIPT, TEST, Path(original.__file__).resolve(), original.TEST,
                    Path(original.generic.__file__).resolve(), original.generic.TEST, original.generic.TCL,
                    OUTPUT / original.CLAIM, OUTPUT / 'population-background.json',
                    OUTPUT / original.PLAN, OUTPUT / 'runtime-plan.json', OUTPUT / 'status.json',
                    OUTPUT / 'population-runner.log')
    pins = {str(p): frozen.sha(p) for p in dependencies}
    record = dict(schema='lzc-seven-foreground-recovery-v1', output=str(OUTPUT), sidecar=str(sidecar),
                  original_launch_seal=LAUNCH_SEAL, original_runtime_seal=RUNTIME_SEAL,
                  original_worker_pid=3080799, original_launcher_pid=3077991,
                  original_records_preserved=True, prepared_config_recreated=False,
                  targets=5868, protected=17702, audited=23570, timeout_seconds=10800,
                  launch_command=launch['command'], method='same foreground main process directly calls original.invoke_run',
                  parent_authorization_required=True, launch_approved=False, automatic_retry=False,
                  receipt=str(sidecar / 'recovery-receipt.json'), log=str(sidecar / 'recovery-runner.log'),
                  systemd_contract='Type=exec KillMode=control-group; main process remains alive through qualification',
                  diagnosis='setsid/new process session does not leave the inherited systemd cgroup; short launcher exit is consistent with cleanup of its worker',
                  historical_signal_trace_available=False, application_approval=False, pins=pins)
    sidecar.mkdir()
    frozen.write(sidecar / 'recovery-plan.json', record)
    frozen.write(sidecar / 'recovery-plan.sha256.json', {str(sidecar / 'recovery-plan.json'): frozen.sha(sidecar / 'recovery-plan.json')})
    return record


def reviewed(sidecar, seal):
    require(sidecar == SIDECAR and sidecar.resolve() == sidecar, 'Only fixed recovery sidecar accepted')
    plan = frozen.load_sealed(sidecar / 'recovery-plan.json', seal)
    require(plan['schema'] == 'lzc-seven-foreground-recovery-v1' and plan['output'] == str(OUTPUT)
            and plan['sidecar'] == str(sidecar) and plan['original_launch_seal'] == LAUNCH_SEAL
            and plan['original_runtime_seal'] == RUNTIME_SEAL and plan['parent_authorization_required']
            and not plan['launch_approved'] and not plan['automatic_retry'] and not plan['application_approval']
            and not plan['prepared_config_recreated'] and plan['original_records_preserved']
            and plan['original_worker_pid'] == 3080799 and plan['original_launcher_pid'] == 3077991
            and plan['method'] == 'same foreground main process directly calls original.invoke_run'
            and (plan['targets'], plan['protected'], plan['audited'], plan['timeout_seconds']) ==
            (5868, 17702, 23570, 10800)
            and plan['receipt'] == str(sidecar / 'recovery-receipt.json')
            and plan['log'] == str(sidecar / 'recovery-runner.log'), 'Recovery contract differs')
    for path, expected in plan['pins'].items():
        require(frozen.sha(path) == expected, 'Recovery dependency drift: ' + path)
    for path in (SCRIPT, TEST, Path(original.__file__).resolve(), original.TEST,
                 Path(original.generic.__file__).resolve(), original.generic.TEST, original.generic.TCL,
                 OUTPUT / original.CLAIM, OUTPUT / 'population-background.json',
                 OUTPUT / original.PLAN, OUTPUT / 'runtime-plan.json', OUTPUT / 'status.json',
                 OUTPUT / 'population-runner.log'):
        require(plan['pins'].get(str(path)) == frozen.sha(path), 'Mandatory recovery dependency omitted')
    launch, _ = fast_guard()
    require(plan['launch_command'] == launch['command'], 'Recovery DVE command differs')
    return plan


def run(sidecar, seal, authorized=False):
    require(authorized, 'Explicit parent foreground-recovery authorization required')
    plan = reviewed(sidecar, seal)
    require(not (sidecar / 'recovery-runner.log').exists(), 'Previous recovery log: no retry')
    receipt = dict(status='CLAIMED_REVIEWING_INPUTS', recovery_plan_sha256=seal,
                   original_launch_seal=LAUNCH_SEAL, owner_pid=os.getpid(), foreground_main=True,
                   parent_explicitly_authorized=True, automatic_retry=False, application_approval=False,
                   cgroup=Path('/proc/self/cgroup').read_text())
    path = sidecar / 'recovery-receipt.json'
    # Exclusive creation is the sole recovery claim; failure remains consumed.
    with path.open('x') as stream:
        json.dump(receipt, stream, indent=2)
        stream.write('\n')
    try:
        with (sidecar / 'recovery-runner.log').open('x') as log, \
             contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            launch, context, config = original.reviewed_entry(OUTPUT, LAUNCH_SEAL)
            fast_guard()
            require(config['command'] == plan['launch_command'], 'Actual recovery command differs')
            receipt['status'] = 'RUNNING_FOREGROUND_DIRECT_INVOKE'
            frozen.write(path, receipt)
            original.invoke_run(OUTPUT, launch, context, config)
            require(frozen.sha(OUTPUT / original.CLAIM) == CLAIM_SHA
                    and frozen.sha(OUTPUT / 'population-background.json') == BACKGROUND_SHA,
                    'Original recovery records changed')
            receipt['status'] = 'FOREGROUND_INVOKE_COMPLETED_REVIEW_CAPTURE_RESULT'
    except BaseException as error:
        receipt.update(status='RECOVERY_FAILED_NO_AUTOMATIC_RETRY', reason=repr(error))
        raise
    finally:
        frozen.write(path, receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'check', 'run-foreground-reviewed'))
    parser.add_argument('--sidecar', type=Path, required=True)
    parser.add_argument('--seal')
    parser.add_argument('--authorize-one-shot-foreground-recovery', action='store_true')
    args = parser.parse_args()
    sidecar = args.sidecar.absolute()
    if args.mode == 'prepare':
        require(not args.seal and not args.authorize_one_shot_foreground_recovery, 'Preparation cannot authorize launch')
        prepare(sidecar)
        print(json.dumps(dict(status='PREPARED_RECOVERY_REVIEW_ONLY_NO_EDA', seal=frozen.sha(sidecar / 'recovery-plan.json'))))
    elif args.mode == 'check':
        require(args.seal and not args.authorize_one_shot_foreground_recovery, 'Check is read-only')
        reviewed(sidecar, args.seal)
        print('RECOVERY_CONTRACT_CHECKED_NO_EDA')
    else:
        require(args.seal, 'Reviewed recovery seal required')
        print(json.dumps(run(sidecar, args.seal, args.authorize_one_shot_foreground_recovery)))


if __name__ == '__main__':
    main()
