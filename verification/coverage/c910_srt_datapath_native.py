"""Exact reviewed C910 local Toggle capture, not population application."""
import argparse
import csv
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

import fma_datapath_native as fma

one = fma.one
life, require, tools = one.life, one.require, one.tools
HERE = Path(__file__).resolve().parent
REVIEW = life.OUT / 'c910-srt-datapath-scoped-review-741-agent-20261007-01.json'
REVIEW_SHA = '9a54de4896ea792ce8c6f0eec8e396b09b50d3c16009456912a4471ce1881c6f'
HANDOFF = life.OUT / 'fma-native-toggle-format-handoff-turing-20261007-01.json'
SCRIPT = Path(__file__).resolve()
TCL = SCRIPT.with_suffix('.tcl')
TEST = SCRIPT.with_name('test_c910_srt_datapath_native.py')


def instances(review):
    require(review['schema'] == 'C910_SRT_EXACT_INTERNAL_DATAPATH_INTEGRATION_REVIEW_741_V1'
            and review['target_signal_objects'] == 1264 and len(review['instances']) == 8,
            'Wrong approved review')
    source = (life.ROOT / review['source']['path']).read_text().splitlines()
    signals = []
    for name, line, width, left, right, file_id in review['signals']:
        match = re.fullmatch(r'\s*(reg|wire)\s+\[[^]]+\]\s+' + re.escape(name) +
                             r'\s*;\s*', source[line - 1])
        require(match and left - right + 1 == width, 'Source declaration differs')
        signals.append(dict(name=name, declline=line, width=width, left=left,
                            right=right, file_id=file_id, source_type=match.group(1)))
    protected = []
    for node in review['protected_native_shape_objects']:
        name = node['name']
        if node['kind'] == 'vectornode':
            name += '[%s:%s]' % (node['left'], node['right'])
        else:
            require(node['kind'] == 'node', 'Unexpected protected object kind')
        protected.append(name)
    require(len(signals) == 158 and len(protected) == 52 and len(set(protected)) == 52,
            'Approved object inventory differs')
    result = [dict(i, design_module_checksum=review['design_checksum'],
                   toggle_checksum=review['toggle_checksum'], signals=signals,
                   protected=protected) for i in review['instances']]
    require(len({i['scope'] for i in result}) == 8 and
            sum(s['width'] for i in result for s in i['signals']) == 77472,
            'Approved instance/bit count differs')
    return result


