"""Exact 612-object local FMA native qualification, not an IEEE certification."""
import argparse
import csv
import gzip
import io
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
import xml.etree.ElementTree as ET

import fma_datapath_native as predecessor
import review_fma_arithmetic_scope as source

life, require, tools = predecessor.life, predecessor.require, predecessor.tools
HERE = Path(__file__).resolve().parent
REVIEW = life.OUT / 'fma-internal-arithmetic-source-review-agent-20261007-01/source-review.json'
REVIEW_SHA = '22e2698705134cf14acf40a14c76385f8e253dfa295c605871e80ef168814dec'
IMAGE_SHA = '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3'
STAGES = ('initial', 'apply', 'reset', 'reload', 'final')
EL_FILES = dict(initial='initial-empty.el', apply='first.el', reset='reset-empty.el',
                reload='second.el', final='final-empty.el')


def inventory(path):
    with path.open() as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        require(reader.fieldnames == ['handle', 'path', 'meta', 'name'], 'Bad inventory header')
        rows = list(reader)
    require(rows and all(set(r) == set(reader.fieldnames) and all(r.values()) for r in rows),
            'Empty/malformed native inventory')
    require(len({r['name'] for r in rows}) == len(rows), 'Ambiguous native names')
    require(len({r['path'] for r in rows}) == len(rows), 'Ambiguous native paths')
    return rows


def semantic_rows(rows):
    # Handles are process-local; native paths/meta/names must remain exact.
    return [(r['path'], r['meta'], r['name']) for r in rows]


def validate_review(review):
    require(review['status'] == 'SOURCE_REVIEW_READY_EXPANDED_NATIVE_ROUNDTRIP_REQUIRED_NOT_APPLIED'
            and review['selection_independent_of_coverage'] and review['no_exhaustive_validation_claim']
            and not review['aggregate_applied'], 'Wrong review policy')
    require(review['target_objects'] == 612 and review['logical_bits'] == 26064
            and review['prior_qualified_objects'] == 108 and review['prior_qualified_logical_bits'] == 8368,
            'Expanded scope changed')
    prior = life.read_bound(source.one.REVIEW, source.one.REVIEW_SHA)
    shape = next(life.ROOT / p['path'] for p in prior['compiled_pins']
                 if p['path'].endswith('tgl.verilog.shape.xml'))
    root = ET.fromstring(gzip.decompress(shape.read_bytes()))
    require(len(review['instances']) == 12 and len({i['scope'] for i in review['instances']}) == 12,
            'Instance union differs')
    require([i['scope'] for i in review['instances']] == [i['scope'] for i in prior['instances']],
            'Instance/source binding differs')
    for fmt in review['formats']:
        modules = [m for m in root.findall('tgldef') if m.get('chksum') == fmt['toggle_checksum']]
        require(len(modules) == 1 and modules[0].get('name') == fmt['compiled_parameter_definition'],
                'Compiled module/checksum differs')
        actual = []
        for node in modules[0].find('tglshape'):
            item = dict(node.attrib, shape_kind=node.tag, dimensions=source.dimensions(node),
                        logical_bits=source.width(node), native_name=source.native_name(node))
            category = source.group(node)
            item['source_group' if category else 'reason'] = category or source.protection_reason(node)
            actual.append(item)
        require({x['name']: x for x in actual} ==
                {x['name']: x for x in fmt['targets'] + fmt['protected']}, 'Full shape partition differs')
    for index, instance in enumerate(review['instances']):
        fmt = next(f for f in review['formats'] if f['format'] == instance['format'])
        require(instance['format'] in ('FP32', 'FP64') and instance['all_descendants_retained']
                and instance['design_module_checksum'] == prior['instances'][index]['design_module_checksum']
                and instance['toggle_checksum'] == fmt['toggle_checksum'], 'Scope/checksum differs')
        rows = inventory(Path(instance['native_identity_source']))
        require(Path(instance['native_identity_source']) == source.CAPTURE / ('native_before_%d.tsv' % index),
                'Wrong native predecessor')
        require([{k: v for k, v in t.items() if k != 'observed_native'} for t in instance['targets']]
                == fmt['targets'], 'Instance target union differs')
        names = {r['name']: r for r in rows}
        for target in instance['targets']:
            require(target['portnode'] == '0' and target['file'] == '381' and target['excluded'] == '0'
                    and names.get(target['native_name']) == target['observed_native'],
                    'Source/native target binding differs')
        require({t['native_name'] for t in fmt['targets'] + fmt['protected']} == set(names),
                'All-nontarget complement is not exact')
    require(sum(len(i['targets']) for i in review['instances']) == 612 and
            sum(t['logical_bits'] for i in review['instances'] for t in i['targets']) == 26064,
            'Wrong full target union')


