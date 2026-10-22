"""Check actual DVE population against the admitted historical union."""
import csv
import json
from pathlib import Path
from run_gap83_simulation import ROOT, digest, save


def main():
    report = ROOT / 'verification/out/raw692-dve-20261006-01'
    base = ROOT / 'verification/out/gap85-offline-admitted-692-20261006-01'
    expected = (base / 'combined-inputs.txt').read_text().splitlines()
    actual = (report / 'inputs.txt').read_text().splitlines()
    if actual != expected or len(actual) != 693 or len(set(actual)) != 693:
        raise ValueError('Design/test population mismatch')
    selected_expected = []
    for name in expected[1:]:
        vdb = Path(name)
        tests = list((vdb / 'snps/coverage/db/testdata').iterdir())
        if len(tests) != 1 or not tests[0].is_dir():
            raise ValueError('Ambiguous test data: ' + name)
        selected_expected.append(str(vdb.with_suffix('') / tests[0].name))
    selected = (report / 'selected_tests.txt').read_text().splitlines()
    if selected != selected_expected or len(set(selected)) != 692:
        raise ValueError('Actual DVE selected tests mismatch')
    if (report / 'diagnostics.txt').read_bytes():
        raise ValueError('DVE diagnostics present')
    if json.loads((report / 'waiver_status.json').read_bytes())['status'] != 'DISABLED':
        raise ValueError('Unexpected exclusions')
    if 'DVE_COVERAGE_EXPORT_DONE' not in (report / 'DVEfiles/dve_gui.log').read_text():
        raise ValueError('Incomplete export')
    with (report / 'summary.csv').open() as stream:
        rows = [r for r in csv.DictReader(stream) if r['Name'] == 'i_system']
    if len(rows) != 1:
        raise ValueError('Ambiguous hierarchy summary')
    files = [base / 'combined-inputs.txt', report / 'inputs.txt',
             report / 'selected_tests.txt', report / 'diagnostics.txt',
             report / 'waiver_status.json', report / 'summary.csv',
             report / 'DVEfiles/dve_gui.log', Path(__file__).resolve()]
    result = dict(status='VERIFIED_HISTORICAL_RAW_REPORT', admitted_tests=692,
                  current_RTL_signoff=False, summary=rows[0],
                  pins={str(p): digest(p) for p in files})
    target = report / 'population-verification.json'
    if target.exists():
        raise ValueError('Preserve existing verification artifact')
    save(target, result)
    print(json.dumps(result['summary']))


if __name__ == '__main__':
    main()
