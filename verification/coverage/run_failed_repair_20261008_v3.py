#!/usr/bin/env python3
"""Bounded v2 successor: same-build re-audit, one pinned QBS checker exception.

Preparation only unless --execute is explicitly supplied. No build, automatic
retry of failures, old-image coverage merge, or full-suite expansion. The v2
dispatcher is reused in memory; its sealed source file is never rewritten.
"""
import argparse
import importlib
import json
from pathlib import Path
import re
import shutil
import sys

import run_failed_repair_20261008_v2 as legacy
from ara_verify.contract import parse_contract_summary

base = legacy.base
ROOT = legacy.ROOT
FOCUSED = tuple(legacy.FOCUSED)
NEIGHBOURS = tuple(legacy.NEIGHBOURS)
EXPECTED_SCOPE = (
    'vgap76_red16', 'mask_restart', 'qbs_canonical', 'vgap101_illegal_segment_store',
    'vmemory_emul_r2_boundary_reject', 'vgap112_sv39_fof',
    'axpy', 'vgap35_carry_ta', 'vgap35_slide_bound', 'gap71_qbs_fault', 'gap71_qbs_read',
    'gap71_akv_fault', 'gap71_akv_read', 'akv_gap73_v1_onehot',
    'vgap75_ext16_f2', 'vgap75_ext32_f4', 'vgap75_ext64_f2', 'vgap75_ext64_f4',
    'vgap75_ext64_f8', 'vgap75_red16', 'vgap75_red32', 'vgap75_red64', 'vgap76_red32')
LEGACY_AUDIT = legacy.audit
V2_SHA = 'ee7cd27dd907c71bfbf36f5d41b81a494e465a2d680cfb1f88f1185e219b2f3a'
QBS_CHECKER_SHA = '3f4a87537a63e443f7415396ee5fe43620f138785fcf4bc153480ec0925955f8'
# Ampere seal confirmed by parent after its 15-test offline acceptance.
FOF_CHECKER_SHA = '3b7e93f1722d81eeea4989aa2dbdf1f6eb498b486db1ecff5c108da4837e95c0'
PREVIOUS = ROOT / 'verification/out/failed-repair-acceptance-20261008-03'
QBS_FAILURE_SHA = '6b953c059f5d8f2387fd1192fb3c7ae6694066861d2c2caded28749e4effc1f5'
QBS_RECEIPT = ROOT / 'verification/out/qbs-canonical-repair-v2-audit-20261008-02/receipt.json'
QBS_RECEIPT_SHA = 'ded9b3364cc35b6dcf98cced5a68c7bbbf235dbb2f0babb49b9e55ced0cfa55c'
V1_SHA = 'f613271ac03e5343e039bd8365f26c66cfbededb2fd3f7c0dc4d4a5329299c48'
QBS_REASON = 'ValueError: Exact terminal tohost store'
RAW_FILES = ('console.log', 'run.vcs.log', 'commit_trace.csv', 'vector_trace.csv',
             'trace_hart_0.log', 'trace_hart_0_commit.log', 'qbs-canonical-focused.vpd')
QBS_INPUTS = ('input.elf', 'console.log', 'run.vcs.log', 'commit_trace.csv',
              'vector_trace.csv', 'qbs-canonical-focused.vpd')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def checker():
    module = importlib.import_module('audit_qbs_canonical_repair_v2')
    require(base.sha256(Path(module.__file__)) == QBS_CHECKER_SHA,
            'QBS v2 checker changed after its reviewed 24-test closure')
    return module


def fof_checker():
    require(FOF_CHECKER_SHA is not None, 'FOF v2 checker awaits Ampere final hash confirmation')
    module = importlib.import_module('audit_fof_repair_v2')
    require(base.sha256(Path(module.__file__)) == FOF_CHECKER_SHA,
            'FOF v2 checker changed after review')
    return module


def same_build(previous, image, image_dir):
    require(base.read(image_dir / 'build-status.json').get('status') == 'PASS',
            'completed source-checked build required')
    image_pins = base.read(image_dir / 'build-image.json')
    source_pins = base.read(image_dir / 'build-source-pins.json')
    require(image_pins and source_pins and str(image) in image_pins,
            'missing image/source identity')
    require(image.resolve() == (image_dir / 'sim/simv').resolve(), 'wrong selected image')
    expected = dict(source_pins)
    expected.update(image_pins)
    pins = base.read(previous / 'source-pins.json')
    require(all(pins.get(path) == value for path, value in expected.items()),
            'previous evidence is not the exact same build/source; new FOF build requires fresh runs')
    require(pins.get(str(Path(legacy.__file__).resolve())) == V2_SHA and
            base.sha256(Path(legacy.__file__)) == V2_SHA, 'unqualified previous runner')
    base.check(expected)
    base.check(pins)
    return pins


