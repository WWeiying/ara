"""Isolated source-bound parent-output RVFI qualification, never population application."""
import argparse
import csv
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

import capture_system_rvfi788 as primitives

life, require, tools = primitives.life, primitives.require, primitives.tools
HERE = Path(__file__).resolve().parent
ENTRY = HERE / 'capture_cva6_parent_rvfi457.tcl'
REVIEW = life.OUT / 'cva6-parent-rvfi-output-source-review763-agent-20261007-01.json'
REVIEW_SHA = 'f5e448c55889ad9d783a6c718a3d3000a2d39e53d5af9a23d1ef562a74754bbb'
PRECEDENT = life.OUT / 'system-rvfi788-native-agent-20261007-03/first.el'
PRECEDENT_SHA = '6839b7592de2519b81477bfa851f6e4829993c35a4221de36270de3907397c5f'
ANNOTATION = 'Source-proven observation-only CVA6 output leaves; full complement retained'
STAGES = ('before', 'selected', 'reset', 'reloaded', 'final')


def bindings(review):
    require(review['source_candidate_objects'] == 457 and review['protected_local_objects'] == 1315
            and review['protected_arrays'] == 31 and not review['source_contract']['hardware_feedback']
            and not review['whole_core_waiver'], 'Wrong source partition')
    result = []
    for role, objects in (('target', review['targets']), ('protected', review['protected_full_complement'])):
        for obj in objects:
            a = obj['attributes']; name = a['name']; kind = obj['kind']
            label = name
            if kind == 'vectornode':
                label += '[%s:%s]' % (a['left'], a['right'])
            elif kind == 'arrays':
                require(role == 'protected' and not a['unpackedrange'].strip(), 'Unreviewed array shape')
                dims = tuple(map(int, a['packedrange'].split()))
                require(len(dims) > 0 and len(dims) % 2 == 0, 'Incomplete array dimensions')
                label += ''.join('[%d]' % l if l == r else '[%d:%d]' % (l, r)
                                 for l, r in zip(dims[::2], dims[1::2]))
            else:
                require(kind == 'node', 'Unknown shape')
            # Only exact compiled sole-bit vectors may have a scalar GUI label.
            allowed = [label]
            if kind == 'vectornode' and a['left'] == a['right'] == '0':
                allowed.append(name)
            if role == 'target':
                require(a['portnode'] == '3' and a['aux_file'] == '419' and a['aux_line_num'] == '343'
                        and a['excluded'] == '0' and a['type'] == '1'
                        and name.startswith(('rvfi_probes_o.instr.', 'rvfi_probes_o.csr.')),
                        'Not exact source-proven output exception')
            result.append(dict(role=role, name=name, kind=kind, attributes=a, label=label,
                               allowed_labels=allowed, width=obj['width']))
    require(len(result) == len({p['name'] for p in result}) == 1772, 'Duplicate/incomplete partition')
    require(len({label for p in result for label in p['allowed_labels']}) ==
            sum(len(p['allowed_labels']) for p in result), 'Ambiguous whole-object labels')
    return result


def contract(c):
    r = life.read_bound(REVIEW, REVIEW_SHA)
    require(c['source_review_sha256'] == REVIEW_SHA and c['bindings'] == bindings(r)
            and (c['scope'], c['design_checksum'], c['toggle_checksum']) ==
            (r['scope'], r['design_checksum'], r['toggle_checksum']), 'Frozen source binding differs')


def inventory(out, c, stage):
    require(stage in STAGES, 'Unknown stage'); contract(c)
    with (out / ('native_' + stage + '.tsv')).open(newline='') as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        require(reader.fieldnames == ['handle', 'path', 'meta', 'name', 'excluded'], 'Wrong native schema')
        rows = list(reader)
    require(len(rows) == 1772 and all(set(p) == set(reader.fieldnames) and all(p.values()) for p in rows),
            'Incomplete native full complement')
    require(all(len({p[key] for p in rows}) == 1772 for key in ('handle', 'path', 'name')),
            'Duplicate native identity')
    require(all(p['path'] == p['meta'] == p['name'] and p['excluded'] in ('0', '1') for p in rows),
            'Native metadata/Boolean differs')
    by_label = {label: p for p in c['bindings'] for label in p['allowed_labels']}
    seen = {}; mapped = []
    for row in rows:
        obj = by_label.get(row['name'])
        require(obj is not None and obj['name'] not in seen, 'Foreign/duplicate full compiled object')
        expected = str(int(stage in ('selected', 'reloaded') and obj['role'] == 'target'))
        require(row['excluded'] == expected, 'Target/protected exclusion differs: ' + row['name'])
        seen[obj['name']] = row['name']
        mapped.append(dict(obj, observed_label=row['name']))
    require(set(seen) == {p['name'] for p in c['bindings']}, 'Missing full complement')
    metadata = sorted((p['path'], p['meta'], p['name']) for p in rows)
    if stage != 'before':
        original = json.loads((out / 'actual-binding.json').read_bytes())
        require(original['config_seal'] == life.digest(out / 'config.json') and
                original['before_sha256'] == life.digest(out / 'native_before.tsv') and
                original['bindings'] == sorted(mapped, key=lambda p: p['name']) and
                original['metadata'] == [list(p) for p in metadata], 'Native actual binding drift')
    return metadata, sorted(mapped, key=lambda p: p['name'])


