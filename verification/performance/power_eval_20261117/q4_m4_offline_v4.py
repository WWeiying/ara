#!/usr/bin/env python3
"""Offline-only compact M4 audit: full raw-log severity scan, bounded actual records."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
MAX_RAW_BYTES = 1 << 30
MAX_LINE_BYTES = 1 << 16
MAX_RECORD_BYTES = 262144
LIMIT_ERROR = 'Compact log exceeds bounded checker limit'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


old = load(HERE/'q4_m4_compact.py', 'offline_q4_frozen_primitives')
require, sha, save = old.require, old.sha, old.save


def scan(path):
    """Never skip a raw line's severity checks or invent replacement UART data."""
    digest = hashlib.sha256()
    kept, total, count, retained = [], 0, 0, 0
    with Path(path).open('rb') as stream:
        while True:
            raw = stream.readline(MAX_LINE_BYTES+1)
            if not raw:
                break
            count += 1
            total += len(raw)
            require(len(raw) <= MAX_LINE_BYTES and total <= MAX_RAW_BYTES, 'Raw log safety budget')
            digest.update(raw)
            line = raw.decode('utf-8').rstrip('\r\n')
            require('\x00' not in line, 'NUL in simulator log')
            if re.search(r'\bUVM_(?:ERROR|FATAL)\b', line):
                require(re.fullmatch(r'\s*UVM_(?:ERROR|FATAL)\s*:\s*0\s*', line),
                        'Raw UVM error/fatal at line '+str(count))
            require(not re.search(r'(?i)(Error[-:]|Fatal:|Assertion failed|\$(?:fatal|error)|\bTIMEOUT\b|\bTIMED OUT\b)', line),
                    'Raw simulator failure at line '+str(count))
            terminal = re.fullmatch(r'Core Test \*\*\* FAILED \*\*\* \(tohost = 1\)', line)
            require(not re.search(r'\bFAILED\b', line) or terminal is not None,
                    'Raw unexpected FAILED at line '+str(count))
            if 'Core Test' in line:
                require(re.fullmatch(r'Core Test \*\*\* (SUCCESS|FAILED) \*\*\* \(tohost = [0-9]+\)', line),
                        'Malformed raw EOC')
            if ('OPQ' in line or '[QBS_PERF]' in line or 'Core Test' in line or
                    re.search(r'\bUVM_(?:ERROR|FATAL)\b', line)):
                retained += len(raw)
                require(retained <= MAX_RECORD_BYTES, 'Actual compact record budget')
                kept.append(line)
    require(total > 0 and kept, 'Empty simulator evidence')
    return '\n'.join(kept)+'\n', dict(raw_bytes=total, raw_lines=count,
        retained_lines=len(kept), retained_source_bytes=retained, raw_sha256=digest.hexdigest(),
        every_raw_line_severity_checked=True, record_origin='Unmodified lines from raw log, original order',
        synthesized_records=False, raw_file_limit=MAX_RAW_BYTES, record_byte_limit=MAX_RECORD_BYTES)


