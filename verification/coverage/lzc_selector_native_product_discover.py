#!/usr/bin/env python3
"""Prepare/launch bounded read-only product DVE discovery. Never captures EL."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

import lzc_selector_native_product_prepare as product
from lzc_selector_native_prepare import require, sha, tcl_word, write, BUILD

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / 'lzc_selector_native_product_discover.tcl'


def safe_script(text):
    forbidden = ('gui_exclusion', 'gui_exclude', 'gui_cov_excl', 'apply_reviewed',
                 'exec ', 'eval ', 'gui_load_session', '.el')
    require(not any(word in text for word in forbidden), 'Read-only script contains forbidden API')
    require(text.count('source ') == 1 and 'source $env(LZC_SELECTOR_NATIVE_PRODUCT_SELECTION)' in text,
            'Only generated static selection may be sourced')


def prepare(prepared, output):
    require(prepared.parent == product.OUT and output.parent == product.OUT and not output.exists(),
            'Fresh direct discovery directory required')
    plan_path = prepared / 'product-plan.json'
    plan = json.loads(plan_path.read_bytes())
    product.check_pins(json.loads((prepared / 'product-plan.sha256.json').read_bytes()))
    product.check_pins(plan['pins'])
    require(plan['status'] == 'PREPARED_707_PRODUCT_PARENT_REVIEW_REQUIRED_NO_LAUNCH' and
            not plan['application_approval'] and not plan['native_qualified'] and
            plan['base'] == str(product.BASE), 'Exact reviewed static plan required')
    safe_script(SCRIPT.read_text())
    bitmap = json.loads((product.BASE / 'combined-bits.json').read_bytes())
    tests, dirs = [], []
    for database in bitmap['tests']:
        root = Path(database) / 'snps/coverage/db/testdata'
        children = [p for p in root.iterdir() if p.is_dir()]
        require(len(children) == 1, 'Ambiguous admitted test directory')
        dirs.append(database)
        tests.append(str(Path(database).with_suffix('') / children[0].name))
    require(len(set(tests)) == len(tests) == 707, 'Duplicate/foreign native test population')
    scopes = sorted({r['scope'] for r in plan['targets']})
    require(len(scopes) == 36, 'Exact product child set required')
    children = []
    for scope in scopes:
        entries = [r for r in plan['protected'] if r['scope'] == scope]
        require(len(entries) == 2 and all(r['module_checksum'] == '3250293308' for r in entries),
                'Product child module ownership differs')
        cond = next(r for r in entries if r['metric'] == 'cond')
        expressions = sorted({p['expression'] for p in cond['points'] if p['attributes']['optype'] != '16'})
        params = next(r['parameters'] for r in plan['targets'] if r['scope'] == scope)
        children.append([scope, '3250293308', ','.join(f'{k}={v}' for k, v in sorted(params.items())), expressions])
    selection = ('set lpd_design ' + tcl_word(BUILD / 'sim/simv.vdb') + '\n' +
                 'set lpd_testdirs [list ' + ' '.join(map(tcl_word, dirs)) + ']\n' +
                 'set lpd_tests [list ' + ' '.join(map(tcl_word, tests)) + ']\n' +
                 'set lpd_children [list\n')
    for scope, checksum, params, expressions in children:
        selection += ('  [list ' + ' '.join(map(tcl_word, (scope, checksum, params))) +
                      ' [list ' + ' '.join(map(tcl_word, expressions)) + ']]\n')
    selection += ']\n'
    output.mkdir()
    write(output / 'selection.tcl', selection)
    pins = dict(plan['pins'])
    for path in (plan_path, prepared / 'product-plan.sha256.json', SCRIPT,
                 Path(__file__).resolve(), HERE / 'test_lzc_selector_native_product_discover.py',
                 output / 'selection.tcl'):
        pins[str(path)] = sha(path)
    command = ['timeout', '--kill-after=10s', '300s', 'xvfb-run', '-a', 'dve', '-full64', '-cov',
               '-script', str(SCRIPT)]
    record = dict(status='READONLY_DISCOVERY_PREPARED', prepared=str(prepared), command=command,
        environment={'LZC_SELECTOR_NATIVE_PRODUCT_SELECTION': str(output / 'selection.tcl'),
                     'LZC_SELECTOR_NATIVE_PRODUCT_OUTPUT': str(output)},
        pins=pins, child_scopes=scopes, tests=707, module_checksum='3250293308',
        excludes=False, captures=False, application_approval=False,
        condition_native_id_policy='Retain actual displayed IDs only; absent IDs remain unqualified, no XML/root inference')
    write(output / 'discovery-plan.json', record)
    write(output / 'discovery-plan.sha256.json', {str(output / 'discovery-plan.json'): sha(output / 'discovery-plan.json')})
    print(json.dumps(dict(status=record['status'], output=str(output), children=len(scopes), tests=707)))


def launch(output):
    plan_path = output / 'discovery-plan.json'
    plan = json.loads(plan_path.read_bytes())
    product.check_pins(json.loads((output / 'discovery-plan.sha256.json').read_bytes()))
    product.check_pins(plan['pins'])
    safe_script(SCRIPT.read_text())
    require(output.parent == product.OUT and plan['status'] == 'READONLY_DISCOVERY_PREPARED'
            and not plan['excludes'] and not plan['captures'] and
            plan['command'] == ['timeout', '--kill-after=10s', '300s', 'xvfb-run', '-a', 'dve',
                               '-full64', '-cov', '-script', str(SCRIPT)], 'Reviewed read-only command required')
    require(all(shutil.which(p) for p in ('timeout', 'xvfb-run', 'dve')), 'Host DVE tools unavailable')
    env = dict(os.environ, **plan['environment'])
    for key in tuple(env):
        if key.startswith('DVE_') or key.startswith('LZC_') and key not in plan['environment']:
            del env[key]
    started = time.monotonic()
    status = dict(status='RUNNING_READONLY', excludes=False, captures=False, application_approval=False)
    with (output / 'dve.log').open('x') as log:
        process = subprocess.Popen(plan['command'], cwd=output, env=env, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        write(output / 'launch.json', dict(wrapper_pid=process.pid, command=plan['command'], cwd=str(output)))
        print(json.dumps(dict(wrapper_pid=process.pid, output=str(output))), flush=True)
        try:
            code = process.wait(timeout=320)
            status['returncode'] = code
            text = (output / 'DVEfiles/dve_gui.log').read_text()
            require(code == 0 and 'LZC_PRODUCT_READONLY_DISCOVERY_COMPLETE' in text and
                    'LZC_PRODUCT_READONLY_DISCOVERY_FAILED' not in text,
                    'Read-only discovery incomplete; inspect preserved logs')
            product.check_pins(plan['pins'])
            require(not list(output.rglob('*.el')), 'Unexpected native exclusion artifact')
            status['status'] = 'READONLY_DISCOVERY_COMPLETE_PENDING_OFFLINE_BINDING'
        except Exception as error:
            if process.poll() is None:
                os.killpg(process.pid, 15)
                process.wait(timeout=15)
            status.update(status='FAILED_RECORDED', error=str(error))
            raise
        finally:
            status['elapsed_seconds'] = round(time.monotonic() - started, 3)
            status['artifacts'] = {str(p): sha(p) for p in output.rglob('*') if p.is_file()}
            write(output / 'discovery-status.json', status)
    print(json.dumps(status['status']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='mode', required=True)
    prep = commands.add_parser('prepare')
    prep.add_argument('--prepared', type=Path, required=True)
    prep.add_argument('--output', type=Path, required=True)
    run = commands.add_parser('launch-readonly')
    run.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'prepare':
        prepare(args.prepared.resolve(), args.output.resolve())
    else:
        launch(args.output.resolve())


if __name__ == '__main__':
    main()
