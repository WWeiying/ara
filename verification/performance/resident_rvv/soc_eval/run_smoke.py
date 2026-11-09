#!/usr/bin/env python3
"""Prepare and directly own exactly one resident PV SoC smoke execution."""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path('/home/wangwy/openproject/ara_dsa')
EVAL = ROOT/'verification/performance/resident_rvv/soc_eval'
CHAIN = ROOT/'verification/performance/chain_profile'
OUT = ROOT.parent/'ara_dsa_signoff_integration/verification/out'
OWN = ('run_smoke.py', 'test_run_smoke.py', 'RUN.md')
HELPERS = {
    EVAL/'experiment.py': '1c15314f58e17b92b5060080f7c63266b3f624a537077bdc4fbe46a1f659d4eb',
    CHAIN/'build_soc.py': '647d3ac49bbeeeeb5d682b11d0c11a7ded05f84e594f47f3ddf675ef0b283448',
    CHAIN/'run_case.py': '7d959cebc8388d08f95481b30043260f0804087463c1d6bce86babc32bfc3cc1',
}
ARA_VERIFY = ROOT/'verification/ara_verify'
IMAGE_CHECK = ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh'
SIM_SECONDS, PROTOCOL_SECONDS, SERVICE_SECONDS = 3600, 600, 4500


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            value.update(chunk)
    return value.hexdigest()


for _path, _digest in HELPERS.items():
    require(sha(_path) == _digest, 'Sealed execution helper drift: '+str(_path))
sys.path.insert(0, str(EVAL))
import experiment as e
sys.path.insert(0, str(CHAIN))
from build_soc import execute, save as status_save
from run_case import successful_log


def fields(text, names, hexadecimal=()):
    result = {}
    for word in text.split():
        require(word.count('=') == 1, 'Malformed SMOKE field')
        key, value = word.split('=')
        require(key in names and key not in result, 'Unknown/duplicate SMOKE field')
        width = 8 if key in ('bits', 'expected') else 16
        pattern = '[0-9a-fA-F]{'+str(width)+'}' if key in hexadecimal else '[0-9]+'
        require(re.fullmatch(pattern, value) is not None, 'Malformed SMOKE value')
        result[key] = int(value, 16 if key in hexadecimal else 10)
        require(result[key] < 1 << 64, 'SMOKE counter overflow')
    require(set(result) == set(names), 'Missing SMOKE field')
    return result


SMOKE_FIELDS = {
    'META': 'd heads tokens tile arm vlenb status groups begin returned end initial_fcsr initial_vcsr initial_vstart fcsr vcsr vstart'.split(),
    'MEMORY': 'query_hash guard_hash data_hash data_bytes'.split(),
    'OUT': 'index bits expected'.split(),
    'DONE': 'calls errors'.split(),
}


def check_numerical(text, software):
    golden = Path(software['golden']['native_tile64'])
    require(sha(golden) == software['golden']['native_tile64_sha256'], 'Native golden drift')
    raw = golden.read_bytes()
    require(len(raw) == 256*4, 'Native golden must contain exactly 256 F32 values')
    reference = struct.unpack('<256I', raw)
    sequence = []
    for line in text.splitlines():
        if 'SMOKE_' not in line:
            continue
        require(line.startswith('SMOKE_') and ' ' in line, 'Malformed SMOKE record')
        tag, payload = line[len('SMOKE_'):].split(' ', 1)
        require(tag in SMOKE_FIELDS, 'Unexpected/failure SMOKE record')
        sequence.append((tag, fields(payload, SMOKE_FIELDS[tag],
            ('bits', 'expected', 'query_hash', 'guard_hash', 'data_hash'))))
    require([tag for tag, _ in sequence] == ['META', 'MEMORY']+['OUT']*256+['DONE'],
            'Missing/duplicate/out-of-order SMOKE records')
    meta, memory = sequence[0][1], sequence[1][1]
    wanted = dict(d=128, heads=2, tokens=137, tile=64, arm=1, vlenb=128, status=0,
        groups=1, initial_fcsr=0, initial_vcsr=0, initial_vstart=0, fcsr=3, vcsr=0, vstart=0)
    require(all(meta[k] == v for k, v in wanted.items()) and
            meta['begin'] < meta['returned'] < meta['end'], 'SMOKE shape/CSR/return/drain mismatch')
    require(all(memory[k] == software['memory_expected'][k] for k in SMOKE_FIELDS['MEMORY']),
            'SMOKE memory/guard/query mismatch')
    for i, (_, row) in enumerate(sequence[2:-1]):
        # The target's expected= field is syntax only, never the oracle.
        require(row['index'] == i and row['bits'] == reference[i], 'SMOKE bitwise output mismatch at '+str(i))
    require(sequence[-1][1] == dict(calls=1, errors=0), 'SMOKE terminal failure')
    return dict(numerical_checked=True, bitwise_outputs=256, fcsr=3, memory_checked=True,
        native_golden_sha256=sha(golden), call_issue_cycles=meta['returned']-meta['begin'],
        final_drain_cycles=meta['end']-meta['returned'], full_call_cycles=meta['end']-meta['begin'])