def parse_el(text, config):
    expected = {i['scope']: i for i in config['instances']}
    checksum, scope, found, blocks = None, None, {}, set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('//'):
            continue
        if line.startswith('ANNOTATION:'):
            require(re.fullmatch(r'ANNOTATION: "[^"\r\n]*"', line), 'Malformed annotation')
            continue
        if line.startswith('CHECKSUM:'):
            match = re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"', line)
            require(match is not None, 'Malformed checksum')
            checksum, scope = match.groups(), None
        elif line.startswith('INSTANCE:'):
            scope = line.split(':', 1)[1].strip()
            require(scope in expected and scope not in blocks and checksum ==
                    (expected[scope]['design_module_checksum'], expected[scope]['toggle_checksum']),
                    'Unapproved/duplicate scope or checksum')
            blocks.add(scope)
        else:
            match = re.fullmatch(r'Toggle ([A-Za-z_][\w.]*) "logic ([A-Za-z_][\w.]*)(.*)"', line)
            require(scope is not None and match is not None, 'Unexpected metric/type/qualifier: ' + line)
            name, signature, bounds = match.groups()
            target = next((t for t in expected[scope]['targets'] if t['name'] == name), None)
            require(target is not None and signature + bounds == target['native_name'] and signature == name,
                    'Wrong whole-object name/ranges/signature: ' + line)
            key = (scope, name)
            require(key not in found, 'Duplicate object')
            found[key] = (checksum, signature + bounds, target['logical_bits'])
    wanted = {(i['scope'], t['name']) for i in config['instances'] for t in i['targets']}
    require(len(wanted) == 612 and set(found) == wanted and blocks == set(expected), 'Not exact 612-object EL')
    return sorted((scope, name, *value) for (scope, name), value in found.items())


def check_stage(out, stage, c):
    require(stage in STAGES, 'Unknown stage')
    text = (out / EL_FILES[stage]).read_text()
    if stage in ('apply', 'reload'):
        parse_el(text, c)
    else:
        require(text == '', 'Global exclusion reset not empty: ' + stage)
    complement = 0
    for index, instance in enumerate(c['instances']):
        rows = inventory(out / ('native_%s_%d.tsv' % (stage, index)))
        old = inventory(Path(instance['native_identity_source']))
        require(semantic_rows(rows) == semantic_rows(old), 'Full native inventory differs: ' + stage)
        targets = {t['native_name'] for t in instance['targets']}
        non_targets = [r for r in rows if r['name'] not in targets]
        require(len(rows) - len(non_targets) == len(targets), 'Target/complement union differs')
        complement += len(non_targets)
    return dict(stage=stage, objects=612, all_nontarget_objects=complement, global_EL_exact=True)


def prepare(out):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh independent output required')
    review = life.read_bound(REVIEW, REVIEW_SHA)
    life.check(review['pins'])
    require(life.digest(life.IMAGE) == IMAGE_SHA, 'Frozen simv mismatch')
    validate_review(review)
    p = life.read_bound(source.CAPTURE / 'capture-result.json', source.CAPTURE_SHA)
    require(p['status'] == 'EXACT_108_FMA_TOGGLE_OBJECTS_NATIVE_ROUNDTRIP_PASS', 'Predecessor not qualified')
    product = life.read_bound(predecessor.PRODUCT / 'capture-result.json', predecessor.PRODUCT_SHA)
    life.check(product['pins'])
    original = json.loads((predecessor.PRODUCT / 'config.json').read_bytes())
    tools.revalidate(original['identity'])
    pins = {**review['pins'], str(REVIEW): REVIEW_SHA, str(life.IMAGE): IMAGE_SHA}
    for path in (Path(__file__).resolve(), HERE / 'fma_expanded_native.tcl',
                 HERE / 'test_fma_expanded_native.py'):
        pins[str(path)] = life.digest(path)
    life.check(pins)
    lines = ['source {' + str(predecessor.PRODUCT / 'selection.tcl') + '}\n', 'set fma_instances {}\n']
    for index, i in enumerate(review['instances']):
        names = ' '.join('{' + t['native_name'] + '}' for t in i['targets'])
        lines.append('lappend fma_instances [list {' + i['scope'] + '} [list ' + names + '] ' + str(index) + ']\n')
    lines.append('set fma_helper {' + str(Path(__file__).resolve()) + '}\n')
    out.mkdir()
    predecessor.one.common.save(out / 'selection.tcl', ''.join(lines))
    pins[str(out / 'selection.tcl')] = life.digest(out / 'selection.tcl')
    config = dict(output=str(out), pins=pins, identity=original['identity'], instances=review['instances'],
                  source_review_sha256=REVIEW_SHA, timeout_seconds=1800, input_VDB_count=1,
                  population_application=False, observer_report_rerun=False, automatic_retry=False,
                  objects=612, logical_bits=26064, selection_method='EXACT_NATIVE_ROW_SELECTION',
                  all_descendants_retained=True, exhaustive_functional_validation=False)
    life.save(out / 'config.json', config)
    print(json.dumps(dict(output=str(out), seal=life.digest(out / 'config.json'), pins=len(pins))))


