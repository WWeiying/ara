"""Single900s owning-service native launcher; prepare never starts a process."""
import argparse
import ast
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

import dve_tool_identity as tools
import masku_zero3_native796_v2 as qualification

need, digest = qualification.need, qualification.digest
HERE = Path(__file__).resolve().parent
ROOT = qualification.ROOT
OUT = qualification.OUT / 'masku-zero3-native796-v2-prepared-agent-20261008-01'
NATIVE_SHA = '1e0095da65f7272d8c15687e29116ddc77fb9c1c1b355ad5bf5fd51ef347fd03'
UNIT = 'ara-masku-zero3-native796-v2-parent-20261008-01.service'
CGROUP = '/user.slice/user-%d.slice/user@%d.service/app.slice/%s' % (os.getuid(), os.getuid(), UNIT)
HOST = HERE / 'capture_cva6_parent_rvfi457.py'
HOST_SHA = '663514840ec08fa64ef8ee4794ecef8e35eae8eb5cf18e52a0b85f31411bc6b4'
PARENT_RUN = HERE / 'run_masku_parent_bit_enable_native775.py'
PARENT_RUN_SHA = '472ec185e4dd3595fa27336f28bcca727d2562b52977e2e5cb4b7dc79d20c510'
TOOLS_SHA = '856d6571ffc1223ec9f82e6e697849051c4b447e3c6f502f37693565041989d6'
SAMPLE = qualification.OUT / 'gap84-div32-old-image-20261006-01/code.vdb'
ADMITTED = qualification.OUT / 'gap84-offline-admitted-691-20261006-01'
EXTRA = {
    ADMITTED / 'status.json': '0088a5d393b15595574575b470b419f806aeba118289e9e3c573557899e70b3e',
    ADMITTED / 'scalar-comparison.json': '850de931a5f8f93d0073ff07f6d46cf1d946d123fd0718bf19c7a716613aff83',
    ADMITTED / 'vector-comparison.json': '0fdf2cf0cf16a88365265e71c0ab6d2e081f1b9f38245c5c1f5cfba8a1f33b5c',
    ADMITTED / 'evidence-pins.json': '1a77cca20c7172ffcdd239f5f5d6bd4608af699d89f5a46304cdf3b066fbbd4c',
    SAMPLE.parent / 'simulation-status.json': 'b26754171089c271d62a0effd83b640a80164de655ec01a31da0524eb30528c9',
}
life = SimpleNamespace(read_bound=qualification.read_bound, check=qualification.check_pins,
                       save=qualification.save, digest=digest)


def frozen_function(path, sha, name):
    need(digest(path) == sha, 'Frozen mature source drift')
    source = path.read_text()
    functions = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == name]
    need(len(functions) == 1, 'One mature function')
    return ast.get_source_segment(source, functions[0])


def pass_evidence():
    life.check({str(p): sha for p, sha in EXTRA.items()})
    namespace = dict(need=need)
    exec(compile(frozen_function(PARENT_RUN, PARENT_RUN_SHA, 'sample_gate'),
                 str(PARENT_RUN) + ':sample-gate', 'exec'), namespace)
    docs = [json.loads((ADMITTED / name).read_bytes()) for name in
            ('status.json', 'scalar-comparison.json', 'vector-comparison.json')]
    docs.append(json.loads((SAMPLE.parent / 'simulation-status.json').read_bytes()))
    namespace['sample_gate'](*docs)
    historical = json.loads((ADMITTED / 'evidence-pins.json').read_bytes())
    chosen = {p: sha for p, sha in historical.items() if p.startswith(str(SAMPLE) + '/') or
              p in (str(SAMPLE.parent / 'manifest.json'), str(SAMPLE.parent / 'simulation-status.json'),
                    str(SAMPLE.parent / 'commit_trace.csv'), str(SAMPLE.parent / 'vector_trace.csv'))}
    need(chosen and any(p.endswith('tgl.verilog.data.xml') for p in chosen), 'PASS tied to actual sample VDB')
    life.check(chosen)
    return chosen, dict(sample=str(SAMPLE), status=docs[0]['status'],
                         scalar_instructions=docs[1]['matched_instructions'],
                         vector_instructions=docs[2]['compared_instructions'],
                         vector_bytes=docs[2]['compared_bytes'], historical_checker_policy_unchanged=True)


