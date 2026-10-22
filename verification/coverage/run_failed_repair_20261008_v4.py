#!/usr/bin/env python3
"""Continue acceptance04: re-audit its six completed runs, then 17 neighbours.

Preparation only by default. No simulator retry of any of the six originals.
The sole FAIL exception is the pinned FOF tracer-format checker error, and
requires a reviewed FOF v3 PASS receipt plus a fresh strict offline re-audit.
Sealed runners/checkers and original receipts are never edited.
"""
import argparse
import importlib
from pathlib import Path
import json
import sys

import run_failed_repair_20261008_v3 as prior

legacy, base, ROOT = prior.legacy, prior.base, prior.ROOT
require = prior.require
FOCUSED, NEIGHBOURS = prior.FOCUSED, prior.NEIGHBOURS
PREVIOUS = ROOT / 'verification/out/failed-repair-acceptance-20261008-04'
IMAGE_DIR = ROOT / 'verification/out/failed-repair-image-20261008-03'
PRIOR_SHA = '3e3099d5b9fd99fec058c18cddd4e4731ee258cb9e9c0fafd2bc0efffd29e755'
FOF = 'vgap112_sv39_fof'
FOF_REASON = 'ValueError: Exactly one S ECALL cause/PC/tval; no FOF page fault'
FOF_FAILURE_SHA = '16519bb53ca8ecc4b01ef028dd141f15c62ae49726b731b110e886ab0c9a9e48'
FOF_CHECKER_SHA = '17047054ff82c8495c6a7f480c0cc198a7543d545efa1fd294d7ecc02bdc104a'
FOF_INPUTS = ('input.elf', 'console.log', 'run.vcs.log', 'commit_trace.csv',
              'vector_trace.csv', 'trace_hart_0.log')
# Parent confirmed Ampere's full replay; retain the original FAIL separately.
FOF_RECEIPT = ROOT / 'verification/out/fof-build03-complete-reaudit-agent-20261008-01/audit.json'
FOF_RECEIPT_SHA = 'b9897aa628f487941015411c374f28a38f514c5ccd748a46262b42f960cb0806'


def fof_checker():
    path = Path(__file__).with_name('audit_fof_repair_v3.py')
    require(base.sha256(path) == FOF_CHECKER_SHA, 'FOF v3 checker seal changed')
    return importlib.import_module('audit_fof_repair_v3')


def previous_state(previous, image, image_dir):
    require(previous.resolve() == PREVIOUS.resolve(), 'only acceptance04 may be reused')
    require(image_dir.resolve() == IMAGE_DIR.resolve(), 'only build03 may be reused')
    pins = prior.same_build(previous, image, image_dir)
    path = str(Path(prior.__file__).resolve())
    require(pins.get(path) == PRIOR_SHA and base.sha256(Path(path)) == PRIOR_SHA,
            'acceptance04 sealed v3 runner identity differs')
    state = base.read(previous / 'status.json')
    require(state.get('status') in ('STOPPED', 'PASS'), 'acceptance04 is not terminal')
    require(state.get('total') == 23 and set(state.get('cases', {})) == set(prior.EXPECTED_SCOPE),
            'acceptance04 scope differs')
    # Originals must never fall through to legacy.run's simulator launch path.
    for name in FOCUSED:
        original_receipt(previous, state, name)
    return state


def original_receipt(previous, state, name):
    old = previous / 'results' / name
    require((old / 'audit.json').is_file(), 'missing completed original; refuse simulator retry: ' + name)
    receipt = base.read(old / 'audit.json')
    require(state['cases'][name] == receipt and receipt.get('directory') == str(old),
            'case receipt/source directory mismatch')
    corrected = (name == FOF and receipt.get('status') == 'FAIL' and
                 receipt.get('reason') == FOF_REASON and
                 base.sha256(old / 'audit.json') == FOF_FAILURE_SHA)
    require(receipt.get('status') == 'PASS' or corrected,
            'unqualified FAIL/incomplete evidence; only pinned FOF tracer error is eligible')
    require(not receipt.get('reused_completed_same_image'), 'acceptance04 must contain fresh build03 runs')
    return receipt, corrected