def verify(out, seal):
    c = life.read_bound(out / 'config.json', seal)
    life.check(c['pins'])
    terminal = json.loads((out / 'terminal.json').read_bytes())
    require(terminal['returncode'] == 0 and not terminal['timeout'] and len(terminal['actual_dve']) == 1,
            'Terminal/actual native identity failed')
    gui = (out / 'DVEfiles/dve_gui.log').read_text()
    require(gui.splitlines().count('FMA_EXPANDED_NATIVE_CAPTURE_DONE') == 1 and
            'FMA_EXPANDED_NATIVE_CAPTURE_FAILED' not in gui, 'Native session failed; captures retained')
    stages = [check_stage(out, stage, c) for stage in STAGES]
    require(parse_el((out / 'first.el').read_text(), c) == parse_el((out / 'second.el').read_text(), c),
            'Typed semantic reload differs')
    result = dict(status='EXACT_612_FMA_EXPANDED_TOGGLE_OBJECTS_NATIVE_ROUNDTRIP_PASS', config_seal=seal,
                  source_review_sha256=REVIEW_SHA, objects=612, logical_bits=26064, both_directions=True,
                  all_nontarget_complement_retained=True, non_target_exclusions=0, stages=stages,
                  all_descendants_retained=True, reset_global_empty=True, semantic_reload=True,
                  population_application=False, exhaustive_functional_validation=False,
                  EL_byte_parity=(out / 'first.el').read_bytes() == (out / 'second.el').read_bytes(),
                  pins={**c['pins'], **{str(p): life.digest(p) for p in out.rglob('*')
                                      if p.is_file() and p.name != 'capture-result.json'}})
    life.save(out / 'capture-result.json', result)
    print(json.dumps(dict(status=result['status'], seal=life.digest(out / 'capture-result.json'))), flush=True)


def run(out, seal):
    c = life.read_bound(out / 'config.json', seal)
    require(not (out / 'execution.json').exists(), 'One-shot already claimed')
    life.check(c['pins'])
    tools.revalidate(c['identity'])
    env = tools.controlled_environment(c['identity'], os.environ)
    env.pop('DVE', None)
    env['DVE_COVERAGE_OUTPUT'] = str(out)
    env['FMA_EXPANDED_CONFIG_SEAL'] = seal
    command = [c['identity']['roles']['xvfb_run'], '-a', '-e', str(out / 'xvfb.log'),
               '-s', '-screen 0 1280x1024x24', c['identity']['roles']['launcher'],
               '-full64', '-cov', '-script', str(HERE / 'fma_expanded_native.tcl')]
    with (out / 'execution.json').open('x') as receipt:
        json.dump(dict(command=command, cwd=str(out), timeout_seconds=c['timeout_seconds'],
                       automatic_retry=False, systemd_service=os.environ.get('INVOCATION_ID')), receipt)
    with (out / 'launcher.log').open('x') as log:
        process = subprocess.Popen(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        time.sleep(10)
        candidates = []
        for p in Path('/proc').iterdir():
            if not p.name.isdigit():
                continue
            try:
                if (p / 'exe').resolve() == Path(c['identity']['executable']) and (p / 'cwd').resolve() == out:
                    candidates.append(dict(pid=int(p.name), exe=str((p / 'exe').resolve()), cwd=str(out),
                                           cgroup=(p / 'cgroup').read_text()))
            except OSError:
                continue
        life.save(out / 'live-identity.json', candidates)
        print(json.dumps(dict(actual_dve=candidates)), flush=True)
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
    try:
        verify(out, seal)
    except Exception as error:
        life.save(out / 'qualification-reject.json', dict(status='REJECTED_NOT_QUALIFIED', reason=str(error),
                  config_seal=seal, captures_preserved=True, automatic_retry=False))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'run', 'verify', 'stage'))
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--seal')
    parser.add_argument('--stage', choices=STAGES)
    args = parser.parse_args()
    out = args.output.absolute()
    if args.mode == 'prepare':
        prepare(out)
    else:
        require(args.seal, 'Sealed config required')
        if args.mode == 'stage':
            c = life.read_bound(out / 'config.json', args.seal)
            life.check(c['pins'])
            print(json.dumps(check_stage(out, args.stage, c)))
        else:
            (run if args.mode == 'run' else verify)(out, args.seal)