def expected_signatures():
    return ([0x0205745b]*32+[0x0485705b])*3


def check_vectors(path):
    actual, config, previous = [], 0, -1
    with Path(path).open(newline='') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames is not None and
                {'cycle', 'event', 'insn', 'nr_lanes', 'vlen_bits'} <= set(reader.fieldnames), 'Missing vector columns')
        require(len(reader.fieldnames) == len(set(reader.fieldnames)), 'Duplicate vector columns')
        for row in reader:
            require(None not in row and all(v is not None for v in row.values()), 'Malformed vector row')
            cycle, event = int(row['cycle']), row['event']
            require(cycle >= previous and (row['nr_lanes'], row['vlen_bits']) == ('4', '1024'),
                    'Vector cycle/configuration drift')
            previous = cycle
            if event == 'config':
                require(config == 0 and cycle == 0 and not actual, 'Unexpected vector epoch')
                config += 1
                continue
            require(config == 1 and event in ('alloc', 'write', 'done'), 'Unknown vector event/reset epoch')
            require(re.fullmatch('[0-9a-fA-F]{8}', row['insn']) is not None, 'Unknown vector instruction')
            insn = int(row['insn'], 16)
            if event == 'alloc' and insn & 0x707f in (0x305b, 0x705b):
                actual.append(insn)
    require(config == 1 and actual == expected_signatures(), 'Wrong exact 99 vector AKV/PV signatures')
    return dict(allocations=99, qk_panel4=96, resident_pv=3, ordered=True,
                legacy_classification=e.LEGACY_CLASSIFICATION, vector_sha256=sha(path))


def check_akv(text):
    _, original = e.contract.sealed_modules()
    expected = [r for r in original.expected_commands()[1046:1283] if r['command'] != 2]
    require(len(expected) == 100, 'Accepted native-auto template drift')
    rows, summaries, totals = [], [], Counter()
    for line in text.splitlines():
        if '[AKV_PERF]' in line:
            require(line.startswith('[AKV_PERF] '), 'Malformed AKV PERF prefix')
            require(not summaries, 'AKV command after terminal summary')
            row = original.parse_fields(line[len('[AKV_PERF] '):], original.PERF_FIELDS)
            i = len(rows)
            require(i < 100 and row['seq'] == i+1 and
                    all(row[k] == v for k, v in expected[i].items()), 'Unexpected AKV command sequence/work')
            require(row['success'] == 1 and row['busy_cycles'] > 0 and
                    all(row[k] == 0 for k in ('fault', 'validation_fault', 'validation_error',
                                             'read_fault', 'v2_rejected')), 'AKV fault/rejection')
            require(row['context_ready'] == int(row['command'] != 3) and
                    row['read_payload_bytes'] == row['q_external_bytes']+row['kv_external_bytes']+
                    64*row['v2_full'], 'AKV lifecycle/payload mismatch')
            for k in original.SUMMARY_FIELDS-{'records', 'success_records', 'fault_records', 'validation_fault_records'}:
                totals[k] = max(totals[k], row[k]) if k == 'read_outstanding_max' else totals[k]+row[k]
            rows.append(row)
        elif '[AKV_PERF_SUMMARY]' in line:
            require(line.startswith('[AKV_PERF_SUMMARY] '), 'Malformed AKV summary prefix')
            require(len(rows) == 100, 'AKV summary before complete command work')
            summaries.append(original.parse_fields(line[len('[AKV_PERF_SUMMARY] '):], original.SUMMARY_FIELDS))
    summary = dict(totals, records=100, success_records=100, fault_records=0, validation_fault_records=0)
    require(len(rows) == 100 and summaries == [summary], 'Missing/duplicate/inconsistent AKV PERF/summary')
    return dict(commands=100, summary=summary)


