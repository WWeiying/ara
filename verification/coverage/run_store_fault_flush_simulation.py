"""Case-specific simv66/600s foreground runner. Separate parent authorization required."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import build_store_fault_flush_preflight_v3 as preflight
import run_pure_war_simulation as frozen

p = preflight.guarded.frozen
life, require = p.life, p.require
BUDGET = 600
LIFECYCLE_SHA = '2e7ded5ac7c1caeff20a0d1febbb7123dbd30973a9fdef0435ad051673e11626'
PRE = life.OUT / 'store-fault-flush-preflight-v3-parent-20261006-01'
PRE_SEAL = '9ca0579d7f3fb7cd9acd37d6e2c711e8996357714e524c36d39a7a3b2aad2fab'


def verify_preflight(directory, seal):
    require(directory == PRE and seal == PRE_SEAL, 'Exact parent preflight seal required')
    require(directory.parent == life.OUT and directory.resolve() == directory, 'Direct preflight required')
    pre = life.read_bound(directory / 'preflight-manifest.json', seal)
    require(pre['status'] == 'STORE_FAULT_FLUSH_HOST_SPIKE_PASS_NOT_DUT_NOT_ADMITTED' and
            pre['case'] == p.NAME and pre['baseline'] == 731 and pre['baseline_seal'] == p.BASE_SEAL and
            pre['vcs_started'] is False and pre['coverage_admitted'] is False and
            pre['raw_gain'] is None and pre['native_timing_observed'] is False and
            pre['simulation_timeout_s'] == BUDGET, 'Strict preflight contract differs')
    expected = dict(status='HOST_SPIKE_ARCHITECTURE_PASS_NOT_DUT', checks=134, buffers_words=100,
        exact_traps=1, cause=7, tval=p.BAD, fault_vstart=0, recovery_words=8,
        trap_information_preserved=True, whole_ISA_qualified=False,
        native_B_error_plus_addr_fault_measured=False)
    require(pre['validation'] == expected, 'Strict134 oracle differs')
    pins = pre['pins']; life.check(pins)
    require(pins[str(directory / 'input.elf')] == pre['input_elf_sha256'] and
            pre['symbols']['tohost'] == 0x80001000 and pre['symbols']['_end'] < 0x80200000,
            'ELF identity/range differs')
    receipt = json.loads((directory / 'target-receipt.json').read_bytes())
    require(receipt['spike_memory_successor']['option'] == preflight.RAM and
            receipt['spike_memory_successor']['expected_cause'] == 7 and
            receipt['spike_memory_successor']['expected_vstart'] == 0, 'Explicit memory receipt required')
    expected_command = [str(p.shared.SPIKE), '--isa=rv64gcv_zvl1024b', '--priv=msu', '--pmpregions=0',
                        preflight.RAM, '-l', '--log-commits', str(directory / 'input.elf')]
    require(json.loads((directory / 'spike-command.json').read_bytes()) == expected_command,
            'Exact single RAM Spike command differs')
    reference = p.shared.parse_spike_commits(directory / 'spike.trace')
    require(p.validate(reference, pre['symbols'], (directory / 'spike.trace').read_text()) == expected,
            'Reference134 replay differs')
    return pre


def command(out, directory):
    return [str(life.IMAGE), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
        '+PRELOAD=' + str(directory / 'input.elf'), '+TESTCASE=' + p.NAME, '+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE=' + str(out / 'commit_trace.csv'), '+VECTOR_TRACE=' + str(out / 'vector_trace.csv'),
        '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(out / 'code.vdb'), '-cm_name', p.NAME]


def prepare(out, directory, seal):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh direct run required')
    pre = verify_preflight(directory, seal)
    image = life.read_bound(preflight.guarded.PLAN, preflight.guarded.PLAN_SHA)
    require(image['simv'] == str(life.IMAGE) and len(image['image']) == 66 and
            image['image'][str(life.IMAGE)] == preflight.guarded.IMAGE_SHA, 'Frozen simv66 differs')
    require(life.digest(Path(frozen.__file__)) == LIFECYCLE_SHA, 'Frozen lifecycle drift')
    pins = life.merge_pins(pre['pins'], image['image'])
    deps = [Path(__file__).resolve(), Path(__file__).with_name('test_run_store_fault_flush_simulation.py')]
    pins = life.merge_pins(pins, {str(x): life.digest(x) for x in deps})
    pins = life.merge_pins(pins, {str(directory / 'preflight-manifest.json'): seal,
        str(Path(frozen.__file__).resolve()): LIFECYCLE_SHA,
        str(preflight.guarded.PLAN): preflight.guarded.PLAN_SHA})
    life.check(pins)
    return dict(case=p.NAME, output=str(out), preflight=str(directory / 'preflight-manifest.json'),
        preflight_seal=seal, command=command(out, directory), pins=pins, timeout_s=BUDGET,
        old_image_files_checked=66, image_sha256=preflight.guarded.IMAGE_SHA,
        elf_sha256=pre['input_elf_sha256'], software_checks=134, static_provenance_population=731,
        raw_gain_requires_latest_formal_baseline_at_least=732, foreground_lifetime=True,
        automatic_retry=False, coverage_admitted=False, admission_performed=False,
        native_internal_timing_observed=False, systemd_policy=dict(RuntimeMaxSec=660,
        TimeoutStopSec=10, KillMode='control-group'), parent_review_required=True)


def invoke_run(out, manifest):
    directory = Path(manifest['preflight']).parent
    require(prepare(out, directory, manifest['preflight_seal']) == manifest, 'Prepared execution drift')
    bindings = dict(PRE=directory, ELF_SEAL=manifest['elf_sha256'],
        preflight=SimpleNamespace(NAME=p.NAME), command=lambda output: command(output, directory))
    previous = {key: getattr(frozen, key) for key in bindings}
    try:
        for key, value in bindings.items(): setattr(frozen, key, value)
        frozen.run(out, manifest)
    finally:
        for key, value in previous.items(): setattr(frozen, key, value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify', 'run'))
    parser.add_argument('--preflight', type=Path, required=True)
    parser.add_argument('--preflight-seal', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prepared-seal')
    parser.add_argument('--parent-authorized', action='store_true')
    args = parser.parse_args()
    require((args.mode != 'prepare') == bool(args.prepared_seal), 'Reviewed seal required for verify/run')
    require((args.mode == 'run') == args.parent_authorized, 'Explicit separate run authorization required')
    out = args.output.absolute()
    manifest = prepare(out, args.preflight.absolute(), args.preflight_seal)
    record = out.with_name(out.name + '.prepared.json')
    if args.mode == 'prepare':
        require(not record.exists(), 'Prepared sidecar already exists')
        life.save(record, manifest)
        print(json.dumps(dict(prepared=str(record), seal=life.digest(record), vcs_started=False)))
    else:
        require(life.read_bound(record, args.prepared_seal) == manifest, 'Prepared sidecar drift')
        if args.mode == 'run': invoke_run(out, manifest)
        else: print('VERIFY_PASS simv66/134checks/600s NO_VCS')


if __name__ == '__main__': main()
