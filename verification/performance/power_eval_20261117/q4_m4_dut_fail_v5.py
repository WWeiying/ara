#!/usr/bin/env python3
"""Offline RVV relative-power scope for exactly one numeric-return DUT_FAIL."""
import argparse
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
spec = importlib.util.spec_from_file_location('dut_fail_original_v4', HERE/'q4_m4_offline_v4.py')
v4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v4)
old, require, sha, save = v4.old, v4.require, v4.sha, v4.save
PROTOCOL_ISSUE = 'UVM error/fatal report summary is missing or nonzero'


def scan(path, source, source_line):
    event_pattern = (r'UVM_ERROR '+re.escape(str(source))+r'\('+str(source_line)+
        r'\) @ ([0-9]+): uvm_test_top \[CVXIF/DUT_FAIL\] real Ara program did not report success')
    kept, exceptions = [], []
    raw_hash = hashlib.sha256()
    total = retained = lines = 0
    events = summaries = ids = fatals = reports = footers = failed_eoc = 0
    with Path(path).open('rb') as stream:
        while True:
            raw = stream.readline(v4.MAX_LINE_BYTES+1)
            if not raw:
                break
            lines += 1
            total += len(raw)
            require(len(raw) <= v4.MAX_LINE_BYTES and total <= v4.MAX_RAW_BYTES, 'Raw safety budget')
            raw_hash.update(raw)
            line = raw.decode('utf-8').rstrip('\r\n')
            require('\x00' not in line, 'NUL in raw log')
            require(not re.search(r'(?i)(Error[-:]|Fatal:|Assertion failed|\$(?:fatal|error)|\bTIMEOUT\b|\bTIMED OUT\b)', line),
                    'Simulator failure at raw line '+str(lines))
            if line == '--- UVM Report Summary ---':
                reports += 1
            if line.startswith('OPQ_DONE '):
                footers += 1
            if line == 'Core Test *** FAILED *** (tohost = 1)':
                failed_eoc += 1
                require(footers == 1, 'Early failed EOC')
            elif 'Core Test' in line or re.search(r'\bFAILED\b', line):
                raise ValueError('Unexpected completion/FAILED record')
            match = re.fullmatch(event_pattern, line)
            if match:
                events += 1
                require(events == 1 and failed_eoc == 1 and reports == 0, 'Duplicate/early DUT_FAIL')
                exceptions.append(dict(line=lines, kind='EXPECTED_NUMERIC_DUT_FAIL', raw=line,
                                       uvm_time=int(match[1])))
                continue
            if re.fullmatch(r'\s*UVM_ERROR\s*:\s*1\s*', line):
                summaries += 1
                require(events == 1 and reports == 1 and summaries == 1, 'Wrong error summary scope/count')
                exceptions.append(dict(line=lines, kind='ERROR_SUMMARY_ONE_DUT_FAIL', raw=line))
                continue
            if re.search(r'\bUVM_(?:ERROR|FATAL)\b', line):
                require(re.fullmatch(r'\s*UVM_FATAL\s*:\s*0\s*', line), 'Unexpected UVM error/fatal')
                fatals += 1
            if '[CVXIF/DUT_FAIL]' in line:
                require(re.fullmatch(r'\[CVXIF/DUT_FAIL\]\s+1', line) and reports == 1,
                        'Unexpected DUT_FAIL record')
                ids += 1
            if 'OPQ' in line or '[QBS_PERF]' in line or 'Core Test' in line:
                retained += len(raw)
                require(retained <= v4.MAX_RECORD_BYTES, 'Semantic record budget')
                kept.append(line)
    require((events, summaries, ids, fatals, reports, footers, failed_eoc) == (1, 1, 1, 1, 1, 1, 1),
            'DUT_FAIL event/summary/completion inventory mismatch')
    return '\n'.join(kept)+'\n', dict(raw_bytes=total, raw_lines=lines, raw_sha256=raw_hash.hexdigest(),
        actual_semantic_source_bytes=retained, every_raw_line_checked=True,
        expected_numerical_failure_records=exceptions, other_uvm_errors=0, uvm_fatals=0,
        synthesized_records=False, raw_log_modified=False,
        scope='Two original UVM failure lines kept as evidence, excluded only from numerical record view; '
              'original full raw log still goes to unchanged protocol checker')


