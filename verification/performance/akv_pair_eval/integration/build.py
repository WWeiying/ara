#!/usr/bin/env python3
"""Prepare the new auto-API ELF from sealed primary recipes and a Git archive."""
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PRIMARY = HERE.parent
ROOT = HERE.parents[3]
OUT = ROOT.parent/'ara_dsa_signoff_integration/verification/out'
BASE = OUT/'akv_pair_eval_build_20261107_01'
BASE_MANIFEST_SHA = 'f21f6f0fda31a426ecc595fe2bb96a1442506bdadeaa7aa38730aeb9e351dc04'
BASE_COMMANDS_SHA = '074e7f261a1159502a5978614e2526fdc8c7733e4e52d95ebc67854387b7480d'
SDK_COMMIT = 'b7c9e6c3c1f8c5e469c130f46ec5bbfaf37a55d1'
BASE_SDK = '785084122af984c1dd3fd6318efaf70cdcb017e8'
GIT = Path('/usr/bin/git')
OWN_FILES = ('build.py', 'main.c', 'check.py', 'test_integration.py', 'run.py')
SEALED = {
    'build.py': '85945ecb8e29c3d614460ed244b68e04977f86c7537b282ded6d05057812b1c1',
    'main.c': '2831a828d0389d387cb86eed34f14b592ff8d0b0d32e79f48767dcb1e8cc5da4',
    'check.py': '97dc836ae0782d4a12e51a4e9e5939e5eadf1272e259c0e6da36b2424ac0e3f5',
    'test_eval.py': 'a31c075aeb306b42e463011e6b837235deb601786988ff7f2dec72044a55c117',
    'reference.c': '28b4d63de3f4f2a2819bf1830f289303564a61ac439c2505cb423508541a6c7c',
    'run.py': '689490ca5c5bc844a9d0ce9f3fe3467353df558d876c73e00468840ef9bd793c',
}
SDK_DIFF = {
    'software/akv/include/akv/akv.h': 'M',
    'software/akv/include/akv/akv_features.h': 'M',
    'software/akv/src/akv_v2_native_riscv.c': 'M',
    'software/akv/experimental/paired_heads/auto_policy.h': 'A',
}
SCHEMA = 'akv-pair-native-auto-integration-v1'
ELF_NAME = 'akv_pair_native_auto.elf'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sealed_modules():
    for name, digest in SEALED.items():
        require(sha(PRIMARY/name) == digest, 'Sealed primary helper drift: '+name)
    return (load(PRIMARY/'build.py', 'auto_integration_primary_build'),
            load(PRIMARY/'check.py', 'auto_integration_primary_check'))


def verify(pins):
    require(isinstance(pins, dict) and pins, 'Empty identity inventory')
    for path, digest in pins.items():
        require(Path(path).is_file() and re.fullmatch('[0-9a-f]{64}', digest) and sha(path) == digest,
                'Input/artifact drift: '+path)


def base_inputs():
    old, checker = sealed_modules()
    require(sha(BASE/'build.json') == BASE_MANIFEST_SHA and
            sha(BASE/'commands.json') == BASE_COMMANDS_SHA, 'Not the accepted primary recipe')
    manifest = checker.verify_build(BASE)
    require(manifest['sdk_head'] == BASE_SDK, 'Base SDK mismatch')
    pins = json.loads((BASE/'source-pins.json').read_text())
    for path, digest in manifest['artifacts'].items():
        require(path not in pins or pins[path] == digest, 'Conflicting base identity')
        pins[path] = digest
    # Every original build file is evidence/input, never an object to link again.
    pins.update({str(p): sha(p) for p in BASE.rglob('*') if p.is_file()})
    pins.update({str(PRIMARY/n): h for n, h in SEALED.items()})
    verify(pins)
    return old, checker, manifest, pins


def git(*args):
    return subprocess.check_output([str(GIT), '-C', str(ROOT), *map(str, args)], cwd=ROOT)


def archive_members(raw):
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        result = {}
        for member in tar.getmembers():
            p = Path(member.name)
            require((member.isfile() or member.isdir()) and not p.is_absolute() and
                    '..' not in p.parts, 'Unsafe SDK archive member')
            if member.isfile():
                require(member.name not in result and
                        member.name.startswith(('software/akv/', 'apps/common/')),
                        'Unexpected/duplicate SDK archive member')
                result[member.name] = tar.extractfile(member).read()
    require(result, 'Empty SDK archive')
    return result