def checker_inventory():
    paths = sorted(ARA_VERIFY.rglob('*.py'))
    require(paths and ARA_VERIFY/'uvm_dut.py' in paths and all(not p.is_symlink() for p in paths),
            'Incomplete/linked ara_verify inventory')
    return {str(p): sha(p) for p in paths}


def environment():
    env = {k: os.environ[k] for k in ('VCS_HOME', 'VCS_ARCH_OVERRIDE', 'LM_LICENSE_FILE',
        'SNPSLMD_LICENSE_FILE', 'LD_LIBRARY_PATH', 'TMPDIR') if k in os.environ}
    env.update(PATH='/usr/bin:/bin', HOME=os.environ.get('HOME', '/home/wangwy'), LC_ALL='C',
        PYTHONPATH=str(ROOT/'verification'), PYTHONDONTWRITEBYTECODE='1', READELF='/usr/bin/readelf')
    return env


def recipes(out, soc, software, python):
    work, simv, elf = out/'work', Path(soc['simv']), Path(software['elf'])
    return dict(
        image_contract=['/usr/bin/bash', str(IMAGE_CHECK), str(simv.parent), str(elf), 'akv_v2'],
        simulation=[str(simv), '-no_save', '-l', str(work/'run.vcs.log'), '+PRELOAD='+str(elf),
            '+TESTCASE=resident_pv_soc_smoke', '+NO_FSDB', '+NO_INSTR_TRACE',
            '+VECTOR_TRACE='+str(work/'vector_trace.csv'), '+COMMIT_TRACE='+str(work/'commit.csv'),
            '+AKV_PERF', '+AKV_SUMMARY', '+RESIDENT_PV_PERF', '+RESIDENT_PV_WATCHDOG',
            '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000'],
        protocol=[python, '-B', '-m', 'ara_verify.uvm_dut', '--require-events', '--require-backend',
            '--require-axi', '--require-axi-write', '--vector-trace', str(work/'vector_trace.csv'),
            '--log', str(work/'run.vcs.log'), '--simv', str(simv), '--elf', str(elf),
            '--output', str(work/'uvm_result.json')])


def selection(out, socdir, build, soc, software, inventory, env, python):
    return dict(schema='resident-pv-smoke-run-v1', kind='smoke', soc_build=str(socdir), build=str(build),
        soc_receipt_sha256=sha(socdir/'build.json'), software_receipt_sha256=sha(build/'build.json'),
        commands=recipes(out, soc, software, python), sim_seconds=SIM_SECONDS,
        protocol_seconds=PROTOCOL_SECONDS, service_seconds=SERVICE_SECONDS,
        checker_inventory=inventory, environment=env, python=python, automatic_abba=False)