def audit(run, output):
    run = Path(run).resolve(strict=True)
    output = Path(output).absolute()
    require(output == output.resolve() and output.parent == OUT and not output.exists() and
            re.fullmatch(r'power_q4_m4_offline_20261117_[A-Za-z0-9_.-]+', output.name), 'Fresh owned audit output required')
    campaign = run.parent.parent
    original = json.loads((run/'result.json').read_text())
    require(original['state'] == 'FAIL' and original.get('error') == "ValueError('ELIGIBILITY exit 1')",
            'Only completed original eligibility-tool failure is in scope')
    failed = json.loads((run/'eligibility.json').read_text())
    require(failed.get('state') == 'FAIL' and failed.get('error') == LIMIT_ERROR,
            'Original failure is not the scoped whole-log size gate')
    plan = json.loads((campaign/'plan.json').read_text())
    matches = [c for c in plan['cases'] if c['id'] == run.name]
    require(len(matches) == 1, 'Original case identity')
    case = matches[0]
    build_dir = Path(case['checker'][case['checker'].index('--build')+1])
    m = old.receipt(build_dir)
    require(m['elf_sha256'] == case['elf_sha256'], 'Original firmware identity')
    image = Path(plan['image'])
    image_build = json.loads((image/'build.json').read_text())
    worker = load(campaign/'inputs/precheck_power_v3.py', 'offline_original_power_worker')
    pins = json.loads((campaign/'source-pins.json').read_text())
    old.verify(pins)
    image_sources = json.loads((image/'source-pins.json').read_text())
    old.verify(image_sources)
    old.verify(image_build['image_pins'])
    evidence = [run/name for name in ('result.json', 'eligibility.json', 'strict-numerical.json',
                'ELIGIBILITY.log', 'STRICT.log', 'run.vcs.log', 'commit.csv', 'vector.csv')]
    evidence += [campaign/'source-pins.json', image/'build.json', build_dir/'build.json',
                 Path(__file__).resolve(), HERE/'test_q4_m4_offline_v4.py']
    identities = {str(p): sha(p) for p in evidence}
    output.mkdir()
    (output/'inputs').mkdir()
    for file in ('q4_m4_offline_v4.py', 'test_q4_m4_offline_v4.py'):
        shutil.copyfile(HERE/file, output/'inputs'/file)
    report = dict(state='FAIL', original_worker_state='FAIL', original_worker_reclassified=False,
                  simulations_launched=0, power_measured=False)
    try:
        with (output/'host-tests.log').open('x') as log:
            subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', str(HERE),
                '-p', 'test_q4_m4_offline_v4.py', '-v'], stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
        text, scanned = scan(run/'run.vcs.log')
        require(scanned['raw_sha256'] == identities[str(run/'run.vcs.log')], 'Raw log changed during scan')
        # This explicitly labeled view is NOT a substitute simulator log or protocol input.
        (output/'actual-semantic-records.log').write_text(text)
        save(output/'raw-scan.json', scanned)
        try:
            strict = old.parse_log(text, m)
        except ValueError as exc:
            strict = dict(state='FAIL', error=str(exc))
        strict.update(original_worker_reclassified=False, scope='Independent offline strict numerical audit',
                      original_raw_log_sha256=scanned['raw_sha256'])
        save(output/'strict-offline.json', strict)
        eligible = old.eligibility(text, m, run/'commit.csv')
        require(eligible['strict_numerical_state'] == strict['state'], 'Strict/eligibility disagreement')
        eligible.update(original_raw_log_sha256=scanned['raw_sha256'], scan=scanned,
                        original_worker_reclassified=False, raw_log_size_fix_only=True)
        save(output/'eligibility-offline.json', eligible)
        env = dict(json.loads((image/'plan.json').read_text())['environment'],
                   PYTHONPATH=plan['protocol_pythonpath'], PYTHONDONTWRITEBYTECODE='1')
        argv = [sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events', '--require-backend',
            '--require-axi', '--require-axi-write', '--vector-trace', str(run/'vector.csv'),
            '--log', str(run/'run.vcs.log'), '--simv', str(image/'sim/simv'), '--elf', case['elf'],
            '--output', str(output/'protocol.json')]
        with (output/'protocol.log').open('x') as log:
            proc = subprocess.run(argv, cwd=output, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=1200)
        require(proc.returncode == 0, 'Independent archived protocol checker failed')
        proof = json.loads((output/'protocol.json').read_text())
        worker.check_protocol(proof, case, image_build['image_pins'][str(image/'sim/simv')],
                              scanned['raw_sha256'], identities[str(run/'vector.csv')])
        old.verify(pins)
        old.verify(image_sources)
        old.verify(image_build['image_pins'])
        old.verify(identities)
        report.update(state='POWER_ELIGIBLE', independent_strict_numerical_state=strict['state'],
            independent_protocol_checked=True, raw_log_scan=scanned, image=str(image), image_state=image_build['state'],
            firmware=str(build_dir), original_run=str(run),
            scope='Independent offline evidence audit only; original FAIL unchanged; not measured power or whole-model signoff')
    except Exception as exc:
        report['error'] = repr(exc)
    all_pins = dict(pins)
    all_pins.update(identities)
    all_pins.update({str(p): sha(p) for p in (output/'inputs').iterdir()})
    save(output/'source-pins.json', all_pins)
    report['evidence_sha256'] = identities
    report['artifacts'] = {str(p): sha(p) for p in output.rglob('*') if p.is_file()}
    save(output/'result.json', report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = audit(a.run, a.output)
    print(json.dumps({k: v for k, v in result.items() if k not in ('artifacts', 'evidence_sha256')}))
    return int(result['state'] != 'POWER_ELIGIBLE')


if __name__ == '__main__':
    raise SystemExit(main())
