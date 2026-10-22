"""Prepare-only by default; parent-reviewed single900s owning-service launcher.

The original config/helper/Tcl remain untouched. Strict terminal checking wraps
the original inspector; the mature host runner is adapted in a private namespace.
"""
import argparse
import inspect
import json
from pathlib import Path
import sys

import masku_parent_bit_enable_native775 as qualification

life, need = qualification.life, qualification.need
host = qualification.mature.host
OUT = qualification.source.OUT / 'masku-parent-bit-enable-native775-prepared-agent-20261007-01'
NATIVE_SHA = 'e73fc88aa0ae663ba6b080e478934062b9c06d9692112cf9e8a5469c733af3d7'
FULL_SHA = '9ebd932ebdc0dfba10f12b4d6d5ddd988be7d2af067650eab91fb4f653b8286f'
EL_SHA = '21c9cf0206407bd94883eab97e1061e806d70fa71ed75e16cf2464e9082bbaea'
SAMPLE = qualification.source.OUT / 'gap84-div32-old-image-20261006-01/code.vdb'
ADMITTED = qualification.source.OUT / 'gap84-offline-admitted-691-20261006-01'
EXTRA = {
    ADMITTED / 'status.json': '0088a5d393b15595574575b470b419f806aeba118289e9e3c573557899e70b3e',
    ADMITTED / 'scalar-comparison.json': '850de931a5f8f93d0073ff07f6d46cf1d946d123fd0718bf19c7a716613aff83',
    ADMITTED / 'vector-comparison.json': '0fdf2cf0cf16a88365265e71c0ab6d2e081f1b9f38245c5c1f5cfba8a1f33b5c',
    ADMITTED / 'evidence-pins.json': '1a77cca20c7172ffcdd239f5f5d6bd4608af699d89f5a46304cdf3b066fbbd4c',
    SAMPLE.parent / 'simulation-status.json': 'b26754171089c271d62a0effd83b640a80164de655ec01a31da0524eb30528c9',
    qualification.source.OUT / 'repaired-aligned-build-20260930-01/build-tool-pins.json':
        '7dc416fdf4098e3a64739aacabc0edc89d232697173f20dbe97b3c3b0ae576da',
    qualification.source.OUT / 'repaired-aligned-build-20260930-01/compile.command.json':
        '30cdd93809c183f5004767d6190ca33d1d78aed68e73dcf42d6fef793269cbb1',
    qualification.source.OUT / 'repaired-aligned-build-20260930-01/build-image.json':
        '0e6fc4e78818cc97b24c1a4f3c0860fb0d60379de39db5931ad5d00dca472894',
}


