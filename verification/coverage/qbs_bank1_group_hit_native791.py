"""Fresh exact partial-bit capture, prepare only unless separately authorized."""
import argparse
import csv
import io
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

import plan_qbs_bank1_group_hit_native as plan
import qbs_even_hit_native762 as partial
import qualify_csr_pmp0_native765 as labels

life, tools, need = partial.life, partial.tools, partial.require
HERE = Path(__file__).resolve().parent
ENTRY = HERE / 'qbs_bank1_group_hit_native791.tcl'
TEMPLATE = life.OUT / 'qbs-even-hit19328-native762-agent-20261007-01'
TEMPLATE_SHA = 'f4f88c4ec1650881dc04858cc24b8950bf96d3241210a887aae41370a159c720'
GRAMMAR_RECEIPT_SHA = 'bf06c26430b00c7201916f564531c6860ee431bee1c0cf5dc151384a323760c7'
STAGES = plan.STAGES
FILES = dict(zip(STAGES, ('initial-empty.el', 'first.el', 'reset-empty.el', 'second.el', 'final-empty.el')))
IMAGE_SHA = '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3'


def process_identity(pid):
    root = Path('/proc') / str(pid)
    fields = (root/'stat').read_text().rsplit(')', 1)[1].split()
    return dict(pid=pid, ppid=int(fields[1]), starttime=int(fields[19]),
                exe=str((root/'exe').resolve(strict=True)), cwd=str((root/'cwd').resolve(strict=True)),
                cgroup=(root/'cgroup').read_text(), uid=root.stat().st_uid)


def owning_identity(actual, worker, launch_pid):
    need(type(actual.get('pid')) is int and actual['pid'] > 0 and
         type(actual.get('starttime')) is int and actual['starttime'] >= worker['starttime'] and
         actual['uid'] == worker['uid'] and actual['cgroup'] == worker['cgroup'] and
         '.service' in worker['cgroup'] and worker.get('invocation_id'), 'Service/starttime/uid ownership')
    ancestors = actual.get('ancestors', [])
    need(launch_pid in ancestors and worker['pid'] in ancestors, 'DVE is not a worker descendant')


def aliases(n):
    obj = dict(n['attributes'], kind=n['tag'])
    result = labels.aliases(obj)
    if n['tag'] == 'vectornode' and obj['left'] == obj['right']:
        result |= {obj['name'], obj['name']+'['+obj['left']+']'}
    return sorted(result)


def instances(p):
    result = []
    for scope, nodes in sorted(p['protected_scopes'].items()):
        used = set()
        bindings = []
        for n in nodes:
            allowed = aliases(n)
            need(not (set(allowed) & used), 'Compiled alias collision')
            used.update(allowed)
            name = n['attributes']['name']
            target = scope == p['scope'] and name in p['target_bits']
            bindings.append(dict(n, allowed_labels=allowed, role='target' if target else 'protected'))
        result.append(dict(scope=scope, bindings=bindings,
                           design_module_checksum=p['compiled_module_identities'][scope]['chksum'],
                           toggle_checksum=p['compiled_checksums'][scope]))
    return result


def bound_rows(text, instance, stage):
    reader = csv.DictReader(io.StringIO(text), delimiter='\t')
    need(reader.fieldnames == ['handle', 'path', 'meta', 'name', 'excluded'], 'Exact native TSV schema')
    rows = list(reader)
    need(len(rows) == len(instance['bindings']), 'Complete native object/array inventory')
    for key in ('handle', 'path', 'name'):
        need(all(row.get(key) for row in rows) and len({row[key] for row in rows}) == len(rows),
             'Unique native '+key)
    bylabel = {label: b for b in instance['bindings'] for label in b['allowed_labels']}
    found = {}
    for row in rows:
        need(set(row) == set(reader.fieldnames) and row['handle'].isdigit() and
             row['path'] == row['meta'] == row['name'] and row['excluded'] in ('0', '1'),
             'Exact native identity/flag')
        b = bylabel.get(row['name'])
        need(b is not None and b['attributes']['name'] not in found, 'Foreign/duplicate typed object')
        # A partial-vector aggregate flag need not encode its individual bits.
        # Only the full global saved EL is authoritative for those bits.
        if b['role'] != 'target' or stage not in ('selected', 'reloaded'):
            need(row['excluded'] == '0', 'Protected/reset object excluded')
        found[b['attributes']['name']] = dict(label=row['name'], path=row['path'], meta=row['meta'])
    need(len(found) == len(instance['bindings']), 'Full bijection')
    return found


