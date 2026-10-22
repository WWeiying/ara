"""Verify the actual DVE693 membership without touching prior report pins."""
import csv
import json
from pathlib import Path
from run_gap83_simulation import ROOT, digest, save


def main():
    report = ROOT / 'verification/out/raw693-dve-20261006-01'
    base = ROOT / 'verification/out/gap86-offline-admitted-693-20261006-01'
    inputs = (base / 'combined-inputs.txt').read_text().splitlines()
    if len(inputs) != 694 or len(set(inputs)) != 694:
        raise ValueError('Wrong unique population')
    if (report / 'inputs.txt').read_text().splitlines() != inputs:
        raise ValueError('Input mismatch')
    expected = []
    for name in inputs[1:]:
        vdb = Path(name)
        tests = list((vdb / 'snps/coverage/db/testdata').iterdir())
        if len(tests) != 1 or not tests[0].is_dir():
            raise ValueError('Ambiguous tests: ' + name)
        expected.append(str(vdb.with_suffix('') / tests[0].name))
    if (report / 'selected_tests.txt').read_text().splitlines() != expected:
        raise ValueError('Actual DVE selection differs')
    if len(set(expected)) != 693 or (report / 'diagnostics.txt').read_bytes():
        raise ValueError('Duplicates/diagnostics')
    if json.loads((report / 'waiver_status.json').read_bytes())['status'] != 'DISABLED':
        raise ValueError('Unexpected exclusions')
    if 'DVE_COVERAGE_EXPORT_DONE' not in (report / 'DVEfiles/dve_gui.log').read_text():
        raise ValueError('Incomplete report')
    with (report / 'summary.csv').open() as stream:
        rows = [r for r in csv.DictReader(stream) if r['Name'] == 'i_system']
    if len(rows) != 1:
        raise ValueError('Ambiguous summary')
    paths = [base / 'combined-inputs.txt', report / 'inputs.txt', report / 'selected_tests.txt',
             report / 'diagnostics.txt', report / 'waiver_status.json', report / 'summary.csv',
             report / 'DVEfiles/dve_gui.log', Path(__file__).resolve()]
    save(report / 'population-verification.json', dict(status='VERIFIED_HISTORICAL_RAW_REPORT',
         admitted_tests=693, current_RTL_signoff=False, summary=rows[0],
         pins={str(path): digest(path) for path in paths}))
    print(json.dumps(rows[0]))


if __name__ == '__main__':
    main()
