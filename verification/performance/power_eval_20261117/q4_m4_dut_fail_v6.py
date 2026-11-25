#!/usr/bin/env python3
"""Compose a scoped power audit from raw evidence, retaining every strict/UVM FAIL."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('dut_fail_v5_unchanged', HERE/'q4_m4_dut_fail_v5.py')
v5 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v5)
old, require, sha, save = v5.old, v5.require, v5.sha, v5.save


def expected_issues(raw, classification):
    eoc = []
    with Path(raw).open() as stream:
        for line_number, line in enumerate(stream, 1):
            if line.rstrip('\r\n') == 'Core Test *** FAILED *** (tohost = 1)':
                eoc.append((line_number, line.rstrip('\r\n')))
    require(len(eoc) == 1, 'One numeric failed EOC required')
    failure = classification['expected_numerical_failure_records']
    require(len(failure) == 2 and failure[0]['kind'] == 'EXPECTED_NUMERIC_DUT_FAIL' and
            failure[1]['kind'] == 'ERROR_SUMMARY_ONE_DUT_FAIL' and
            eoc[0][0] < failure[0]['line'] < failure[1]['line'], 'Causal failure order')
    return [f'line {eoc[0][0]}: Core Test failure: {eoc[0][1]}',
            *[f"line {r['line']}: UVM diagnostic: {r['raw']}" for r in failure],
            'missing Core Test *** SUCCESS marker', v5.PROTOCOL_ISSUE]


def check_scope(proof, expected, case, simv_hash, log_hash, vector_hash):
    require(proof.get('status') == 'FAIL' and proof.get('issues') == expected and len(expected) == 5,
            'Protocol issues are not exactly the five bound numerical-DUT_FAIL diagnostics')
    require(all(proof.get('contract_counts', {}).get(k) == 0 for k in
                ('exceptions', 'protocol_errors', 'outstanding')), 'Protocol or architectural fault')
    for key, value in (('elf_sha256', case['elf_sha256']), ('simv_sha256', simv_hash),
                       ('log_sha256', log_hash), ('vector_trace_sha256', vector_hash)):
        require(proof.get(key) == value, 'Evidence identity: '+key)
    return dict(traffic_protocol_checked=True, full_protocol_pass=False, original_protocol_status='FAIL',
                bound_numerical_failure_diagnostics=expected, additional_protocol_issues=[])


def audit(run, prior, output):
    run, prior = Path(run).resolve(strict=True), Path(prior).resolve(strict=True)
    output = Path(output).absolute()
    require(output == output.resolve() and output.parent == v5.v4.OUT and not output.exists() and
            re.fullmatch(r'power_q4_m4_dut_fail_20261117_[A-Za-z0-9_.-]+', output.name), 'Fresh audit output required')
    previous = json.loads((prior/'result.json').read_text())
    require(previous['state'] == 'FAIL' and previous.get('error') ==
            "ValueError('Protocol failure is not solely the preserved numerical UVM summary')",
            'Exact original partial audit required')
    old.verify(previous['artifacts'])
    inherited = json.loads((prior/'source-pins.json').read_text())
    old.verify(inherited)
    campaign = run.parent.parent
    plan = json.loads((campaign/'plan.json').read_text())
    cases = [c for c in plan['cases'] if c['id'] == run.name]
    require(len(cases) == 1, 'Case identity')
    case = cases[0]
    build = Path(case['checker'][case['checker'].index('--build')+1])
    m = old.receipt(build)
    require(m['mode'] == 'rvv' and m['elf_sha256'] == case['elf_sha256'], 'Original RVV firmware required')
    image = Path(plan['image'])
    image_build = json.loads((image/'build.json').read_text())
    image_sources = json.loads((image/'source-pins.json').read_text())
    old.verify(image_sources)
    old.verify(image_build['image_pins'])
    package, source_line, sources = v5.source_proof(image)
    for path, digest in sources.items():
        require(image_sources.get(path) == digest or inherited.get(path) == digest, 'Unpinned UVM source semantics')
    files = [run/name for name in ('run.vcs.log', 'commit.csv', 'vector.csv', 'result.json',
                                   'strict-numerical.json', 'eligibility.json')]
    files += [prior/'result.json', prior/'source-pins.json', prior/'protocol-original.json',
              Path(__file__).resolve(), HERE/'test_q4_m4_dut_fail_v6.py']
    identities = {str(p): sha(p) for p in files}
    output.mkdir()
    result = dict(state='FAIL', original_worker_state='FAIL', original_audit_state='FAIL',
        original_worker_reclassified=False, original_audit_reclassified=False,
        simulations_launched=0, raw_log_modified=False, power_measured=False, full_protocol_pass=False)
    try:
        with (output/'host-tests.log').open('x') as log:
            subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', str(HERE),
                '-p', 'test_q4_m4_dut_fail_v6.py', '-v'], stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
        text, classified = v5.scan(run/'run.vcs.log', package, source_line)
        require(classified['raw_sha256'] == identities[str(run/'run.vcs.log')], 'Raw log drift')
        save(output/'raw-classification.json', classified)
        expected = expected_issues(run/'run.vcs.log', classified)
        proof = json.loads((prior/'protocol-original.json').read_text())
        scoped = check_scope(proof, expected, case, image_build['image_pins'][str(image/'sim/simv')],
            identities[str(run/'run.vcs.log')], identities[str(run/'vector.csv')])
        save(output/'protocol-scoped.json', scoped)
        eligible = old.eligibility(text, m, run/'commit.csv')
        require(eligible['strict_numerical_state'] == 'FAIL' and eligible['strict_failure_records'] == 4,
                'Numeric failure inventory')
        require(all(c['mismatches'] == 0 for c in eligible['comparisons'] if c['kind'] in ('GUARD', 'OUT')) and
                all(c['mismatches'] > 0 for c in eligible['comparisons'] if c['kind'] in ('Q8', 'PACK')),
                'Failure is not only Q8/PACK numerical identity')
        save(output/'eligibility-numerical.json', eligible)
        for inventory in (inherited, identities, image_sources, image_build['image_pins'], sources):
            old.verify(inventory)
        result.update(state='POWER_ELIGIBLE', eligibility_kind='RELATIVE_POWER_ONLY_NUMERICAL_DUT_FAIL',
            strict_numerical_state='FAIL', original_uvm_status='FAIL', original_protocol_status='FAIL',
            traffic_protocol_checked=True, protocol_checker_rerun=False,
            protocol_evidence=str(prior/'protocol-original.json'),
            expected_diagnostics=expected, architectural_traps=0,
            commit_work=eligible['commit_work'], power_numeric_summaries=eligible['power_numeric_summaries'],
            comparisons=eligible['comparisons'], original_run=str(run), previous_audit=str(prior),
            scope='Finite bounded-output-error relative-power eligibility only. Strict Q8/packed checks, '
                  'original UVM/protocol and both previous audits remain FAIL. Not correctness/signoff or measured power.')
    except Exception as exc:
        result['error'] = repr(exc)
    pins = dict(inherited)
    pins.update(identities)
    pins.update(sources)
    save(output/'source-pins.json', pins)
    result['artifacts'] = {str(p): sha(p) for p in output.rglob('*') if p.is_file()}
    save(output/'result.json', result)
    return result


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
