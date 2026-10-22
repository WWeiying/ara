"""Sealed clip17 old-image runner; prepare/verify do not launch EDA."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import build_narrow_clip_reject_preflight as preflight
import run_pure_war_simulation as frozen

life, require = preflight.life, preflight.require
NAME = 'vnarrow_clip_reject_matrix'
PRE = life.OUT / 'narrow-clip-reject-preflight-737-agent-20261006-01'
PRE_SEAL = 'f0fc1ee53df6af7c7a1b78df9ff2aa5bb4655dc2c805268dcce32606a3b7576e'
ELF = PRE / 'input.elf'
ELF_SHA = 'a0cb0f491a8cee459b93855138db8cc961a5eda74a35caea9bde5854a57a6f04'
IMAGE_SHA = '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3'
PREFLIGHT_SHA = '0605d3a3817f48df0774bf3e1dc6ecd79b6160a11304d5884bcf1d8fd35bdf2d'
ACTUAL_TEST = Path(__file__).with_name('test_actual_narrow_clip_reject_preflight.py').resolve()
ACTUAL_TEST_SHA = '9d637c5f17f2b997e4a8a487ed5fac7db3d6245ab7cdacc85a1f18003a3f19c0'
LIFECYCLE_SHA = '2e7ded5ac7c1caeff20a0d1febbb7123dbd30973a9fdef0435ad051673e11626'
BUDGET = 300


def verify_preflight():
    require(life.digest(Path(preflight.__file__)) == PREFLIGHT_SHA and
            life.digest(ACTUAL_TEST) == ACTUAL_TEST_SHA, 'Frozen preflight/test drift')
    pre = life.read_bound(PRE / 'preflight-manifest.json', PRE_SEAL)
    require(pre['case'] == NAME and pre['input_elf'] == str(ELF) and
            pre['elf_sha256'] == ELF_SHA and pre['checks'] == 2094 and
            pre['trap_cells'] == 17 and pre['full_VRF_snapshots'] == 3 and
            pre['old_image_files_checked'] == 66 and pre['rtl_changed'] is False and
            pre['DUT_differential_executed'] is False and
            pre['legal_narrow_compute_executed'] is False and
            pre['pins'].get(str(ELF)) == ELF_SHA and life.digest(ELF) == ELF_SHA,
            'Exact clip17 sealed preflight required')
    require(pre['validation']['checks'] == 2094 and pre['validation']['illegal_traps'] == 17 and
            pre['validation']['illegal_vector_writes'] == 0 and
            pre['validation']['three_full_VRF_snapshots'] is True and
            pre['validation']['rejected_backend_native_zero_required_at_DUT'] is True,
            'Full rejection/preservation oracle required')
    require(preflight.verify(PRE, PRE_SEAL) == pre, 'Independent preflight replay differs')
    return pre


def command(out):
    return [str(life.IMAGE), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
            '+PRELOAD=' + str(ELF), '+TESTCASE=' + NAME, '+COMMIT_TOHOST=80001000',
            '+COMMIT_TRACE=' + str(out / 'commit_trace.csv'),
            '+VECTOR_TRACE=' + str(out / 'vector_trace.csv'),
            '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(out / 'code.vdb'), '-cm_name', NAME]


def runtime_inputs(pre):
    plan = life.read_bound(life.PLAN, life.PLAN_SEAL)
    runtime = plan['image']
    require(plan['simv'] == str(life.IMAGE) and len(runtime) == 66 and
            runtime.get(str(life.IMAGE)) == IMAGE_SHA and
            all(pre['pins'].get(path) == sha for path, sha in runtime.items()),
            'Frozen runtime66 differs or missing from sealed preflight')
    return runtime


def manifest(out):
    require(out.parent == life.OUT and out.resolve() == out, 'Direct run directory required')
    pre = verify_preflight()
    image = runtime_inputs(pre)
    require(life.digest(Path(frozen.__file__)) == LIFECYCLE_SHA, 'Frozen lifecycle drift')
    deps = {str(Path(__file__).resolve()): life.digest(Path(__file__)),
            str(Path(__file__).with_name('test_run_narrow_clip_reject_simulation.py').resolve()):
                life.digest(Path(__file__).with_name('test_run_narrow_clip_reject_simulation.py')),
            str(ACTUAL_TEST): ACTUAL_TEST_SHA,
            str(Path(preflight.__file__).resolve()): PREFLIGHT_SHA,
            str(Path(frozen.__file__).resolve()): LIFECYCLE_SHA,
            str(PRE / 'preflight-manifest.json'): PRE_SEAL, str(life.PLAN): life.PLAN_SEAL}
    pins = life.merge_pins(life.merge_pins(pre['pins'], image), deps)
    life.check(pins)
    return dict(case=NAME, output=str(out), preflight=str(PRE / 'preflight-manifest.json'),
                preflight_seal=PRE_SEAL, input_elf=str(ELF), elf_sha256=ELF_SHA,
                image_sha256=IMAGE_SHA, pins=pins, command=command(out), timeout_s=BUDGET,
                old_image_files_checked=66, software_checks=2094, exact_illegal_traps=17,
                full_VRF_snapshots=3, targets=pre['targets'], static_baseline=737,
                raw_gain_requires_latest_formal_population_at_least=737,
                scalar_reference_counts=pre['reference_counts'], foreground_lifetime=True,
                normal_wait_calls=1, automatic_retry=False, no_FSDB=True,
                coverage_admitted=False, admission_performed=False, rtl_changed=False,
                native_cycle_qualified=False, terminal_oracle_verified=False,
                legal_narrow_compute_executed=False, simulator_exit_is_not_functional_pass=True,
                qualification_required='Full scalar/vector/CSR/trap/memory; exact17 owners zero backend/native; no interstitial vector writers',
                systemd_policy=dict(RuntimeMaxSec=360, TimeoutStopSec=10, KillMode='control-group'))


def prepare(out):
    require(not out.exists(), 'Fresh run required; no retry')
    return manifest(out)


def verify_prepared(out, record):
    require(record == manifest(out), 'Prepared pins/command/fields drift')
    return record


def invoke_run(out, record):
    require(prepare(out) == record, 'Reviewed execution drift')
    bindings = dict(PRE=PRE, ELF_SEAL=ELF_SHA, IMAGE_SEAL=IMAGE_SHA, BUDGET=BUDGET,
                    preflight=SimpleNamespace(NAME=NAME), command=command)
    previous = {key: getattr(frozen, key) for key in bindings}
    try:
        for key, value in bindings.items():
            setattr(frozen, key, value)
        frozen.run(out, record)
    finally:
        for key, value in previous.items():
            setattr(frozen, key, value)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify', 'run'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prepared-seal')
    parser.add_argument('--parent-authorized', action='store_true')
    a = parser.parse_args(argv)
    require((a.mode != 'prepare') == bool(a.prepared_seal), 'Verify/run need reviewed sidecar seal')
    require((a.mode == 'run') == a.parent_authorized, 'Explicit separate parent run authorization required')
    out = a.output.absolute()
    sidecar = out.with_name(out.name + '.prepared.json')
    if a.mode == 'prepare':
        require(not sidecar.exists(), 'Fresh sidecar required')
        record = prepare(out)
        life.save(sidecar, record)
        print(json.dumps(dict(prepared=str(sidecar), seal=life.digest(sidecar), timeout_s=BUDGET, VCS_started=False)))
    else:
        record = life.read_bound(sidecar, a.prepared_seal)
        if a.mode == 'run':
            invoke_run(out, record)
        else:
            verify_prepared(out, record)
            print('VERIFY_PASS NO_VCS')


if __name__ == '__main__':
    main()