def qualified_fof_receipt():
    require(FOF_RECEIPT is not None and FOF_RECEIPT_SHA is not None,
            'reviewed FOF v3 receipt path and SHA are required before execution')
    path = Path(FOF_RECEIPT).resolve(strict=True)
    require(base.sha256(path) == FOF_RECEIPT_SHA, 'FOF qualification receipt changed')
    receipt = base.read(path)
    checker = fof_checker()
    require(receipt.get('status') == 'PASS' and receipt.get('case') == checker.base.CASE and
            receipt.get('checker') == 'audit_fof_repair_v3', 'FOF qualification did not strictly pass v3')
    old = PREVIOUS / 'results' / FOF
    require(receipt.get('directory') == str(old), 'FOF receipt is not acceptance04 evidence')
    require(receipt.get('original_failure_receipt') == str(old / 'audit.json') and
            receipt.get('original_failure_receipt_sha256') == FOF_FAILURE_SHA and
            base.sha256(old / 'audit.json') == FOF_FAILURE_SHA, 'FOF original failure seal differs')
    pins = receipt.get('input_pins', {})
    require(pins.get(str(Path(checker.__file__).resolve())) == FOF_CHECKER_SHA,
            'FOF receipt lacks v3 checker pin')
    for name in FOF_INPUTS:
        require(pins.get(str(old / name)) == base.sha256(old / name),
                'FOF receipt input mismatch: ' + name)
    base.check(pins)
    return receipt


def audit(directory, name):
    if name != FOF:
        return prior.audit(directory, name)
    prior.completed_logs(directory, name)
    result = fof_checker().audit(directory)
    require(result.get('status') == 'PASS', 'strict FOF v3 re-audit failed')
    return result


def link_raw(directory, old):
    require(directory.resolve() != old.resolve(), 're-audit must use a new directory')
    require(all(p.name in ('input.elf', 'spike.trace') for p in directory.iterdir()),
            're-audit destination is not fresh')
    # Never carry over generated audit subdirectories, JSON outputs or code.vdb.
    # In particular qbs-canonical-audit-v3 must be newly created by prior.audit.
    for name in prior.RAW_FILES:
        source = old / name
        if source.is_file():
            (directory / name).symlink_to(source.resolve(strict=True))


