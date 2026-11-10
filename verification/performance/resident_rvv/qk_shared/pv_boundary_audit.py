#!/usr/bin/env python3
"""Separate, read-only audit of the immutable stage-3 original PV replay FAIL."""
import argparse
from contextlib import contextmanager
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
RUN = OUT/'stage3_pv_boundary_20261110_01'
SOC = OUT/'stage3_soc_20261110_02'
VECTOR = RUN/'work/vector_trace.csv'
ANCHORS = {
    RUN/'result.json': '41d8f22c0d720d20a509dc898e8591f545be77e3ab105360f78646a10254f935',
    RUN/'source-pins.json': 'a1c9fc693e1908a964b143d44f1070a890c62656a893a3b907f501c0bc4f128c',
    RUN/'inputs/run_boundary.py': '1995765bf9ee8ce2f26856bba84fa6c6323715755e97680758cb0dfbbfe44638',
    RUN/'inputs/build_soc.py': 'ad6cfb879e5ee61344a92591f2d78dd290e4a649b543e09b7f179ce88c3337b2',
    SOC/'build.json': 'a947cd4ed4dd16c07bfe0335f28c3c13d88178593d4b1b49090bff8d30fd849b',
    SOC/'source-pins.json': 'dd736b5fef7fd75b5a84f3fc2ece43b794f8888d87e4a77567903036f8a22e13',
    VECTOR: '4114a08262bdab036e565f6939dd04a1bfb71303f274e4cf94b51a578bfc27e2',
}
FIELDS = ('cycle,event,arch_seq,vid,lane,source,insn,use_vd,vd,eew,vl,vstart,'
          'addr,be,wdata,nr_lanes,vlen_bits').split(',')
IDENTITY = ('arch_seq', 'vid', 'insn', 'use_vd', 'vd', 'eew', 'vl', 'vstart',
            'nr_lanes', 'vlen_bits')
DECIMAL = set(FIELDS)-{'event', 'insn', 'be', 'wdata'}
SERIAL_ERROR = 'Overlapping PV maintenance/final allocation'
PV_INSN = '0485705b'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def frozen_runner():
    for path, digest in ANCHORS.items():
        require(not path.is_symlink() and sha(path) == digest, 'Audit anchor drift: '+str(path))
    spec = importlib.util.spec_from_file_location('pv_audit_frozen_runner', RUN/'inputs/run_boundary.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    return runner


def validate_row(row):
    require(set(row) == set(FIELDS), 'Vector row schema drift')
    require(all(isinstance(row[k], str) and re.fullmatch(r'[0-9]+', row[k]) for k in DECIMAL),
            'Malformed decimal vector field')
    require(all(isinstance(row[k], str) and re.fullmatch('[0-9a-fA-F]{'+str(n)+'}', row[k])
                for k, n in (('insn', 8), ('be', 2))), 'Malformed hex vector field')
    # Global ownership includes unrelated RVV preparation with uninitialized
    # data. Only the unchanged PV/QBS/postlude checker claims payload validity.
    digits = '[0-9a-fA-F]' if row['insn'] == PV_INSN else '[0-9a-fA-FxXzZ]'
    require(isinstance(row['wdata'], str) and re.fullmatch(digits+'{16}', row['wdata']),
            'Malformed vector data')
    require((row['nr_lanes'], row['vlen_bits']) == ('4', '1024'), 'Vector configuration drift')
    require(0 <= int(row['vid']) < 8 and 0 <= int(row['lane']) < 4 and
            0 <= int(row['source']) < 5 and 0 <= int(row['vd']) < 32 and
            int(row['use_vd']) in (0, 1) and 0 <= int(row['eew']) < 4, 'Vector field out of range')


def split_active(rows):
    """Keep trace order and each active VID's identity; return allocation order."""
    active, result, previous = {}, [], -1
    for row in rows:
        validate_row(row)
        cycle, vid, event = int(row['cycle']), int(row['vid']), row['event']
        require(cycle >= previous, 'Nonmonotonic vector events')
        previous = cycle
        require(event in ('alloc', 'write', 'done'), 'Unknown backend event')
        if event != 'write':
            require(all(int(row[k], base) == 0 for k, base in
                        (('lane', 10), ('source', 10), ('addr', 10), ('be', 16), ('wdata', 16))),
                    'Non-write carries write payload')
        if event == 'alloc':
            require(vid not in active, 'VID reused before done')
            active[vid] = [row]
            result.append(active[vid])
        else:
            require(vid in active, 'Unowned/late backend write/done')
            uop = active[vid]
            require(all(row[k] == uop[0][k] for k in IDENTITY), 'Backend identity changed')
            if event == 'done':
                require(cycle > int(uop[0]['cycle']) and
                        all(int(r['cycle']) < cycle for r in uop[1:]), 'Completion before/at write')
            uop.append(row)
            if event == 'done':
                del active[vid]
    require(not active, 'Unfinished backend uop')
    return result


def split_uops(rows):
    require(rows and all(r['arch_seq'] == rows[0]['arch_seq'] and r['insn'] == PV_INSN
                         for r in rows), 'PV architectural identity changed')
    result = split_active(rows)
    if len(result) > 1:
        final = result[-1][0]
        require((final['vd'], final['vl']) == ('0', '256'), 'Missing final PV allocation')
        require(all(int(uop[-1]['cycle']) < int(final['cycle']) for uop in result[:-1]),
                'Final PV allocated before all maintenance done')
    return result


def read_trace(path):
    with Path(path).open(newline='') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == FIELDS, 'Vector CSV header drift')
        rows = list(reader)
    require(rows, 'Empty vector trace')
    validate_row(rows[0])
    require(rows[0]['event'] == 'config' and all(int(rows[0][k], 16 if k in
            ('insn', 'be', 'wdata') else 10) == 0 for k in FIELDS
            if k not in ('event', 'nr_lanes', 'vlen_bits')), 'Missing/invalid initial configuration')
    split_active(rows[1:])
    return rows[1:]


