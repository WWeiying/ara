"""One historical PASS VDB, read-only Line/Branch native identity discovery."""
import argparse
import csv
import io
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
import capture_cvxif_passive_two_scope770 as base

life, need = base.life, base.require
HERE = Path(__file__).resolve().parent
HOOK = HERE / 'observe_cvxif_point_identity789_v3.tcl'
SERVICE = 'ara-observe-cvxif-point789-parent-20261008-01.service'
SELECTOR_SHA = '7562ff42582a6adab356f8eecbacd41aa1abecf7ea957137c35539b838ab21f3'
ORIGINAL_SHA = '70aeac1fd5a3f5dd3300f613c2bf0253f80a27fa40251aaef68fee1d3e2f0546'


def quote(value):
    need(not any(c in str(value) for c in '{}\\\n\x00'), 'Unsafe Tcl literal')
    return '{' + str(value) + '}'


def selection(c):
    values = dict(cv_design=c['design'], cv_vdb=c['vdb'], cv_test=c['test'],
                  point_scope=base.SCOPES[0], point_library=HERE/'apply_points740_v4.tcl',
                  point_selector=HERE/'capture_cvxif_passive_two_scope770_v2.tcl')
    return ''.join('set ::%s %s\n' % (key, quote(value)) for key, value in values.items())