def completed_logs(directory, name):
    """Require actual finish, not just an early SUCCESS print or partial trace."""
    require(name in EXPECTED_SCOPE, 'unknown terminal contract')
    tohost = name not in (*legacy.custom.NAMES, *legacy.COUNTS, 'axpy', 'qbs_canonical')
    finishes, contracts = [], []
    for name in ('console.log', 'run.vcs.log'):
        path = directory / name
        text = path.read_text()
        require(text.count('Core Test *** SUCCESS ***') == 1 and
                'Core Test *** FAILED ***' not in text, 'missing unique successful completion')
        require(not legacy.operands.check_contract_log(path), 'RTL contract failure')
        require(not re.search(r'(?im)^\s*(?:Error|Fatal)(?:-|:)|watchdog.*(?:expired|timeout)', text),
                'simulator error/watchdog termination')
        require(not re.search(r'(?m)^.*UVM_(?:ERROR|FATAL)(?!\s*:\s*0\s*$)', text),
                'UVM error/fatal')
        require('$finish called from file' in text and 'V C S   S i m u l a t i o n   R e p o r t' in text,
                'missing normal simulator finish/report')
        stamps = re.findall(r'^Time:\s*(\d+)\s+fs\s*$', text, re.M)
        require(len(stamps) == 1 and int(stamps[0]) > 0, 'missing unique simulator finish timestamp')
        finishes.append(int(stamps[0]))
        if tohost:
            # +COMMIT_TOHOST terminates in the commit monitor, before UVM's
            # report phase. Require its exact finish origin plus the final
            # independent contract; ISA/terminal store checks remain in audit.
            origin = str(ROOT / 'hardware/tb/ara_commit_monitor.sv')
            require(text.count('$finish called from file "' + origin + '"') == 1,
                    'wrong tohost finish origin')
            summaries = [r for line in text.splitlines()
                         if (r := parse_contract_summary(line)) is not None]
            require(len(summaries) == 1, 'missing unique tohost protocol summary')
            summary = summaries[0]
            require(summary['requests'] > 0 and summary['requests'] == summary['responses'] and
                    all(summary[k] == 0 for k in
                        ('protocol_errors', 'outstanding', 'req_stalled', 'resp_stalled')),
                    'tohost protocol failure')
            contracts.append(summary)
        else:
            protocol = legacy.check_real_uvm_log(path, require_axi=True, require_axi_write=True)
            require(protocol.get('status') == 'PASS', 'protocol failure: ' + str(protocol.get('issues')))
    require(finishes[0] == finishes[1], 'console/run finish timestamps differ')
    require(not tohost or contracts[0] == contracts[1], 'console/run protocol summaries differ')
    cycle = legacy.last_cycle(directory / 'commit_trace.csv')
    require(0 < cycle * 1000000 <= finishes[0], 'trace extends beyond simulator finish')
    return dict(status='PASS', finish_fs=finishes[0], last_cycle=cycle,
                scope=('commit-monitor tohost finish + independent final request/response contract; '
                       'no UVM check/report phase' if tohost else
                       'UVM completion and AXI summaries/contracts; not full backend per-beat certification'))


