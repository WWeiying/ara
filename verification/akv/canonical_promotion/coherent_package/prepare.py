#!/usr/bin/env python3
"""Compose accepted proposals in temporary fixtures, never apply to canonical."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
PROMOTION = HERE.parent
ROOT = PROMOTION.parents[2]
RECEIPTS = {
    'plan.json': '3d8033452074d6c4ec147e9797d1d324f451b7c1267cf82e58ca52963f0befc1',
    'standalone_package/manifest.json': '10263fd6ad500a1d87370097dfcea36c7ab987d23cc9cbf3909ef8abc690db08',
    'physical_flow_compat_v2/prospective-02/manifest.json': '5d9757c96ce212aee2550d9d5dce8206afbf37e8458313a9f2546b091ef69a88',
    'wrapper-elaboration.json': 'b67289e23ec5366cd3c19ff91c5fd45bd4c21ede5b2353d4c9547585938c8391',
}
WRAPPER = 'verification/akv/synthesis/akv_engine_synth_wrapper.sv'
HOST_SUITES = (
    ('physical_flow_compat_v2', 'test_compat.py', 46),
    ('', 'test_standalone_makefiles.py', 9),
    ('', 'test_measurement_wrapper.py', 5),
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(path):
    return sha(Path(path).read_bytes())


def target(name):
    p = Path(name)
    require(not p.is_absolute() and p.as_posix() == name and
            '..' not in p.parts and name not in ('', '.'), 'Unsafe target: ' + name)
    return name


class Inputs:
    def __init__(self):
        self.pins = {}

    def bind(self, path, expected=None):
        path = Path(path).absolute()
        data = path.read_bytes()
        observed = sha(data)
        require(expected is None or observed == expected, 'Input drift: ' + str(path))
        require(str(path) not in self.pins or self.pins[str(path)] == observed,
                'Conflicting input identity: ' + str(path))
        self.pins[str(path)] = observed
        return data

    def mapping(self, values):
        for path, expected in values.items():
            self.bind(path, expected)

    def verify(self):
        for path, expected in self.pins.items():
            require(digest(path) == expected, 'Post-input drift: ' + path)


def collect():
    inputs = Inputs()
    receipts = {name: json.loads(inputs.bind(PROMOTION / name, expected))
                for name, expected in RECEIPTS.items()}
    rtl = receipts['plan.json']
    standalone = receipts['standalone_package/manifest.json']
    physical = receipts['physical_flow_compat_v2/prospective-02/manifest.json']
    wrapper = receipts['wrapper-elaboration.json']
    require(rtl['production_promoted'] is False and standalone['production_promoted'] is False
            and physical['state'] == 'STATIC_PHYSICAL_FLOW_COMPATIBILITY_V2_NOT_APPLIED'
            and wrapper['state'] == 'VCS_ELABORATION_ONLY_PASS', 'Wrong proposal state')
    inputs.bind(Path(rtl['snapshot']) / 'manifest.json', rtl['snapshot_manifest_sha256'])
    before, modes, expected, sources, steps = {}, {}, {}, {}, []

    def initial(name, h):
        target(name)
        require(name not in before, 'Duplicate initial target: ' + name)
        path = ROOT / name
        if h is None:
            require(not path.exists() and not path.is_symlink(), 'Added target already exists: ' + name)
            before[name] = None
            modes[name] = 0o644
        else:
            require(not path.is_symlink(), 'Canonical target symlink: ' + name)
            before[name] = inputs.bind(path, h)
            modes[name] = path.stat().st_mode & 0o777

    def step(name, patch_path, patch_hash, after):
        require(after and all(target(n) == n for n in after), 'Empty/unsafe patch scope')
        steps.append(dict(name=name, patch=inputs.bind(patch_path, patch_hash),
                          input=str(patch_path), after=dict(after)))
        expected.update(after)

    for row in rtl['files']:
        name = row['target']
        initial(name, row['before_sha256'])
        if row['source'] is not None:
            data = inputs.bind(row['source'], row['source_sha256'])
            require(sha(data) == row['after_sha256'], 'RTL source/after mismatch')
            sources[name] = row['source']
        else:
            require(name == 'Bender.yml', 'Unexpected generated RTL target')
            sources[name] = str(PROMOTION / 'shared_resources.patch')
    step('accepted_shared_resources', PROMOTION / 'shared_resources.patch', rtl['patch_sha256'],
         {r['target']: r['after_sha256'] for r in rtl['files']})

    for report, directory, patch_name, label in (
            (standalone, PROMOTION / 'standalone_package', 'standalone_makefiles.patch', 'standalone'),
            (physical, PROMOTION / 'physical_flow_compat_v2/prospective-02', 'physical_flow.patch', 'physical')):
        inputs.mapping(report['helper_pins'])
        inputs.mapping(report['inputs'])
        for name, h in report['after'].items():
            initial(name, report['inputs'][str(ROOT / name)])
            inputs.bind(directory / name, h)
            sources[name] = str(directory / name)
        step(label, directory / patch_name, report['patch_sha256'], report['after'])

    caller = physical['standalone_caller']
    name = target(caller['target'])
    require(name == 'verification/akv/Makefile' and expected[name] == caller['before_sha256'],
            'Standalone caller stage not bound to prior stage')
    require(caller['input'] == sources[name], 'Wrong caller base path')
    directory = PROMOTION / 'physical_flow_compat_v2/prospective-02'
    require(physical['patch_apply_order'] == [steps[i]['input'] for i in (1, 2)] +
            [str(directory / 'standalone_caller.patch')], 'Wrong accepted serial order')
    inputs.bind(directory / name, caller['after_sha256'])
    sources[name] = str(directory / name)
    step('standalone_caller', directory / 'standalone_caller.patch', caller['patch_sha256'],
         {name: caller['after_sha256']})

    inputs.mapping(wrapper['source_and_artifact_sha256'])
    require(wrapper['snapshot_manifest_sha256'] == rtl['snapshot_manifest_sha256'], 'Wrapper snapshot mismatch')
    initial(WRAPPER, wrapper['source_and_artifact_sha256'][str(ROOT / WRAPPER)])
    new_wrapper = inputs.bind(PROMOTION / 'akv_engine_synth_wrapper.sv')
    wrapper_patch = make_patch({WRAPPER: before[WRAPPER]}, {WRAPPER: new_wrapper})
    steps.append(dict(name='accepted_measurement_wrapper', patch=wrapper_patch,
                      input=str(PROMOTION / 'akv_engine_synth_wrapper.sv'),
                      after={WRAPPER: sha(new_wrapper)}))
    expected[WRAPPER] = sha(new_wrapper)
    sources[WRAPPER] = str(PROMOTION / 'akv_engine_synth_wrapper.sv')
    # Existing compatibility generators and host suites remain unchanged inputs.
    for relative in (
            'hardware/scripts/akv/test_collect_synthesis_results.py',
            'hardware/scripts/akv/test_synthesis_preflight.py',
            'verification/qbs/qbs_engine_tb.sv', 'verification/akv/akv_engine_tb.sv',
            'verification/qbs/qbs_context_sram_macro_model.sv',
            'verification/akv/shared_reader_integration/compose_canonical_standalone.py',
            'verification/akv/shared_reader_integration/compose_standalone.py',
            'verification/akv/shared_reader_integration/standalone_port_contracts/manifest.json',
            'verification/akv/shared_reader_integration/standalone_port_contracts/qbs_engine_legacy_header.svh',
            'verification/akv/shared_reader_integration/standalone_port_contracts/akv_engine_legacy_header.svh'):
        inputs.bind(ROOT / relative)
    require(len(before) == len(expected) == 19 and sum(v is None for v in before.values()) == 7,
            'Unexpected coherent package target inventory')
    return inputs, before, modes, expected, sources, steps


def make_patch(before, after):
    require(set(before) == set(after), 'Patch target set differs')
    result = ''
    for name in sorted(before):
        target(name)
        a, b = before[name], after[name]
        require(b is not None and a != b, 'Empty/deleted target: ' + name)
        require(b.endswith(b'\n') and (a is None or a.endswith(b'\n')), 'Unsupported missing final newline')
        result += ''.join(difflib.unified_diff(
            [] if a is None else a.decode().splitlines(keepends=True),
            b.decode().splitlines(keepends=True),
            fromfile='/dev/null' if a is None else 'a/' + name, tofile='b/' + name))
    return result.encode()


def tree(directory):
    files = list(directory.rglob('*'))
    require(not any(p.is_symlink() for p in files), 'Symlink in temporary fixture')
    return {p.relative_to(directory).as_posix(): p.read_bytes() for p in files if p.is_file()}


def matches(directory, expected):
    actual = {name: sha(data) for name, data in tree(directory).items()}
    require(actual == expected, 'Temporary target set/bytes differ: ' + str(sorted(set(actual) ^ set(expected))))


def host_env():
    return dict(PATH='/usr/bin:/bin', HOME='/nonexistent', LC_ALL='C', PYTHONDONTWRITEBYTECODE='1',
                GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null')


def apply_temp(directory, patch, reverse=False):
    require(directory.resolve() != ROOT and not directory.resolve().is_relative_to(ROOT),
            'Patches may only be applied to an independent temporary fixture')
    command = ['/usr/bin/git', 'apply', '--whitespace=nowarn'] + (['-R'] if reverse else [])
    for check in (True, False):
        subprocess.run(command + (['--check'] if check else []), input=patch, cwd=directory,
                       env=host_env(), capture_output=True, check=True, timeout=30)


def exercise(before, modes, expected, steps):
    original = {n: sha(v) for n, v in before.items() if v is not None}
    with tempfile.TemporaryDirectory(prefix='coherent-review-', dir='/tmp') as tmp:
        directory = Path(tmp)
        for name, data in before.items():
            if data is not None:
                path = directory / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                path.chmod(modes[name])
        current, stage_results = dict(original), []
        for stage in steps:
            pre = dict(current)
            apply_temp(directory, stage['patch'])
            current.update(stage['after'])
            matches(directory, current)
            require({n for n in current if current[n] != pre.get(n)} == set(stage['after']),
                    'Declared stage has unchanged targets')
            stage_results.append(dict(name=stage['name'], input=stage['input'],
                                      patch_sha256=sha(stage['patch']), after=stage['after']))
        matches(directory, expected)
        final = tree(directory)
        for stage in reversed(steps):
            apply_temp(directory, stage['patch'], reverse=True)
        matches(directory, original)
        aggregate = make_patch(before, final)
        apply_temp(directory, aggregate)
        matches(directory, expected)
        for name, mode in modes.items():
            require(bool((directory / name).stat().st_mode & 0o111) == bool(mode & 0o111),
                    'Git executable bit changed: ' + name)
        apply_temp(directory, aggregate, reverse=True)
        matches(directory, original)
    return aggregate, stage_results


def run_suites(output):
    records = []
    for index, (directory, pattern, count) in enumerate(HOST_SUITES):
        command = [sys.executable, '-B', '-m', 'unittest', 'discover', '-s',
                   str(PROMOTION / directory), '-p', pattern]
        result = subprocess.run(command, cwd=ROOT, env=host_env(), capture_output=True, timeout=120)
        log = result.stdout + result.stderr
        path = output / f'host-suite-{index}.log'
        path.write_bytes(log)
        require(result.returncode == 0 and f'Ran {count} tests in '.encode() in log and log.rstrip().endswith(b'OK'),
                'Accepted host suite failed: ' + str(path))
        records.append(dict(command=command, exit_code=0, tests=count, log=path.name, sha256=sha(log)))
    return records


def prepare(output):
    output = output.resolve()
    require(output.is_relative_to(HERE) and output != HERE and not output.exists(),
            'Use fresh output beneath coherent_package only')
    inputs, before, modes, expected, sources, steps = collect()
    for path in HERE.iterdir():
        if path.is_file():
            inputs.bind(path)
    for path in (Path(sys.executable).resolve(), Path('/usr/bin/git'), Path('/usr/bin/make')):
        inputs.bind(path)
    inputs.verify()
    output.mkdir()
    tests = run_suites(output)
    aggregate, stages = exercise(before, modes, expected, steps)
    inputs.verify()
    for name, data in before.items():
        p = ROOT / name
        require((not p.exists() and not p.is_symlink()) if data is None else p.read_bytes() == data,
                'Canonical target changed during review: ' + name)
    (output / 'coherent.patch').write_bytes(aggregate)
    plan = dict(schema='coherent_resource_package_review_v1', state='PREPARED_NOT_PROMOTED',
                production_promoted=False, application_authorized=False,
                compiler_invoked=False, simulator_invoked=False, bender_invoked=False, ppa_measured=False,
                stages=stages, input_pins=inputs.pins,
                files=[dict(target=n, before_sha256=None if before[n] is None else sha(before[n]),
                            after_sha256=expected[n], source=sources[n], mode=oct(modes[n]))
                       for n in sorted(before)],
                target_count=19, added_count=7, replaced_count=12,
                serial_exact_after=True, serial_reverse_exact=True,
                aggregate_exact_after=True, aggregate_reverse_exact=True,
                permissions_scope='Source permissions inventoried; Git executable bit checked, not local group/other permission restoration',
                canonical_unchanged=True, host_tests=tests,
                patch_sha256=sha(aggregate),
                remaining_barriers=['Parent acceptance of held-AR/ordinary regression evidence',
                                    'All live source/include pin consumers terminal and audited',
                                    'Explicit canonical promotion authorization',
                                    'Actual promoted canonical graph verification; not performed here'])
    data = (json.dumps(plan, indent=2, sort_keys=True) + '\n').encode()
    (output / 'plan.json').write_bytes(data)
    (output / 'plan.sha256').write_text(sha(data) + '  plan.json\n')
    return plan


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = prepare(args.output)
    print(report['state'], 'targets=' + str(report['target_count']))