def source_proof(image):
    package = image/'source/verification/uvm/ara_cvxif_uvm_pkg.sv'
    binding = image/'source/verification/uvm/ara_cvxif_dut_bind.sv'
    text, bind = package.read_text(), binding.read_text()
    event = '`uvm_error("CVXIF/DUT_FAIL", "real Ara program did not report success")'
    require(text.count(event) == 1 and 'if (!observed_pass)\n        '+event in text and
            "observed_pass = (vif.smoke_pass === 1'b1);" in text and
            '@(posedge vif.clk_i iff vif.smoke_done);' in text, 'DUT_FAIL source semantics changed')
    require('assign cvxif.smoke_done = test_done_i;' in bind and
            'assign cvxif.smoke_pass = test_pass_i;' in bind and
            '.test_done_i(ara_tb.exit[0])' in bind and '.test_pass_i(ara_tb.exit == 64\'d1)' in bind,
            'DUT success/exit binding semantics changed')
    line = text[:text.index(event)].count('\n')+1
    return package, line, {str(package): sha(package), str(binding): sha(binding)}


def protocol_scope(proof, case, simv_hash, log_hash, vector_hash):
    require(proof.get('status') == 'FAIL' and proof.get('issues') == [PROTOCOL_ISSUE],
            'Protocol failure is not solely the preserved numerical UVM summary')
    require(all(proof.get('contract_counts', {}).get(k) == 0 for k in
                ('exceptions', 'protocol_errors', 'outstanding')), 'Protocol/architectural fault')
    for key, value in (('elf_sha256', case['elf_sha256']), ('simv_sha256', simv_hash),
                       ('log_sha256', log_hash), ('vector_trace_sha256', vector_hash)):
        require(proof.get(key) == value, 'Protocol evidence identity: '+key)
    return dict(traffic_protocol_checked=True, full_protocol_pass=False,
                original_protocol_status='FAIL', original_protocol_issues=proof['issues'],
                scope='All other archived CVXIF/backend/AXI checks passed; numerical DUT_FAIL remains a failure')