@contextmanager
def scoped_splitter(old, failures):
    original = old.split_uops

    def replacement(rows):
        # Reproduce the sealed splitter failure in the actual check_work call,
        # without rescanning the 3.1M-row CPU trace a second time.
        try:
            serial = original(rows)
        except ValueError as error:
            require(str(error) == SERIAL_ERROR and rows[0]['arch_seq'] == '926',
                    'Unexpected original splitter failure: '+str(error))
            failures.append(dict(arch_seq=926, error=str(error)))
            serial = None
        parsed = split_uops(rows)
        require(serial is None or serial == parsed, 'Nonoverlapping splitter behavior changed')
        return parsed

    old.split_uops = replacement
    try:
        yield
    finally:
        old.split_uops = original


def check_protocol(old, proof, soc, sw, log, vector):
    old.smoke.check_protocol(proof, soc, sw, log, vector)
    fresh = old.uvm_dut.check_real_uvm_log(log, require_events=True, require_backend=True,
        require_axi=True, require_axi_write=True, vector_trace=vector)
    identities = {'elf_sha256', 'simv_sha256', 'sim_image_sha256', 'log_sha256', 'vector_trace_sha256'}
    require(set(proof) == set(fresh) | identities and fresh['status'] == 'PASS' and
            fresh['issues'] == [] and all(proof[k] == v for k, v in fresh.items()),
            'Independent protocol recomputation mismatch')
    return fresh