def collect(socdir, build):
    soc, pins = e.checked_soc(socdir)
    software = e.verify_build(build)
    require(software['kind'] == 'smoke' and software['image_contract'] == soc['image_contract'],
            'Only the sealed compatible smoke build is allowed; no ABBA')
    extra = json.loads((build/'source-pins.json').read_text())
    e.merge(pins, extra)
    e.merge(pins, software['artifacts'])
    e.merge(pins, {str(p): sha(p) for p in (build/'build.json', build/'source-pins.json')})
    inventory = checker_inventory()
    e.merge(pins, inventory)
    e.merge(pins, HELPERS)
    e.merge(pins, {str(p): sha(p) for p in (IMAGE_CHECK, Path(sys.executable).resolve(),
        Path('/usr/bin/bash').resolve(), Path('/usr/bin/readelf').resolve(),
        Path('/usr/bin/systemctl').resolve(), Path('/usr/bin/systemd-run').resolve(),
        *(EVAL/n for n in OWN))})
    e.contract.verify(pins)
    return soc, software, pins, inventory


def output_path(path):
    out = Path(path).resolve()
    require(out.parent == OUT and re.fullmatch(r'(?:resident_pv_)?soc_smoke_vcs_[A-Za-z0-9_-]{1,100}', out.name),
            'Use a fresh direct signoff soc_smoke_vcs output')
    return out


def frozen_receipt(out):
    return dict(state='PREPARED_SMOKE_NOT_EXECUTED', parent_review_required=True,
                execution='NOT_RUN', source_pins_sha256=sha(out/'source-pins.json'))


def verify_prepared(out):
    out = output_path(out)
    require(json.loads((out/'prepared.json').read_text()) == frozen_receipt(out), 'Prepared receipt drift')
    pins = json.loads((out/'source-pins.json').read_text())
    e.contract.verify(pins)
    s = json.loads((out/'selection.json').read_text())
    require(s['checker_inventory'] == checker_inventory(), 'ara_verify module inventory drift')
    soc, software, mandatory, inventory = collect(Path(s['soc_build']), Path(s['build']))
    require(all(pins.get(p) == h for p, h in mandatory.items()), 'Missing original hardware/software/helper pin')
    require(s == selection(out, Path(s['soc_build']), Path(s['build']), soc, software,
                           inventory, s['environment'], str(Path(sys.executable).resolve())), 'Unreviewed smoke selection')
    require({p.name for p in (out/'inputs').iterdir()} == set(OWN), 'Unexpected frozen runner input')
    for name in OWN:
        require(pins.get(str(out/'inputs'/name)) == pins.get(str(EVAL/name)) == sha(out/'inputs'/name),
                'Frozen runner/document identity drift')
    for name in ('selection.json', 'host-tests.log', 'host-tests.command.json',
                 'image-contract.log', 'image-contract.command.json'):
        require(pins.get(str(out/name)) == sha(out/name), 'Unpinned preflight evidence')
    return s, pins, soc, software


def prepare(socdir, build, output):
    require(Path(__file__).resolve() == EVAL/'run_smoke.py', 'Prepare with the original reviewed runner')
    out = output_path(output)
    require(not out.exists(), 'Preserve previous attempts; use a fresh output')
    socdir, build = Path(socdir).resolve(strict=True), Path(build).resolve(strict=True)
    out.mkdir()
    (out/'work').mkdir()
    status = dict(state='PREFLIGHT', owner_pid=os.getpid(), child_pid=None, execution='NOT_RUN')
    report = dict(state='FAIL', execution='NOT_RUN', performance_measured=False)
    try:
        soc, software, pins, inventory = collect(socdir, build)
        (out/'inputs').mkdir()
        for name in OWN:
            dest = out/'inputs'/name
            shutil.copyfile(EVAL/name, dest)
            dest.chmod(0o444)
            e.merge(pins, {str(dest): sha(dest)})
        python = str(Path(sys.executable).resolve())
        env = environment()
        s = selection(out, socdir, build, soc, software, inventory, env, python)
        e.save(out/'selection.json', s)
        e.merge(pins, {str(out/'selection.json'): sha(out/'selection.json')})
        os.environ.clear()
        os.environ.update(env)
        execute([python, '-B', str(out/'inputs/test_run_smoke.py'), '-v'], out/'inputs',
                out/'host-tests.log', 60, status, out/'status.json', 'HOST_TESTS')
        execute(s['commands']['image_contract'], out/'work', out/'image-contract.log', 180,
                status, out/'status.json', 'IMAGE_CONTRACT')
        require(checker_inventory() == inventory, 'ara_verify inventory drift during preflight')
        e.contract.verify(pins)
        e.merge(pins, {str(out/n): sha(out/n) for n in ('host-tests.log', 'host-tests.command.json',
            'image-contract.log', 'image-contract.command.json')})
        e.save(out/'source-pins.json', pins)
        e.save(out/'prepared.json', frozen_receipt(out))
        verify_prepared(out)
        report.update(state='PREPARED_SMOKE_NOT_EXECUTED', source_pins_sha256=sha(out/'source-pins.json'))
    except BaseException as exc:
        report['error'] = repr(exc)
    e.save(out/'prepare-report.json', report)
    status.update(state=report['state'], child_pid=None)
    status_save(out/'status.json', status)
    require(report['state'] == 'PREPARED_SMOKE_NOT_EXECUTED', 'Preflight failed; retained '+str(out))
    return report


