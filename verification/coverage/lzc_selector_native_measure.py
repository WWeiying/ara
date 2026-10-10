#!/usr/bin/env python3
"""Execute a reviewed standalone native capture; never opens processor VDBs."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

import lzc_selector_native_prepare as native
import lzc_selector_native_run as runner


def measure(prepared, evidence, top, suffix='lzc_selector_native_capture-01',
            script='lzc_selector_native_capture.tcl'):
    calibration = json.loads((evidence / 'calibration.json').read_bytes())
    native.require(calibration['status'] == 'STANDALONE_SELFCHECK_PASS_8', 'Eight real selfchecks required')
    matches = [r for r in calibration['results'] if r['top'] == top]
    native.require(len(matches) == 1 and matches[0]['selfcheck'] == 'PASS', 'Not selfchecked standalone case')
    case = prepared / top
    capture = case / suffix
    native.require(capture.parent == case and suffix.startswith('lzc_selector_native_capture-'),
                   'Standalone capture directory required')
    plan = json.loads((capture / 'capture-plan.json').read_bytes())
    native.require(plan['experiment']['cwd'] == str(case) and
                   prepared.parent == native.OUT and top.startswith('lzc_selector_native_'),
                   'Standalone plan owner differs')
    native.require(plan['command'] == ['timeout', '300s', 'xvfb-run', '-a', 'dve', '-full64',
                   '-cov', '-script', str(native.HERE / script)] and
                   script in ('lzc_selector_native_capture.tcl', 'lzc_selector_native_capture_v2.tcl',
                              'lzc_selector_native_capture_v3.tcl'),
                   'Unreviewed DVE command')
    native.require(plan['environment'] == {'LZC_SELECTOR_NATIVE_SELECTION': str(capture / 'selection.tcl')},
                   'Foreign selection environment')
    native.require(len(plan['targets']) == (4 if script.endswith('_v3.tcl') else 6),
                   'Exact standalone singleton targets required')
    runner.check_pins(plan['pins'])
    env = dict(os.environ, **plan['environment'])
    for variable in ('DVE_REVIEWED_WAIVERS', 'DVE_COVERAGE_OUTPUT'):
        env.pop(variable, None)
    started = time.monotonic()
    status = dict(top=top, old_processor_exclusions=False, processor_admission=False,
                  command=plan['command'], cwd=str(capture))
    try:
        with (capture / 'dve.log').open('x') as log:
            result = subprocess.run(plan['command'], cwd=capture, env=env, stdout=log,
                                    stderr=subprocess.STDOUT, timeout=310)
        status['returncode'] = result.returncode
        native.require(result.returncode == 0, 'DVE process did not complete')
        gui_log = capture / 'DVEfiles/dve_gui.log'
        text = gui_log.read_text()
        native.require('LZC_SELECTOR_NATIVE_CAPTURE_COMPLETE_PENDING_SEMANTIC_REVIEW' in text and
                       'LZC_SELECTOR_NATIVE_FAILED' not in text, 'Native capture failed; inspect DVE log')
        runner.check_pins(plan['pins'])
        status['status'] = 'CAPTURE_COMPLETE_PENDING_OFFLINE_VERIFICATION'
    except Exception as error:
        status.update(status='FAILED_RECORDED', error=str(error))
        raise
    finally:
        status['elapsed_seconds'] = round(time.monotonic() - started, 3)
        status['artifacts'] = {str(p): native.sha(p) for p in capture.rglob('*') if p.is_file()}
        native.write(capture / 'native-capture-status.json', status)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--top', required=True)
    parser.add_argument('--suffix', default='lzc_selector_native_capture-01')
    parser.add_argument('--script', default='lzc_selector_native_capture.tcl')
    args = parser.parse_args()
    measure(args.prepared.absolute(), args.evidence.absolute(), args.top, args.suffix, args.script)


if __name__ == '__main__':
    main()
