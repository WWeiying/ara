"""Prepare a single foreground 600s simv66 run; separate parent review before run."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time

import build_pure_war_preflight as preflight

life, require = preflight.life, preflight.require
PRE = life.OUT / 'pure-war-div-indexed-preflight-727-20261006-01'
PRE_SEAL = 'e2c29d00524aeee602f219b7d464f62e3fc39906736fecad523eaee03253201a'
SUPPLEMENT = life.OUT / 'pure-war-preflight-test-supplement-727-20261006-01.json'
SUPPLEMENT_SEAL = '2c1de5658ab1f9d3182d0b03c589b0e54b39572b5c43dd535caaafeaccab0f91'
BUDGET = 600
IMAGE_SEAL = '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3'
ELF_SEAL = '8b67e496c6a12c880d64a88bb0ad4aeba2862c405dded1d406d40908a9e0e4af'


def validate(pre):
    require(pre['status'] == preflight.STATUS and pre['case'] == preflight.NAME and
            pre['baseline_tests'] == 727 and pre['baseline_manifest_sha256'] == preflight.BASE_SEAL and
            pre['vcs_started'] is False and pre['rtl_changed'] is False and pre['coverage_admitted'] is False and
            pre['ZCC_executed'] is False and pre['dut_diff_executed'] is False and
            pre['measured_raw_increment'] is None and pre['backend_budget_seconds'] == BUDGET,
            'Preflight contract differs')
    expected = dict(status='PURE_WAR_SPIKE_FULL_ORACLE_PASS_NOT_DUT', checks=1765,
        exceptions=0, snapshots=2, full_vrf_registers=32, observed_vrf_bytes=8192,
        vrf_guard_bytes=1024, source_bytes=4224, source_guard_bytes=528,
        vector_write_instructions=34, known_vector_write_bytes=6144,
        DIV_old_source_bytes=1024, indexed_load_bytes=1024, VL=1024, vstart=0,
        CSR_restoration=True, skipped_unknown_bytes=0, coverage_admitted=False)
    require(pre['validation'] == expected and pre['checks'] == 1765, 'Full independent oracle contract differs')
    require(pre['input_elf'] == str(PRE / 'input.elf') and pre['symbols']['tohost'] == 0x80001000 and
            pre['old_image_files_checked'] == 66 and pre['reference_counts']['matched_instructions'] == 241635 and
            pre['pins'][str(PRE / 'input.elf')] == ELF_SEAL and
            pre['symbols']['gpw_load'] == pre['symbols']['gpw_div'] + 4 and
            pre['instruction_pair'] == ['0x8282ec57', '0x7050407'], 'ELF/image/reference/pair differs')
    require(pre['targets'] == preflight.target_binding()[0], 'Exact727 requester compiled targets differ')
    for name in ('input.elf', 'spike.trace', 'spike-validation.json', 'reference-counts.json',
                 'host.log', 'host-reference', 'compile-command.json', 'spike-command.json', 'target-before.json', 'elf-dedup.json'):
        require(str(PRE / name) in pre['pins'], 'Missing preflight pin: ' + name)


def command(out):
    return [str(life.IMAGE), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
        '+PRELOAD=' + str(PRE / 'input.elf'), '+TESTCASE=' + preflight.NAME, '+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE=' + str(out / 'commit_trace.csv'), '+VECTOR_TRACE=' + str(out / 'vector_trace.csv'),
        '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(out / 'code.vdb'), '-cm_name', preflight.NAME]


def prepare(out):
    out = out.absolute()
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh direct run directory required')
    pre = life.read_bound(PRE / 'preflight-manifest.json', PRE_SEAL)
    validate(pre); life.check(pre['pins'])
    supplement = life.read_bound(SUPPLEMENT, SUPPLEMENT_SEAL)
    require(supplement['preflight_seal'] == PRE_SEAL and supplement['status'] ==
            'ACTUAL_FIXTURE_TESTS_PASS_NO_NEW_SPIKE_NO_VCS' and
            {k: supplement['successor_result'][k] for k in ('tests', 'passed', 'errors', 'failures', 'skipped')} ==
            dict(tests=38, passed=38, errors=0, failures=0, skipped=0), 'Actual fixture test supplement differs')
    plan = life.read_bound(life.PLAN, life.PLAN_SEAL)
    require(plan['simv'] == str(life.IMAGE) and len(plan['image']) == 66 and
            plan['image'][str(life.IMAGE)] == IMAGE_SEAL, 'Frozen simv66 differs')
    pins = life.merge_pins(pre['pins'], plan['image'])
    pins = life.merge_pins(pins, supplement['pins'])
    pins = life.merge_pins(pins, {str(PRE / 'preflight-manifest.json'): PRE_SEAL,
        str(SUPPLEMENT): SUPPLEMENT_SEAL, str(life.PLAN): life.PLAN_SEAL,
        str(Path(__file__).resolve()): life.digest(Path(__file__)),
        str(Path(__file__).with_name('test_run_pure_war_simulation.py')):
            life.digest(Path(__file__).with_name('test_run_pure_war_simulation.py'))})
    life.check(pins)
    return out, dict(case=preflight.NAME, preflight=str(PRE / 'preflight-manifest.json'), preflight_seal=PRE_SEAL,
        test_supplement=str(SUPPLEMENT), test_supplement_seal=SUPPLEMENT_SEAL,
        command=command(out), output=str(out), pins=pins, timeout_s=BUDGET, baseline_tests=727,
        targets=pre['targets'], old_image_files_checked=66, scalar_reference_counts=pre['reference_counts'],
        image_sha256=IMAGE_SEAL, elf_sha256=ELF_SEAL,
        authorization_source='SEPARATE_PARENT_AGENT_REVIEW_REQUIRED_BEFORE_RUN',
        foreground_lifetime=True, normal_wait_calls=1, start_new_session=True,
        systemd_policy=dict(RuntimeMaxSec=630, TimeoutStopSec=10, KillMode='control-group'),
        coverage_admitted=False, admission_performed=False, rtl_changed=False, new_RTL_signoff=False,
        dut_self_check_verified=False, simulator_exit_is_not_functional_pass=True,
        no_FSDB=True, automatic_retry=False, raw_commit=True, raw_vector=True,
        qualification_required='Full independent scalar/vector/signature/lifecycle; positive latest-baseline raw delta')


def run(out, manifest):
    require(manifest['timeout_s'] == BUDGET and manifest['command'] == command(out) and
            manifest['output'] == str(out), 'Bounded execution contract differs')
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh run directory required')
    life.check(manifest['pins'])
    out.mkdir(); life.save(out / 'manifest.json', manifest)
    process, result, cleanup = None, None, False
    start = time.monotonic()
    try:
        with (out / 'console.log').open('x') as log:
            process = subprocess.Popen(manifest['command'], cwd=out, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            life.save(out / 'started.json', dict(pid=process.pid, process_group=process.pid,
                launcher_pid=os.getpid(), unix_time=time.time(), budget_s=BUDGET,
                input_elf=str(PRE / 'input.elf'), elf_sha256=ELF_SEAL, image=str(life.IMAGE),
                image_sha256=IMAGE_SEAL, command=manifest['command'],
                foreground_lifetime=True, live_identity_verified=False, coverage_admitted=False))
            result = process.wait(timeout=BUDGET)
        require(result == 0, 'Nonzero simulator exit: ' + str(result))
        life.check(manifest['pins'])
        life.save(out / 'simulation-status.json', dict(status='SIMULATION_EXITED_NOT_ADMITTED',
            returncode=result, case=preflight.NAME, wall_seconds=time.monotonic() - start,
            timeout=False, pid=process.pid, coverage_admitted=False, admission_performed=False,
            dut_self_check_verified=False, terminal_oracle_verified=False))
    except BaseException as error:
        if process is not None and process.poll() is None:
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            process.wait(); cleanup = True
        drift = None
        try: life.check(manifest['pins'])
        except Exception as e: drift = str(e)
        life.save(out / 'simulation-status.json', dict(status='SIMULATION_FAILED_OR_TIMEOUT_NOT_ADMITTED',
            reason=type(error).__name__ + ': ' + str(error), post_failure_pin_error=drift,
            returncode=process.returncode if process is not None else None,
            wall_seconds=time.monotonic() - start, timeout=isinstance(error, subprocess.TimeoutExpired),
            process_group_cleanup=cleanup, case=preflight.NAME,
            coverage_admitted=False, admission_performed=False, terminal_oracle_verified=False))
        raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'verify', 'run')); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--prepared-seal'); p.add_argument('--parent-authorized', action='store_true')
    a = p.parse_args(); require((a.mode != 'prepare') == bool(a.prepared_seal), 'Verify/run need fixed prepared seal')
    require((a.mode == 'run') == a.parent_authorized, 'Only separately authorized run uses --parent-authorized')
    out, manifest = prepare(a.output); record = out.with_name(out.name + '.prepared.json')
    if a.mode == 'prepare':
        life.save(record, manifest)
        print(json.dumps(dict(prepared=str(record), seal=life.digest(record), timeout_s=BUDGET, pins=len(manifest['pins']))))
    else:
        require(life.read_bound(record, a.prepared_seal) == manifest, 'Prepared command/pins drift')
        if a.mode == 'verify': print('VERIFY_PASS simv66/727/exact4/600wall/rawcommit/vector/noFSDB NO_VCS')
        else:
            manifest = dict(manifest, authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL')
            run(out, manifest)


if __name__ == '__main__': main()