def service_unit(out):
    return 'resident-pv-soc-smoke-'+out.name+'.service'


def service_command(out, review_sha256):
    verify_prepared(out)
    require(review_sha256 == sha(out/'source-pins.json'), 'Review hash does not identify this bundle')
    return ['/usr/bin/systemd-run', '--user', '--unit='+service_unit(out),
        '--property=WorkingDirectory='+str(out/'work'), '--property=RuntimeMaxSec=4500',
        '--property=KillMode=control-group', '--property=TimeoutStopSec=20',
        '--property=StandardOutput=append:'+str(out/'service.stdout.log'),
        '--property=StandardError=append:'+str(out/'service.stderr.log'),
        str(Path(sys.executable).resolve()), '-B', '-u', str(out/'inputs/run_smoke.py'),
        'run', '--output', str(out), '--parent-reviewed', '--review-sha256', review_sha256]


def direct_owner(cgroup, unit, main_pid, own_pid):
    require(unit in cgroup.split('/'), 'Worker outside expected systemd CGroup')
    require(main_pid == own_pid, 'Python worker must directly own systemd MainPID')


def check_protocol(proof, soc, software, log, vector):
    image = {p: h for p, h in soc['image_pins'].items() if p == soc['simv'] or p.endswith('.so')}
    require(any(p.endswith('.so') for p in image), 'No compiled design libraries')
    require(proof.get('status') == 'PASS' and proof.get('issues') == [] and
            proof.get('elf_sha256') == software['elf_sha256'] and
            proof.get('simv_sha256') == sha(soc['simv']) and proof.get('sim_image_sha256') == image and
            proof.get('log_sha256') == sha(log) and proof.get('vector_trace_sha256') == sha(vector),
            'Independent CPU/backend/AXI protocol evidence mismatch')


