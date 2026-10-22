"""Offline functional acceptance of the fixed scalar-only cache04 ELF.

Exactly two vector-traffic requirements are inapplicable to this ELF. The raw
UVM report remains non-clean. No general suppression, simulator or VDB admission.
"""
import argparse
import csv
import io
import json
from pathlib import Path
import re

import audit_system_cache_repair as old

require, sha, ROOT = old.require, old.extra.sha, old.ROOT
DIRECTORY = ROOT / 'verification/out/system-cache-repair-20261008-04'
OLD_SHA = 'eddf824e0e54b247a6182fa620141ec569143541956bb7a3883612ac39487d3c'
RUNNER = ROOT / 'verification/coverage/run_system_cache_repair_20261008_v2.py'
RUNNER_SHA = 'b7485734e637ca3764f72470f0d0e02868ff84f2ebd4033335bce30ba8e40ddf'
FAIL_SHA = '33bfcec589b75bb29f6f6f60f16e86857a7e936bbe040573f3ef56005a4fe50d'
PKG = str(ROOT / 'verification/uvm/ara_cvxif_uvm_pkg.sv')
ALLOWED = (
    (504, 'uvm_test_top.env.scoreboard', 'CVXIF/NO_TRAFFIC', 'scoreboard observed no complete CVXIF traffic'),
    (630, 'uvm_test_top', 'VID/NO_TRAFFIC', 'real Ara program did not allocate a backend vid'),
)
ZERO_COUNTS = {
    'AXI/STALL_COUNT': 'ar=0 r=0 aw=0 w=0 b=0 hold_checks=0',
    'CVXIF/COUNT': 'observed requests=0 responses=0 aborted=0 reused=0 immediate=0',
    'VID/COUNT': 'allocations=0 completions=0 aborted=0 max_live=0',
    'AXI/READ_COUNT': 'ar=0 r_beats=0 completed=0 aborted=0 pending=0 max_pending=0',
    'AXI/WRITE_COUNT': 'aw=0 w_beats=0 w_bursts=0 matched=0 b=0 aborted=0 pending=0 max_pending=0',
}


def read(path):
    return json.loads(Path(path).read_text())


def check_log(text, elf_sha):
    require(elf_sha == old.ELF_SHA, 'Exception limited to exact original scalar ELF')
    lines = [line.strip() for line in text.splitlines()]
    allowed_lines, error_times = [], []
    for lineno, owner, tag, message in ALLOWED:
        pattern = (r'UVM_ERROR ' + re.escape(PKG) + r'\(' + str(lineno) + r'\) @ (\d+): ' +
                   re.escape(owner + ' [' + tag + '] ' + message))
        found = [(line, re.fullmatch(pattern, line)) for line in lines if re.fullmatch(pattern, line)]
        require(len(found) == 1, 'Exactly one precise scalar-inapplicable error required: ' + tag)
        allowed_lines.append(found[0][0])
        error_times.append(int(found[0][1][1]))
        require([line for line in lines if line.startswith('[' + tag + ']')] == ['[' + tag + ']     1'],
                'Exact report-id count required: ' + tag)
    require(error_times[0] == error_times[1] > 0, 'NO_TRAFFIC errors must belong to one final check phase')
    for severity, count in (('ERROR', 2), ('FATAL', 0), ('WARNING', 0)):
        counts = re.findall(r'^UVM_' + severity + r'\s*:\s*(\d+)\s*$', text, re.M)
        require(counts == [str(count)], 'Exact UVM severity count required: ' + severity)
    for tag, expected in ZERO_COUNTS.items():
        found = [line for line in lines if line.startswith('UVM_INFO ') and '[' + tag + ']' in line]
        require(len(found) == 1 and found[0].endswith('[' + tag + '] ' + expected) and
                f' @ {error_times[0]}:' in found[0] and PKG in found[0],
                'Exact zero accelerator summary required: ' + tag)
    errors = [line for line in lines if re.search(r'\bUVM_(?:ERROR|FATAL)\b', line) and
              not re.fullmatch(r'UVM_(?:ERROR|FATAL)\s*:\s*\d+', line)]
    require(errors == allowed_lines, 'Unexpected/duplicate UVM error or fatal')
    # Apply the unchanged original software/contract checks only after proving
    # this exact exception. This derived string is never written into raw logs.
    remaining = '\n'.join('UVM_ERROR : 0' if re.fullmatch(r'UVM_ERROR\s*:\s*2', line) else line
                          for line in lines if line not in allowed_lines)
    require(not re.search(r'(?i)\b(?:assertion|assert|error|fatal)\b|\$fatal|watchdog.*(?:expired|timeout)',
                          remaining), 'Other assertion/error/fatal rejected')
    contract = old.check_log(remaining)
    require(text.count('$finish called from file') == 1 and
            'V C S   S i m u l a t i o n   R e p o r t' in text, 'Normal full simulator finish required')
    stamps = re.findall(r'^Time:\s*(\d+)\s+fs\s*$', text, re.M)
    require(len(stamps) == 1 and int(stamps[0]) > 0, 'Unique finish timestamp required')
    return dict(contract=contract, finish_fs=int(stamps[0]), uvm_error_count=2,
                inapplicable_ids=[item[2] for item in ALLOWED], uvm_clean=False)