def validate_sdk_archive(raw, old_raw):
    members, previous = archive_members(raw), archive_members(old_raw)
    changed = {n: 'A' if n not in previous else 'D' if n not in members else 'M'
               for n in members.keys() | previous.keys() if members.get(n) != previous.get(n)}
    require(changed == SDK_DIFF, 'SDK archive delta must be exactly the four approved files')
    header = members['software/akv/include/akv/akv.h'].decode()
    feature_header = members['software/akv/include/akv/akv_features.h'].decode()
    require(re.search(r'^#define AKV_NATIVE_AUTO_PAIR_POLICY 1$', header, re.M), 'Auto policy macro missing')
    plain = ('akv_status_t akv_attention_execute_v2_native_auto( const akv_device_t *device, '
             'const akv_attention_plan_t *plan, akv_attention_v2_workspace_t *workspace);')
    feature = ('akv_status_t akv_attention_execute_v2_with_features_native_auto( '
               'const akv_device_t *device, const akv_attention_plan_t *plan, '
               'akv_attention_v2_workspace_t *workspace, const akv_attention_features_t *features);')
    require(plain in ' '.join(header.split()) and feature in ' '.join(feature_header.split()),
            'Auto API signature drift')
    return members


def sdk_contract(commit=SDK_COMMIT):
    require(isinstance(commit, str) and re.fullmatch('[0-9a-f]{7,40}', commit), 'Explicit SDK commit required')
    resolved = git('rev-parse', '--verify', commit+'^{commit}').decode().strip()
    git('merge-base', '--is-ancestor', BASE_SDK, resolved)
    diff = {}
    for line in git('diff', '--name-status', '--no-renames', BASE_SDK, resolved,
                    '--', 'software/akv', 'apps/common').decode().splitlines():
        status, path = line.split('\t')
        require(path not in diff, 'Duplicate SDK diff path')
        diff[path] = status
    require(diff == SDK_DIFF, 'SDK Git diff is not the exact four-file delta')
    raw = git('archive', resolved, 'software/akv', 'apps/common')
    members = validate_sdk_archive(raw, (BASE/'inputs/sdk-785084122.tar').read_bytes())
    common = git('rev-parse', resolved+':apps/common').decode().strip()
    old, _ = sealed_modules()
    require(common == old.COMMON_TREE, 'Common runtime changed')
    return dict(sdk_new=resolved, baseSDK=BASE_SDK, sdk_diffset=SDK_DIFF,
                sdk_tree=git('rev-parse', resolved+':software/akv').decode().strip(),
                common_tree=common, sdk_archive_sha256=hashlib.sha256(raw).hexdigest(),
                SDKpins={n: hashlib.sha256(b).hexdigest() for n, b in members.items()
                         if n.startswith('software/akv/')}), raw, members


def target_recipe(output):
    """Rewrite structured argv fields, retaining every accepted codegen flag."""
    output = Path(output).resolve()
    require(sha(BASE/'commands.json') == BASE_COMMANDS_SHA, 'Accepted command recipe drift')
    commands = json.loads((BASE/'commands.json').read_text())
    selected = [c for c in commands if c['label'].startswith('compile-') or
                c['label'] in ('link', 'disassembly', 'segments')]
    require(len(selected) == 19 and sum(c['label'].startswith('compile-') for c in selected) == 16,
            'Incomplete accepted target recipe')

    def source(path):
        path = Path(path)
        if path == PRIMARY/'main.c':
            return HERE/'main.c'
        if path == BASE/'data.S':
            return path
        require(path.is_relative_to(BASE/'inputs'), 'Unexpected accepted source')
        return output/'inputs'/path.relative_to(BASE/'inputs')

    recipe = []
    for command in selected:
        old = command['argv']
        argv, index = [], 0
        while index < len(old):
            token = old[index]
            if token in ('-c', '-o', '-MF'):
                value = Path(old[index+1])
                if token == '-c':
                    value = source(value)
                else:
                    require(value.parent == BASE, 'Unexpected object/dependency/ELF path')
                    value = output/(ELF_NAME if value.suffix == '.elf' else value.name)
                argv += [token, str(value)]
                index += 2
                continue
            if token in ('-I'+str(BASE/'inputs/software/akv/include'), '-I'+str(BASE/'inputs/apps/common')):
                token = '-I'+str(output/Path(token[2:]).relative_to(BASE))
            elif token == '-Wl,-Map='+str(BASE/'link.map'):
                token = '-Wl,-Map='+str(output/'link.map')
            elif Path(token).suffix == '.o':
                require(Path(token).parent == BASE, 'Unexpected link object')
                token = str(output/Path(token).name)
            elif token == str(BASE/'akv_pair_eval.elf'):
                token = str(output/ELF_NAME)
            argv.append(token)
            index += 1
        recipe.append(dict(label=command['label'], argv=argv))
    return recipe