def run(out, parent_reviewed, review_sha256):
    out = output_path(out)
    require(parent_reviewed and review_sha256 == sha(out/'source-pins.json'), 'Explicit frozen-bundle parent review required')
    require(Path(__file__).resolve() == out/'inputs/run_smoke.py', 'Execute the frozen runner')
    unit = service_unit(out)
    cgroup = Path('/proc/self/cgroup').read_text().strip().splitlines()[-1].split(':', 2)[-1]
    main_pid = int(subprocess.check_output(['/usr/bin/systemctl', '--user', 'show', unit,
        '--property=MainPID', '--value'], text=True, timeout=10).strip())
    direct_owner(cgroup, unit, main_pid, os.getpid())
    require(not (out/'result.json').exists() and not any((out/'work').iterdir()),
            'Execution already attempted; preserve first failure and use a new output')
    status = dict(state='PREFLIGHT', owner_pid=os.getpid(), child_pid=None,
                  started=datetime.now(timezone.utc).isoformat())
    result = dict(state='FAIL', kind='smoke', performance_measured=False, automatic_abba=False,
                  deployment_approved=False, numerical_checked=False, independent_protocol_checked=False)
    try:
        s, pins, soc, software = verify_prepared(out)
        os.environ.clear()
        os.environ.update(s['environment'])
        execute(s['commands']['image_contract'], out/'work', out/'run-image-contract.log', 180,
                status, out/'status.json', 'IMAGE_CONTRACT')
        e.contract.verify(pins)
        started = time.monotonic()
        execute(s['commands']['simulation'], out/'work', out/'work/console.log', SIM_SECONDS,
                status, out/'status.json', 'RUNNING')
        wall = time.monotonic()-started
        log, vector = out/'work/run.vcs.log', out/'work/vector_trace.csv'
        text = log.read_text()
        successful_log(text)
        numeric = check_numerical(text, software)
        akv, vectors = check_akv(text), check_vectors(vector)
        resident = e.check_resident_work(vector, text, 'smoke')
        require(resident['commands'] == 3 and resident['numerical_checked'] is False and
                resident['protocol_checked'] is False, 'Resident checker scope/command mismatch')
        execute(s['commands']['protocol'], out/'work', out/'work/checker.log', PROTOCOL_SECONDS,
                status, out/'status.json', 'PROTOCOL_CHECK')
        proof = json.loads((out/'work/uvm_result.json').read_text())
        check_protocol(proof, soc, software, log, vector)
        require(sha(out/'source-pins.json') == review_sha256, 'Reviewed run inventory drift')
        e.contract.verify(pins)
        post, _, _, _ = verify_prepared(out)
        require(post == s and sha(out/'source-pins.json') == review_sha256,
                'Reviewed run selection/inventory drift')
        result.update(state='PASS', numerical_checked=True, independent_protocol_checked=True,
            post_pins_match=True, post_image_match=True, numerical=numeric, akv_work=akv,
            vector_work=vectors, resident_work=resident, simulation_wall_seconds=wall,
            source_pins_sha256=sha(out/'source-pins.json'), soc_build=s['soc_build'], build=s['build'],
            software_sha256=software['elf_sha256'], image_sha256=sha(soc['simv']),
            configuration=soc['configuration'])
    except BaseException as exc:
        result.update(state='TIMEOUT' if isinstance(exc, subprocess.TimeoutExpired) else 'FAIL', error=repr(exc))
    result['artifacts'] = {str(p): sha(p) for p in out.rglob('*') if p.is_file() and
        p.name not in ('status.json', 'service.stdout.log', 'service.stderr.log')}
    e.save(out/'result.json', result)
    status.update(state=result['state'], child_pid=None, finished=datetime.now(timezone.utc).isoformat())
    status_save(out/'status.json', status)
    print(json.dumps(dict(state=result['state'], output=str(out))), flush=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('prepare', allow_abbrev=False)
    p.add_argument('--soc-build', type=Path, required=True)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    for action in ('preflight', 'service-command', 'run'):
        p = sub.add_parser(action, allow_abbrev=False)
        p.add_argument('--output', type=Path, required=True)
        if action != 'preflight':
            p.add_argument('--review-sha256', required=True)
        if action == 'run':
            p.add_argument('--parent-reviewed', action='store_true')
    args = parser.parse_args(argv)
    if args.action == 'prepare':
        print(json.dumps(prepare(args.soc_build, args.build, args.output), indent=2))
    elif args.action == 'preflight':
        verify_prepared(output_path(args.output))
        print('PREFLIGHT_PASS_NOT_EXECUTED')
    elif args.action == 'service-command':
        print(shlex.join(service_command(output_path(args.output), args.review_sha256)))
    else:
        return int(run(args.output, args.parent_reviewed, args.review_sha256)['state'] != 'PASS')
    return 0


if __name__ == '__main__':
    def interrupted(sig, _frame):
        raise InterruptedError('Signal '+str(sig))
    for _signal in (signal.SIGTERM, signal.SIGINT):
        signal.signal(_signal, interrupted)
    sys.exit(main())