def check_vector(text):
    rows = list(csv.DictReader(io.StringIO(text)))
    require(len(rows) == 1 and rows[0].get('event') == 'config' and
            rows[0].get('nr_lanes') == '4' and rows[0].get('vlen_bits') == '1024',
            'Scalar ELF must have no native vector request/allocation/write/completion events')


def audit(directory):
    directory = Path(directory).resolve(strict=True)
    require(directory == DIRECTORY.resolve(), 'Only original completed cache04 evidence')
    require(sha(Path(old.__file__)) == OLD_SHA and sha(RUNNER) == RUNNER_SHA, 'Sealed helpers changed')
    require(sha(directory / 'status.json') == FAIL_SHA, 'Original STOPPED record changed')
    status = read(directory / 'status.json')
    require(status.get('status') == 'STOPPED' and
            status.get('reason') == 'ValueError: UVM error/fatal diagnostic', 'Different failure reason')
    elf = directory / 'input.elf'
    require(sha(elf) == old.ELF_SHA == sha(old.source() / 'input.elf'), 'Original scalar ELF required')
    pins = read(directory / 'source-pins.json')
    require(pins.get(str(RUNNER)) == RUNNER_SHA, 'Original runner provenance missing')
    paths = [directory / name for name in ('status.json', 'process-exit.json', 'started.json',
        'command.json', 'source-pins.json', 'console.log', 'run.vcs.log', 'commit_trace.csv',
        'vector_trace.csv', 'input.elf', 'acceptance-gate.json')]
    paths += [Path(__file__).resolve(), Path(old.__file__).resolve(), Path(old.extra.__file__).resolve()]
    pins.update({str(p): sha(p) for p in paths})
    require(all(sha(p) == h for p, h in pins.items()), 'Input/source drift')
    started, exited, command = (read(directory / f) for f in ('started.json', 'process-exit.json', 'command.json'))
    image = Path(status['image'])
    require(started.get('image') == str(image) and started.get('image_sha256') == sha(image) == pins[str(image)] and
            started.get('elf_sha256') == old.ELF_SHA, 'Image/ELF launch identity')
    require(type(exited.get('returncode')) is int and exited['returncode'] == 0 and
            exited.get('timed_out') is False and exited.get('pid') == started.get('pid'), 'Normal zero process exit')
    require(command.get('cwd') == str(directory) and command.get('timeout_s') == 1800 and
            command.get('command') == [str(image), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
                '+PRELOAD=' + str(elf), '+TESTCASE=system_gap30_cache',
                '+COMMIT_TRACE=' + str(directory / 'commit_trace.csv'),
                '+VECTOR_TRACE=' + str(directory / 'vector_trace.csv'), '-cm', 'line+cond+fsm+tgl+branch',
                '-cm_dir', str(directory / 'code.vdb'), '-cm_name', 'system_gap30_cache'], 'Exact original launch')
    gate = read(directory / 'acceptance-gate.json')
    require(gate.get('status') == 'PASS' and gate.get('count') == 23 and gate.get('image') == str(image),
            'Fresh23 acceptance gate required')
    logs = {name: check_log((directory / name).read_text(), old.ELF_SHA)
            for name in ('console.log', 'run.vcs.log')}
    require(logs['console.log'] == logs['run.vcs.log'], 'Console/run contracts differ')
    check_vector((directory / 'vector_trace.csv').read_text())
    result = old.check_rows(list(old.extra.rows(directory / 'commit_trace.csv')), elf.read_bytes())
    require(result['last_cycle'] * 1000000 <= logs['console.log']['finish_fs'], 'Trace beyond full finish')
    require(all(sha(p) == h for p, h in pins.items()), 'Evidence changed during offline audit')
    result.update(functional_status='PASS', uvm_clean=False, uvm_error_count=2,
        uvm_status='TWO_VECTOR_TRAFFIC_REQUIREMENTS_NOT_APPLICABLE_TO_FIXED_SCALAR_ELF',
        inapplicable_ids=[item[2] for item in ALLOWED], logs=logs,
        monitored_AXI_scope='accelerator monitor; not the scalar cache memory traffic',
        native_vector_events=0, process_exit_verified=True, image_provenance_verified=True,
        original_status='STOPPED', original_status_sha256=FAIL_SHA, original_record_unchanged=True,
        directory=str(directory), ELF_sha256=old.ELF_SHA, input_pins=pins,
        coverage_admitted=False, new_simulation_started=False, other_23_acceptance_unchanged=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), 'Refuse output overwrite')
    result = audit(args.directory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
