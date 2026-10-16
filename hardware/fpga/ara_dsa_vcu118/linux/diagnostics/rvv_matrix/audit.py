"""Audit completed board markers separately from references and pending cases."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re


def audit(manifest, report):
    cases = {case['name']: case for case in manifest['cases']}
    if len(cases) != len(manifest['cases']):
        raise ValueError('Duplicate planned case')
    if report['inputs']['cases'] != manifest['cases']:
        raise ValueError('Board/reference case identities differ')
    if report['inputs']['archive_sha256'] != manifest['archive_sha256']:
        raise ValueError('Board/reference archive identities differ')
    if report['rtl_modified'] or report['board_reset']:
        raise ValueError('Not an unchanged-image campaign')
    seen = set()
    counts = Counter()
    configurations = 0
    findings = []
    for result in report['results']:
        name = result['name']
        if name not in cases or name in seen:
            raise ValueError('Unexpected or repeated board case: ' + name)
        seen.add(name)
        status = result['status']
        if status not in ('passed', 'failed', 'stalled', 'incomplete', 'running'):
            raise ValueError('Unknown result status')
        if status == 'passed':
            marker = cases[name]['pass_marker']
            lines = [line for line in result.get('output', '').splitlines()
                     if line.startswith(marker)]
            if result.get('exit_code') != 0 or len(lines) != 1:
                raise ValueError('Missing unique numerical pass: ' + name)
            from guest_batch import configuration_count
            count = configuration_count(cases[name], lines[0])
            if count is None:
                raise ValueError('Missing executed configuration count: ' + name)
            configurations += count
        elif status != 'running':
            findings.append(dict(name=name, status=status,
                                 exit_code=result.get('exit_code'),
                                 error=result.get('error'), output=result.get('output')))
        counts[status] += 1
    counts['not_run'] = len(cases) - len(seen)
    complete = report['state'] == 'all_cases_finished_review_results'
    if complete and (counts['running'] or counts['not_run'] or
                     counts['stalled'] or counts['incomplete']):
        raise ValueError('Completion state contradicts results')
    return dict(planned=len(cases), counts=dict(counts),
                passing_configurations=configurations, complete=complete,
                passed=complete and counts['failed'] == 0, findings=findings)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('roots', nargs='+', type=Path)
    args = parser.parse_args()
    summaries = []
    for root in args.roots:
        result = audit(json.loads((root/'transfer_manifest.json').read_text()),
                       json.loads((root/'board_report.json').read_text()))
        summaries.append(dict(root=str(root), **result))
    print(json.dumps(summaries, indent=2))