def parse_el(text, config):
    expected = {i['scope']: i for i in config['instances']}
    scope, checksum, found = None, None, {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('//'):
            continue
        if line.startswith('ANNOTATION:'):
            require(re.fullmatch(r'ANNOTATION: "[^"\r\n]*"', line), 'Bad annotation')
        elif line.startswith('CHECKSUM:'):
            match = re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"', line)
            require(match is not None, 'Bad checksum directive')
            checksum, scope = match.groups(), None
        elif line.startswith('INSTANCE:'):
            scope = line.split(':', 1)[1].strip()
            require(scope in expected and checksum ==
                    (expected[scope]['design_module_checksum'], expected[scope]['toggle_checksum']),
                    'Unapproved scope/checksum')
        else:
            match = re.fullmatch(r'Toggle (\w+) "(reg|wire|logic) (\w+)\[(\d+):(\d+)\]"', line)
            require(scope is not None and match is not None, 'Unknown exclusion syntax')
            name, kind, signature, left, right = match.groups()
            target = next((s for s in expected[scope]['signals'] if s['name'] == name), None)
            require(target is not None and name == signature and
                    kind in (target['source_type'], 'logic') and
                    (int(left), int(right)) == (target['left'], target['right']),
                    'Wrong vector/type/bounds')
            key = (scope, name)
            require(key not in found, 'Duplicate target')
            found[key] = (*checksum, kind, int(left), int(right))
    wanted = {(i['scope'], s['name']) for i in config['instances'] for s in i['signals']}
    require(len(wanted) == 1264 and set(found) == wanted, 'Not exact1264')
    return sorted((scope, name, *value) for (scope, name), value in found.items())


def inventory(out, config, stage, index):
    require(stage in ('before', 'selected', 'reset', 'reloaded', 'final') and
            0 <= index < 8, 'Invalid inventory stage/index')
    path = out / ('native_%s_%d.tsv' % (stage, index))
    with path.open(newline='') as stream:
        table = list(csv.reader(stream, delimiter='\t'))
    require(table and table[0] == ['handle', 'path', 'meta', 'name'] and
            all(len(r) == 4 and all(r) for r in table[1:]), 'Invalid native inventory')
    rows = [tuple(row[1:]) for row in table[1:]]
    require(rows and len(rows) == len(set(rows)), 'Ambiguous native inventory')
    instance = config['instances'][index]
    names = [r[2] for r in rows]
    required = instance['protected'] + [s['name'] + '[%d:%d]' % (s['left'], s['right'])
                                       for s in instance['signals']]
    require(len(required) == len(set(required)) == 210 and
            all(names.count(name) == 1 for name in required),
            'Target/protected native row missing or ambiguous')
    return rows


def prepare(out):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(),
            'Fresh output required')
    review = life.read_bound(REVIEW, REVIEW_SHA)
    configured = instances(review)
    handoff_sha = life.digest(HANDOFF)
    handoff = life.read_bound(HANDOFF, handoff_sha)
    require(handoff['status'] == 'MEASURED_FMA_FORMAT_ONLY_NOT_C910_QUALIFICATION' and
            handoff['capture_result_sha256'] == fma.PRODUCT_SHA, 'Unqualified syntax handoff')
    product = life.read_bound(fma.PRODUCT / 'capture-result.json', fma.PRODUCT_SHA)
    require(product['status'] == 'ONE_FP32_PRODUCT_NATIVE_FORMAT_ROUNDTRIP_PASS' and
            product['reset_global_empty'] and product['non_target_signal_exclusions'] == 0,
            'Native format reference not qualified')
    pins = life.merge_pins(product['pins'], {str(REVIEW): REVIEW_SHA,
                           str(HANDOFF): handoff_sha,
                           str(fma.PRODUCT / 'capture-result.json'): fma.PRODUCT_SHA})
    items = [*review['baseline'], *review['compiled_pins'], review['source'],
             review['source_ledger'], *(r for e in review['evidence'] for r in e['pins'])]
    for item in items:
        pins = life.merge_pins(pins, {str(life.ROOT / item['path']): item['sha256']})
    selected = review['evidence'][0]
    require(selected['kind'] == 'FP32_DIV' and selected['exact_arithmetic_requests'] == 30 and
            selected['exact_arithmetic_bytes'] == 3840, 'Unqualified capture sample')
    vdb = life.OUT / 'gap84-div32-old-image-20261006-01/code.vdb'
    require(str(vdb) in (life.ROOT / review['baseline'][1]['path']).read_text().splitlines(),
            'Capture sample is not admitted741')
    directories = list((vdb / 'snps/coverage/db/testdata').iterdir())
    require(len(directories) == 1 and directories[0].is_dir(), 'Ambiguous native sample')
    for path in vdb.rglob('*'):
        if path.is_file():
            require(path.resolve() == path and not path.is_symlink(), 'Aliased sample')
            pins = life.merge_pins(pins, {str(path): life.digest(path)})
    config_one = json.loads((fma.PRODUCT / 'config.json').read_bytes())
    tools.revalidate(config_one['identity'])
    for path in (SCRIPT, TCL, TEST, Path(fma.__file__).resolve(),
                 HERE / 'fma_datapath_native.tcl', Path(one.__file__).resolve(),
                 Path(one.common.__file__).resolve(), Path(tools.__file__).resolve(),
                 Path(life.__file__).resolve()):
        pins = life.merge_pins(pins, {str(path): life.digest(path)})
    life.check(pins)
    values = dict(fma_design=str(life.IMAGE) + '.vdb', fma_vdb=str(vdb),
                  fma_test=str(vdb.with_suffix('') / directories[0].name),
                  fma_python=shutil.which('python3'), fma_helper=str(SCRIPT),
                  c910_fma_tcl=str(HERE / 'fma_datapath_native.tcl'))
    require(all(v and not any(c in v for c in '{}\\\r\n') for v in values.values()),
            'Unsafe Tcl value')
    lines = ['set %s {%s}\n' % pair for pair in values.items()] + ['set fma_instances {}\n']
    for index, instance in enumerate(configured):
        names = ' '.join(s['name'] + '[%d:%d]' % (s['left'], s['right'])
                         for s in instance['signals'])
        lines.append('lappend fma_instances [list {%s} {%s} {%s} %d]\n' %
                     (instance['scope'], names, ' '.join(instance['protected']), index))
    out.mkdir()
    one.common.save(out / 'selection.tcl', ''.join(lines))
    pins = life.merge_pins(pins, {str(out / 'selection.tcl'): life.digest(out / 'selection.tcl')})
    config = dict(schema='C910_SRT_NATIVE1264_PREPARED_V1', output=str(out), pins=pins,
                  identity=config_one['identity'], instances=configured, timeout_seconds=1800,
                  input_VDB_count=1, native_test=values['fma_test'], objects=1264,
                  logical_bits=77472, population_application=False, automatic_retry=False)
    life.save(out / 'config.json', config)
    print(json.dumps(dict(output=str(out), seal=life.digest(out / 'config.json'),
                          objects=1264, pins=len(pins))), flush=True)


