"""Capture the reviewed 108 local FMA Toggle vectors; no population report."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

import fma_product_native as one

life, require, tools = one.life, one.require, one.tools
HERE = Path(__file__).resolve().parent
PRODUCT = life.OUT / 'fma-product-native-fp32-agent-20261007-01'
PRODUCT_SHA = '95dc2b72c37a22df8d245906e5cf3b24434efa4d1ebbb17272983a05d77dcbd8'


def candidate_text(instances):
    lines = []
    for i in instances:
        lines.extend(['CHECKSUM: "' + i['design_module_checksum'] + ' ' + i['toggle_checksum'] + '"',
                      'INSTANCE: ' + i['scope'],
                      'ANNOTATION: "Approved unchanged local FMA datapath integration scope; all other signals retained"'])
        for s in i['signals']:
            lines.append('Toggle ' + s['name'] + ' "logic ' + s['name'] + '[' + str(s['left']) + ':' + str(s['right']) + ']"')
    return '\n'.join(lines) + '\n'


def parse_el(text, config):
    expected = {i['scope']: i for i in config['instances']}
    checksum, scope, found = None, None, {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(('//', 'ANNOTATION:')):
            continue
        if line.startswith('CHECKSUM:'):
            checksum = line.split(':', 1)[1].strip().strip('"').split()
            scope = None
        elif line.startswith('INSTANCE:'):
            scope = line.split(':', 1)[1].strip()
            require(scope in expected and checksum == [expected[scope]['design_module_checksum'],
                    expected[scope]['toggle_checksum']], 'Unapproved scope/checksum')
        else:
            match = re.fullmatch(r'Toggle (\w+) "logic (\w+)\[(\d+):(\d+)\]"', line)
            require(scope is not None and match is not None, 'Unexpected metric/direction/signature: ' + line)
            name, signature, left, right = match.groups()
            target = next((s for s in expected[scope]['signals'] if s['name'] == name), None)
            require(target is not None and signature == name and
                    (int(left), int(right)) == (target['left'], target['right']), 'Wrong vector/signature')
            key = (scope, name)
            require(key not in found, 'Duplicate exclusion')
            found[key] = (checksum, int(left), int(right))
    wanted = {(i['scope'], s['name']) for i in config['instances'] for s in i['signals']}
    require(len(wanted) == 108 and set(found) == wanted, 'Not exact 108 objects')
    return sorted((scope, name, *value) for (scope, name), value in found.items())


def prepare(out):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh output required')
    product = life.read_bound(PRODUCT / 'capture-result.json', PRODUCT_SHA)
    life.check(product['pins'])
    require(product['status'] == 'ONE_FP32_PRODUCT_NATIVE_FORMAT_ROUNDTRIP_PASS' and
            product['reset_global_empty'] and product['non_target_signal_exclusions'] == 0, 'Product capture not qualified')
    review = life.read_bound(one.REVIEW, one.REVIEW_SHA)
    pins = {**product['pins'], str(PRODUCT / 'capture-result.json'): PRODUCT_SHA}
    for item in [*review['source_pins'], *review['compiled_pins'], *review['baseline'],
                 *(p for case in review['evidence'] for p in case['pins'])]:
        pins[str((life.ROOT / item['path']).resolve())] = item['sha256']
    formats = {f['format']: f for f in review['formats']}
    instances = [dict(i, signals=formats[i['format']]['signals'],
                      protected=formats[i['format']]['protected_other_named_shape_signals']) for i in review['instances']]
    require(len(instances) == 12 and len({i['scope'] for i in instances}) == 12 and
            sum(len(i['signals']) for i in instances) == 108 and
            sum(s['width'] for i in instances for s in i['signals']) == 8368, 'Review scope differs')
    for i in instances:
        require(not ({s['name'] for s in i['signals']} & set(i['protected'])), 'Protected overlap')
    for p in (Path(__file__).resolve(), HERE / 'fma_datapath_native.tcl', HERE / 'test_fma_datapath_native.py'):
        pins[str(p)] = life.digest(p)
    config_one = json.loads((PRODUCT / 'config.json').read_bytes())
    tools.revalidate(config_one['identity'])
    life.check(pins)
    candidate = candidate_text(instances)
    parse_el(candidate, dict(instances=instances))
    out.mkdir()
    one.common.save(out / 'candidate.el', candidate)
    pins[str(out / 'candidate.el')] = life.digest(out / 'candidate.el')
    lines = ['source {' + str(PRODUCT / 'selection.tcl') + '}\n', 'set fma_instances {}\n']
    for index, i in enumerate(instances):
        names = ' '.join(s['name'] + '[' + str(s['left']) + ':' + str(s['right']) + ']' for s in i['signals'])
        protected = ' '.join(i['protected'])
        lines.append('lappend fma_instances [list {' + i['scope'] + '} {' + names + '} {' + protected + '} ' + str(index) + ']\n')
    lines.append('set fma_helper {' + str(Path(__file__).resolve()) + '}\n')
    one.common.save(out / 'selection.tcl', ''.join(lines))
    pins[str(out / 'selection.tcl')] = life.digest(out / 'selection.tcl')
    c = dict(output=str(out), pins=pins, identity=config_one['identity'], instances=instances,
             timeout_seconds=1800, input_VDB_count=1, population_application=False,
             recursive_exclusions=False, automatic_retry=False, logical_bits=8368,
             selection_method='SHAPE_GENERATED_CANDIDATE_REQUIRES_NATIVE_READBACK',
             product_capture_sha256=PRODUCT_SHA)
    life.save(out / 'config.json', c)
    print(json.dumps(dict(output=str(out), seal=life.digest(out / 'config.json'), pins=len(pins), objects=108)))


def verify(out, seal):
    c = life.read_bound(out / 'config.json', seal)
    life.check(c['pins'])
    terminal = json.loads((out / 'terminal.json').read_bytes())
    require(terminal['returncode'] == 0 and not terminal['timeout'] and len(terminal['actual_dve']) == 1, 'Terminal identity failed')
    gui = (out / 'DVEfiles/dve_gui.log').read_text()
    require(gui.splitlines().count('FMA_DATAPATH_NATIVE_CAPTURE_DONE') == 1 and
            'FMA_DATAPATH_NATIVE_CAPTURE_FAILED' not in gui, 'Capture did not complete')
    first = parse_el((out / 'first.el').read_text(), c)
    require(first == parse_el((out / 'second.el').read_text(), c), 'Semantic reload differs')
    for name in ('initial-empty.el', 'reset-empty.el', 'final-empty.el'):
        require((out / name).read_bytes() == b'', 'Reset not empty')
    for index in range(12):
        def rows(stage):
            return [tuple(line.split('\t')[1:]) for line in
                    (out / ('native_' + stage + '_' + str(index) + '.tsv')).read_text().splitlines()[1:]]
        before = rows('before')
        require(before and len(before) == len(set(before)), 'Empty/ambiguous native inventory')
        for stage in ('selected', 'reset', 'reloaded', 'final'):
            require(rows(stage) == before, 'Native/protected identity changed: ' + stage)
    result = dict(status='EXACT_108_FMA_TOGGLE_OBJECTS_NATIVE_ROUNDTRIP_PASS', config_seal=seal,
                  objects=108, logical_bits=8368, both_directions=True, non_target_exclusions=0,
                  reset_global_empty=True, protected_native_inventory_identity=True,
                  semantic_reload=True, EL_byte_parity=(out / 'first.el').read_bytes() == (out / 'second.el').read_bytes(),
                  population_application=False, exhaustive_functional_validation=False,
                  pins={**c['pins'], **{str(p): life.digest(p) for p in out.rglob('*') if p.is_file() and p.name != 'capture-result.json'}})
    life.save(out / 'capture-result.json', result)
    print(json.dumps(dict(status=result['status'], seal=life.digest(out / 'capture-result.json'))))


def run(out, seal):
    c = life.read_bound(out / 'config.json', seal)
    require(not (out / 'execution.json').exists(), 'One-shot already claimed')
    life.check(c['pins'])
    tools.revalidate(c['identity'])
    env = tools.controlled_environment(c['identity'], os.environ)
    env.pop('DVE', None)
    env['DVE_COVERAGE_OUTPUT'] = str(out)
    command = [shutil.which('xvfb-run'), '-a', '-e', str(out / 'xvfb.log'), '-s', '-screen 0 1280x1024x24',
               c['identity']['roles']['launcher'], '-full64', '-cov', '-script', str(HERE / 'fma_datapath_native.tcl')]
    with (out / 'execution.json').open('x') as receipt:
        json.dump(dict(command=command, cwd=str(out), timeout_seconds=c['timeout_seconds'], automatic_retry=False), receipt)
    with (out / 'launcher.log').open('x') as log:
        process = subprocess.Popen(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        time.sleep(10)
        candidates = []
        for p in Path('/proc').iterdir():
            if not p.name.isdigit():
                continue
            try:
                if (p / 'exe').resolve() == Path(c['identity']['executable']) and (p / 'cwd').resolve() == out:
                    candidates.append(dict(pid=int(p.name), exe=str((p / 'exe').resolve()), cwd=str(out)))
            except OSError:
                continue
        life.save(out / 'live-identity.json', candidates)
        timed_out = False
        try:
            process.wait(timeout=c['timeout_seconds'])
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
    life.save(out / 'terminal.json', dict(returncode=process.returncode, timeout=timed_out, actual_dve=candidates))
    verify(out, seal)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'run', 'verify', 'el'))
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--seal')
    parser.add_argument('--file', choices=('first.el', 'second.el'))
    args = parser.parse_args()
    out = args.output.absolute()
    if args.mode == 'prepare':
        prepare(out)
    elif args.mode == 'el':
        require(args.file, 'EL filename required')
        print(json.dumps(dict(objects=len(parse_el((out / args.file).read_text(), json.loads((out / 'config.json').read_bytes()))))))
    else:
        require(args.seal, 'Sealed config required')
        (run if args.mode == 'run' else verify)(out, args.seal)