def cgroup_gate(text, expected):
    need(type(text) is str and text.splitlines() == ['0::' + expected], 'Exact owning cgroup')


def owning_gate(out, c):
    need(os.environ.get('INVOCATION_ID') and c['output'] == str(out), 'Direct owning systemd service required')
    cgroup_gate(Path('/proc/self/cgroup').read_text(), c['expected_cgroup'])


def live_gate(pid, identity, launch_pid, launch_starttime, c):
    witness = tools.verify_live_executable(pid, identity, launch_pid, launch_starttime)
    proc = Path('/proc') / str(pid)
    need(proc.joinpath('cwd').resolve() == OUT, 'Actual child cwd differs')
    cgroup = proc.joinpath('cgroup').read_text()
    cgroup_gate(cgroup, c['expected_cgroup'])
    return dict(witness, cwd=str(OUT), cgroup=cgroup, worker_pid=os.getpid(),
                systemd_invocation=os.environ['INVOCATION_ID'])


def terminal_gate(terminal, c, live, witnesses, execution):
    need(type(terminal.get('returncode')) is int and terminal['returncode'] == 0,
         'Integer0 terminal required, not bool/float/string')
    need(type(terminal.get('timeout')) is bool and terminal['timeout'] is False, 'Exact boolFalse timeout')
    actual = terminal.get('actual_dve')
    need(type(actual) is list and len(actual) == 1 and actual == live and
         type(witnesses) is list and len(witnesses) == 1, 'One actual native process and fresh witness')
    p, w = actual[0], witnesses[0]
    need(type(p.get('pid')) is int and p['pid'] > 0 and p.get('exe') == c['identity']['executable'] and
         p.get('cwd') == str(OUT), 'Exact actual PID/exe/cwd')
    cgroup_gate(p.get('cgroup'), c['expected_cgroup'])
    need(w.get('pid') == p['pid'] and type(w.get('pid')) is int and w.get('executable') == p['exe'] and
         w.get('cwd') == p['cwd'] and w.get('cgroup') == p['cgroup'] and
         w.get('executable_verified') is True and type(w.get('launch_pid')) is int and
         w['launch_pid'] > 0 and w['launch_pid'] != p['pid'] and type(w.get('worker_pid')) is int and
         w['worker_pid'] > 0 and type(w.get('starttime')) is int and
         type(w.get('launch_starttime')) is int and w['starttime'] >= w['launch_starttime'] > 0 and
         bool(w.get('systemd_invocation')) and w['systemd_invocation'] == execution.get('systemd_invocation'),
         'Fresh /proc executable/ancestry/cgroup witness required')
    need(execution.get('automatic_retry') is False and type(execution.get('timeout_seconds')) is int and
         execution['timeout_seconds'] == 900, 'Single900s execution contract')


def load_launch(out, native_seal, manifest_path, launch_seal):
    need(out == OUT and native_seal == NATIVE_SHA, 'Exact v2 native freeze')
    c = qualification.verify(out, native_seal)
    manifest = life.read_bound(manifest_path, launch_seal)
    need(manifest['schema'] == 'MASKU_ZERO3_V2_SINGLE900S_OWNING_SERVICE_LAUNCH' and
         manifest['manifest_path'] == str(manifest_path) and manifest['output'] == str(OUT) and
         manifest['native_config_sha256'] == NATIVE_SHA and manifest['systemd_unit'] == UNIT and
         manifest['expected_cgroup'] == CGROUP and type(manifest['timeout_seconds']) is int and
         manifest['timeout_seconds'] == 900 and manifest['automatic_retry'] is False and
         manifest['population_application'] is False and manifest['parent_review_required'] is True,
         'Exact separate launch manifest')
    life.check(manifest['pins'])
    tools.revalidate(manifest['identity'])
    need(manifest['identity']['executable'] == c['expected_dve_exe'], 'Actual native executable matches v2 config')
    _, evidence = pass_evidence()
    need(evidence == manifest['already_PASS_sample'], 'Exact unchanged admitted PASS')
    return dict(c, identity=manifest['identity'], expected_cgroup=manifest['expected_cgroup'],
                pins=dict(c['pins'], **manifest['pins']))