def sample_gate(status, scalar, vector, simulation):
    need(status['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY' and status['new_passed'] == 1,
         'One existing admitted PASS, not preparation status')
    need(type(simulation['returncode']) is int and simulation['returncode'] == 0
         and simulation['status'] == 'SIMULATION_EXITED_NOT_ADMITTED', 'Real sample exited0')
    need(scalar['status'] == 'TERMINAL_TOHOST_MATCH' and scalar['mismatch'] is None and
         scalar['terminal_tohost']['write_value'] == '0x1' and scalar['matched_instructions'] == 55987,
         'Exact historical scalar terminal qualification')
    need(vector['status'] == 'PASS' and vector['first_mismatch'] is None and
         vector['compared_instructions'] == 225 and vector['compared_bytes'] == 38760 and
         vector['skipped_unknown_bytes'] == 0 and vector['non_bit_exact_instructions'] == 0 and
         not vector['incomplete_requests'] and not vector['unretired_requests'], 'Exact existing vector PASS')


def source_gate(c):
    need(c['output'] == str(OUT) and c['sample'] == str(SAMPLE) and c['test'] ==
         str(SAMPLE.with_suffix('') / 'vgap84_div32'), 'One exact admitted representative sample only')
    need(c['pins'][str(qualification.FULL / 'config.json')] == FULL_SHA and
         c['population_evidence']['current_EL'] == str(qualification.FULL / 'combined.el') and
         c['population_evidence']['current_EL_sha256'] == EL_SHA and
         c['pins'][str(qualification.FULL / 'combined.el')] == EL_SHA and
         c['population_evidence']['manifest_sha256'] == qualification.BASE_SHA,
         'Fixed775 config/EL/admission digests, no dynamic wrong-file self-seal')
    need(c['source_review_sha256'] == qualification.REVIEW_SHA and
         c['population_evidence']['target_missing_positions'] == list(range(3422, 3934)) and
         c['population_evidence']['target_missing_slots'] == 512 and
         c['population_evidence']['target_observed_hit_slots'] == 0 and not c['initial_X_excluded'],
         'Exact512 source-bound bits, no observed/startup activity exclusion')


def pass_evidence():
    life.check({str(p): sha for p, sha in EXTRA.items()})
    status, scalar, vector = (json.loads((ADMITTED / n).read_bytes()) for n in
                              ('status.json', 'scalar-comparison.json', 'vector-comparison.json'))
    simulation = json.loads((SAMPLE.parent / 'simulation-status.json').read_bytes())
    sample_gate(status, scalar, vector, simulation)
    old = json.loads((ADMITTED / 'evidence-pins.json').read_bytes())
    chosen = {p: sha for p, sha in old.items() if p.startswith(str(SAMPLE) + '/') or
              p in (str(SAMPLE.parent / 'manifest.json'), str(SAMPLE.parent / 'simulation-status.json'),
                    str(SAMPLE.parent / 'commit_trace.csv'), str(SAMPLE.parent / 'vector_trace.csv'))}
    need(chosen and any(p.endswith('tgl.verilog.data.xml') for p in chosen), 'Historical PASS tied to actual VDB')
    life.check(chosen)
    return chosen, dict(status=status['status'], scalar_instructions=scalar['matched_instructions'],
        vector_instructions=vector['compared_instructions'], vector_bytes=vector['compared_bytes'],
        historical_unobservable_instructions=vector['unobservable_instructions'],
        historical_policy_unchanged=True, sample=str(SAMPLE))


def terminal_gate(terminal, config):
    need(type(terminal.get('returncode')) is int and terminal['returncode'] == 0,
         'Native terminal returncode must be integer0, never bool/float/string')
    need(type(terminal.get('timeout')) is bool and terminal['timeout'] is False,
         'Native timeout must be exact boolFalse')
    actual = terminal.get('actual_dve')
    need(type(actual) is list and len(actual) == 1, 'One actual native executable')
    identity = actual[0]
    need(type(identity.get('pid')) is int and identity['pid'] > 0 and
         identity.get('exe') == config['identity']['executable'] and identity.get('cwd') == str(OUT)
         and isinstance(identity.get('cgroup'), str) and identity['cgroup'], 'Exact actual PID/exe/cwd/cgroup')


def load_launch(out, native_seal, manifest_path, launch_seal):
    need(out == OUT and native_seal == NATIVE_SHA, 'Frozen native configuration only')
    qualification.verify(out, native_seal)
    c = life.read_bound(out / 'config.json', native_seal); source_gate(c)
    manifest = life.read_bound(manifest_path, launch_seal)
    need(manifest['schema'] == 'MASKU_PARENT_ONLY_SINGLE900S_LAUNCH_V1' and
         manifest['native_config_sha256'] == NATIVE_SHA and manifest['output'] == str(OUT) and
         manifest['manifest_path'] == str(manifest_path) and manifest['timeout_seconds'] == 900 and
         manifest['automatic_retry'] is False and manifest['population_application'] is False,
         'Exact separate launcher contract')
    life.check(manifest['pins']); host.tools.revalidate(manifest['identity'])
    _, evidence = pass_evidence()
    need(evidence == manifest['already_PASS_sample'], 'Exact existing PASS evidence')
    return dict(c, identity=manifest['identity'], pins=life.merge_pins(c['pins'], manifest['pins']))


def strict_inspect(out, native_seal, manifest_path, launch_seal):
    c = load_launch(out, native_seal, manifest_path, launch_seal)
    terminal_gate(json.loads((out / 'terminal.json').read_bytes()), c)
    # The sealed inspector still performs all original source, EL, inventory and
    # five-stage gates. This wrapper only adds stronger terminal/launch binding.
    qualification.inspect(out, native_seal)
    receipt = dict(status='MASKU_PARENT_ONLY_STRICT_NATIVE_QUALIFIED_NOT_APPLIED',
        launch_manifest_sha256=launch_seal, native_config_sha256=native_seal,
        native_result_sha256=life.digest(out / 'capture-result.json'),
        terminal_sha256=life.digest(out / 'terminal.json'), exact_integer_terminal0=True,
        population_application=False, official_percentage=None)
    path = manifest_path.parent / 'strict-inspection-receipt.json'
    if path.exists():
        need(json.loads(path.read_bytes()) == receipt, 'Existing strict receipt differs')
    else:
        life.save(path, receipt)


def worker(manifest_path, launch_seal):
    code = inspect.getsource(host.run)
    header = "c = life.read_bound(out / 'config.json', seal); contract(c); life.check(c['pins']); tools.revalidate(c['identity'])"
    env = 'CVA6_PARENT_RVFI457_SEAL=seal'
    popen = 'process = subprocess.Popen(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)'
    wait = "process.wait(timeout=c['timeout_seconds'])"
    need(code.count(header) == code.count(env) == code.count(popen) == code.count(wait) == 1,
         'Exact mature host runner adapter anchors')
    code = code.replace(header, 'c = load_launch(out, seal)').replace(env, 'MASKU_PARENT_ONLY_SEAL=seal')
    code = code.replace(popen, "deadline = time.monotonic() + c['timeout_seconds']\n        " + popen)
    code = code.replace(wait, 'process.wait(timeout=max(0, deadline - time.monotonic()))')
    namespace = dict(vars(host), ENTRY=qualification.ENTRY,
        load_launch=lambda out, seal: load_launch(out, seal, manifest_path, launch_seal),
        verify=lambda out, seal: strict_inspect(out, seal, manifest_path, launch_seal))
    exec(compile(code, __file__ + ':private-host-adapter', 'exec'), namespace)
    return namespace['run']


def prepare(directory):
    need(directory.parent == qualification.source.OUT and not directory.exists(), 'Fresh separate launcher directory')
    qualification.verify(OUT, NATIVE_SHA)
    c = life.read_bound(OUT / 'config.json', NATIVE_SHA); source_gate(c)
    chosen, evidence = pass_evidence()
    identity = host.tools.prepare('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/dve', '/usr/bin/xvfb-run')
    pins = life.merge_pins(c['pins'], chosen)
    pins.update({str(p): sha for p, sha in EXTRA.items()})
    pins[str(OUT / 'config.json')] = NATIVE_SHA
    pins.update({f['path']: f['sha256'] for f in identity['files']})
    for module in list(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path and Path(path).suffix == '.py' and Path(path).resolve().parent == qualification.HERE:
            pins[str(Path(path).resolve())] = life.digest(path)
    test = Path(__file__).with_name('test_run_masku_parent_bit_enable_native775.py')
    pins[str(test)] = life.digest(test)
    manifest_path = directory / 'launch-manifest.json'
    result = dict(schema='MASKU_PARENT_ONLY_SINGLE900S_LAUNCH_V1',
        status='SEALED_LAUNCH_PREPARED_NOT_AUTHORIZED_NOT_STARTED', manifest_path=str(manifest_path),
        output=str(OUT), native_config_sha256=NATIVE_SHA, identity=identity, pins=pins,
        timeout_seconds=900, automatic_retry=False, population_application=False,
        already_PASS_sample=evidence, full775_config_sha256=FULL_SHA, full775_EL_sha256=EL_SHA,
        parent_review_required=True, EDA_launched=False,
        mutable_launcher_logs='service.log/worker.log are excluded from original native result pins; terminal/captures remain immutable')
    worker(manifest_path, 'STATIC_ONLY')
    life.check(pins); directory.mkdir(); life.save(manifest_path, result)
    print(json.dumps(dict(manifest=str(manifest_path), seal=life.digest(manifest_path), status=result['status'])))


def run(manifest_path, launch_seal, parent_reviewed_seal):
    need(launch_seal == parent_reviewed_seal, 'Parent-reviewed exact launch manifest required; no automatic launch')
    load_launch(OUT, NATIVE_SHA, manifest_path, launch_seal)
    need(not any((OUT / name).exists() for name in ('execution.json', 'terminal.json', 'launcher.log',
             'live-identity.json', 'capture-result.json', 'qualification-reject.json', 'error.txt')),
         'One fresh execution only; all previous evidence preserved, no retries')
    worker(manifest_path, launch_seal)(OUT, NATIVE_SHA)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify', 'run', 'inspect'))
    parser.add_argument('--directory', type=Path); parser.add_argument('--manifest', type=Path)
    parser.add_argument('--seal'); parser.add_argument('--parent-reviewed-seal')
    args = parser.parse_args()
    if args.mode == 'prepare':
        need(args.directory, 'Fresh launcher preparation directory'); prepare(args.directory.resolve())
    else:
        need(args.manifest and args.seal, 'Exact launcher manifest/seal required')
        path = args.manifest.resolve()
        if args.mode == 'run': run(path, args.seal, args.parent_reviewed_seal)
        elif args.mode == 'inspect': strict_inspect(OUT, NATIVE_SHA, path, args.seal)
        else:
            load_launch(OUT, NATIVE_SHA, path, args.seal)
            print('MASKU_PARENT_ONLY_LAUNCH_MANIFEST_VERIFY_PASS_NOT_STARTED')