def reuse_pass(directory, name, previous, image, image_dir):
    require(name in prior.EXPECTED_SCOPE, 'case outside fixed 6+17 scope')
    state = previous_state(previous, image, image_dir)
    old = previous / 'results' / name
    if not (old / 'audit.json').is_file():
        require(name in NEIGHBOURS and state['cases'][name].get('status') == 'QUEUED' and
                (not old.exists() or all(p.name in ('input.elf', 'spike.trace') for p in old.iterdir())),
                'incomplete previous attempt; no automatic simulator retry')
        return None
    receipt, corrected = original_receipt(previous, state, name)
    before = base.pins(p for p in old.iterdir() if p.is_file())
    before.update(base.pins([previous / 'status.json', previous / 'source-pins.json']))
    launch, command = base.read(old / 'started.json'), base.read(old / 'command.json')
    require(command.get('cwd') == str(old) and (old / 'started.json').resolve().parent == old.resolve(),
            'unbound launch directory')
    require(launch.get('image') == str(image) and launch.get('image_sha256') == base.sha256(image),
            'previous simulator image differs')
    require(launch.get('elf_sha256') == base.sha256(legacy.source(name) / 'input.elf') ==
            base.sha256(old / 'input.elf') == base.sha256(directory / 'input.elf'), 'previous ELF differs')
    if (legacy.source(name) / 'spike.trace').is_file():
        require(base.sha256(old / 'spike.trace') == base.sha256(directory / 'spike.trace') ==
                base.sha256(legacy.source(name) / 'spike.trace'), 'Spike reference differs')
    require(launch.get('command') == command.get('command') ==
            legacy.simulation_command(image, old, name) and command.get('timeout_s') == 1800,
            'launch command/timeout differs')
    terminal = prior.completed_logs(old, name)
    qualified = qualified_fof_receipt() if name == FOF else None
    if qualified is not None:
        before.update(base.pins([Path(FOF_RECEIPT)]))
        before.update(qualified['input_pins'])
    link_raw(directory, old)
    evidence = audit(directory, name)
    require(evidence.get('status', 'PASS') == 'PASS', 'strict re-audit failed')
    if qualified is not None:
        # Locations/pins change in a new directory; all substantive results must
        # match the qualified full replay, including mtval and native FOF bytes.
        for key in ('case', 'elf_sha256', 'scalar', 'scalar_memory', 'footprint',
                    'native', 'lifecycle', 'tracer', 'checker'):
            require(key in qualified and evidence.get(key) == qualified[key],
                    'FOF re-audit disagrees with qualified receipt: ' + key)
    prior.same_build(previous, image, image_dir)
    base.check(before)
    return dict(status='PASS', evidence=evidence, last_cycle=terminal['last_cycle'], terminal=terminal,
                reused_completed_same_image=str(old), simulation_launched=False,
                previous_status=receipt['status'], checker_error_reclassified=corrected,
                original_receipt_sha256=before[str((old / 'audit.json').resolve())],
                qualification_receipt=str(FOF_RECEIPT) if qualified is not None else None,
                evidence_pins=before, coverage_admitted=False, old_vdb_reuse=False,
                image_provenance_verified=True, simulator_process_exit_verified=False,
                process_exit_basis='Zero exit inferred from sealed v2 wait/code/pin-check-before-audit '
                                   'and sealed v3 audit dispatch plus terminal receipt; '
                                   'no independent exit-code artifact')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args, remaining = parser.parse_known_args(argv)
    require(FOCUSED + NEIGHBOURS == prior.EXPECTED_SCOPE and (len(FOCUSED), len(NEIGHBOURS)) == (6, 17),
            'bounded acceptance scope changed')
    if not args.execute:
        print(json.dumps(dict(status='PREPARED_ONLY', reuse_only=FOCUSED, neighbours=NEIGHBOURS,
            required_previous=str(PREVIOUS), required_build=str(IMAGE_DIR),
            qualified_fof_receipt_required=True, full_regression_started=False), indent=2))
        return 0
    config = argparse.ArgumentParser(add_help=False)
    config.add_argument('--previous-output', type=Path, required=True)
    config.add_argument('--wait-previous-unit', required=True)
    config.add_argument('--image-directory', type=Path, required=True)
    selected, _ = config.parse_known_args(remaining)
    selected.previous_output = selected.previous_output.resolve(strict=True)
    selected.image_directory = selected.image_directory.resolve(strict=True)
    require(base.sha256(Path(prior.__file__)) == PRIOR_SHA and
            base.sha256(Path(legacy.__file__)) == prior.V2_SHA, 'sealed runner changed')
    # Import both current checkers before legacy.main captures transitive pins.
    prior.checker()
    fof_checker()
    previous_state(selected.previous_output, selected.image_directory / 'sim/simv', selected.image_directory)
    qualified_fof_receipt()
    old_audit, old_reuse, old_argv = legacy.audit, legacy.reuse_pass, sys.argv
    try:
        legacy.audit, legacy.reuse_pass = audit, reuse_pass
        sys.argv = [str(Path(__file__).resolve()), *remaining]
        return legacy.main()
    except Exception as error:
        if legacy.ACTIVE_OUTPUT is not None:
            target = legacy.ACTIVE_OUTPUT / 'status.json'
            state = base.read(target) if target.is_file() else {}
            state.update(status='STOPPED', controller_error=f'{type(error).__name__}: {error}')
            base.save(target, state)
        raise
    finally:
        legacy.audit, legacy.reuse_pass, sys.argv = old_audit, old_reuse, old_argv


if __name__ == '__main__':
    raise SystemExit(main())
