#!/usr/bin/env python3
"""Complete independent standalone captures and retain verified case evidence."""
import argparse
import json
from pathlib import Path

import lzc_selector_native_measure as measure
import lzc_selector_native_prepare as native
from lzc_selector_native_verify import verify


def run(prepared, evidence):
    experiments = json.loads((prepared / 'experiments.json').read_bytes())['experiments']
    results = []
    for experiment in experiments:
        top = experiment['top']
        capture = prepared / top / 'lzc_selector_native_capture-03'
        status = capture / 'native-capture-status.json'
        if not status.exists():
            measure.measure(prepared, evidence, top, capture.name, 'lzc_selector_native_capture_v3.tcl')
        report = verify(capture)
        target = evidence / (top + '-native.json')
        native.require(not target.exists(), 'Do not overwrite verified evidence')
        native.write(target, report)
        results.append(str(target))
        print(f"STANDALONE_NATIVE_VERIFIED {top} rows={report['protected_rows_per_audit']} "
              f"roundtrips={report['singleton_roundtrips']}", flush=True)
    native.write(evidence / 'native-batch.json', dict(status='STANDALONE_NATIVE_CAPTURES_VERIFIED_8',
                 reports=results, old_processor_exclusions=False, application_approval=False,
                 limitation='XML-only op16 subexpressions are not independently native-qualified.'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    run(args.prepared.absolute(), args.evidence.absolute())