def verify_qbs_receipt(directory, receipt_path, output):
    """Pure offline replay using the qualified VCD; never calls vpd2vcd."""
    qbs = checker()
    receipt_path = receipt_path.resolve(strict=True)
    require(base.sha256(receipt_path) == QBS_RECEIPT_SHA, 'qualified QBS receipt changed')
    receipt = base.read(receipt_path)
    require(receipt.get('status') == 'PASS' and receipt.get('case') == qbs.previous.CASE,
            'strict QBS successor receipt did not pass')
    inp, out = receipt.get('input_pins', {}), receipt.get('output_pins', {})
    require(inp.get(str(Path(qbs.__file__).resolve())) == QBS_CHECKER_SHA and out,
            'receipt missing qualified checker/output provenance')
    original = PREVIOUS / 'results/qbs_canonical'
    for name in QBS_INPUTS:
        require(inp.get(str(original / name)) == base.sha256(directory / name),
                'QBS receipt does not describe these exact artifacts: ' + name)
    base.check(inp)
    base.check(out)
    vcd = receipt_path.parent / 'focused.vcd'
    require(out.get(str(vcd)) == base.sha256(vcd), 'qualified cycle evidence missing')
    before = base.pins([receipt_path, *[directory / name for name in QBS_INPUTS]])
    output.mkdir(exist_ok=False)
    info, _ = qbs.previous.fixture_contract(directory / 'input.elf')
    uart, perf = qbs.previous.log_gate((directory / 'run.vcs.log').read_text())
    console = (directory / 'console.log').read_text()
    qbs.previous.log_gate(console)
    qbs.strict.markers(console)
    require(console.count('Core Test *** SUCCESS *** (tohost = 0)') == 1,
            'missing exact native MMIO completion')
    architecture = qbs.native_architecture(directory / 'commit_trace.csv',
        directory / 'vector_trace.csv', info, (directory / 'input.elf').read_bytes(), output)
    require(architecture['owner']['full_scalar_compared_words'] == 4688,
            'full original architectural checks missing')
    # Gated clock edges are NOT compared to the core cycle count. This API
    # validates reset-to-finish timestamps and drain state, as reviewed in v2.
    cycles = qbs.cycle_wave(vcd, architecture['last_cycle'], console)
    require(cycles.get('status') == 'PASS' and uart.get('checks') == 160,
            'strict numerical/cycle checks incomplete')
    for key, value in [('stdout', uart), ('perf', perf),
                       ('architecture', architecture), ('cycles', cycles)]:
        # The in-memory oracle uses tuples for custom requests; the sealed
        # JSON receipt represents those same sequences as arrays.
        require(receipt.get(key) == json.loads(json.dumps(value)),
                'qualified QBS replay disagrees: ' + key)
    base.check(before)
    base.check(inp)
    base.check(out)
    return dict(status='PASS', qualified_receipt=str(receipt_path), receipt_sha256=base.sha256(receipt_path),
                checker_sha256=QBS_CHECKER_SHA, stdout=uart, architecture=architecture, cycles=cycles,
                perf=perf, replay='native architecture + qualified VCD; no converter or simulator',
                coverage_admitted=False, per_beat_protocol_certified=False,
                independent_full_scalar_ISA_replay=False)