def strict_inspect(out, native_seal, manifest_path, launch_seal):
    c = load_launch(out, native_seal, manifest_path, launch_seal)
    terminal = json.loads((out / 'terminal.json').read_bytes())
    terminal_gate(terminal, c, json.loads((out / 'live-identity.json').read_bytes()),
                  json.loads((out / 'process-witness.json').read_bytes()),
                  json.loads((out / 'execution.json').read_bytes()))
    need(not (out / 'process-validation-error.json').exists(), 'Live process validation failed')
    qualification.inspect(out, native_seal)
    receipt = dict(status='MASKU_ZERO3_V2_STRICT_NATIVE_QUALIFIED_NOT_APPLIED',
                   launch_manifest_sha256=launch_seal, native_config_sha256=native_seal,
                   native_result_sha256=digest(out / 'capture-result.json'),
                   terminal_sha256=digest(out / 'terminal.json'), process_witness_sha256=digest(out / 'process-witness.json'),
                   population_application=False, official_percentage=None)
    path = manifest_path.parent / 'strict-inspection-receipt.json'
    if path.exists():
        need(json.loads(path.read_bytes()) == receipt, 'Strict receipt drift')
    else:
        life.save(path, receipt)


def worker(manifest_path, launch_seal):
    code = frozen_function(HOST, HOST_SHA, 'run')
    header = "c = life.read_bound(out / 'config.json', seal); contract(c); life.check(c['pins']); tools.revalidate(c['identity'])"
    popen = 'process = subprocess.Popen(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)'
    replacements = {
        header: 'c = load_launch(out, seal, manifest_path, launch_seal)',
        "require(os.environ.get('INVOCATION_ID') and c['output'] == str(out), 'Direct owning systemd service required')":
            'owning_gate(out, c)',
        'CVA6_PARENT_RVFI457_SEAL=seal': 'MASKU_ZERO3_SEAL=seal',
        popen: "deadline = time.monotonic() + c['timeout_seconds']\n        " + popen,
        'actual = []': 'actual = []; witnesses = []',
        "tools.verify_live_executable(int(p.name), c['identity'], process.pid, start)":
            "witnesses.append(live_gate(int(p.name), c['identity'], process.pid, start, c))",
        'except (OSError, ProcessLookupError): pass':
            "except (OSError, ProcessLookupError): pass\n            except ValueError as error:\n                "
            "actual = []; witnesses = []\n                life.save(out / 'process-validation-error.json', "
            "dict(reason=str(error)))\n                break",
        "life.save(out / 'live-identity.json', actual)":
            "life.save(out / 'process-witness.json', witnesses); life.save(out / 'live-identity.json', actual)",
        "process.wait(timeout=c['timeout_seconds'])": 'process.wait(timeout=max(0, deadline - time.monotonic()))',
    }
    for before, after in replacements.items():
        need(code.count(before) == 1, 'Exact mature runner adapter anchor: ' + before)
        code = code.replace(before, after)
    namespace = dict(globals(), ENTRY=qualification.ENTRY, require=need, manifest_path=manifest_path,
                     launch_seal=launch_seal,
                     verify=lambda out, seal: strict_inspect(out, seal, manifest_path, launch_seal))
    exec(compile(code, __file__ + ':private-mature-host-run', 'exec'), namespace)
    return namespace['run']


