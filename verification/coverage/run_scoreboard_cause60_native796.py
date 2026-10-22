"""Prepare one900s mature owning-service worker; run requires a separate exact parent seal."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import FunctionType, SimpleNamespace

import scoreboard_cause60_native796 as core

mature, need, tools = core.mature, core.need, core.mature.tools
OUT, HERE = core.OUT, core.HERE
SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_run_scoreboard_cause60_native796.py')
LAUNCH = core.u.OUT / 'scoreboard-cause60-native796-launcher-prepared-agent-20261008-03'
UNIT = 'ara-scoreboard-cause60-native796-agent-20261008-03.service'
CGROUP = '/user.slice/user-%d.slice/user@%d.service/app.slice/%s' % (os.getuid(),os.getuid(),UNIT)
life = SimpleNamespace(save=core.source.write_json, check=core.source.check_pins,
                       read_bound=core.read_bound, digest=core.u.digest)


def approve(seal, parent):
    need(type(seal) is str and len(seal) == 64 and all(ch in '0123456789abcdef' for ch in seal)
         and seal == parent, 'Independent parent-reviewed exact manifest seal required')


def owning_gate(out, c):
    need(os.environ.get('INVOCATION_ID') and c['output'] == str(out), 'Direct owning systemd worker')
    mature.cgroup_gate(Path('/proc/self/cgroup').read_text(), c['expected_cgroup'])


def live_gate(pid, identity, launch_pid, launch_starttime, c):
    return FunctionType(mature.live_gate.__code__, dict(vars(mature), OUT=OUT))(
        pid, identity, launch_pid, launch_starttime, c)


def terminal_gate(terminal, c, live, witnesses, execution):
    return FunctionType(mature.terminal_gate.__code__, dict(vars(mature), OUT=OUT))(
        terminal, c, live, witnesses, execution)


def load_launch(out, native_seal, manifest_path, launch_seal):
    need(out == OUT and manifest_path == LAUNCH / 'launch-manifest.json', 'Exact successor paths')
    manifest = core.read_bound(manifest_path, launch_seal)
    need(manifest['schema'] == 'CAUSE60_SINGLE900S_MATURE_OWNING_SERVICE_V1' and
         manifest['manifest_path'] == str(manifest_path) and manifest['output'] == str(OUT) and
         manifest['native_config_sha256'] == native_seal and manifest['systemd_unit'] == UNIT and
         manifest['expected_cgroup'] == CGROUP and type(manifest['timeout_seconds']) is int and
         manifest['timeout_seconds'] == 900 and manifest['automatic_retry'] is False and
         manifest['population_application'] is False and manifest['parent_review_required'] is True and
         manifest['worker_environment'] == dict(CAUSE60_CONFIG_SEAL=native_seal,PYTHONPATH=str(HERE)),
         'Exact owning-service one-shot contract')
    life.check(manifest['pins'])
    c = core.check(OUT, native_seal)
    tools.revalidate(manifest['identity'])
    need(manifest['identity'] == c['identity'], 'Same sealed actual native ELF roles')
    _, passed = mature.pass_evidence()
    need(passed == manifest['already_PASS_sample'] == c['already_PASS_sample'], 'Unchanged admitted PASS')
    return dict(c, expected_cgroup=CGROUP, pins=dict(c['pins'], **manifest['pins']))


def inspect(out, native_seal, manifest_path, launch_seal):
    c = load_launch(out, native_seal, manifest_path, launch_seal)
    need(not (out / 'process-validation-error.json').exists(), 'Actual live identity validation failed')
    terminal = json.loads((out / 'terminal.json').read_bytes())
    execution = json.loads((out / 'execution.json').read_bytes())
    live = json.loads((out / 'live-identity.json').read_bytes())
    witness = json.loads((out / 'process-witness.json').read_bytes())
    terminal_gate(terminal, c, live, witness, execution)
    result = core.inspect_capture(out, native_seal)
    for name in ('launch-once.json','execution.json','terminal.json','live-identity.json',
                 'process-witness.json','launcher.log'):
        result['pins'][str(out / name)] = life.digest(out / name)
    result['launch_manifest_sha256'] = launch_seal
    result['native_process_verified'] = True
    life.save(out / 'capture-result.json', result)
    return result


def worker(manifest_path, launch_seal):
    code = mature.frozen_function(mature.HOST, mature.HOST_SHA, 'run')
    replacements = {
        "c = life.read_bound(out / 'config.json', seal); contract(c); life.check(c['pins']); tools.revalidate(c['identity'])":
            'deadline = time.monotonic() + 900\n    c = load_launch(out, seal, manifest_path, launch_seal)',
        "require(os.environ.get('INVOCATION_ID') and c['output'] == str(out), 'Direct owning systemd service required')":
            'owning_gate(out, c)',
        'CVA6_PARENT_RVFI457_SEAL=seal': 'CAUSE60_CONFIG_SEAL=seal, PYTHONPATH=str(HERE)',
        'process = subprocess.Popen(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)':
            "need(time.monotonic() < deadline - 20, '900s budget exhausted before native start')\n        "
            'process = subprocess.Popen(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)',
        'actual = []': 'actual = []; witnesses = []',
        "tools.verify_live_executable(int(p.name), c['identity'], process.pid, start)":
            "witnesses.append(live_gate(int(p.name), c['identity'], process.pid, start, c))",
        'except (OSError, ProcessLookupError): pass':
            "except (OSError, ProcessLookupError): pass\n            except ValueError as error:\n                "
            "actual = []; witnesses = []\n                life.save(out / 'process-validation-error.json', dict(reason=str(error)))\n                break",
        "life.save(out / 'live-identity.json', actual)":
            "life.save(out / 'process-witness.json', witnesses); life.save(out / 'live-identity.json', actual)",
        "process.wait(timeout=c['timeout_seconds'])": 'process.wait(timeout=max(0, deadline - 10 - time.monotonic()))',
        'process.wait(timeout=10)': 'process.wait(timeout=5)',
        'process.wait()': 'process.wait(timeout=5)',
    }
    for before, after in replacements.items():
        need(code.count(before) == 1, 'Exact frozen mature runner adapter anchor: ' + before)
        code = code.replace(before, after)
    namespace = dict(globals(), ENTRY=OUT / 'native-bind.tcl', require=need,
        manifest_path=manifest_path, launch_seal=launch_seal,
        verify=lambda out, seal: inspect(out, seal, manifest_path, launch_seal))
    exec(compile(code, __file__ + ':private-mature-host-run', 'exec'), namespace)
    return namespace['run']


def service_command(manifest, launch_seal):
    return ['/usr/bin/systemd-run','--user','--unit=' + UNIT,'--property=Type=exec',
        '--property=KillMode=control-group','--property=RuntimeMaxSec=900','--property=TimeoutStopSec=10',
        '--property=Restart=no','--property=StandardOutput=append:' + str(LAUNCH / 'service.log'),
        '--property=StandardError=append:' + str(LAUNCH / 'service.log'),
        '--working-directory=' + str(OUT), '--setenv=PYTHONPATH=' + str(HERE),
        str(Path(sys.executable).resolve()),'-B',str(SCRIPT),'run','--manifest',manifest['manifest_path'],
        '--seal',launch_seal,'--parent-reviewed-seal',launch_seal]


def prepare(directory):
    need(directory == LAUNCH and not directory.exists(), 'Fresh separate launcher preparation')
    native_seal = life.digest(OUT / 'config.json'); c = core.check(OUT, native_seal)
    chosen, passed = mature.pass_evidence()
    pins = dict(c['pins'], **chosen, **{str(OUT / 'config.json'): native_seal})
    for path, sha in ((mature.HOST,mature.HOST_SHA),(mature.PARENT_RUN,mature.PARENT_RUN_SHA),
                      (Path(tools.__file__).resolve(),mature.TOOLS_SHA)):
        need(life.digest(path) == sha, 'Mature native service/helper seal'); pins[str(path)] = sha
    for path in (SCRIPT, TEST, Path(mature.__file__).resolve()):
        pins[str(path)] = life.digest(path)
    host_tools = [tools.seal_file(p) for p in
                  (Path('/usr/bin/systemd-run'),Path('/usr/bin/systemctl'),Path(sys.executable).resolve())]
    pins.update({p['path']:p['sha256'] for p in host_tools})
    manifest_path = directory / 'launch-manifest.json'
    manifest = dict(schema='CAUSE60_SINGLE900S_MATURE_OWNING_SERVICE_V1',
        status='FROZEN_PREPARED_NOT_AUTHORIZED_NOT_STARTED', manifest_path=str(manifest_path),
        output=str(OUT), native_config_sha256=native_seal, identity=c['identity'], pins=pins,
        host_tools=host_tools, timeout_seconds=900, automatic_retry=False, population_application=False,
        systemd_unit=UNIT, expected_cgroup=CGROUP, parent_review_required=True,
        already_PASS_sample=passed, EDA_started=False,
        worker_environment=dict(CAUSE60_CONFIG_SEAL=native_seal,PYTHONPATH=str(HERE)),
        partial_API_status=c['API_evidence']['status'],
        execution_policy='One atomic launch lock; direct owning service; actual ELF ancestry/cgroup; '
            'total900s with bounded cleanup; no retry; complete bit/complement capture or HOLD.')
    worker(manifest_path, 'STATIC_ONLY')  # Compile the frozen adapter; never invoke it here.
    life.check(pins)
    directory.mkdir(); life.save(manifest_path,manifest)
    seal = life.digest(manifest_path)
    receipt = dict(status=manifest['status'], manifest_sha256=seal, native_config_sha256=native_seal,
        parent_authorized_command_not_executed=service_command(manifest,seal), EDA_started=False,
        native_qualified=False, timeout_seconds=900, automatic_retry=False, frozen14_changed=False)
    life.save(directory / 'prepare-receipt.json',receipt)
    return receipt


def run(manifest_path, launch_seal, parent_reviewed_seal):
    approve(launch_seal,parent_reviewed_seal)
    manifest = core.read_bound(manifest_path,launch_seal)
    native_seal = manifest['native_config_sha256']
    c = load_launch(OUT,native_seal,manifest_path,launch_seal); owning_gate(OUT,c)
    need(os.environ.get('CAUSE60_CONFIG_SEAL', native_seal) == native_seal, 'Config environment seal')
    names = ('launch-once.json','execution.json','terminal.json','launcher.log','live-identity.json',
             'process-witness.json','error.txt','capture-result.json','qualification-reject.json','first.el')
    need(not any((OUT / n).exists() for n in names) and not list(OUT.glob('objects_*.tsv')) and
         not list(OUT.glob('bits_*.tsv')), 'Fresh one-shot native only; no reuse/retry')
    life.save(OUT / 'launch-once.json',dict(launch_manifest_sha256=launch_seal,
        worker_pid=os.getpid(),systemd_invocation=os.environ['INVOCATION_ID'],automatic_retry=False))
    worker(manifest_path,launch_seal)(OUT,native_seal)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('prepare','check','run','inspect'))
    p.add_argument('--directory',type=Path,default=LAUNCH)
    p.add_argument('--manifest',type=Path,default=LAUNCH / 'launch-manifest.json')
    p.add_argument('--seal');p.add_argument('--parent-reviewed-seal')
    a = p.parse_args()
    if a.mode == 'prepare':
        need(a.seal is None and a.parent_reviewed_seal is None, 'Prepare is not launch authorization')
        result = prepare(a.directory.resolve())
    elif a.mode == 'run':
        run(a.manifest.resolve(),a.seal,a.parent_reviewed_seal);result=dict(status='NATIVE_RUN_COMPLETED')
    else:
        manifest = core.read_bound(a.manifest.resolve(),a.seal)
        result = inspect(OUT,manifest['native_config_sha256'],a.manifest.resolve(),a.seal) if a.mode == 'inspect' else (
            load_launch(OUT,manifest['native_config_sha256'],a.manifest.resolve(),a.seal) and dict(status='CHECK_PASS_NO_EDA'))
    print(json.dumps(result,indent=2),flush=True)