def inventory(out, c, stage, index):
    need(stage in STAGES and type(index) is int and 0 <= index < len(c['instances']), 'Exact stage/index')
    i = c['instances'][index]
    path = out / ('native_%s_%d.tsv' % (stage, index))
    found = bound_rows(path.read_text(), i, stage)
    if stage != 'before':
        before = out / ('native_before_%d.tsv' % index)
        saved = json.loads((out / 'actual-binding.json').read_bytes())
        need(saved['config_sha256'] == life.digest(out / 'config.json') and
             saved['before_pins'][str(before)] == life.digest(before) and
             saved['scopes'][index] == found, 'Fresh before identity drift')
    return found


def target_config(c):
    scope = c['plan']['scope']
    i = next(i for i in c['instances'] if i['scope'] == scope)
    return dict(instances=[dict(scope=scope, design_module_checksum=i['design_module_checksum'],
        toggle_checksum=i['toggle_checksum'], signals=[dict(name=name, bits=bits, scalar=False,
        left=31, right=0) for name, bits in sorted(c['plan']['target_bits'].items())])])


def records(text, c):
    # Established measured QBS partial-vector grammar; exact net/wire signatures
    # and partial ranges, both directions, checksums and source bit indices.
    lines = [x.strip() for x in text.splitlines() if x.strip() and not x.strip().startswith('//')]
    need(len(lines) >= 2 and lines[0].startswith('CHECKSUM:') and lines[1].startswith('INSTANCE:') and
         sum(x.startswith('CHECKSUM:') for x in lines) == 1 and
         sum(x.startswith('INSTANCE:') for x in lines) == 1, 'One complete exact scope/checksum block')
    return partial.parse_el(text, target_config(c))


def bind(out, c):
    need(not (out / 'actual-binding.json').exists(), 'One fresh binding only')
    found = [inventory(out, c, 'before', k) for k in range(len(c['instances']))]
    before_pins = {str(out / ('native_before_%d.tsv' % k)): life.digest(out / ('native_before_%d.tsv' % k))
                   for k in range(len(found))}
    life.save(out / 'actual-binding.json', dict(config_sha256=life.digest(out / 'config.json'),
        before_pins=before_pins, scopes=found, native_qualified=False))
    # Selection names are only generated after all26 native inventories bind.
    text = partial.primitive.candidate(target_config(c))
    need(len(records(text, c)) == 3232, 'Exact partial direction union')
    with (out / 'actual-candidate.el').open('x') as stream:
        stream.write(text)


def check_el(out, c, stage):
    need(stage in STAGES, 'Exact EL stage')
    p = out / FILES[stage]
    if stage in ('before', 'reset', 'final'):
        need(p.read_bytes() == b'', 'Global exclusions not empty')
        return 0
    result = records(p.read_text(), c)
    if stage == 'reloaded':
        need(result == records((out / FILES['selected']).read_text(), c), 'Semantic reload differs')
    return len(result)


def check(out, seal):
    c = life.read_bound(out / 'config.json', seal)
    life.check(c['pins'])
    need(c['output'] == str(out) and c['timeout_seconds'] == 900 and
         c['population_application'] is False and c['automatic_retry'] is False,
         'Output/timeout/nonapplication contract')
    # Pin closure was validated before preparation. Reconstruct all compiled
    # target and complement identities from the sealed plan, not mutable reports.
    need(c['instances'] == instances(c['plan']) and len(c['instances']) == 26 and
         len(partial.primitive.bitset(target_config(c))) == 3232, 'Exact full source partition')
    tools.revalidate(c['identity'])
    return c


