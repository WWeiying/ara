"""Single reviewed foreground simv66 run; prepare never starts simulation."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import build_readonly_csr_preflight as preflight
import run_pure_war_simulation as frozen

life, require = preflight.life, preflight.require
BUDGET = 600
LIFECYCLE_SHA = '2e7ded5ac7c1caeff20a0d1febbb7123dbd30973a9fdef0435ad051673e11626'


def command(out, directory):
    return [str(life.IMAGE), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
        '+PRELOAD=' + str(directory / 'input.elf'), '+TESTCASE=' + preflight.NAME,
        '+COMMIT_TOHOST=80001000', '+COMMIT_TRACE=' + str(out / 'commit_trace.csv'),
        '+VECTOR_TRACE=' + str(out / 'vector_trace.csv'), '-cm', 'line+cond+fsm+tgl+branch',
        '-cm_dir', str(out / 'code.vdb'), '-cm_name', preflight.NAME]


def prepare(out, directory, seal):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh direct run required')
    require(directory.parent == life.OUT and directory.resolve() == directory, 'Direct sealed preflight required')
    pre = preflight.verify(directory, seal)
    image = preflight.image_inputs()
    require(life.digest(Path(frozen.__file__)) == LIFECYCLE_SHA, 'Frozen lifecycle drift')
    pins = life.merge_pins(pre['pins'], image)
    deps = (Path(__file__).resolve(), Path(__file__).with_name('test_run_readonly_csr_simulation.py'))
    pins = life.merge_pins(pins, {str(p): life.digest(p) for p in deps})
    pins = life.merge_pins(pins, {str(directory / 'preflight-manifest.json'): seal,
        str(Path(frozen.__file__).resolve()): LIFECYCLE_SHA})
    life.check(pins)
    return dict(case=preflight.NAME, output=str(out), preflight=str(directory / 'preflight-manifest.json'),
        preflight_seal=seal, command=command(out, directory), pins=pins, timeout_s=BUDGET,
        elf_sha256=pre['elf_sha256'], image_sha256=preflight.IMAGE_SHA, old_image_files_checked=66,
        software_checks=preflight.CHECKS, exact_illegal_traps=12, targets=pre['targets'],
        static_baseline=733, raw_gain_requires_latest_formal_population_at_least=733,
        foreground_lifetime=True, automatic_retry=False, coverage_admitted=False,
        admission_performed=False, native_cycle_qualified=False, parent_review_required=True,
        terminal_qualification_required='Full scalar/vector/ELF/store/CSR/trap/postpins, not software PASS alone',
        systemd_policy=dict(RuntimeMaxSec=660, TimeoutStopSec=10, KillMode='control-group'))


def invoke_run(out, manifest):
    directory = Path(manifest['preflight']).parent
    require(prepare(out, directory, manifest['preflight_seal']) == manifest, 'Reviewed execution drift')
    bindings = dict(PRE=directory, ELF_SEAL=manifest['elf_sha256'],
        preflight=SimpleNamespace(NAME=preflight.NAME), command=lambda output: command(output, directory))
    previous = {key: getattr(frozen, key) for key in bindings}
    try:
        for key, value in bindings.items(): setattr(frozen, key, value)
        frozen.run(out, manifest)
    finally:
        for key, value in previous.items(): setattr(frozen, key, value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify', 'run'))
    parser.add_argument('--preflight', type=Path, required=True); parser.add_argument('--preflight-seal', required=True)
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--prepared-seal')
    parser.add_argument('--parent-authorized', action='store_true')
    a = parser.parse_args()
    require((a.mode != 'prepare') == bool(a.prepared_seal), 'Verify/run need reviewed seal')
    require((a.mode == 'run') == a.parent_authorized, 'Explicit separate parent run authorization required')
    out = a.output.absolute(); manifest = prepare(out, a.preflight.absolute(), a.preflight_seal)
    record = out.with_name(out.name + '.prepared.json')
    if a.mode == 'prepare':
        require(not record.exists(), 'Prepared sidecar already exists')
        life.save(record, manifest)
        print(json.dumps(dict(prepared=str(record), seal=life.digest(record), vcs_started=False)))
    else:
        require(life.read_bound(record, a.prepared_seal) == manifest, 'Prepared sidecar drift')
        if a.mode == 'run': invoke_run(out, manifest)
        else: print('VERIFY_PASS simv66/733checks/600s NO_VCS')


if __name__ == '__main__': main()