def verify(out, seal):
    config = life.read_bound(out / 'config.json', seal)
    life.check(config['pins'])
    terminal = json.loads((out / 'terminal.json').read_bytes())
    require(terminal['returncode'] == 0 and not terminal['timeout'] and
            len(terminal['actual_dve']) == 1, 'DVE terminal identity failed')
    gui = (out / 'DVEfiles/dve_gui.log').read_text()
    require(gui.splitlines().count('C910_SRT_NATIVE_CAPTURE_DONE') == 1 and
            'C910_SRT_NATIVE_CAPTURE_FAILED' not in gui, 'Native capture failed')
    first = parse_el((out / 'first.el').read_text(), config)
    require(first == parse_el((out / 'second.el').read_text(), config), 'Reload differs')
    for name in ('initial-empty.el', 'reset-empty.el', 'final-empty.el'):
        require((out / name).read_bytes() == b'', 'Global reset not empty')
    for index in range(8):
        before = inventory(out, config, 'before', index)
        for stage in ('selected', 'reset', 'reloaded', 'final'):
            require(inventory(out, config, stage, index) == before,
                    'Native target/protection identity drift')
    result = dict(status='EXACT_C910_1264_NATIVE_ROUNDTRIP_NOT_POPULATION_APPLICATION',
                  config_seal=seal, objects=1264, logical_bits=77472,
                  protected_local_objects=416, both_directions=True, non_target_exclusions=0,
                  semantic_reload=True, finalreset=True, population_application=False,
                  pins=life.merge_pins(config['pins'], {str(p): life.digest(p)
                    for p in out.rglob('*') if p.is_file() and p.name != 'capture-result.json'}))
    life.save(out / 'capture-result.json', result)
    print(json.dumps(dict(status=result['status'], seal=life.digest(out / 'capture-result.json'))))


def run(out, seal):
    config = life.read_bound(out / 'config.json', seal)
    require(config['schema'] == 'C910_SRT_NATIVE1264_PREPARED_V1' and
            config['output'] == str(out) and not (out / 'execution.json').exists(),
            'One-shot config/claim differs')
    life.check(config['pins'])
    tools.revalidate(config['identity'])
    env = tools.controlled_environment(config['identity'], os.environ)
    env.pop('DVE', None)
    env['DVE_COVERAGE_OUTPUT'] = str(out)
    command = [shutil.which('xvfb-run'), '-a', '-e', str(out / 'xvfb.log'), '-s',
               '-screen 0 1280x1024x24', config['identity']['roles']['launcher'],
               '-full64', '-cov', '-script', str(TCL)]
    with (out / 'execution.json').open('x') as stream:
        json.dump(dict(command=command, cwd=str(out), timeout_seconds=1800,
                       automatic_retry=False), stream)
    with (out / 'launcher.log').open('x') as log:
        process = subprocess.Popen(command, cwd=out, env=env, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        time.sleep(10)
        actual = []
        for p in Path('/proc').iterdir():
            if not p.name.isdigit():
                continue
            try:
                if ((p / 'exe').resolve() == Path(config['identity']['executable']) and
                        (p / 'cwd').resolve() == out):
                    actual.append(dict(pid=int(p.name), exe=str((p / 'exe').resolve()),
                                       cwd=str(out), command=(p / 'cmdline').read_bytes().decode().replace('\0', ' ')))
            except OSError:
                continue
        life.save(out / 'live-identity.json', actual)
        print(json.dumps(dict(actual_dve=actual)), flush=True)
        timed_out = False
        try:
            process.wait(timeout=config['timeout_seconds'])
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
    life.save(out / 'terminal.json', dict(returncode=process.returncode,
                                        timeout=timed_out, actual_dve=actual))
    verify(out, seal)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'run', 'verify', 'el', 'inventory'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal')
    parser.add_argument('--file', choices=('first.el', 'second.el'))
    parser.add_argument('--stage')
    parser.add_argument('--index', type=int)
    args = parser.parse_args()
    out = args.output.absolute()
    if args.mode == 'prepare':
        prepare(out)
    elif args.mode in ('el', 'inventory'):
        config = json.loads((out / 'config.json').read_bytes())
        if args.mode == 'el':
            require(args.file, 'EL required')
            print(json.dumps(dict(objects=len(parse_el((out / args.file).read_text(), config)))))
        else:
            print(json.dumps(dict(rows=len(inventory(out, config, args.stage, args.index)))))
    else:
        require(args.seal, 'Frozen seal required')
        (run if args.mode == 'run' else verify)(out, args.seal)


if __name__ == '__main__':
    main()