def prepare(out):
    need(out.parent == life.OUT and not out.exists(), 'Fresh independent output')
    p = plan.collect()
    t = life.read_bound(TEMPLATE / 'config.json', TEMPLATE_SHA)
    r = life.read_bound(TEMPLATE / 'capture-result.json', GRAMMAR_RECEIPT_SHA)
    need(r['status'] == 'QBS_EVEN_START9664_BITS19328_NATIVE_ROUNDTRIP_NOT_APPLICATION', 'Measured QBS grammar authority')
    for name in ('first.el', 'second.el'):
        path = TEMPLATE / name
        need(life.digest(path) == r['pins'][str(path)], 'Actual measured grammar fixture seal')
    partial.parse_el((TEMPLATE / 'first.el').read_text(), t)
    partial.parse_el((TEMPLATE / 'second.el').read_text(), t)
    pins = dict(p['input_pins'])
    for path, sha in t['pins'].items():
        if path.startswith(t['design']+'/') or path.startswith(t['vdb']+'/'):
            need(path not in pins or pins[path] == sha, 'Conflicting frozen design/sample pins')
            pins[path] = sha
    need(life.digest(life.IMAGE) == IMAGE_SHA, 'Frozen simv image SHA')
    pins[str(life.IMAGE)] = IMAGE_SHA
    for path in (TEMPLATE / 'config.json', TEMPLATE / 'capture-result.json', TEMPLATE / 'first.el',
                 TEMPLATE / 'second.el', Path(__file__).resolve(), ENTRY,
                 HERE / 'test_qbs_bank1_group_hit_native791.py', Path(plan.__file__).resolve(),
                 Path(partial.__file__).resolve(), Path(partial.primitive.__file__).resolve(),
                 Path(labels.__file__).resolve(), HERE / 'qualify_dwc_points742.tcl'):
        pins[str(path)] = life.digest(path)
    pending = [ENTRY, HERE / 'qualify_dwc_points742.tcl']
    visited = set()
    while pending:
        path = pending.pop()
        if path in visited: continue
        visited.add(path); pins[str(path)] = life.digest(path)
        for match in re.finditer(r'source\s+\{(/[^{}\n]+)\}', path.read_text()):
            dependency = Path(match[1])
            need(dependency.is_file() and dependency.is_relative_to(life.ROOT), 'Absolute Tcl dependency')
            pending.append(dependency)
    for module in list(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path and Path(path).resolve().is_relative_to(life.ROOT / 'verification'):
            pins[str(Path(path).resolve())] = life.digest(Path(path).resolve())
    c = dict(output=str(out), plan=p, instances=instances(p), pins=pins,
        identity=t['identity'], design=t['design'], sample=t['vdb'], test=t['test'],
        python=sys.executable, helper=str(Path(__file__).resolve()), timeout_seconds=900,
        automatic_retry=False, population_application=False, sample_membership_required=True)
    ledger = (plan.CURRENT / 'combined-inputs.txt').read_text().splitlines()
    need(c['sample'] in ledger[1:], 'Sample must be an already admitted PASS member')
    life.check(pins); tools.revalidate(c['identity'])
    out.mkdir()
    values = {k: c[k] for k in ('design', 'sample', 'test', 'python', 'helper')}
    need(all(v and not any(x in v for x in '{}\\\n\r') for v in values.values()), 'Plain safe Tcl config')
    text = ''.join('set ::bg_'+k+' {'+v+'}\n' for k, v in values.items())
    text += 'set ::bg_scopes [list '+' '.join('{'+i['scope']+'}' for i in c['instances'])+']\n'
    for name, data in (('selection.tcl', text), (ENTRY.name, ENTRY.read_text())):
        with (out / name).open('x') as stream: stream.write(data)
        pins[str(out / name)] = life.digest(out / name)
    life.save(out / 'config.json', c)
    seal = life.digest(out / 'config.json'); check(out, seal)
    print(json.dumps(dict(output=str(out), seal=seal, target_objects=72, target_directions=3232,
                         scopes=26, EDA_launched=False)))


def inspect(out, seal):
    c = check(out, seal)
    terminal = json.loads((out / 'terminal.json').read_bytes())
    need(type(terminal['returncode']) is int and terminal['returncode'] == 0 and
         type(terminal['timeout']) is bool and not terminal['timeout'] and
         len(terminal['actual_dve']) == 1, 'Strict actual terminal')
    actual = terminal['actual_dve'][0]
    worker = terminal['worker_identity']
    owning_identity(actual, worker, terminal['launcher_pid'])
    need(json.loads((out/'live-identity.json').read_bytes()) == terminal['actual_dve'], 'Live/terminal actual identity')
    need(type(actual['pid']) is int and actual['pid'] > 0 and actual['exe'] == c['identity']['executable']
         and actual['cwd'] == str(out), 'Actual executable/output')
    log = (out / 'DVEfiles/dve_gui.log').read_text()
    need(log.splitlines().count('QBS_BANK1_GROUP_HIT_NATIVE_DONE') == 1 and
         'QBS_BANK1_GROUP_HIT_NATIVE_FAILED' not in log and not (out / 'error.txt').exists(), 'Complete five stages')
    for name in ('launcher.log', 'DVEfiles/dve_gui.log'):
        need(not re.search(r'UCAPI-DLMA|DVCDT136|EK-CMD-|Load Failed|Error:|Fatal:', (out/name).read_text()), 'Tool rejection')
    for stage in STAGES:
        check_el(out, c, stage)
        for k in range(26): inventory(out, c, stage, k)
    need((out / 'cleanup-empty.el').read_bytes() == b'', 'Final cleanup empty')
    names = ['config.json', 'selection.tcl', ENTRY.name, 'actual-binding.json', 'actual-candidate.el',
             'initial-empty.el', 'first.el', 'reset-empty.el', 'second.el', 'final-empty.el',
             'cleanup-empty.el', 'terminal.json', 'live-identity.json', 'live-ready',
             'execution.json', 'launcher.log', 'xvfb.log']
    names += ['native_%s_%d.tsv' % (stage, index) for stage in STAGES for index in range(26)]
    files = [out / n for n in names]
    files += [p for p in (out/'DVEfiles').rglob('*') if p.is_file()]
    need(files and all(p.is_file() for p in files), 'Complete immutable native output set')
    result = dict(status='QBS_BANK1_GROUP_HIT3232_NATIVE_QUALIFIED_NOT_APPLIED', target_objects=72,
        target_bits=1616, target_directions=3232, all26scope_full_five_stage_inventory=True,
        parent_non_target_objects=3214, retained_target_bits=688,
        mapping_permitted_missing704_protected=True, population_application=False,
        source_review_sha256=plan.REVIEW_SHA, config_sha256=seal,
        pins={str(p): life.digest(p) for p in files}, input_pins=c['pins'],
        mutable_wrapper_stdout_not_native_evidence=True)
    path = out / 'qualification.json'
    if path.exists(): need(json.loads(path.read_bytes()) == result, 'Receipt differs')
    else: life.save(path, result)
    print(json.dumps(dict(status=result['status'], sha256=life.digest(path))))


def run(out, seal):
    c = check(out, seal)
    worker = process_identity(os.getpid())
    worker['invocation_id'] = os.environ.get('INVOCATION_ID')
    need('.service' in worker['cgroup'] and worker['invocation_id'], 'Direct owning background service required')
    env = tools.controlled_environment(c['identity'], os.environ)
    env.pop('DVE', None); env.update(DVE_COVERAGE_OUTPUT=str(out), QBS_BANK1_NATIVE_SEAL=seal)
    cmd = [c['identity']['roles']['xvfb_run'], '-a', '-e', str(out/'xvfb.log'), '-s', '-screen 0 1280x1024x24',
           c['identity']['roles']['launcher'], '-full64', '-cov', '-script', str(out/ENTRY.name)]
    with (out/'execution.json').open('x') as stream: json.dump(dict(command=cmd, cwd=str(out)), stream)
    with (out/'launcher.log').open('x') as log:
        proc = subprocess.Popen(cmd, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        time.sleep(10)
        actual = []
        for p in Path('/proc').iterdir():
            if not p.name.isdigit(): continue
            try:
                if (p/'exe').resolve() == Path(c['identity']['executable']) and (p/'cwd').resolve() == out:
                    identity = process_identity(int(p.name)); ancestors = []; ancestor = identity['ppid']
                    for _ in range(32):
                        if ancestor <= 1: break
                        ancestors.append(ancestor)
                        if ancestor == worker['pid']: break
                        ancestor = process_identity(ancestor)['ppid']
                    identity['ancestors'] = ancestors
                    owning_identity(identity, worker, proc.pid)
                    actual.append(identity)
            except (OSError, ValueError): pass
        life.save(out/'live-identity.json', actual)
        if len(actual) == 1:
            with (out/'live-ready').open('x') as ready: ready.write('OWNED_ACTUAL_DVE_EXACT1\n')
        timed = False
        try: proc.wait(timeout=890)
        except subprocess.TimeoutExpired:
            timed = True; os.killpg(proc.pid, signal.SIGTERM)
            try: proc.wait(timeout=10)
            except subprocess.TimeoutExpired: os.killpg(proc.pid, signal.SIGKILL); proc.wait()
    life.save(out/'terminal.json', dict(returncode=proc.returncode, timeout=timed, actual_dve=actual,
                                      worker_identity=worker, launcher_pid=proc.pid))
    try: inspect(out, seal)
    except Exception as error:
        life.save(out/'qualification-reject.json', dict(error=str(error), native_qualified=False)); raise


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('mode', choices=('prepare', 'check', 'bind', 'inventory', 'el', 'inspect', 'run'))
    cli.add_argument('--output', type=Path, required=True); cli.add_argument('--seal')
    cli.add_argument('--stage', choices=STAGES); cli.add_argument('--index', type=int)
    a = cli.parse_args(); out = a.output.resolve()
    if a.mode == 'prepare': prepare(out)
    elif a.mode == 'run': run(out, a.seal)
    elif a.mode == 'inspect': inspect(out, a.seal)
    else:
        c = check(out, a.seal) if a.mode in ('check', 'bind') else life.read_bound(out / 'config.json', a.seal)
        if a.mode == 'bind': bind(out, c)
        elif a.mode == 'inventory': inventory(out, c, a.stage, a.index)
        elif a.mode == 'el': check_el(out, c, a.stage)
        print('QBS_BANK1_'+a.mode.upper()+'_PASS')
