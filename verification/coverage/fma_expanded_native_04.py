"""Exact source-bound whole-or-complete-direction-pair FMA native qualification."""
import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

import fma_expanded_native_03 as prior

frozen = prior.frozen
life, require, tools = prior.life, prior.require, prior.tools
HERE = Path(__file__).resolve().parent
OLD = life.OUT / 'fma_expanded_native_612-agent-20261007-03'
OLD_SEAL = 'a7ae1e9e3752e722c235101ba09410086fcfea1301c3414f9641c2baf2cc0717'
FIRST_SHA = 'bfc0ebf928307be85e65f146c1d84ccbc8259c8295c94e7fe8851c09caf9b6bc'
ENTRY = HERE / 'fma_expanded_native_04.tcl'
NAME = r'[A-Za-z_][\w.]*'
DIMS = r'(?:\[-?\d+:-?\d+\])+'


def source_bindings(c):
    review = life.read_bound(frozen.REVIEW, frozen.REVIEW_SHA)
    require(c['instances'] == review['instances'], 'Configuration/source reviewed identity differs')
    source_pin = next(p for p in review['source_pins'] if p['path'].endswith('/fpnew_fma.sv'))
    path = life.ROOT / source_pin['path']
    require(life.digest(path) == source_pin['sha256'], 'Source identity drift')
    lines = path.read_text().splitlines()
    result = {}
    for instance in c['instances']:
        for target in instance['targets']:
            name = target['name']
            decl = lines[int(target['line_num']) - 1].strip()
            member = name.rsplit('.', 1)[-1]
            require(re.match(r'logic\b', decl) and re.search(r'\b' + re.escape(member) + r'\b', decl),
                    'Source declaration not bound: ' + name)
            aux = None
            if '.' in name:
                require(name.startswith(('operand_a.', 'operand_b.', 'operand_c.')) and
                        target['aux_file'] == target['file'] == '381', 'Unknown struct binding')
                aux = lines[int(target['aux_line_num']) - 1].strip()
                require(re.match(r'fp_t\b', aux) and name.split('.')[0] in aux,
                        'Struct declaration identity differs')
            result[instance['scope'], name] = dict(source_sha256=source_pin['sha256'],
                source_file=target['file'], declaration_line=int(target['line_num']), declaration=decl,
                source_signed=bool(re.match(r'logic\s+signed\b', decl)), struct_declaration=aux,
                source_aux_file=target.get('aux_file'), source_aux_line=target.get('aux_line_num'),
                shape_kind=target['shape_kind'], dimensions=target['dimensions'], native_type='logic',
                native_qualifiers=[], compiled_type=target['type'])
    require(len(result) == 612, 'Source identity union differs')
    if 'source_type_bindings' in c:
        require(c['source_type_bindings'] == [dict(scope=k[0], name=k[1], **v) for k, v in result.items()],
                'Stored complete source type identity differs')
    return result


def parse_el(text, c):
    expected = {i['scope']: i for i in c['instances']}
    require(len(expected) == 12, 'Wrong instance union')
    bindings = source_bindings(c)
    checksum, scope, blocks = None, None, set()
    found = defaultdict(list)
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('//'):
            continue
        if line.startswith('ANNOTATION:'):
            require(re.fullmatch(r'ANNOTATION: "[^"\r\n]*"', line), 'Malformed annotation')
            continue
        if line.startswith('CHECKSUM:'):
            require(scope is not None or checksum is None, 'Consecutive/unbound checksum')
            m = re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"', line)
            require(m is not None, 'Malformed checksum')
            checksum, scope = m.groups(), None
            continue
        if line.startswith('INSTANCE:'):
            scope = line.split(':', 1)[1].strip()
            require(scope in expected and scope not in blocks and checksum ==
                    (expected[scope]['design_module_checksum'], expected[scope]['toggle_checksum']),
                    'Unapproved/duplicate scope or checksum')
            blocks.add(scope)
            continue
        m = re.fullmatch(r'Toggle (?:(0to1|1to0) )?(' + NAME + r') "(logic) ([^"\r\n]+)"', line)
        require(scope is not None and m is not None, 'Unexpected metric/type/qualifier: ' + line)
        direction, name, native_type, declaration = m.groups()
        target = next((t for t in expected[scope]['targets'] if t['name'] == name), None)
        require(target is not None, 'Non-target object: ' + name)
        # Only relocate the complete ordered dimension sequence, never slice it.
        suffix = re.fullmatch('(' + NAME + ')(' + DIMS + ')?', declaration)
        prefix = re.fullmatch('(' + DIMS + ')(' + NAME + ')', declaration)
        require(suffix is not None or prefix is not None, 'Malformed typed declaration')
        declared, dims = suffix.groups() if suffix else tuple(reversed(prefix.groups()))
        dims = dims or ''
        require(declared == name and name + dims == target['native_name'], 'Name/full bounds identity differs')
        binding = bindings[scope, name]
        key = (scope, name, native_type, tuple(tuple(d) for d in target['dimensions']), checksum,
               json.dumps(binding, sort_keys=True))
        found[key].append(direction)
    wanted = {(i['scope'], t['name']) for i in c['instances'] for t in i['targets']}
    require(len(wanted) == len(found) == 612 and {(k[0], k[1]) for k in found} == wanted and
            blocks == set(expected) and scope is not None, 'Not exact full 612-object union')
    for key, directions in found.items():
        require(directions == [None] or (len(directions) == 2 and set(directions) == {'0to1', '1to0'}),
                'Missing/duplicate/mixed whole and split directions: ' + key[1])
    return sorted(found)


