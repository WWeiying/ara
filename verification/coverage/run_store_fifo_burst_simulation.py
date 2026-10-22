"""Prepare one foreground 600s old-image run; never launch without parent review."""
import argparse
import json
from pathlib import Path

import build_store_fifo_burst_preflight_v2 as adapter
import run_pure_war_simulation as frozen

p = adapter.library
life, require = p.life, p.require
PRE = life.OUT / 'store-fifo-burst-preflight-v2-729-agent-20261006-01'
BUDGET = 600
FROZEN_SHA = '2e7ded5ac7c1caeff20a0d1febbb7123dbd30973a9fdef0435ad051673e11626'


def validate(pre):
    require(pre['status'] == p.STATUS and pre['case'] == p.NAME and pre['baseline_tests'] == 729 and
            pre['baseline_manifest_sha256'] == p.BASE_SEAL and pre['checks'] == 2360 and
            pre['vcs_started'] is False and pre['rtl_changed'] is False and pre['coverage_admitted'] is False and
            pre['measured_raw_increment'] is None and pre['duplicate729_ELF'] is False, 'Preflight contract differs')
    expected = dict(status=p.STATUS, checks=2360, bursts=7, target_stores=56, lengths=list(p.LENGTHS),
                    destination_words=2016, source_words=36, source_dump_words=252, CSR_words=56,
                    exceptions=0, coverage_admitted=False, native_scheduling_measured=False)
    require(pre['validation'] == expected and len(pre['targets']) == 8 and
            all(t['hit729'] is False and t['native_GUI_binding'] is False for t in pre['targets']), 'Oracle/targets differ')
    require(pre['pins'][str(PRE / 'input.elf')] == pre['input_elf_sha256'] and
            pre['symbols']['tohost'] == 0x80001000, 'ELF/terminal identity differs')


def command(out):
    return [str(life.IMAGE), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
            '+PRELOAD=' + str(PRE / 'input.elf'), '+TESTCASE=' + p.NAME, '+COMMIT_TOHOST=80001000',
            '+COMMIT_TRACE=' + str(out / 'commit_trace.csv'), '+VECTOR_TRACE=' + str(out / 'vector_trace.csv'),
            '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(out / 'code.vdb'), '-cm_name', p.NAME]


def prepare(out, preseal):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh direct output required')
    pre = p.verify(PRE, preseal)
    validate(pre)
    image = life.read_bound(life.PLAN, life.PLAN_SEAL)
    require(image['simv'] == str(life.IMAGE) and len(image['image']) == 66 and
            image['image'][str(life.IMAGE)] == frozen.IMAGE_SEAL, 'Exact old simv66 differs')
    require(life.digest(Path(frozen.__file__)) == FROZEN_SHA, 'Frozen lifecycle drift')
    pins = life.merge_pins(pre['pins'], image['image'])
    pins = life.merge_pins(pins, {
        str(PRE / 'preflight-manifest.json'): preseal,
        str(Path(frozen.__file__).resolve()): FROZEN_SHA,
        str(Path(__file__).resolve()): life.digest(Path(__file__)),
        str(Path(__file__).with_name('test_run_store_fifo_burst_simulation.py')):
            life.digest(Path(__file__).with_name('test_run_store_fifo_burst_simulation.py')),
        str(Path(frozen.preflight.__file__).resolve()): life.digest(Path(frozen.preflight.__file__)),
    })
    life.check(pins)
    return dict(case=p.NAME, preflight=str(PRE / 'preflight-manifest.json'), preflight_seal=preseal,
                command=command(out), output=str(out), pins=pins, timeout_s=BUDGET,
                baseline_tests=729, targets=pre['targets'], old_image_files_checked=66,
                scalar_reference_counts=pre['reference_counts'], elf_sha256=pre['input_elf_sha256'],
                image_sha256=frozen.IMAGE_SEAL, foreground_lifetime=True, automatic_retry=False,
                authorization_source='SEPARATE_PARENT_REVIEW_REQUIRED_BEFORE_RUN',
                systemd_policy=dict(RuntimeMaxSec=630, TimeoutStopSec=10, KillMode='control-group'),
                coverage_admitted=False, admission_performed=False, rtl_changed=False, new_RTL_signoff=False,
                native_scheduling_measured=False, simulator_exit_is_not_functional_pass=True,
                qualification_required='Complete RVFI/vector/software/guard/source oracle plus latest raw gain; record all UVM errors')


def invoke_run(out, manifest):
    require(manifest['command'] == command(out) and manifest['timeout_s'] == BUDGET and
            manifest['baseline_tests'] == 729 and manifest['coverage_admitted'] is False,
            'Execution contract differs')
    require(life.digest(Path(frozen.__file__)) == FROZEN_SHA, 'Frozen lifecycle drift')
    # Reuse the reviewed foreground wait/timeout cleanup, not its DIV/indexed-load inputs.
    bindings = dict(PRE=PRE, ELF_SEAL=manifest['elf_sha256'], preflight=p, command=command)
    previous = {name: getattr(frozen, name) for name in bindings}
    try:
        for name, value in bindings.items():
            setattr(frozen, name, value)
        frozen.run(out, manifest)
    finally:
        for name, value in previous.items():
            setattr(frozen, name, value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify', 'run'))
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--preflight-seal', required=True)
    parser.add_argument('--prepared-seal')
    parser.add_argument('--parent-authorized', action='store_true')
    args = parser.parse_args()
    require((args.mode != 'prepare') == bool(args.prepared_seal), 'Verify/run require prepared seal')
    require((args.mode == 'run') == args.parent_authorized, 'Run requires separate parent authorization')
    out = args.output.absolute()
    record = out.with_name(out.name + '.prepared.json')
    manifest = prepare(out, args.preflight_seal)
    if args.mode == 'prepare':
        life.save(record, manifest)
        print(json.dumps(dict(prepared=str(record), seal=life.digest(record), budget_seconds=BUDGET, vcs_started=False)))
    else:
        require(life.read_bound(record, args.prepared_seal) == manifest, 'Prepared inputs/command drift')
        if args.mode == 'verify':
            print('VERIFY_PASS exact729/eight-targets/2360checks/simv66/600s NO_VCS')
        else:
            invoke_run(out, manifest)


if __name__ == '__main__':
    main()
