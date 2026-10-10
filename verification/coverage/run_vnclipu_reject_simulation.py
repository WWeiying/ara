"""Prepare one 1200s frozen-image runner. Separate parent review required before run."""
import argparse
import json
from pathlib import Path
import subprocess

import build_vnclipu_reject_preflight as preflight

life, require = preflight.life, preflight.require
PRE, BUDGET = preflight.PRE, 1200


def validate(pre):
    require(pre['status'] == preflight.STATUS and pre['case'] == preflight.NAME and
            pre['baseline_tests'] == 725 and pre['baseline_manifest_sha256'] == preflight.BASE_SEAL and
            pre['vcs_started'] is False and pre['rtl_changed'] is False and pre['coverage_admitted'] is False and
            pre['ZCC_executed'] is False and pre['dut_diff_executed'] is False and
            pre['measured_raw_increment'] is None, 'Preflight contract differs')
    expected = dict(status='VNCLIPU_REJECT_SPIKE_FULL_ORACLE_PASS_NOT_DUT', checks=2346,
        illegal_traps=1, trap_vstart=1, post_mret_vstart=1, snapshots=3, full_vrf_registers=32,
        observed_vrf_bytes=12288, vrf_guard_bytes=1536, source_bytes=4096, source_guard_bytes=512,
        handler_store_words=13, vector_write_instructions=33, illegal_vector_write_bytes=0,
        recovery_modified_bytes=4, restored_vector_CSRs=True, coverage_admitted=False)
    require(pre['validation'] == expected and pre['checks'] == 2346, 'Full independent oracle contract differs')
    require(pre['input_elf'] == str(PRE / 'input.elf') and pre['symbols']['tohost'] == 0x80001000 and
            pre['old_image_files_checked'] == 66 and pre['reference_counts']['matched_instructions'] > 0,
            'ELF/image/reference population differs')
    require(pre['targets'] == preflight.target_binding()[0], 'Exact725 scope/native compiled targets differ')
    for name in ('input.elf', 'spike.trace', 'spike-validation.json', 'reference-counts.json',
                 'host.log', 'host-reference', 'compile-command.json', 'spike-command.json', 'target-before.json', 'elf-dedup.json'):
        require(str(PRE / name) in pre['pins'], 'Missing preflight pin: ' + name)


def command(out):
    return [str(life.IMAGE), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
        '+PRELOAD=' + str(PRE / 'input.elf'), '+TESTCASE=' + preflight.NAME, '+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE=' + str(out / 'commit_trace.csv'), '+VECTOR_TRACE=' + str(out / 'vector_trace.csv'),
        '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(out / 'code.vdb'), '-cm_name', preflight.NAME]


def prepare(out, seal):
    out = out.absolute()
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh direct run directory required')
    pre = life.read_bound(PRE / 'preflight-manifest.json', seal)
    validate(pre); life.check(pre['pins'])
    plan = life.read_bound(life.PLAN, life.PLAN_SEAL)
    require(plan['simv'] == str(life.IMAGE) and len(plan['image']) == 66 and plan['image'][str(life.IMAGE)] ==
            '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3', 'Frozen simv66 differs')
    pins = life.merge_pins(pre['pins'], plan['image'])
    pins = life.merge_pins(pins, {str(PRE / 'preflight-manifest.json'): seal, str(life.PLAN): life.PLAN_SEAL,
        str(Path(__file__).resolve()): life.digest(Path(__file__)),
        str(Path(__file__).with_name('test_run_vnclipu_reject_simulation.py')):
            life.digest(Path(__file__).with_name('test_run_vnclipu_reject_simulation.py'))})
    life.check(pins)
    return out, dict(case=preflight.NAME, preflight=str(PRE / 'preflight-manifest.json'), preflight_seal=seal,
        command=command(out), output=str(out), pins=pins, timeout_s=BUDGET, baseline_tests=725,
        targets=pre['targets'], old_image_files_checked=66, scalar_reference_counts=pre['reference_counts'],
        authorization_source='SEPARATE_PARENT_AGENT_REVIEW_REQUIRED_BEFORE_RUN',
        coverage_admitted=False, admission_performed=False, rtl_changed=False, new_RTL_signoff=False,
        dut_self_check_verified=False, no_FSDB=True)


def run(out, manifest):
    require(manifest['timeout_s'] == BUDGET, 'Budget drift'); life.check(manifest['pins'])
    out.mkdir(); life.save(out / 'manifest.json', manifest)
    try:
        with (out / 'console.log').open('x') as log:
            result = subprocess.run(manifest['command'], cwd=out, stdout=log, stderr=subprocess.STDOUT,
                                    timeout=BUDGET, check=True)
        life.check(manifest['pins'])
        life.save(out / 'simulation-status.json', dict(status='SIMULATION_EXITED_NOT_ADMITTED',
            returncode=result.returncode, case=preflight.NAME, coverage_admitted=False, admission_performed=False))
    except Exception as error:
        drift = None
        try: life.check(manifest['pins'])
        except Exception as e: drift = str(e)
        life.save(out / 'simulation-status.json', dict(status='SIMULATION_FAILED_OR_TIMEOUT_NOT_ADMITTED',
            reason=type(error).__name__ + ': ' + str(error), post_failure_pin_error=drift,
            case=preflight.NAME, coverage_admitted=False, admission_performed=False))
        raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'verify', 'run')); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--preflight-seal', required=True); p.add_argument('--prepared-seal'); p.add_argument('--parent-authorized', action='store_true')
    a = p.parse_args(); require((a.mode != 'prepare') == bool(a.prepared_seal), 'Verify/run need fixed prepared seal')
    require((a.mode == 'run') == a.parent_authorized, 'Only separately authorized run uses --parent-authorized')
    out, manifest = prepare(a.output, a.preflight_seal); record = out.with_name(out.name + '.prepared.json')
    if a.mode == 'prepare':
        life.save(record, manifest)
        print(json.dumps(dict(prepared=str(record), seal=life.digest(record), timeout_s=BUDGET, pins=len(manifest['pins']))))
    else:
        require(life.read_bound(record, a.prepared_seal) == manifest, 'Prepared command/pins drift')
        if a.mode == 'verify': print('VERIFY_PASS simv66/725/exact5/1200wall/rawcommit/vector/noFSDB NO_VCS')
        else:
            manifest = dict(manifest, authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL')
            run(out, manifest)


if __name__ == '__main__': main()