def check_stage(out, stage, c):
    require(stage in frozen.STAGES, 'Unknown stage')
    text = (out / frozen.EL_FILES[stage]).read_text()
    if stage in ('apply', 'reload'):
        parse_el(text, c)
    else:
        require(text == '', 'Global exclusion reset not empty: ' + stage)
    complement = 0
    for index, instance in enumerate(c['instances']):
        rows = frozen.inventory(out / ('native_%s_%d.tsv' % (stage, index)))
        old = frozen.inventory(Path(instance['native_identity_source']))
        require(frozen.semantic_rows(rows) == frozen.semantic_rows(old), 'Full native inventory differs: ' + stage)
        targets = {t['native_name'] for t in instance['targets']}
        non_targets = [r for r in rows if r['name'] not in targets]
        require(len(rows) - len(non_targets) == len(targets), 'Target/complement union differs')
        complement += len(non_targets)
    require(complement == 2832, 'Full complement differs')
    return dict(stage=stage, objects=612, all_nontarget_objects=complement, global_EL_exact=True)


def fixture():
    c = life.read_bound(OLD / 'config.json', OLD_SEAL)
    life.check(c['pins'])
    require(life.digest(OLD / 'first.el') == FIRST_SHA, 'Actual03 native fixture drift')
    frozen.validate_review(life.read_bound(frozen.REVIEW, frozen.REVIEW_SHA))
    records = parse_el((OLD / 'first.el').read_text(), c)
    stages = [check_stage(OLD, s, c) for s in ('initial', 'apply')]
    require((OLD / 'cleanup-empty.el').read_bytes() == b'', 'Actual cleanup not empty')
    return c, dict(status='ACTUAL03_FULL_612_EL_OFFLINE_SCHEMA_PASS_NOT_ROUNDTRIP',
        actual_first_sha256=FIRST_SHA, objects=len(records), logical_bits=26064, stages=stages,
        whole_or_exact_two_direction_pair=True, complete_source_type_identity_retained=True,
        records_sha256=hashlib.sha256(json.dumps(records).encode()).hexdigest())


def selection_text():
    lines = (OLD / 'selection.tcl').read_text().splitlines(keepends=True)
    require(lines[-1] == 'set fma_helper {' + str(HERE / 'fma_expanded_native_03.py') + '}\n', 'Wrong old helper')
    return ''.join(lines[:-1]) + 'set fma_helper {' + str(Path(__file__).resolve()) + '}\n'


def write_selection(out):
    frozen.predecessor.one.common.save(out / 'selection.tcl', selection_text())
    require((out / 'selection.tcl').read_bytes() == selection_text().encode('ascii'), 'Selection bytes differ')