def audit(run, prior, output):
    run, prior = Path(run).resolve(strict=True), Path(prior).resolve(strict=True)
    output = Path(output).absolute()
    require(output == output.resolve() and output.parent == v4.OUT and not output.exists() and
            re.fullmatch(r'power_q4_m4_dut_fail_20261117_[A-Za-z0-9_.-]+', output.name), 'Fresh audit output required')
    previous = json.loads((prior/'result.json').read_text())
    failure = re.fullmatch(r"ValueError\('Raw UVM error/fatal at line ([0-9]+)'\)", previous.get('error', ''))
    require(previous['state'] == 'FAIL' and failure is not None, 'Original UVM FAIL audit required')
    old.verify(previous['artifacts'])
    old.verify(json.loads((prior/'source-pins.json').read_text()))
    campaign = run.parent.parent
    original = json.loads((run/'result.json').read_text())
    require(original['state'] == 'FAIL', 'Original worker FAIL required')
    plan = json.loads((campaign/'plan.json').read_text())
    cases = [c for c in plan['cases'] if c['id'] == run.name]
    require(len(cases) == 1, 'Case identity')
    case = cases[0]
    build = Path(case['checker'][case['checker'].index('--build')+1])
    m = old.receipt(build)
    require(m['mode'] == 'rvv' and m['elf_sha256'] == case['elf_sha256'], 'RVV M4 firmware identity')
    image = Path(plan['image'])
    image_build = json.loads((image/'build.json').read_text())
    pins = json.loads((campaign/'source-pins.json').read_text())
    image_sources = json.loads((image/'source-pins.json').read_text())
    for inventory in (pins, image_sources, image_build['image_pins']):
        old.verify(inventory)
    source, source_line, sources = source_proof(image)
    for p, digest in sources.items():
        require(image_sources.get(p) == digest or pins.get(p) == digest, 'Unpinned UVM source semantics')
    identities = {str(p): sha(p) for p in [prior/'result.json', prior/'source-pins.json',
        run/'result.json', run/'eligibility.json', run/'strict-numerical.json', run/'run.vcs.log',
        run/'commit.csv', run/'vector.csv', image/'build.json', build/'build.json',
        Path(__file__).resolve(), HERE/'test_q4_m4_dut_fail_v5.py']}
    require(previous['evidence_sha256'][str(run/'run.vcs.log')] == identities[str(run/'run.vcs.log')],
            'Raw evidence differs from original failed audit')
    output.mkdir()
    report = dict(state='FAIL', original_worker_state='FAIL', original_audit_state='FAIL',
        original_worker_reclassified=False, original_audit_reclassified=False,
        simulations_launched=0, raw_log_modified=False, power_measured=False)
    try:
        with (output/'host-tests.log').open('x') as stream:
            subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', str(HERE),
                '-p', 'test_q4_m4_dut_fail_v5.py', '-v'], stdout=stream, stderr=subprocess.STDOUT,
                timeout=120, check=True)
        text, scanned = scan(run/'run.vcs.log', source, source_line)
        require(scanned['raw_sha256'] == identities[str(run/'run.vcs.log')] and
                scanned['expected_numerical_failure_records'][0]['line'] == int(failure[1]), 'Raw failure lineage mismatch')
        (output/'actual-numerical-records.log').write_text(text)
        save(output/'raw-classification.json', scanned)
        try:
            strict = old.parse_log(text, m)
        except ValueError as exc:
            strict = dict(state='FAIL', error=str(exc))
        require(strict['state'] == 'FAIL', 'Strict failure unexpectedly absent')
        save(output/'strict-offline.json', strict)
        eligible = old.eligibility(text, m, run/'commit.csv')
        require(eligible['strict_numerical_state'] == 'FAIL' and eligible['strict_failure_records'] == 4,
                'Failure is not exactly the four retained Q8/PACK checks')
        checks = eligible['comparisons']
        require(all(c['mismatches'] == 0 for c in checks if c['kind'] in ('GUARD', 'OUT')) and
                all(c['mismatches'] > 0 for c in checks if c['kind'] in ('Q8', 'PACK')),
                'Non-quantization numerical/guard failure')
        save(output/'eligibility-numerical.json', eligible)
        env = dict(json.loads((image/'plan.json').read_text())['environment'],
            PYTHONPATH=plan['protocol_pythonpath'], PYTHONDONTWRITEBYTECODE='1')
        argv = [sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events', '--require-backend',
            '--require-axi', '--require-axi-write', '--vector-trace', str(run/'vector.csv'),
            '--log', str(run/'run.vcs.log'), '--simv', str(image/'sim/simv'), '--elf', case['elf'],
            '--output', str(output/'protocol-original.json')]
        with (output/'protocol.log').open('x') as stream:
            proc = subprocess.run(argv, cwd=output, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=1200)
        require(proc.returncode == 1, 'Original protocol FAIL must remain FAIL')
        proof = json.loads((output/'protocol-original.json').read_text())
        scoped = protocol_scope(proof, case, image_build['image_pins'][str(image/'sim/simv')],
            identities[str(run/'run.vcs.log')], identities[str(run/'vector.csv')])
        save(output/'protocol-scoped.json', scoped)
        for inventory in (pins, image_sources, image_build['image_pins'], identities, sources):
            old.verify(inventory)
        report.update(state='POWER_ELIGIBLE', strict_numerical_state='FAIL',
            eligibility_kind='RELATIVE_POWER_ONLY_WITH_EXPLICIT_NUMERICAL_DUT_FAIL',
            original_protocol_state='FAIL', full_protocol_pass=False,
            traffic_protocol_checked=True, architectural_traps=0,
            power_numeric_summaries=eligible['power_numeric_summaries'],
            commit_work=eligible['commit_work'], comparisons=eligible['comparisons'],
            source_semantics=sources, prior_audit=str(prior), original_run=str(run),
            scope='Original captured runtime computation, bounded finite output error and full work only; '
                  'strict Q8/packed/UVM FAILs remain. Not RTL correctness, IEEE-FDIV, protocol PASS or measured power.')
    except Exception as exc:
        report['error'] = repr(exc)
    all_pins = dict(pins)
    all_pins.update(identities)
    all_pins.update(sources)
    save(output/'source-pins.json', all_pins)
    report['artifacts'] = {str(p): sha(p) for p in output.rglob('*') if p.is_file()}
    save(output/'result.json', report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for key in ('run', 'prior-audit', 'output'):
        p.add_argument('--'+key, type=Path, required=True)
    a = p.parse_args()
    result = audit(a.run, a.prior_audit, a.output)
    print(json.dumps({k: v for k, v in result.items() if k not in ('artifacts', 'comparisons')}))
    return int(result['state'] != 'POWER_ELIGIBLE')


if __name__ == '__main__':
    raise SystemExit(main())
