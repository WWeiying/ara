#!/usr/bin/env python3
"""Replay original failures, then bounded neighbours on one repaired VCS image.

No old-RTL coverage merge and no full-suite dispatch. A failed gate stops the
next gate; already running independent cases finish and preserve their evidence.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import importlib
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

import build_memory_vl0_repair as builder
import run_gap75_operand_batch as operands
import run_qbs_fault_layout_repair as custom
from ara_verify.uvm_dut import check_real_uvm_log

base = builder.base
ROOT = base.ROOT
OUT = ROOT / 'verification/out'
READELF = Path('/home/wangwy/openproject/ara/install/riscv-llvm/bin/llvm-readelf')
PRIOR = OUT / 'gap35-restart-repair-20261005-01/results'
WIDE = OUT / 'gap76-old-image-20261006-01/results'
AXPY = OUT / 'repaired-aligned-600-20260930-01/results/c0014-axpy-bc770a2e46ab'
COUNTS = {'vgap35_carry_ta': 459, 'vgap35_slide_bound': 535}
FOCUSED = ['vgap76_red16', 'mask_restart', 'qbs_canonical',
           'vgap101_illegal_segment_store', 'vmemory_emul_r2_boundary_reject',
           'vgap112_sv39_fof']
NEIGHBOURS = ['axpy', *COUNTS, *custom.NAMES, *operands.NAMES, 'vgap76_red32']


def source(name):
    if name == 'axpy':
        return AXPY / 'work'
    if name == 'mask_restart':
        return OUT / 'mask-compare-restart-known-preflight786-agent-20261008-01'
    if name == 'qbs_canonical':
        return OUT / 'gap71-canonical779-qbs-positive-preflight-agent-20261008-03'
    if name == 'vgap112_sv39_fof':
        return OUT / 'gap112-sv39-fof-preflight-740-agent-20261007-01'
    if name in ('vgap101_illegal_segment_store', 'vmemory_emul_r2_boundary_reject'):
        return importlib.import_module('audit_memory_decode_repair').source(name)
    return (WIDE if name.startswith('vgap76_') else PRIOR) / name


def last_cycle(path):
    with path.open() as stream:
        return max(int(r['cycle']) for r in csv.DictReader(stream))


def audit(directory, name):
    log = (directory / 'run.vcs.log').read_text()
    if operands.check_contract_log(directory / 'run.vcs.log'):
        raise RuntimeError('RTL contract failure')
    if 'Core Test *** SUCCESS ***' not in log or 'Core Test *** FAILED ***' in log:
        raise RuntimeError('DUT self-check did not complete successfully')
    if name == 'axpy':
        if base.sha256(directory / 'input.elf') != base.sha256(AXPY / 'work/input.elf'):
            raise RuntimeError('AXPY performance reference ELF mismatch')
        protocol = check_real_uvm_log(directory / 'run.vcs.log', require_events=True,
            require_backend=True, require_axi=True, require_axi_write=True,
            vector_trace=directory / 'vector_trace.csv')
        base.save(directory / 'independent_uvm_audit.json', protocol)
        if protocol['status'] != 'PASS':
            raise RuntimeError('AXPY protocol failure: ' + str(protocol['issues']))
        reference = base.read(AXPY / 'cycle_comparison.json')
        measured = re.findall(r'\[PERF\]\s+total_cycles\s*:\s*(\d+)', log)
        if reference['status'] != 'PASS' or len(measured) != 1:
            raise RuntimeError('missing unique AXPY cycle measurement/reference')
        cycles, limit = int(measured[0]), reference['cycles']
        result = dict(status='PASS' if cycles <= limit else 'FAIL', cycles=cycles,
                      limit=limit, reference=str(AXPY), protocol=protocol['status'])
        base.save(directory / 'cycle_comparison.json', result)
        if result['status'] != 'PASS':
            raise RuntimeError(f'AXPY performance regression: {cycles} > {limit}')
        return result
    if name in ('mask_restart', 'qbs_canonical'):
        module = importlib.import_module('audit_mask_restart_repair' if name == 'mask_restart'
                                        else 'audit_qbs_canonical_repair')
        return module.audit(directory)
    if name == 'vgap112_sv39_fof':
        return importlib.import_module('audit_fof_repair').audit(directory)
    if name in ('vgap101_illegal_segment_store', 'vmemory_emul_r2_boundary_reject'):
        return importlib.import_module('audit_memory_decode_repair').audit(directory, name)
    if name in custom.NAMES:
        return custom.audit(directory, name)
    if name in COUNTS:
        counts = re.findall(r'gap35 checks=(\d+) failures=(\d+)', log)
        if counts != [(str(COUNTS[name]), '0')]:
            raise RuntimeError('incomplete carry/slide self-check: ' + str(counts))
        return dict(checks=COUNTS[name], failures=0,
                    trace=operands.validate_trace(directory / 'commit_trace.csv'))
    elf = directory / 'input.elf'
    tohost = operands._elf_symbol(elf, READELF, 'tohost')
    signature = operands._elf_symbol(elf, READELF, 'g75_result')
    writes = {a: v for c in operands.parse_spike_commits(directory / 'spike.trace')
              for a, v in c.memory_accesses if v is not None}
    if writes.get(tohost) != 1 or not writes.get(signature) or writes.get(signature + 4) != 0:
        raise RuntimeError('independent Spike self-check failed')
    entry = operands.struct.unpack_from('<Q', elf.read_bytes(), 24)[0]
    scalar = operands.compare_commit_prefix(directory / 'spike.trace',
        directory / 'commit_trace.csv', entry, terminal_tohost_address=tohost,
        rvfi_store_data_layout='unshifted')
    vector = operands.compare_vector_commits(directory / 'spike.trace',
        directory / 'commit_trace.csv', directory / 'vector_trace.csv', entry)
    base.save(directory / 'scalar-comparison.json', scalar)
    base.save(directory / 'vector-comparison.json', vector)
    if scalar['status'] not in ('MATCH', 'TERMINAL_TOHOST_MATCH') or vector['status'] != 'PASS':
        raise RuntimeError('strict scalar/vector comparison failed')
    # Scalar loads compare the exactly representable reduction result even
    # where the generic vector checker permits unordered FP reassociation.
    return dict(checks=writes[signature], failures=0, scalar=scalar['status'],
                vector=vector['status'], vector_bytes=vector.get('compared_bytes'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image-directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--wait-build-unit', help='Wait for this existing build service; never restart it')
    args = parser.parse_args()
    base.check_service()
    image_dir = args.image_directory.resolve(strict=True)
    output = base.checked_output(args.output)
    output.mkdir(exist_ok=False)
    if args.wait_build_unit:
        deadline = time.monotonic() + 7200
        base.save(output / 'status.json', dict(status='WAITING_BUILD', unit=args.wait_build_unit,
            image_directory=str(image_dir), full_regression_started=False))
        while True:
            result = subprocess.run(['systemctl', '--user', 'show', args.wait_build_unit,
                '--property=ActiveState', '--property=MainPID', '--property=ExecMainStatus'],
                capture_output=True, text=True, check=True, timeout=10)
            state = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
            if state.get('ActiveState') in ('inactive', 'failed'):
                if state.get('ExecMainStatus') != '0':
                    base.save(output / 'status.json', dict(status='STOPPED', reason='build failed', service=state))
                    return 1
                break
            if state.get('ActiveState') != 'active' or state.get('MainPID') in (None, '0'):
                raise RuntimeError('build service is not actually running: ' + str(state))
            if time.monotonic() >= deadline:
                raise RuntimeError('build wait budget exhausted; build was not restarted or stopped')
            time.sleep(30)
    if base.read(image_dir / 'build-status.json')['status'] != 'PASS':
        raise RuntimeError('completed source-checked build required')
    image = image_dir / 'sim/simv'
    pins = base.read(image_dir / 'build-source-pins.json')
    pins.update(base.read(image_dir / 'build-image.json'))
    pins.update(base.pins([Path(__file__), READELF]))
    pins.update(base.pins([AXPY / 'cycle_comparison.json']))
    # Freeze the actual imported checkers, including transitive local helpers.
    importlib.import_module('audit_mask_restart_repair')
    qbs_auditor = importlib.import_module('audit_qbs_canonical_repair')
    importlib.import_module('audit_memory_decode_repair')
    importlib.import_module('audit_fof_repair')
    pins.update(base.pins([qbs_auditor.PROBE,
        ROOT / 'verification/coverage/mask_compare_restart_known786_probe.tcl']))
    pins.update(base.pins(Path(m.__file__) for m in list(sys.modules.values())
        if getattr(m, '__file__', None) and str(Path(m.__file__).resolve()).startswith(str(ROOT / 'verification'))
        and Path(m.__file__).is_file()))
    names = FOCUSED + NEIGHBOURS
    for name in names:
        directory = output / 'results' / name
        directory.mkdir(parents=True)
        origin = source(name)
        shutil.copyfile(origin / 'input.elf', directory / 'input.elf')
        pins.update(base.pins([origin / 'input.elf', directory / 'input.elf']))
        if (origin / 'spike.trace').is_file():
            shutil.copyfile(origin / 'spike.trace', directory / 'spike.trace')
            pins.update(base.pins([origin / 'spike.trace', directory / 'spike.trace']))
    base.check(pins)
    base.save(output / 'source-pins.json', pins)
    state = dict(status='RUNNING', phase='original failures', image=str(image),
                 cases={n: dict(status='QUEUED') for n in names}, total=len(names),
                 full_regression_started=False, old_vdb_reuse=False)
    def save(): base.save(output / 'status.json', state)
    save()

    def run(name):
        directory = output / 'results' / name
        elf = directory / 'input.elf'
        tohost = operands._elf_symbol(elf, READELF, 'tohost')
        command = [str(image), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
            '+PRELOAD=' + str(elf), '+TESTCASE=' + name, '+COMMIT_TOHOST=%x' % tohost,
            '+COMMIT_TRACE=' + str(directory / 'commit_trace.csv'),
            '+VECTOR_TRACE=' + str(directory / 'vector_trace.csv'),
            '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(directory / 'code.vdb'),
            '-cm_name', name]
        if 'qbs' in name: command.append('+QBS_PERF')
        if 'akv' in name: command.append('+AKV_PERF')
        if name == 'axpy':
            command += ['+ARA_CONTRACT_TRACE_LIMIT=100000', '+ARA_UVM_TRACE_LIMIT=100000']
        if name == 'qbs_canonical':
            command = importlib.import_module('audit_qbs_canonical_repair').simulation_command(image, directory)
        if name == 'mask_restart':
            command += ['-ucli', '-do', str(ROOT / 'verification/coverage/mask_compare_restart_known786_probe.tcl')]
        base.save(directory / 'command.json', dict(command=command, cwd=str(directory), timeout_s=1800))
        started = time.monotonic()
        result = dict(status='RUNNING', directory=str(directory))
        try:
            base.check(pins)
            with (directory / 'console.log').open('w') as log:
                with subprocess.Popen(command, cwd=directory, stdout=log, stderr=subprocess.STDOUT) as proc:
                    base.save(directory / 'started.json', dict(pid=proc.pid, image=str(image),
                        image_sha256=base.sha256(image), elf_sha256=base.sha256(elf), command=command))
                    try: code = proc.wait(timeout=1800)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
                        raise
                    if code != 0: raise RuntimeError('simulator exit ' + str(code))
            base.check(pins)
            result.update(status='PASS', evidence=audit(directory, name),
                          last_cycle=last_cycle(directory / 'commit_trace.csv'))
            old_trace = source(name) / 'commit_trace.csv'
            if old_trace.is_file():
                result['prior_last_cycle'] = last_cycle(old_trace)
                result['prior_elf_sha256'] = base.sha256(source(name) / 'input.elf')
        except Exception as error:
            result.update(status='TIMEOUT' if isinstance(error, subprocess.TimeoutExpired) else 'FAIL',
                          reason=f'{type(error).__name__}: {error}')
        result['elapsed_s'] = round(time.monotonic() - started, 3)
        base.save(directory / 'audit.json', result)
        return name, result

    for gate in (FOCUSED, NEIGHBOURS):
        with ThreadPoolExecutor(max_workers=5) as pool:
            pending = iter(gate)
            running = {}
            failed = False
            for name in list(gate)[:5]:
                next(pending)
                state['cases'][name] = dict(status='RUNNING')
                running[pool.submit(run, name)] = name
            save()
            while running:
                future = next(as_completed(running))
                name, result = future.result()
                del running[future]
                state['cases'][name] = result
                failed |= result['status'] != 'PASS'
                if not failed:
                    name = next(pending, None)
                    if name:
                        state['cases'][name] = dict(status='RUNNING')
                        running[pool.submit(run, name)] = name
                save()
        if failed:
            state.update(status='STOPPED', phase='failed focused acceptance; no further dispatch')
            save()
            return 1
        state['phase'] = 'bounded neighbouring regressions'
        save()
    base.check(pins)
    state.update(status='PASS', phase='focused acceptance complete; waiting for manual full-suite command')
    save()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