def audit(runner):
    b = runner.b
    original = b.read(RUN/'result.json')
    require(original['state'] == 'FAIL' and original['automatic_retry'] is False and
            original['error'] == "ValueError('Command exit 1: "+str(RUN/'work/boundary.log')+"')",
            'Unexpected original terminal failure')
    b.exact_files(RUN, original['artifacts'],
        exclude=('result.json', 'status.json', 'service.stdout.log', 'service.stderr.log'))
    preserved = b.files(RUN)
    traceback = (RUN/'work/boundary.log').read_text()
    require('old.split_uops(rows)' in traceback and
            traceback.rstrip().endswith('ValueError: '+SERIAL_ERROR), 'Original checker failure changed')
    plan, pins, soc, sw, vectors, contract = runner.verify_prepared(RUN)
    require(plan['soc_build'] == str(SOC), 'Unexpected SoC pairing')
    old, checker, _ = runner.legacy()
    rows = read_trace(VECTOR)
    mixed = [row for row in rows if row['arch_seq'] == '926']
    uops = split_uops(mixed)
    lifetimes = [dict(vid=int(u[0]['vid']), vd=int(u[0]['vd']), alloc=int(u[0]['cycle']),
                     done=int(u[-1]['cycle']), writes=len(u)-2) for u in uops]
    require(lifetimes == [dict(vid=vid, vd=vd, alloc=a, done=d, writes=w) for vid, vd, a, d, w in (
        (0, 8, 3088673, 3088688, 16), (1, 9, 3088674, 3088696, 16),
        (0, 10, 3088698, 3088713, 16), (1, 11, 3088699, 3088721, 16),
        (0, 12, 3088723, 3088738, 16), (1, 13, 3088724, 3088746, 16),
        (0, 0, 3088748, 3088921, 48))], 'Mixed-case lifetime evidence changed')
    log, commit = RUN/'work/run.vcs.log', RUN/'work/commit.csv'
    text = log.read_text()
    require(text.count('Core Test *** SUCCESS ***') == 1, 'Missing/duplicate successful EOC')
    proof = b.read(RUN/'work/uvm_result.json')
    protocol = check_protocol(old, proof, soc, sw, log, VECTOR)
    numerical = checker.old.check_log(text, vectors, contract['fault_pc'])
    failures = []
    with scoped_splitter(checker.old, failures):
        work, architecture = checker.check_work(VECTOR, commit, text, vectors, contract)
    require(failures == [dict(arch_seq=926, error=SERIAL_ERROR)], 'Original failure not reproduced exactly once')
    negative = old.scoped_illegals(text, commit, vectors, sw, proof)
    b.verify(pins)
    b.checked_build(SOC)
    b.exact_files(RUN, preserved)
    return dict(state='PASS', schema='stage3-original-pv-separate-audit-v1',
        original_run=str(RUN), original_state='FAIL', original_failure_preserved=True,
        original_failure_reproduced=failures, evidence_sha256=preserved,
        source_pins_sha256=sha(RUN/'source-pins.json'), image_pins=soc['image_pins'],
        elf_sha256=sw['elf_sha256'], post_pins_match=True, post_image_match=True,
        numerical_checked=True, independent_protocol_checked=True, numerical=numerical,
        work=work, trap_architecture=architecture, negative_scope=negative, protocol=protocol,
        ownership=dict(backend_uops=sum(r['event'] == 'alloc' for r in rows),
                       pv_uops=sum(r['event'] == 'alloc' and r['insn'] == PV_INSN for r in rows)),
        mixed_case=dict(id=15, arch_seq=926, lifetimes=lifetimes,
            cause='Serial architectural splitter rejects distinct concurrent maintenance VIDs; '
                  'final PV starts after all six maintenance uops complete.'),
        trace_retimed=False, sealed_helpers_modified=False, simulation_started=False,
        performance_measured=False, deployment_approved=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    runner = frozen_runner()
    b = runner.b
    out = b.output_path(args.output, 'stage3_pv_boundary_audit_')
    require(not out.exists(), 'Preserve every prior audit attempt')
    out.mkdir()
    (out/'inputs').mkdir()
    for name in ('pv_boundary_audit.py', 'test_pv_boundary_audit.py'):
        shutil.copyfile(HERE/name, out/'inputs'/name)
    pins = {str(p): h for p, h in ANCHORS.items()} | b.files(out/'inputs')
    pins.update({str(HERE/name): sha(HERE/name) for name in
                 ('pv_boundary_audit.py', 'test_pv_boundary_audit.py')})
    b.save(out/'source-pins.json', pins)
    report = dict(state='FAIL', simulation_started=False, original_run=str(RUN))
    try:
        command = [sys.executable, '-B', str(out/'inputs/test_pv_boundary_audit.py')]
        b.save(out/'host-tests.command.json', dict(argv=command, timeout_seconds=120))
        with (out/'host-tests.log').open('x') as stream:
            result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=120)
        require(result.returncode == 0, 'Audit host tests failed')
        report = audit(runner)
        report['host_tests_passed'] = True
        b.verify(pins)
    except Exception as error:
        report.update(state='FAIL', error=repr(error))
    report['audit_source_pins_sha256'] = sha(out/'source-pins.json')
    report['artifacts'] = b.files(out)
    b.save(out/'report.json', report)
    print(json.dumps(dict(state=report['state'], output=str(out), report_sha256=sha(out/'report.json'))))
    return int(report['state'] != 'PASS')


if __name__ == '__main__':
    sys.exit(main())
