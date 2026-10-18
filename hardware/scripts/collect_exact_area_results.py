#!/usr/bin/env python3
"""Report completed, matched local area ablations; never extrapolate SoC savings."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def number(text, label):
    match = re.search(re.escape(label) + r'\s*:\s*([-+0-9.eE]+)', text)
    if not match:
        raise ValueError('Missing report field: ' + label)
    return float(match[1])


def collect(directory):
    manifest = json.loads((directory / 'manifest.json').read_text())
    scripts = [(directory / mode / 'run.tcl').read_text() for mode in ('0', '1')]
    parameter_pattern = r'Shared(?:Extract|BeatUpdate|Normalize)=[01]'
    if manifest.get('accumulator_mechanism') == 'representation':
        parameter_pattern = r'ExponentSegmented=[01]'
    elif manifest.get('accumulator_mechanism') == 'segments':
        parameter_pattern = r'CompactSegments=[01]'
    elif manifest.get('accumulator_mechanism') in ('direct-read', 'wide-segments'):
        parameter = {'direct-read': 'DirectBinRead', 'wide-segments': 'WideSegments'}[manifest['accumulator_mechanism']]
        parameter_pattern = parameter + r'=[01]'
        for mode, script in enumerate(scripts):
            if re.findall(parameter_pattern, script) != [f'{parameter}={mode}']:
                raise ValueError('Expected exactly one independent candidate toggle')
    normalized = [re.sub(parameter_pattern, 'CandidateOption=MODE', text) for text in scripts]
    if normalized[0] != normalized[1]:
        raise ValueError('Synthesis scripts differ beyond the candidate parameters')
    root = Path(__file__).resolve().parents[2]
    frozen_libraries = json.loads((root / 'hardware/build/synthesis/full_retry2/manifest.json').read_text())['libraries']
    hashes = {entry['path']: entry['sha256'] for entry in frozen_libraries}
    for library in manifest['libraries']:
        if hashlib.sha256(Path(library).read_bytes()).hexdigest() != hashes.get(library):
            raise ValueError('Technology library differs from the frozen baseline: ' + library)
        if 'library_sha256' in manifest and manifest['library_sha256'].get(library) != hashes.get(library):
            raise ValueError('Run library hash differs from baseline: ' + library)
    source = list(directory.glob('fp32_exact_reduction_*.sv'))
    if len(source) != 1 or hashlib.sha256(source[0].read_bytes()).hexdigest() != manifest['source_sha256']:
        raise ValueError('Frozen RTL hash mismatch')
    rows = []
    for mode in ('0', '1'):
        status = manifest['results'].get(mode, {})
        if not status.get('complete') or status.get('returncode') != 0:
            raise ValueError('Mode ' + mode + ' has not completed successfully')
        run = directory / mode
        for key, name in (('script_sha256', 'run.tcl'), ('log_sha256', 'console.log')):
            if key in status and hashlib.sha256((run / name).read_bytes()).hexdigest() != status[key]:
                raise ValueError('Frozen run artifact changed: ' + str(run / name))
        log = (run / 'console.log').read_text()
        if 'FINALIZE_PPA_COMPLETE' not in log.splitlines() or re.search(r'^Error:', log, re.M):
            raise ValueError('Missing completion marker or tool error')
        area = (run / 'area.rpt').read_text()
        qor = (run / 'qor.rpt').read_text()
        timing = (run / 'timing.rpt').read_text()
        slacks = re.findall(r'slack\s+\((?:MET|VIOLATED)\)\s+([-+0-9.]+)', timing)
        if not slacks:
            raise ValueError('No timing paths reported')
        rows.append({'mode': int(mode), 'cell_area': number(area, 'Total cell area'),
                     'sequential_cells': number(qor, 'Sequential Cell Count'),
                     'worst_setup_slack_ns': min(map(float, slacks)),
                     'setup_tns_ns': number(qor, 'Total Negative Slack'),
                     'setup_violating_paths': number(qor, 'No. of Violating Paths'),
                     'worst_hold_slack_ns': number(qor, 'Worst Hold Violation'),
                     'hold_violating_paths': number(qor, 'No. of Hold Violations'),
                     'report_hashes': {p: hashlib.sha256((run / p).read_bytes()).hexdigest()
                                       for p in ('area.rpt', 'qor.rpt', 'timing.rpt', 'run.tcl')}})
    return {'directory': str(directory), 'source_sha256': manifest['source_sha256'],
            'constraints_match': True, 'library_hashes': {p: hashes[p] for p in manifest['libraries']},
            'results': rows, 'area_saved': rows[0]['cell_area'] - rows[1]['cell_area'],
            'area_saved_percent': 100 * (1 - rows[1]['cell_area'] / rows[0]['cell_area']),
            'scope': 'Local synthesis only; unchanged simulation cycles do not establish unchanged SoC Fmax.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directories', nargs='+', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    reports = [collect(p.resolve()) for p in args.directories]
    with args.out.open('x') as stream:
        json.dump(reports, stream, indent=2)
        stream.write('\n')
    for report in reports:
        print(f"{report['directory']}: area saved {report['area_saved_percent']:.3f}%")


if __name__ == '__main__':
    main()