def bind(out, c):
    metadata, bound = inventory(out, c, 'before')
    life.save(out / 'actual-binding.json', dict(config_seal=life.digest(out / 'config.json'),
        before_sha256=life.digest(out / 'native_before.tsv'), bindings=bound, metadata=metadata,
        targets=457, protected=1315, protected_arrays=31, source_review_sha256=REVIEW_SHA))
    labels = [p['observed_label'] for p in bound if p['role'] == 'target']
    (out / 'actual-selection.tcl').write_text('set ::cr_targets [list ' +
        ' '.join(atom(label) for label in labels) + ']\n')


def records(text, c):
    contract(c)
    wanted = {p['name']: p for p in c['bindings'] if p['role'] == 'target'}
    checksum = None; scope = None; annotation = None; found = {}; whole = set(); pairs = {}
    for line in text.splitlines():
        m = re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"', line)
        if m:
            require(checksum is None, 'Duplicate checksum'); checksum = m.groups(); continue
        m = re.fullmatch(r'INSTANCE:\s*(\S+)', line)
        if m:
            require(scope is None and m[1] == c['scope'] and checksum ==
                    (c['design_checksum'], c['toggle_checksum']), 'Foreign scope/checksum')
            scope = m[1]; continue
        m = re.fullmatch(r'ANNOTATION: "([^"\r\n]*)"', line)
        if m:
            require(m[1] == ANNOTATION, 'Wrong annotation'); annotation = m[1]; continue
        m = re.fullmatch(r'Toggle (?:(0to1|1to0) )?(\S+?)(?: \[([^\]]+)\])? "(logic) (\S+)"', line)
        require(m is not None and scope is not None and annotation == ANNOTATION, 'Unknown/partial typed directive')
        direction, name, bit, kind, decl = m.groups(); p = wanted.get(name)
        require(p is not None, 'Protected/foreign EL object')
        # Scalar aliases are source-bound to the identical sole compiled bit, never ranges of larger objects.
        require(decl in p['allowed_labels'], 'Wrong whole bounds/qualifier')
        identity = (scope, *checksum, kind, p['label'], annotation)
        if direction:
            require(p['width'] == 1 and name not in whole, 'Partial vector/mixed whole pair')
            require((p['kind'] == 'node' and bit is None) or
                    (p['kind'] == 'vectornode' and bit == '0' and decl == p['label']), 'Wrong sole-bit selector')
            old, directions = pairs.setdefault(name, ((kind, decl), set()))
            require(old == (kind, decl) and direction not in directions, 'Duplicate/conflicting direction')
            directions.add(direction)
        else:
            require(bit is None and name not in whole and name not in pairs, 'Duplicate/mixed whole object')
            whole.add(name)
        require(name not in found or found[name] == identity, 'Typed identity drift')
        found[name] = identity
    require(all(dirs == {'0to1', '1to0'} for _, dirs in pairs.values()), 'Incomplete direction pair')
    require(set(found) == set(wanted) and len(found) == 457, 'Not exact457 EL')
    return sorted((name, *identity) for name, identity in found.items())


def atom(value):
    require(not any(ch in str(value) for ch in '{}\\\n\r'), 'Unsafe Tcl atom')
    return '{' + str(value) + '}'


def selection(c):
    return ''.join('set ::cr_' + key + ' ' + atom(c[key]) + '\n'
                   for key in ('design', 'sample', 'test', 'scope', 'python', 'helper'))


def static():
    text = ENTRY.read_text()
    require('info script' not in text and not re.search(r'\{\*\}|\bdict\s|\s(?:in|ni)\s', text),
            'Tcl8.4/eval boundary violation')
    require(text.count('uplevel #0 [list source [file join $::env(DVE_COVERAGE_OUTPUT) selection.tcl]]') == 1,
            'Selection must source actual plain text at global scope')