def manifest_fields(output, sdk, base_manifest):
    output = Path(output).resolve()
    recipe = target_recipe(output)
    return dict(schema=SCHEMA, kind='qwen3_abba', state='BUILT_NOT_EXECUTED',
        target_executed=False, rtl_executed=False, performance_measured=False, hardware_changed=False,
        **sdk, sdk_head=sdk['sdk_new'], sdk_unmodified=True, dirty_asm_excluded=True,
        base_build=str(BASE), base_build_sha256=BASE_MANIFEST_SHA,
        base_commands_sha256=BASE_COMMANDS_SHA, all_runtime_objects_recompiled=True,
        objects_recompiled=16, objects=[c['argv'][-1] for c in recipe if c['label'].startswith('compile-')],
        compile_commands=str(output/'commands.json'), elf=str(output/ELF_NAME),
        sdk_archive=str(output/'inputs/sdk-auto.tar'), source_pins=str(output/'source-pins.json'),
        shape=base_manifest['shape'], order=base_manifest['order'], memory_expected=base_manifest['memory_expected'],
        image_contract=base_manifest['image_contract'], data=base_manifest['data'], capture=base_manifest['capture'],
        golden=base_manifest['golden'], toolchain=base_manifest['toolchain'],
        initial_csr=base_manifest['initial_csr'], required_plusargs=base_manifest['required_plusargs'],
        total_roi=base_manifest['total_roi'], instrumentation='Sealed primary caller; SDK shared auto implementation',
        environment=dict(all_names='NULL', baseline='legacy native', candidate='native_auto with cached device'),
        scope='One captured Qwen3 plain F16 group; no feature/Prefill/GGML/default acceptance',
        checker=dict(entry=str(HERE/'check.py'), function='check_run(log_path, build_dir)',
                     required_vector_api='check_vector_workcounts(path, build_dir)',
                     independent_image_and_uvm_required=True))


def build(output, sdk_commit=SDK_COMMIT):
    output = Path(output).resolve()
    require(output.parent == OUT.resolve() and re.fullmatch(r'akv_pair_integration_build_\d{8}_\w+', output.name),
            'Output ownership restriction')
    require(not output.exists(), 'Fresh independent build directory required')
    old, _, base_manifest, pins = base_inputs()
    pins.update({str(HERE/n): sha(HERE/n) for n in OWN_FILES})
    pins[str(GIT.resolve())] = sha(GIT.resolve())
    verify(pins)
    sdk, raw, members = sdk_contract(sdk_commit)
    verify(pins)
    output.mkdir()
    inputs = output/'inputs'
    inputs.mkdir()
    archive = inputs/'sdk-auto.tar'
    archive.write_bytes(raw)
    old.unpack_archive(raw, inputs)
    pins.update({str(inputs/n): hashlib.sha256(b).hexdigest() for n, b in members.items()})
    pins[str(archive)] = sha(archive)
    commands = [dict(label='archive', argv=[str(GIT), '-C', str(ROOT), 'archive', sdk['sdk_new'],
        'software/akv', 'apps/common'], cwd=str(ROOT), returncode=0, log=str(output/'archive.log'),
        output=str(archive))]
    (output/'archive.log').write_text('git archive stdout captured in '+str(archive)+'\n')
    env = dict(PATH='/usr/bin:/bin', HOME=os.environ.get('HOME', '/home/wangwy'),
               LC_ALL='C', PYTHONDONTWRITEBYTECODE='1')

    def run(label, argv):
        verify(pins)
        argv = list(map(str, argv))
        proc = subprocess.run(argv, cwd=output, env=env, capture_output=True, text=True, timeout=180)
        logfile = output/(label+'.log')
        logfile.write_text(proc.stdout+proc.stderr)
        commands.append(dict(label=label, argv=argv, cwd=str(output), returncode=proc.returncode,
                             log=str(logfile), env=env))
        (output/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        require(proc.returncode == 0, label+' failed: '+(proc.stdout+proc.stderr)[-3000:])

    run('hosttests', [sys.executable, '-B', HERE/'test_integration.py', '-v'])
    for command in target_recipe(output):
        if command['label'].startswith('compile-'):
            require(not Path(command['argv'][-1]).exists(), 'Old object reuse forbidden')
        run(command['label'], command['argv'])
    for c in commands:
        if not c['label'].startswith('compile-'):
            continue
        dep = Path(c['argv'][-1]).with_suffix('.d')
        for p in old.dependency_inputs(dep):
            digest = sha(p)
            require(str(p) not in pins or pins[str(p)] == digest, 'Compiler dependency drift')
            pins[str(p)] = digest
    verify(pins)
    pinfile = output/'source-pins.json'
    pinfile.write_text(json.dumps(pins, indent=2, sort_keys=True)+'\n')
    manifest = manifest_fields(output, sdk, base_manifest)
    manifest.update(elf_sha256=sha(output/ELF_NAME), source_pins_sha256=sha(pinfile),
        artifacts={str(p): sha(p) for p in sorted(output.rglob('*')) if p.is_file()})
    (output/'build.json').write_text(json.dumps(manifest, indent=2)+'\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sdk-commit', default=SDK_COMMIT)
    args = parser.parse_args()
    result = build(args.output, args.sdk_commit)
    print(json.dumps({k: result[k] for k in ('state', 'sdk_new', 'baseSDK', 'elf', 'elf_sha256')}))