def reuse_pass(directory, name, previous, image, image_dir):
    """Only acceptance03 PASS or its one exact checker-induced FAIL may enter."""
    require(name in FOCUSED + NEIGHBOURS, 'case outside six-original/seventeen-neighbour scope')
    require(previous.resolve() == PREVIOUS.resolve(), 'only reviewed acceptance03 reuse is allowed')
    state = base.read(previous / 'status.json')
    require(state.get('status') in ('STOPPED', 'PASS'), 'previous campaign is not terminal')
    require(set(state.get('cases', {})) == set(FOCUSED + NEIGHBOURS) and state.get('total') == 23,
            'previous campaign scope differs')
    same_build(previous, image, image_dir)
    old = previous / 'results' / name
    if not (old / 'audit.json').is_file():
        require(state['cases'][name].get('status') == 'QUEUED' and
                (not old.exists() or all(p.name in ('input.elf', 'spike.trace') for p in old.iterdir())),
                'previous attempt has incomplete evidence; no automatic retry')
        return None
    receipt = base.read(old / 'audit.json')
    require(state['cases'][name] == receipt, 'campaign and case receipts differ')
    corrected = (name == 'qbs_canonical' and receipt.get('status') == 'FAIL' and
                 receipt.get('reason') == QBS_REASON and
                 base.sha256(old / 'audit.json') == QBS_FAILURE_SHA)
    require(receipt.get('status') == 'PASS' or corrected,
            'previous case did not pass; no exception beyond pinned QBS tohost-checker error')
    before = base.pins(p for p in old.iterdir() if p.is_file())
    if receipt.get('reused_completed_same_image'):
        require(receipt.get('evidence_pins'), 'missing inherited evidence provenance')
        base.check(receipt['evidence_pins'])
    launch = base.read(old / 'started.json')
    command = base.read(old / 'command.json')
    launch_dir = Path(command['cwd']).resolve(strict=True)
    require(launch_dir == (old / 'started.json').resolve().parent and
            (launch_dir == old.resolve() or
             receipt.get('reused_completed_same_image') == str(launch_dir)), 'unbound launch directory')
    if launch_dir != old.resolve():
        origin = launch_dir.parent.parent
        require(origin == ROOT / 'verification/out/failed-repair-acceptance-20261008-02',
                'unreviewed inherited launch origin')
        origin_pins = base.read(origin / 'source-pins.json')
        v1 = ROOT / 'verification/coverage/run_failed_repair_20261008.py'
        require(origin_pins.get(str(v1)) == V1_SHA and
                base.read(launch_dir / 'audit.json').get('status') == 'PASS',
                'inherited exit-code control-flow evidence missing')
        for manifest in ('build-image.json', 'build-source-pins.json'):
            require(all(origin_pins.get(p) == h for p, h in base.read(image_dir / manifest).items()),
                    'inherited evidence is not the same build/source')
        base.check(origin_pins)
    require(launch['image'] == str(image) and launch['image_sha256'] == base.sha256(image),
            'previous simulator image differs')
    elf_hash = base.sha256(legacy.source(name) / 'input.elf')
    require(launch['elf_sha256'] == elf_hash == base.sha256(old / 'input.elf') ==
            base.sha256(directory / 'input.elf'), 'previous ELF differs')
    if (legacy.source(name) / 'spike.trace').is_file():
        require(base.sha256(old / 'spike.trace') == base.sha256(directory / 'spike.trace') ==
                base.sha256(legacy.source(name) / 'spike.trace'), 'reference trace differs')
    require(launch['command'] == command['command'] == legacy.simulation_command(image, launch_dir, name)
            and command.get('timeout_s') == 1800, 'launch command/timeout differs')
    require(float(receipt.get('elapsed_s', 1)) >= 0, 'invalid elapsed time')
    terminal = completed_logs(old, name)
    # Copy raw artifacts only. Never symlink old audit outputs: several legacy
    # auditors write JSON, which would otherwise overwrite sealed evidence.
    for filename in RAW_FILES:
        path = old / filename
        if path.is_file():
            require(not (directory / filename).exists(), 'refuse output overwrite: ' + filename)
            shutil.copyfile(path, directory / filename)
    if name == 'qbs_canonical':
        evidence = verify_qbs_receipt(directory, QBS_RECEIPT, directory / 'qbs-offline-reaudit-v3')
    else:
        evidence = audit(directory, name)
    require(evidence.get('status', 'PASS') == 'PASS', 'strict successor audit failed')
    same_build(previous, image, image_dir)
    base.check(before)
    return dict(status='PASS', evidence=evidence, last_cycle=terminal['last_cycle'], terminal=terminal,
                reused_completed_same_image=str(old), simulation_launched=False,
                previous_status=receipt['status'], checker_error_reclassified=corrected,
                original_receipt_sha256=before[str((old / 'audit.json').resolve())],
                evidence_pins=before, coverage_admitted=False, old_vdb_reuse=False,
                image_provenance_verified=True, simulator_process_exit_verified=False,
                process_exit_basis='Zero exit inferred from pinned v1/v2 wait/code/pin-check-before-audit '
                                   'control flow and terminal receipt; no independent exit-code artifact')


def audit(directory, name):
    completed_logs(directory, name)
    if name == 'qbs_canonical':
        # For an explicitly authorized fresh run, v2 may convert its new VPD.
        result = checker().audit(directory, output=directory / 'qbs-canonical-audit-v3')
        require(result.get('status') == 'PASS', 'strict QBS successor audit failed')
        return result
    if name == 'vgap112_sv39_fof':
        result = fof_checker().audit(directory)
        require(result.get('status') == 'PASS', 'strict FOF successor audit failed')
        return result
    return LEGACY_AUDIT(directory, name)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument('--execute', action='store_true')
    args, remaining = parser.parse_known_args(argv)
    require(len(FOCUSED) == 6 and len(NEIGHBOURS) == 17 and FOCUSED + NEIGHBOURS == EXPECTED_SCOPE,
            'bounded acceptance scope changed')
    if not args.execute:
        print(json.dumps(dict(status='PREPARED_ONLY', focused=FOCUSED, neighbours=NEIGHBOURS,
            execute_required=True, qbs_receipt=str(QBS_RECEIPT), full_regression_started=False), indent=2))
        return 0
    require(base.sha256(Path(legacy.__file__)) == V2_SHA, 'sealed v2 runner changed')
    checker()
    fof_checker()  # Preimport before legacy.main captures all checker source pins.
    # Preserve v2's service ownership, wait-before-reuse, source pins, two gates,
    # five workers, stop-on-failure, and pause-after-23 behaviour unchanged.
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