def prepare(directory):
    need(directory.parent == qualification.OUT and not directory.exists(), 'Fresh launcher directory')
    c = qualification.verify(OUT, NATIVE_SHA)
    chosen, evidence = pass_evidence()
    identity = tools.prepare(str(qualification.DVE_ENTRY), '/usr/bin/xvfb-run')
    tools.revalidate(identity)
    need(identity['executable'] == c['expected_dve_exe'], 'Exact prepared DVE ELF')
    pins = dict(c['pins'], **chosen)
    pins[str(OUT / 'config.json')] = NATIVE_SHA
    pins.update({str(p): sha for p, sha in EXTRA.items()})
    pins.update({f['path']: f['sha256'] for f in identity['files']})
    for path, sha in ((HOST, HOST_SHA), (PARENT_RUN, PARENT_RUN_SHA), (Path(tools.__file__).resolve(), TOOLS_SHA)):
        need(digest(path) == sha, 'Mature tool drift')
        pins[str(path)] = sha
    for path in (Path(__file__).resolve(), HERE / 'test_run_masku_zero3_native796_v2.py'):
        pins[str(path)] = digest(path)
    manifest_path = directory / 'launch-manifest.json'
    manifest = dict(schema='MASKU_ZERO3_V2_SINGLE900S_OWNING_SERVICE_LAUNCH',
                    status='FROZEN_PREPARED_NOT_AUTHORIZED_NOT_STARTED', manifest_path=str(manifest_path),
                    output=str(OUT), native_config_sha256=NATIVE_SHA, identity=identity, pins=pins,
                    timeout_seconds=900, automatic_retry=False, population_application=False,
                    systemd_unit=UNIT, expected_cgroup=CGROUP, parent_review_required=True,
                    already_PASS_sample=evidence, EDA_started=False,
                    worker_environment=dict(MASKU_ZERO3_SEAL=NATIVE_SHA),
                    execution_policy='Direct systemd owning worker, one atomic launch lock, total900s; no retry or population application')
    worker(manifest_path, 'STATIC_ONLY')
    life.check(pins)
    directory.mkdir()
    life.save(manifest_path, manifest)
    launch_seal = digest(manifest_path)
    command = ['systemd-run', '--user', '--unit=' + UNIT, '--property=KillMode=control-group',
               '--property=RuntimeMaxSec=960', '--property=StandardOutput=append:' + str(directory / 'service.log'),
               '--property=StandardError=append:' + str(directory / 'service.log'),
               '--working-directory=' + str(OUT), sys.executable, '-B',
               str(Path(__file__).resolve()), 'run', '--manifest', str(manifest_path), '--seal', launch_seal,
               '--parent-reviewed-seal', launch_seal]
    life.save(directory / 'prepare-receipt.json', dict(status=manifest['status'], manifest_sha256=launch_seal,
              native_config_sha256=NATIVE_SHA, parent_authorized_command_not_executed=command,
              EDA_started=False, native_qualified=False, old_freeze_changed=False))
    return manifest


def run(manifest_path, launch_seal, parent_reviewed_seal):
    need(type(launch_seal) is str and launch_seal and launch_seal == parent_reviewed_seal,
         'Parent-reviewed exact manifest seal required')
    c = load_launch(OUT, NATIVE_SHA, manifest_path, launch_seal)
    owning_gate(OUT, c)
    names = ('launch-once.json', 'execution.json', 'terminal.json', 'launcher.log', 'live-identity.json',
             'process-witness.json', 'process-validation-error.json', 'capture-result.json',
             'qualification-reject.json', 'error.txt', 'actual-binding.json', 'first.el')
    need(not any((OUT / n).exists() for n in names) and not list(OUT.glob('native_*.tsv')),
         'Fresh execution only; no retry, overwrite or evidence reuse')
    life.save(OUT / 'launch-once.json', dict(launch_manifest_sha256=launch_seal,
              worker_pid=os.getpid(), systemd_invocation=os.environ['INVOCATION_ID'], automatic_retry=False))
    worker(manifest_path, launch_seal)(OUT, NATIVE_SHA)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify', 'run', 'inspect'))
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--seal')
    parser.add_argument('--parent-reviewed-seal')
    args = parser.parse_args()
    if args.mode == 'prepare':
        need(args.directory, 'Fresh launcher preparation directory')
        result = prepare(args.directory.resolve())
        print(json.dumps(dict(status=result['status'], manifest=result['manifest_path'],
                              seal=digest(result['manifest_path']))))
    else:
        need(args.manifest and args.seal, 'Exact launch manifest and seal')
        path = args.manifest.resolve()
        if args.mode == 'run': run(path, args.seal, args.parent_reviewed_seal)
        elif args.mode == 'inspect': strict_inspect(OUT, NATIVE_SHA, path, args.seal)
        else:
            load_launch(OUT, NATIVE_SHA, path, args.seal)
            print('MASKU_ZERO3_V2_LAUNCH_VERIFY_PASS_NOT_STARTED')
