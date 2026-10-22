"""Verify a PASS-only historical union against actual DVE selected tests."""
import argparse
import csv
import json
from pathlib import Path
from run_gap83_simulation import ROOT, digest, save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    base, report = args.base.resolve(), args.report.resolve()
    if base.parent != ROOT / 'verification/out' or report.parent != base.parent:
        raise ValueError('Independent historical evidence directories required')
    status = json.loads((base / 'status.json').read_bytes())
    if status['status'] != 'PASS_RAW_UNION_HISTORICAL_ONLY':
        raise ValueError('Unadmitted union')
    count = status['aggregate_passed']
    union = json.loads((base / 'combined-bits.json').read_bytes())
    inputs = (base / 'combined-inputs.txt').read_text().splitlines()
    if len(inputs) != count + 1 or len(set(inputs)) != count + 1 or inputs[1:] != union['tests']:
        raise ValueError('Union membership mismatch')
    if (report / 'inputs.txt').read_text().splitlines() != inputs:
        raise ValueError('DVE input mismatch')
    expected = []
    for name in inputs[1:]:
        vdb = Path(name)
        tests = list((vdb / 'snps/coverage/db/testdata').iterdir())
        if len(tests) != 1 or not tests[0].is_dir():
            raise ValueError('Ambiguous test data: ' + name)
        expected.append(str(vdb.with_suffix('') / tests[0].name))
    if len(set(expected)) != count or (report / 'selected_tests.txt').read_text().splitlines() != expected:
        raise ValueError('Actual selected tests differ')
    if (report / 'diagnostics.txt').read_bytes() or json.loads(
            (report / 'waiver_status.json').read_bytes())['status'] != 'DISABLED':
        raise ValueError('Diagnostics or unexpected exclusions')
    if 'DVE_COVERAGE_EXPORT_DONE' not in (report / 'DVEfiles/dve_gui.log').read_text():
        raise ValueError('Incomplete export')
    with (report / 'summary.csv').open() as stream:
        rows = [r for r in csv.DictReader(stream) if r['Name'] == 'i_system']
    if len(rows) != 1:
        raise ValueError('Ambiguous hierarchy summary')
    files = [base / 'status.json', base / 'combined-bits.json', base / 'combined-inputs.txt',
             report / 'inputs.txt', report / 'selected_tests.txt', report / 'diagnostics.txt',
             report / 'waiver_status.json', report / 'summary.csv',
             report / 'DVEfiles/dve_gui.log', Path(__file__).resolve()]
    save(report / 'population-verification.json', dict(status='VERIFIED_HISTORICAL_RAW_REPORT',
         admitted_tests=count, current_RTL_signoff=False, summary=rows[0],
         pins={str(path): digest(path) for path in files}))
    print(json.dumps(dict(admitted_tests=count, summary=rows[0])))


if __name__ == '__main__':
    main()
