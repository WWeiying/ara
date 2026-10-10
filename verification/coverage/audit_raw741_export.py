"""Independent post-export identity/waiver audit; never launches DVE."""
import argparse
import csv
import json
from pathlib import Path

import run_admitted_741_dve as report

life, require = report.life, report.require


def hierarchy(path):
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames is not None and 'Name' in reader.fieldnames and
                'Depth' in reader.fieldnames, 'Missing hierarchy columns')
        rows = list(reader)
    report.system_row(path)
    result = []
    for row in rows:
        require(None not in row and row['Name'] and row['Depth'].isdigit(), 'Malformed hierarchy row')
        result.append((row['Name'], row['Depth']))
    return result


def identity_contract(expected_inputs, expected_selected, inputs, selected, gui, waiver,
                      old_hierarchy, new_hierarchy, exclusion_names):
    require(len(expected_inputs) == len(set(expected_inputs)) == 742 and inputs == expected_inputs,
            'Actual742 input identities differ')
    require(len(expected_selected) == len(set(expected_selected)) == 741 and
            selected == expected_selected, 'Actual741 selected identities differ')
    logged = [line[len('DVE_SELECTED_TESTS: '):].split() for line in gui.splitlines()
              if line.startswith('DVE_SELECTED_TESTS: ')]
    require(logged == [expected_selected], 'GUI741 identity evidence differs')
    require(gui.splitlines().count('DVE_COVERAGE_EXPORT_DONE') == 1 and
            'DVE_COVERAGE_EXPORT_FAILED' not in gui, 'GUI completion evidence differs')
    require(len(old_hierarchy) == len(new_hierarchy) == 2989 and
            old_hierarchy == new_hierarchy, 'Full Name/Depth sequence differs')
    require(waiver.get('mode') == 'off' and waiver.get('status') == 'DISABLED' and
            waiver.get('waived_report') is None and waiver.get('raw_report') == 'summary.csv',
            'Actual waiver mode differs')
    require(not exclusion_names, 'Unexpected exclusion artifacts')


def audit(directory, output):
    require(directory.parent == output.parent == life.OUT and directory.resolve() == directory and
            output.resolve() == output and not output.exists(), 'Independent fresh receipt required')
    book = life.read_bound(report.BASE / 'admission-manifest.json', report.SEAL)
    pins = life.merge_pins(book['input_pins'], book['output_pins'])
    pins = life.merge_pins(pins, {str(report.BASE / 'admission-manifest.json'): report.SEAL,
                                str(report.PRIOR): report.PRIOR_SHA})
    life.check(pins)
    raw = life.read_bound(report.admission.RAW, report.admission.RAW_SHA)
    expected_inputs = raw['input_ledger'] + [str(report.admission.VDB)]
    require((report.BASE / 'combined-inputs.txt').read_text().splitlines() == expected_inputs,
            'Admitted ledger differs')
    tests = list((report.admission.VDB / 'snps/coverage/db/testdata').iterdir())
    require(len(tests) == 1 and tests[0].is_dir() and not tests[0].is_symlink() and
            tests[0].name == 'qbs_gap113_payload_toggle', 'Candidate native identity differs')
    expected_selected = raw['selected_tests'] + [str(report.admission.VDB.with_suffix('') / tests[0].name)]
    names = ('inputs.txt', 'selected_tests.txt', 'DVEfiles/dve_gui.log', 'waiver_status.json',
             'summary.csv', 'diagnostics.txt', 'report-result.json')
    artifacts = {str(directory / name): life.digest(directory / name) for name in names}
    completed = json.loads((directory / 'report-result.json').read_bytes())
    require(completed['status'] == 'RAW741_DVE_REPORT_VERIFIED' and completed['tests'] == 741 and
            completed['admission_seal'] == report.SEAL and completed['waiver_mode'] == 'off' and
            completed['summary_sha256'] == artifacts[str(directory / 'summary.csv')],
            'Original runner terminal result differs')
    require((directory / 'diagnostics.txt').read_bytes() == b'', 'Nonempty DVE diagnostics')
    waiver = json.loads((directory / 'waiver_status.json').read_bytes())
    require(waiver['design_sha256'] == raw['pins'][raw['input_ledger'][0] +
                '/snps/coverage/db/design/verilog.design.xml'], 'Waiver design epoch differs')
    identity_contract(expected_inputs, expected_selected,
        (directory / 'inputs.txt').read_text().splitlines(),
        (directory / 'selected_tests.txt').read_text().splitlines(),
        (directory / 'DVEfiles/dve_gui.log').read_text(), waiver,
        hierarchy(report.PRIOR), hierarchy(directory / 'summary.csv'),
        [str(p) for p in directory.rglob('*') if p.is_file() and
         (p.suffix == '.el' or p.name.startswith('summary_waived'))])
    life.check(pins)
    life.check(artifacts)
    helpers = {str(Path(p).resolve()): life.digest(Path(p).resolve()) for p in
               (__file__, report.__file__, Path(__file__).with_name('test_audit_raw741_export.py'))}
    receipt = dict(status='RAW741_POST_EXPORT_IDENTITY_WAIVER_AUDIT_PASS', report=str(directory),
        admission_seal=report.SEAL, input_count=742, selected_count=741, hierarchy_rows=2989,
        exact_full_hierarchy_sequence=True, waiver_mode='off', exclusions=[],
        report_pins=artifacts, helper_pins=helpers, source_pins=pins,
        simulations_started=False, DVE_started=False, new_RTL_signoff=False)
    life.save(output, receipt)
    print(json.dumps(dict(status=receipt['status'], output=str(output), seal=life.digest(output))))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    audit(a.report.absolute(), a.output.absolute())