def prepare(out):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh output required')
    c, real_evidence = fixture()
    require(life.digest(life.IMAGE) == frozen.IMAGE_SHA, 'Frozen simv differs')
    tools.revalidate(c['identity'])
    pins = {**c['pins'], **{str(p): life.digest(p) for p in OLD.rglob('*') if p.is_file()}}
    for p in (Path(__file__).resolve(), ENTRY, HERE / 'test_fma_expanded_native_04.py',
              HERE / 'fma_expanded_session_mock_04.py'):
        pins[str(p)] = life.digest(p)
    life.check(pins)
    out.mkdir()
    write_selection(out)
    life.save(out / 'actual03-full-EL-regression.json', real_evidence)
    from fma_expanded_session_mock_04 import qualify_disk_entry
    life.save(out / 'plain-tcl-entry-regression.json', qualify_disk_entry(out / 'selection.tcl'))
    tests = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'test_fma_expanded_native',
        'test_review_fma_arithmetic_scope', 'test_fma_datapath_native', 'test_fma_expanded_native_02',
        'test_fma_expanded_native_03', 'test_fma_expanded_native_04', '-v'], cwd=HERE, text=True, capture_output=True)
    require(tests.returncode == 0 and tests.stderr.rstrip().endswith('OK'), 'Regressions failed: ' + tests.stderr)
    life.save(out / 'test-regression.json', dict(returncode=tests.returncode, stdout=tests.stdout, stderr=tests.stderr))
    for name in ('selection.tcl', 'actual03-full-EL-regression.json', 'plain-tcl-entry-regression.json', 'test-regression.json'):
        pins[str(out / name)] = life.digest(out / name)
    c.update(output=str(out), pins=pins, predecessor_config_seal=OLD_SEAL, entry_script=str(ENTRY),
             repair='Native complete direction pairs and full typed dimension-order normalization',
             actual03_full_EL_fixture_qualified=True, actual_disk_Tcl_entry_mock_qualified=True,
             source_type_bindings=[dict(scope=k[0], name=k[1], **v) for k, v in source_bindings(c).items()])
    life.check(pins)
    life.save(out / 'config.json', c)
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
    stages = [check_stage(out, s, c) for s in frozen.STAGES]
    records = parse_el((out / 'first.el').read_text(), c)
    require(records == parse_el((out / 'second.el').read_text(), c), 'Typed/source identity semantic reload differs')
    if (out / 'service.log').exists():
        shutil.copyfile(out / 'service.log', out / 'service-output-before-seal.log')
    result = dict(status='EXACT_612_FMA_EXPANDED_TOGGLE_OBJECTS_NATIVE_ROUNDTRIP_PASS', config_seal=seal,
        source_review_sha256=frozen.REVIEW_SHA, actual03_first_EL_sha256=FIRST_SHA, objects=612,
        logical_bits=26064, both_directions=True, non_target_exclusions=0, stages=stages,
        all_nontarget_complement_retained=True, all_descendants_retained=True, reset_global_empty=True,
        semantic_reload=True, complete_source_type_identity_retained=True, population_application=False,
        exhaustive_functional_validation=False,
        unsealed_worker_stdout=str(out / 'service.log'), worker_stdout_snapshot='service-output-before-seal.log',
        EL_byte_parity=(out / 'first.el').read_bytes() == (out / 'second.el').read_bytes(),
        pins={**c['pins'], **{str(p): life.digest(p) for p in out.rglob('*')
                            if p.is_file() and p.name != 'capture-result.json' and p != out / 'service.log'}})
    life.save(out / 'capture-result.json', result)
    print(json.dumps(dict(status=result['status'], seal=life.digest(out / 'capture-result.json'))), flush=True)


def run(out, seal):
    c = life.read_bound(out / 'config.json', seal)
    life.check(c['pins'])
    tools.revalidate(c['identity'])
    require(c['entry_script'] == str(ENTRY) and c['actual03_full_EL_fixture_qualified'], 'Wrong entry')
    env = tools.controlled_environment(c['identity'], os.environ)
    env.pop('DVE', None)
    env.update(DVE_COVERAGE_OUTPUT=str(out), FMA_EXPANDED_CONFIG_SEAL=seal)
    command = [c['identity']['roles']['xvfb_run'], '-a', '-e', str(out / 'xvfb.log'),
        '-s', '-screen 0 1280x1024x24', c['identity']['roles']['launcher'], '-full64', '-cov', '-script', str(ENTRY)]
    with (out / 'execution.json').open('x') as receipt:
        json.dump(dict(command=command, cwd=str(out), timeout_seconds=c['timeout_seconds'], automatic_retry=False,
                       systemd_service=os.environ.get('INVOCATION_ID')), receipt)
    with (out / 'launcher.log').open('x') as log:
        process = subprocess.Popen(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
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
    parser.add_argument('mode', choices=('prepare', 'run', 'verify', 'stage', 'fixture'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--seal')
    parser.add_argument('--stage', choices=frozen.STAGES)
    args = parser.parse_args()
    if args.mode == 'fixture':
        print(json.dumps(fixture()[1]))
    else:
        require(args.output, 'Output required')
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