def precedent_records(c):
    require(life.digest(PRECEDENT) == PRECEDENT_SHA, 'Preserved actual RVFI serialization differs')
    lines = ['CHECKSUM: "%s %s"' % (c['design_checksum'], c['toggle_checksum']),
             'INSTANCE: ' + c['scope'], 'ANNOTATION: "' + ANNOTATION + '"']
    # Same frozen packed type leaves at the upstream output. This is serialization
    # calibration only, not a substitute for this scope's actual native inventory.
    for line in PRECEDENT.read_text().splitlines():
        if line.startswith('Toggle ') and re.match(r'Toggle (?:(?:0to1|1to0) )?rvfi_probes\.', line):
            lines.append(line.replace('rvfi_probes.', 'rvfi_probes_o.'))
    return records('\n'.join(lines), c)


def prepare(out):
    require(out.parent == life.OUT and not out.exists(), 'Fresh independent output required')
    static(); r = life.read_bound(REVIEW, REVIEW_SHA); life.check(r['pins'])
    b = bindings(r)
    # Freeze the complete imported helper closure without changing any shared module.
    pins = dict(r['pins']); pins[str(REVIEW)] = REVIEW_SHA
    pins[str(PRECEDENT)] = PRECEDENT_SHA
    for module in list(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path and Path(path).resolve().parent == HERE and Path(path).suffix == '.py':
            pins[str(Path(path).resolve())] = life.digest(Path(path).resolve())
    for path in [ENTRY, HERE / 'test_capture_cva6_parent_rvfi457.py', *HERE.glob('*.tcl')]:
        pins[str(path)] = life.digest(path)
    identity = primitives.tools.prepare('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/dve', '/usr/bin/xvfb-run')
    pins.update({p['path']: p['sha256'] for p in identity['files']})
    sample = life.OUT / 'gap84-div32-old-image-20261006-01/code.vdb'
    dirs = list((sample / 'snps/coverage/db/testdata').iterdir())
    require(len(dirs) == 1 and dirs[0].is_dir(), 'Not one representative admitted test')
    bitmap = life.OUT / 'operand-mask-data-defined-policy-admitted763-agent-20261007-01/combined-bits.json'
    require(str(sample) in json.loads(bitmap.read_bytes())['tests'], 'Sample not admitted763')
    pins[str(bitmap)] = life.digest(bitmap)
    for path in sample.rglob('*'):
        if path.is_file(): pins[str(path)] = life.digest(path)
    c = dict(source_review_sha256=REVIEW_SHA, bindings=b, scope=r['scope'],
             design_checksum=r['design_checksum'], toggle_checksum=r['toggle_checksum'],
             design=str(life.OUT / 'repaired-aligned-build-20260930-01/sim/simv.vdb'),
             sample=str(sample), test=str(sample.with_suffix('') / dirs[0].name),
             python=sys.executable, helper=str(Path(__file__).resolve()), identity=identity,
             pins=pins, output=str(out), timeout_seconds=1800,
             population_application=False, automatic_retry=False)
    precedent_records(c)
    out.mkdir(); (out / 'selection.tcl').write_text(selection(c))
    pins[str(out / 'selection.tcl')] = life.digest(out / 'selection.tcl')
    contract(c); life.check(pins); life.save(out / 'config.json', c)
    print(json.dumps(dict(output=str(out), seal=life.digest(out / 'config.json'), targets=457,
                          protected=1315, arrays=31, pins=len(pins))), flush=True)


def verify(out, seal):
    c = life.read_bound(out / 'config.json', seal); contract(c); life.check(c['pins']); tools.revalidate(c['identity'])
    terminal = json.loads((out / 'terminal.json').read_bytes())
    require(terminal['returncode'] == 0 and not terminal['timeout'] and len(terminal['actual_dve']) == 1,
            'Actual native terminal failed')
    log = (out / 'DVEfiles/dve_gui.log').read_text()
    require(log.splitlines().count('CVA6_PARENT_RVFI457_NATIVE_DONE') == 1 and
            log.splitlines().count('CVA6_PARENT_RVFI457_SELECTED ' + c['test']) == 1 and
            not re.search(r'Error:|Fatal:|EK-CMD-|DVTC[0-9]+|UCAPI-DLMA|DVCDT136|CVA6_PARENT_RVFI457_FAILED', log),
            'GUI native/load failure')
    require(records((out / 'first.el').read_text(), c) == records((out / 'second.el').read_text(), c),
            'Typed native roundtrip differs')
    for name in ('initial-empty.el', 'reset-empty.el', 'final-empty.el', 'cleanup-empty.el'):
        require((out / name).read_bytes() == b'', 'Nonempty global reset')
    initial = inventory(out, c, 'before')
    for stage in STAGES[1:]: require(inventory(out, c, stage) == initial, 'Full native metadata drift')
    result = dict(status='CVA6_PARENT_RVFI457_NATIVE_QUALIFIED_NOT_POPULATION_APPLICATION',
        config_seal=seal, source_review_sha256=REVIEW_SHA, targets=457, logical_bits=2599,
        protected=1315, protected_arrays=31, five_stages=list(STAGES), non_target_new_exclusions=0,
        observation_output_exception_only=True, child_and_functional_hardware_exclusions=0,
        population_application=False, official_percentage_claim=False,
        pins={**c['pins'], **{str(p): life.digest(p) for p in out.rglob('*') if p.is_file()
                           and p.name != 'capture-result.json' and p != out / 'service.log'}})
    life.check(result['pins']); life.save(out / 'capture-result.json', result)
    print('QUALIFIED ' + life.digest(out / 'capture-result.json'), flush=True)


def run(out, seal):
    c = life.read_bound(out / 'config.json', seal); contract(c); life.check(c['pins']); tools.revalidate(c['identity'])
    require(os.environ.get('INVOCATION_ID') and c['output'] == str(out), 'Direct owning systemd service required')
    env = tools.controlled_environment(c['identity'], os.environ); env.pop('DVE', None)
    env.update(DVE_COVERAGE_OUTPUT=str(out), CVA6_PARENT_RVFI457_SEAL=seal)
    command = [c['identity']['roles']['xvfb_run'], '-a', '-e', str(out / 'xvfb.log'), '-s',
               '-screen 0 1280x1024x24', c['identity']['roles']['launcher'], '-full64', '-cov', '-script', str(ENTRY)]
    life.save(out / 'execution.json', dict(command=command, automatic_retry=False,
              systemd_invocation=os.environ['INVOCATION_ID'], timeout_seconds=c['timeout_seconds']))
    with (out / 'launcher.log').open('x') as log:
        process = subprocess.Popen(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        start = tools.process_info(process.pid)['starttime']; time.sleep(10); actual = []
        for p in Path('/proc').iterdir():
            if not p.name.isdigit(): continue
            try:
                if (p / 'exe').resolve() == Path(c['identity']['executable']) and (p / 'cwd').resolve() == out:
                    tools.verify_live_executable(int(p.name), c['identity'], process.pid, start)
                    actual.append(dict(pid=int(p.name), exe=str((p / 'exe').resolve()), cwd=str(out),
                                       cgroup=(p / 'cgroup').read_text()))
            except (OSError, ProcessLookupError): pass
        life.save(out / 'live-identity.json', actual); print(json.dumps(dict(actual_dve=actual)), flush=True)
        timeout = False
        try: process.wait(timeout=c['timeout_seconds'])
        except subprocess.TimeoutExpired:
            timeout = True; os.killpg(process.pid, signal.SIGTERM)
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: os.killpg(process.pid, signal.SIGKILL); process.wait()
    life.save(out / 'terminal.json', dict(returncode=process.returncode, timeout=timeout, actual_dve=actual))
    try: verify(out, seal)
    except Exception as error:
        life.save(out / 'qualification-reject.json', dict(status='REJECTED_NOT_QUALIFIED', reason=str(error),
                  config_seal=seal, captures_preserved=True, automatic_retry=False)); raise


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=('prepare', 'run', 'verify', 'inventory', 'bind', 'el'))
    ap.add_argument('--output', type=Path, required=True); ap.add_argument('--seal')
    ap.add_argument('--stage', choices=STAGES); ap.add_argument('--file', choices=('first.el', 'second.el'))
    args = ap.parse_args(); out = args.output.absolute()
    if args.mode == 'prepare': prepare(out)
    else:
        seal = args.seal or os.environ.get('CVA6_PARENT_RVFI457_SEAL')
        require(seal, 'Config seal required'); c = life.read_bound(out / 'config.json', seal); life.check(c['pins'])
        if args.mode == 'bind': bind(out, c); print('EXACT_ACTUAL1772_BINDING457_TARGETS1315_PROTECTED')
        elif args.mode == 'inventory': print('FULL1772 ' + str(len(inventory(out, c, args.stage)[0])))
        elif args.mode == 'el': print('EXACT457 ' + str(len(records((out / args.file).read_text(), c))))
        else: (run if args.mode == 'run' else verify)(out, seal)