def prepare(out):
    need(out.parent == life.OUT and not out.exists(), 'Fresh output required')
    sample = life.read_bound(base.SAMPLE, base.SAMPLE_SHA)
    q = life.read_bound(base.QUAL, base.QUAL_SHA)
    review = life.read_bound(base.REVIEW, base.REVIEW_SHA)
    pins = life.merge_pins(life.merge_pins(sample['pins'], q['pins']), review['pins'])
    life.check(pins); base.local.tools.revalidate(sample['identity'])
    need(life.digest(HERE/'capture_cvxif_passive_two_scope770_v2.tcl') == SELECTOR_SHA, 'Selector pin')
    need(life.digest(HERE/'capture_cvxif_passive_two_scope770.tcl') == ORIGINAL_SHA, 'Original source pin')
    files = [Path(__file__), HOOK, HERE/'test_observe_cvxif_point_identity789_v3.py',
             Path(base.__file__), HERE/'capture_cvxif_passive_two_scope770_v2.tcl',
             HERE/'capture_cvxif_passive_two_scope770.tcl', HERE/'apply_points740_v4.tcl',
             base.SAMPLE, base.QUAL, base.REVIEW]
    # Seal the actual imported generator/launcher dependencies, not only this file.
    import sys
    for module in list(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name and Path(name).resolve().parent == HERE:
            files.append(Path(name).resolve())
    pins = life.merge_pins(pins, {str(p): life.digest(p) for p in files})
    c = dict(schema='READONLY_CVXIF_POINT789_V3', service=SERVICE, timeout_seconds=300,
             scope=base.SCOPES[0], compiled_zero_scope=base.SCOPES[1], metrics=['Line','Branch'],
             expected_capacity={'Line':8,'Branch':4}, native_labels_known=False,
             application=False, official_percentage=None,
             sample_seal=base.SAMPLE_SHA, historical_qualification_seal=base.QUAL_SHA,
             **{k: sample[k] for k in ('identity','design','vdb','test')})
    out.mkdir()
    with (out/'selection.tcl').open('x') as stream: stream.write(selection(c))
    pins[str(out/'selection.tcl')] = life.digest(out/'selection.tcl')
    c['pins'] = pins
    life.save(out/'config.json', c)
    print(json.dumps(dict(output=str(out), seal=life.digest(out/'config.json'), pins=len(pins), EDA_launched=False)))


def check(out, seal):
    c = life.read_bound(out/'config.json', seal)
    need(c['schema'] == 'READONLY_CVXIF_POINT789_V3', 'Successor schema')
    role_gate(c['identity'])
    need(c['service'] == SERVICE and c['timeout_seconds'] == 300 and c['scope'] == base.SCOPES[0]
         and c['metrics'] == ['Line','Branch'] and c['application'] is False, 'Read-only contract')
    life.check(c['pins']); base.local.tools.revalidate(c['identity'])
    need((out/'selection.tcl').read_text() == selection(c), 'Generated selection drift')
    return c


def role_gate(identity):
    roles = identity['roles']
    files = {item['path']: item for item in identity['files']}
    need(len(files) == len(identity['files']), 'Duplicate tool identity')
    need(set(roles) == {'launcher','xvfb_run','executable','architecture'}, 'Tool roles')
    need(roles['executable'] == identity['executable'], 'Executable role differs')
    for path in roles.values():
        need(Path(path).is_absolute() and path in files, 'Unsealed launch role')


def owned(group):
    return any(SERVICE in line.split(':', 2)[-1].split('/')
               for line in group.splitlines() if line.count(':') >= 2)


def launch_command(out, c):
    role_gate(c['identity'])
    return [c['identity']['roles']['xvfb_run'], '-a', '-e', str(out/'xvfb.log'),
            '-s', '-screen 0 1280x1024x24', c['identity']['roles']['launcher'],
            '-full64', '-cov', '-script', str(HOOK)]


def receipt_base(out, seal, c):
    return dict(config_seal=seal, service=SERVICE, cwd=str(out), identity=c['identity'])


def receipt_gate(out, seal, c, execution, live, terminal):
    expected = receipt_base(out, seal, c)
    for record in (execution, live, terminal):
        need(all(record.get(key) == value for key, value in expected.items()), 'Receipt seal/identity/owner differs')
    need(execution['command'] == launch_command(out, c), 'Actual launch command differs')
    need(live['actual_dve'] == terminal['actual_dve'] and len(live['actual_dve']) == 1, 'Live/terminal DVE differs')
    actual = live['actual_dve'][0]
    executable = c['identity']['executable']
    tool = next(item for item in c['identity']['files'] if item['path'] == executable)
    need(type(actual['pid']) is int and actual['pid'] > 0, 'Actual PID')
    need(actual['exe'] == executable and actual['cwd'] == str(out) and owned(actual['cgroup']), 'Actual process identity')
    need(actual['executable_sha256'] == tool['sha256'], 'Actual executable digest')
    need(type(actual['cmdline']) is list and actual['cmdline'], 'Missing actual command line')
    args = actual['cmdline']
    need(str(Path(args[0]).resolve()) == executable and args.count('-script') == 1, 'Foreign DVE command line')
    index = args.index('-script')
    need(index+1 < len(args) and args[index+1] == str(HOOK), 'Foreign native entry script')


def verify(out, seal):
    c = check(out, seal)
    t = json.loads((out/'terminal.json').read_text())
    receipt_gate(out, seal, c, json.loads((out/'execution.json').read_text()),
                 json.loads((out/'live-identity.json').read_text()), t)
    need(type(t['returncode']) is int and t['returncode'] == 0 and t['timeout'] is False
         and len(t['actual_dve']) == 1, 'Terminal/actual DVE identity')
    log = (out/'DVEfiles/dve_gui.log').read_text()
    need(log.splitlines().count('POINT789_READONLY_DONE') == 1 and not (out/'error.txt').exists(), 'Read-only completion')
    need(not re.search(r'Error-|Fatal-|POINT789_READONLY_FAILED', log), 'GUI error')
    counts = {}
    for metric in c['metrics']:
        rows = observation_rows((out/('observed_'+metric+'_0.tsv')).read_text())
        need((out/('observed_'+metric+'_0.columns')).read_text().strip(), 'Missing columns')
        counts[metric] = len(rows)
    need(not list(out.glob('*.el')), 'Unexpected EL artifact')
    outputs = {str(p):life.digest(p) for p in out.rglob('*') if p.is_file()
               and p.name not in ('observation.json','service.log')}
    life.save(out/'observation.json', dict(status='READONLY_NATIVE_LABELS_NOT_POINT_QUALIFICATION',
        native_row_counts=counts, exclusion_attributes='UNOBSERVED', point_binding_qualified=False,
        config_seal=seal, pins=c['pins'], output_pins=outputs, application=False, official_percentage=None))


def observation_rows(text):
    reader = csv.DictReader(io.StringIO(text), delimiter='\t')
    need(reader.fieldnames == ['path','meta','name','excluded','cells'], 'Observation schema')
    result = set()
    for row in reader:
        need(None not in row and all(value is not None for value in row.values()), 'Truncated observation')
        key = tuple(row[k] for k in ('path','meta','name'))
        need(all(key) and key not in result and row['excluded'] == 'UNOBSERVED', 'Invalid/fabricated observation')
        result.add(key)
    need(result, 'Empty identity observation')
    return result


def run(out, seal, approved):
    need(approved, 'Parent review required')
    c = check(out, seal)
    need(owned(Path('/proc/self/cgroup').read_text()), 'Fixed service ownership required')
    need(not (out/'execution.json').exists(), 'Once only')
    env = base.local.tools.controlled_environment(c['identity'], os.environ)
    env.pop('DVE', None); env['DVE_COVERAGE_OUTPUT'] = str(out)
    cmd = launch_command(out, c)
    receipt = receipt_base(out, seal, c)
    life.save(out/'execution.json', dict(receipt, command=cmd))
    with (out/'launcher.log').open('x') as stream:
        p = subprocess.Popen(cmd, cwd=out, env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        start = time.monotonic(); time.sleep(5); actual = []
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit(): continue
            try:
                if (proc/'exe').resolve() == Path(c['identity']['executable']) and (proc/'cwd').resolve() == out:
                    group = (proc/'cgroup').read_text()
                    actual.append(dict(pid=int(proc.name), exe=str((proc/'exe').resolve()), cwd=str(out), cgroup=group,
                                       executable_sha256=life.digest(proc/'exe'),
                                       cmdline=(proc/'cmdline').read_bytes().decode().rstrip('\x00').split('\x00')))
            except (OSError, FileNotFoundError): pass
        life.save(out/'live-identity.json', dict(receipt, actual_dve=actual))
        timed_out = False
        try: p.wait(timeout=max(1, 300-(time.monotonic()-start)))
        except subprocess.TimeoutExpired:
            timed_out = True; os.killpg(p.pid, signal.SIGTERM)
            try: p.wait(timeout=5)
            except subprocess.TimeoutExpired: os.killpg(p.pid, signal.SIGKILL); p.wait()
    life.save(out/'terminal.json', dict(receipt, returncode=p.returncode, timeout=timed_out, actual_dve=actual))
    verify(out, seal)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare','check','run','verify'))
    p.add_argument('--output', required=True, type=Path); p.add_argument('--seal')
    p.add_argument('--parent-reviewed', action='store_true')
    a = p.parse_args(); out = a.output.resolve()
    if a.mode == 'prepare': prepare(out)
    elif a.mode == 'run': run(out, a.seal, a.parent_reviewed)
    elif a.mode == 'verify': verify(out, a.seal)
    else: check(out, a.seal); print('READONLY_POINT789_CHECK_PASS_NO_EDA')
