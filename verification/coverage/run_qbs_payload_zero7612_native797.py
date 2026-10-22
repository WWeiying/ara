"""Prepare a separate parent-reviewed one-shot900s owning-service launcher."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import qbs_payload_zero7612_native797 as core

need, digest, save = core.need, core.digest, core.save
SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_run_qbs_payload_zero7612_native797.py')
MATURE = core.HERE / 'run_masku_zero3_native796_v2.py'
MATURE_SHA = '274b7cc8f67b383d492a5d0344908fda13638201ed500aab8348545c78ef3e20'
C910 = core.HERE / 'c910_lane23_padding1424_local.py'
C910_SHA = '111f2ddb34c7b91be13ce67877ce8790902df9dceca350b47c1a95e9981bdbd7'
SCHEMA = 'QBS7612_SINGLE900S_OWNING_SERVICE_PREPARED_V1'


def mature_gates(out):
    need(digest(MATURE) == MATURE_SHA, 'Mature MaskU gate drift')
    return core.source.extracted(MATURE, {'cgroup_gate', 'terminal_gate'},
                                 dict(need=need, OUT=out), {})


def approved(seal, reviewed):
    need(type(seal) is str and len(seal) == 64 and seal == reviewed, 'Exact parent-reviewed launch seal required')


def cgroup_gate(text, expected):
    return mature_gates(core.OUT)['cgroup_gate'](text, expected)


def owning_gate(out, c):
    need(os.environ.get('INVOCATION_ID') and c['output'] == str(out), 'Direct owning systemd worker required')
    cgroup_gate(Path('/proc/self/cgroup').read_text(), c['expected_cgroup'])


def command(c, out):
    identity = c['identity']
    return [identity['roles']['xvfb_run'], '-a', '-e', str(out / 'xvfb.log'),
            '-s', '-screen 0 1280x1024x24', identity['roles']['launcher'],
            '-full64', '-cov', '-script', str(out / 'native-bind.tcl')]


def service_command(manifest_path, seal, m):
    return [m['host_tools'][0]['path'], '--user', '--unit=' + m['unit'], '--collect',
            '--property=Type=exec', '--property=KillMode=control-group', '--property=RuntimeMaxSec=900',
            '--property=TimeoutStopSec=10', '--working-directory=' + m['output'],
            '--setenv=PYTHONPATH=' + str(core.HERE), m['host_tools'][2]['path'], '-B', str(SCRIPT), 'run',
            '--manifest', str(manifest_path), '--seal', seal, '--parent-reviewed-seal', seal]


def prepare(directory, out, native_seal):
    need(directory.parent == core.OUT and not directory.exists(), 'Fresh independent launch directory')
    c = core.check(out, native_seal)
    identity = c['identity']
    core.tools.revalidate(identity)
    pins = dict(c['pins'], **{str(out / 'config.json'): native_seal})
    for path, sha in ((MATURE, MATURE_SHA), (C910, C910_SHA)):
        need(digest(path) == sha, 'Reviewed helper freeze')
        pins[str(path)] = sha
    for path in (SCRIPT, TEST):
        pins[str(path)] = digest(path)
    host = [core.tools.seal_file(p) for p in
            (Path('/usr/bin/systemd-run'), Path('/usr/bin/systemctl'), Path(sys.executable).resolve())]
    pins.update({r['path']: r['sha256'] for r in host})
    unit = 'qbs7612-local-' + core.source.value_sha(str(out))[:20] + '.service'
    group = '/user.slice/user-%d.slice/user@%d.service/app.slice/%s' % (os.getuid(), os.getuid(), unit)
    path = directory / 'launch-manifest.json'
    m = dict(schema=SCHEMA, status='FROZEN_PREPARED_NOT_AUTHORIZED_NOT_STARTED',
             manifest_path=str(path), output=str(out), native_config_sha256=native_seal,
             identity=identity, pins=pins, host_tools=host, uid=os.getuid(), unit=unit, expected_cgroup=group,
             timeout_seconds=900, automatic_retry=False, parent_review_required=True,
             population_application=False, EDA_started=False, native_qualified=False,
             initial_X_excluded=False, initial_X_counts_as_known_toggle=False,
             known_toggle_qualification=False, raw797_suffix_mandatory=True)
    mature_gates(out)
    core.check_pins(pins)
    directory.mkdir()
    save(path, m)
    seal = digest(path)
    save(directory / 'prepare-receipt.json', dict(status=m['status'], manifest_path=str(path),
         manifest_sha256=seal, native_config_sha256=native_seal, timeout_seconds=900,
         parent_authorized_command_not_executed=service_command(path, seal, m),
         EDA_started=False, native_qualified=False, known_toggle_qualification=False))
    return dict(status=m['status'], manifest=str(path), seal=seal, EDA_started=False)


def load_launch(path, seal):
    m = core.read_bound(path, seal)
    out = Path(m['output'])
    need(m['schema'] == SCHEMA and m['manifest_path'] == str(path) and path.parent.parent == core.OUT and
         out.parent == core.OUT and type(m['timeout_seconds']) is int and m['timeout_seconds'] == 900 and
         type(m['uid']) is int and m['uid'] == os.getuid() and
         all(m[k] is False for k in ('automatic_retry', 'population_application', 'EDA_started',
             'native_qualified', 'initial_X_excluded', 'initial_X_counts_as_known_toggle', 'known_toggle_qualification'))
         and m['parent_review_required'] is True and m['raw797_suffix_mandatory'] is True, 'Closed one-shot launch contract')
    unit = 'qbs7612-local-' + core.source.value_sha(str(out))[:20] + '.service'
    expected = '/user.slice/user-%d.slice/user@%d.service/app.slice/%s' % (m['uid'], m['uid'], unit)
    need(m['unit'] == unit and m['expected_cgroup'] == expected, 'Exact owning service identity')
    core.check_pins(m['pins'])
    c = core.check(out, m['native_config_sha256'])
    need(m['identity'] == c['identity'] and all(m['pins'].get(p) == sha for p, sha in c['pins'].items()),
         'Exact sealed native config/tool roles and complete dependencies')
    for p, sha in ((SCRIPT, digest(SCRIPT)), (TEST, digest(TEST)), (MATURE, MATURE_SHA), (C910, C910_SHA),
                   (out / 'config.json', m['native_config_sha256'])):
        need(m['pins'].get(str(p)) == sha, 'Required launcher/native/gate pin')
    need(m['host_tools'] == [core.tools.seal_file(p) for p in
         (Path('/usr/bin/systemd-run'), Path('/usr/bin/systemctl'), Path(sys.executable).resolve())], 'Sealed host tools')
    return out, dict(c, expected_cgroup=m['expected_cgroup']), m


def live_gate(pid, c, launch_pid, start, execution):
    witness = core.tools.verify_live_executable(pid, c['identity'], launch_pid, start)
    proc = Path('/proc') / str(pid)
    need(proc.joinpath('cwd').resolve() == Path(c['output']), 'Actual native child cwd')
    group = proc.joinpath('cgroup').read_text()
    cgroup_gate(group, c['expected_cgroup'])
    witness.update(cwd=c['output'], cgroup=group, worker_pid=execution['worker_pid'],
                   systemd_invocation=execution['systemd_invocation'])
    return dict(pid=pid, exe=c['identity']['executable'], cwd=c['output'], cgroup=group), witness


def terminal_gate(t, c, live, witnesses, execution):
    mature_gates(Path(c['output']))['terminal_gate'](t, c, live, witnesses, execution)
    need(execution['cwd'] == c['output'] and execution['command'] == command(c, Path(c['output'])) and
         type(execution['worker_pid']) is int and execution['worker_pid'] > 0 and
         execution['worker_pid'] == witnesses[0]['worker_pid'] and
         execution['launch_pid'] == witnesses[0]['launch_pid'] and
         execution['launch_starttime'] == witnesses[0]['launch_starttime'], 'Exact worker/launch terminal binding')
    cgroup_gate(execution['worker_cgroup'], c['expected_cgroup'])


def inspect(path, seal):
    out, c, m = load_launch(path, seal)
    need(not (out / 'worker-error.json').exists(), 'Recorded worker error HOLD')
    t = json.loads((out / 'terminal.json').read_bytes())
    e = json.loads((out / 'execution.json').read_bytes())
    live = json.loads((out / 'live-identity.json').read_bytes())
    witnesses = json.loads((out / 'process-witness.json').read_bytes())
    need(e['launch_manifest_sha256'] == seal and e['config_seal'] == m['native_config_sha256'] and
         e['parent_reviewed_seal'] == seal, 'Exact parent-reviewed execution seals')
    terminal_gate(t, c, live, witnesses, e)
    result = core.inspect_local(out, m['native_config_sha256'])
    result.update(launch_manifest_sha256=seal, timeout_seconds=900, process_identity_verified=True,
                  native_qualified=False, qualification_boundary='Native identity/partial exclusion roundtrip only; no known-edge or X waiver')
    names = ['terminal.json', 'execution.json', 'live-identity.json', 'process-witness.json',
             'launch-once.json', 'actual-binding.json', 'candidate.el', 'first.el', 'second.el',
             'initial-empty.el', 'reset-empty.el', 'final-empty.el', 'cleanup-empty.el',
             'selected_tests.txt', 'DVEfiles/dve_gui.log']
    names += ['%s_%s_%d.tsv' % (prefix, stage, i) for prefix in ('native', 'bits')
              for stage in core.STAGES for i in range(len(c['instances']))]
    result['pins'] = dict(m['pins'], **{str(path): seal},
                          **{str(out / n): digest(out / n) for n in names})
    core.check_pins(result['pins'])
    save(path.parent / 'native-binding-receipt.json', result)
    return result


def fresh_gate(out):
    names = ('launch-once.json', 'execution.json', 'terminal.json', 'launcher.log', 'error.txt',
             'live-identity.json', 'process-witness.json', 'live-ready', 'actual-binding.json',
             'candidate.el', 'first.el', 'worker-error.json', 'selected_tests.txt')
    need(not any((out / n).exists() for n in names) and not list(out.glob('native_*.tsv')) and
         not list(out.glob('bits_*.tsv')), 'Fresh one-shot only; no retry or evidence reuse')


def run(path, seal, reviewed):
    approved(seal, reviewed)
    deadline = time.monotonic() + 900
    out, c, m = load_launch(path, seal)
    owning_gate(out, c)
    fresh_gate(out)
    invocation = os.environ['INVOCATION_ID']
    save(out / 'launch-once.json', dict(manifest_sha256=seal, worker_pid=os.getpid(),
         systemd_invocation=invocation, automatic_retry=False))
    env = core.tools.controlled_environment(c['identity'], os.environ)
    env.pop('DVE', None)
    env.update(DVE_COVERAGE_OUTPUT=str(out), QBS7612_SEAL=m['native_config_sha256'], PYTHONPATH=str(core.HERE))
    execution = dict(command=command(c, out), cwd=str(out), config_seal=m['native_config_sha256'],
        launch_manifest_sha256=seal, parent_reviewed_seal=reviewed, automatic_retry=False, timeout_seconds=900,
        worker_pid=os.getpid(), worker_cgroup=Path('/proc/self/cgroup').read_text(), systemd_invocation=invocation)
    process, live, witnesses, timeout, rc = None, [], [], False, -1
    try:
        need(time.monotonic() < deadline - 10, 'Preparation validation exhausted900s budget')
        with (out / 'launcher.log').open('x') as log:
            process = subprocess.Popen(execution['command'], cwd=out, env=env, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            start = core.tools.process_info(process.pid)['starttime']
            execution.update(launch_pid=process.pid, launch_starttime=start)
            save(out / 'execution.json', execution)
            probe_deadline = min(deadline - 10, time.monotonic() + 60)
            while time.monotonic() < probe_deadline:
                live, witnesses = [], []
                for p in Path('/proc').iterdir():
                    if not p.name.isdigit():
                        continue
                    try:
                        if (p / 'exe').resolve() != Path(c['identity']['executable']) or (p / 'cwd').resolve() != out:
                            continue
                        row, witness = live_gate(int(p.name), c, process.pid, start, execution)
                        live.append(row); witnesses.append(witness)
                    except (OSError, ProcessLookupError):
                        continue
                if live or process.poll() is not None:
                    break
                time.sleep(0.5)
            need(len(live) == len(witnesses) == 1, 'One fresh actual DVE child required')
            save(out / 'live-identity.json', live)
            save(out / 'process-witness.json', witnesses)
            with (out / 'live-ready').open('x') as stream:
                stream.write(seal + '\n')
            try:
                process.wait(timeout=max(0, deadline - 10 - time.monotonic()))
            except subprocess.TimeoutExpired:
                timeout = True
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
            rc = process.returncode
    except Exception as error:
        save(out / 'worker-error.json', dict(error=str(error), EDA_started=process is not None))
        if process is not None:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
            rc = process.returncode
        raise
    finally:
        save(out / 'terminal.json', dict(returncode=rc, timeout=timeout, actual_dve=live))
    return inspect(path, seal)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'check', 'run', 'inspect'))
    p.add_argument('--directory', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--native-seal')
    p.add_argument('--manifest', type=Path)
    p.add_argument('--seal')
    p.add_argument('--parent-reviewed-seal')
    a = p.parse_args()
    if a.mode == 'prepare':
        need(a.directory and a.output and a.native_seal and a.seal is None and a.parent_reviewed_seal is None,
             'Preparation cannot authorize EDA')
        result = prepare(a.directory.resolve(), a.output.resolve(), a.native_seal)
    else:
        need(a.manifest and a.seal, 'Exact independent launcher manifest and seal')
        path = a.manifest.resolve()
        if a.mode == 'run': result = run(path, a.seal, a.parent_reviewed_seal)
        elif a.mode == 'inspect': result = inspect(path, a.seal)
        else:
            load_launch(path, a.seal)
            result = dict(status='LAUNCHER_CHECK_PASS_NOT_STARTED')
    print(json.dumps(result, indent=2), flush=True)
