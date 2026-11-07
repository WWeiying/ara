#!/usr/bin/env python3
"""Prepare the b7c9e6c3c AUTO/fallback boundary ELF only after owner seal-ready."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
SEALED = {
    'boundary/build.py': 'e9811405b436ddd7626762790e9b4f7f7342c60bec560da93ebbeaa925f2a0ff',
    'boundary/main.c': 'fbce019455cb00036acadba57d08a75174623435e5fca19df6c1cddd88571e06',
    'boundary/check.py': '321c6bbe98faa90f1853e32b90442761f34f4d8790491994b85038067e166849',
    'boundary/test_boundary.py': '25ff570dd3cf570cc47a56a3fc8ba9f1937e58327ef04e7594f01c4aeba6fa7a',
    'boundary/check_successor.py': '20bb73635f5cdd7f9d49553030f1502c82d8f485bd681b092ba91c7c92585d8c',
    'run.py': '689490ca5c5bc844a9d0ce9f3fe3467353df558d876c73e00468840ef9bd793c',
}


def load(path, name, expected=None):
    if expected is not None and hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
        raise ValueError('Sealed helper changed: ' + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


for _name, _digest in SEALED.items():
    if hashlib.sha256((PARENT / _name).read_bytes()).hexdigest() != _digest:
        raise ValueError('Sealed helper changed: ' + _name)
old = load(PARENT / 'boundary/build.py', 'integration_boundary_old_build')
ROOT, OUT, CC, HOST_CC, GIT = old.ROOT, old.OUT, old.CC, old.HOST_CC, old.GIT
require, sha, save, read_json = old.require, old.sha, old.save, old.read_json
SDK_COMMIT = 'b7c9e6c3c1f8c5e469c130f46ec5bbfaf37a55d1'
SDK_TREE = '22428696b7475eda1936be8285a569ea7780503a'
ARCHIVE_SHA = '50867374c105b4785b077f7ffb5e1c1e7c734711233826869a3f989e6332bfbf'
SDK_DELTA = {
    'software/akv/experimental/paired_heads/auto_policy.h':
        'bac8fe0783164d67b52ec50505b998cc444d6f615f869a93bf4d028585f05c51',
    'software/akv/include/akv/akv.h':
        'c69a80175f5d9a441a038f186c2f8fb4e6e3c510dbb3eea014f311dd072b0c04',
    'software/akv/include/akv/akv_features.h':
        '0898c1392d90d33ca12b9c642ede24d1fda9a343f0a1070441799654b72c4e9e',
    'software/akv/src/akv_v2_native_riscv.c':
        '44b02e9a1cfbe2db272d049cc9ff59315e35ac778279c980928cc0b9295d7d29',
}
OWN_FILES = ('build.py', 'main.c', 'check.py', 'test_boundary.py', 'run.py')
WORK = dict(schema='native_auto_boundary_v1', sdk_head=SDK_COMMIT,
    cases=old.CASES, order=['OFF', 'AUTO', 'OFF'], missing_panel_case=3,
    per_call_commands=[197, 84, 197, 774, 373, 774, 137, 137, 137, 386, 386, 386],
    native_commands=3968, raw_custom_allocations=3980, maintenance_groups=6,
    maintenance_allocations=12, info_commands=4)
ELF_NAME = 'akv_pair_integration_boundary.elf'
DEFAULT_OUTPUT = OUT / 'akv_pair_integration_boundary_build_20261107_01'


def helper_pins():
    return {str(PARENT / n): h for n, h in SEALED.items()}


def compile_recipe(output):
    result = old.compile_recipe(output)
    result[0][result[0].index('-c') + 1] = str(HERE / 'main.c')
    return result


def link_recipe(output):
    result = old.link_recipe(output)
    result[-1] = str(Path(output) / ELF_NAME)
    return result


def validate_archives(current, baseline):
    require(hashlib.sha256(current).hexdigest() == ARCHIVE_SHA and
            hashlib.sha256(baseline).hexdigest() == old.ARCHIVE_SHA, 'Exact SDK archive identity')
    new, previous = old.archive_members(current), old.archive_members(baseline)
    changed = {n for n in new.keys() | previous.keys() if new.get(n) != previous.get(n)}
    require(changed == set(SDK_DELTA) and all(hashlib.sha256(new[n]).hexdigest() == h
            for n, h in SDK_DELTA.items()), 'SDK diffset/assembly/common/harness drift')
    require(all(hashlib.sha256(new[n]).hexdigest() == h for n, h in old.LEGACY.items()),
            'Original harness/parser import closure changed')
    return new


def build(output=DEFAULT_OUTPUT, *, seal_ready=False):
    require(seal_ready is True, 'Owner seal-ready is required before crossbuild')
    output = Path(output).resolve()
    require(output.parent == OUT.resolve() and re.fullmatch(
        r'akv_pair_integration_boundary_build_\d{8}_\w+', output.name), 'Output ownership restriction')
    require(not output.exists(), 'Use a fresh output directory')
    require(sha(CC) == old.CC_SHA and sha(HOST_CC) == old.HOST_CC_SHA and sha(GIT) == old.GIT_SHA,
            'Fixed GNU tool identity')
    pins = {**old.validate_data(), **helper_pins(),
            **{str(HERE / n): sha(HERE / n) for n in OWN_FILES}}
    pins.update({str(p.resolve()): sha(p) for p in (CC, HOST_CC, GIT, Path(sys.executable))})
    output.mkdir()
    inputs = output / 'inputs'
    inputs.mkdir()
    (output / 'tmp').mkdir()
    env = dict(PATH='/usr/bin:/bin', HOME=os.environ.get('HOME', '/home/wangwy'), LC_ALL='C',
               TMPDIR=str(output / 'tmp'), PYTHONDONTWRITEBYTECODE='1')
    commands = []

    def run(label, argv, binary=False):
        argv = list(map(str, argv))
        p = subprocess.run(argv, cwd=output, env=env, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=180)
        log = output / (label + '.log')
        log.write_bytes(p.stderr if binary else p.stdout + p.stderr)
        commands.append(dict(label=label, argv=argv, cwd=str(output), env=env,
                             returncode=p.returncode, log=str(log)))
        save(output / 'commands.json', commands)
        require(p.returncode == 0, label + ': ' + log.read_text(errors='replace')[-3000:])
        return p.stdout if binary else p.stdout.decode().strip()

    try:
        for part, tree in (('software/akv', SDK_TREE), ('apps/common', old.COMMON_TREE)):
            require(run('tree-' + Path(part).name, [GIT, '-C', ROOT, 'rev-parse',
                        SDK_COMMIT + ':' + part]) == tree, 'SDK/common tree identity')
        current = run('archive', [GIT, '-C', ROOT, 'archive', SDK_COMMIT, *old.ARCHIVE_PATHS], True)
        baseline = run('baseline-archive', [GIT, '-C', ROOT, 'archive', old.SDK_COMMIT,
                                          *old.ARCHIVE_PATHS], True)
        validate_archives(current, baseline)
        (inputs / 'sdk-b7c9e6c3c.tar').write_bytes(current)
        (inputs / 'baseline-785084122.tar').write_bytes(baseline)
        old.unpack_archive(current, inputs)
        pins.update({str(p): sha(p) for p in inputs.rglob('*') if p.is_file()})
        run('gnu-version', [CC, '--version'])
        run('hosttests', [sys.executable, '-B', HERE / 'test_boundary.py', '-v'])
        (output / 'expected.h').write_text(old.expected_header())
        (output / 'data.S').write_text(old.data_assembly())
        (output / 'link.ld').write_text(old.linker_script(inputs / 'apps/common'))
        for lib in ('libm.a', 'libc.a', 'libgcc.a', 'libnosys.a'):
            p = Path(run('locate-' + lib, [CC, *old.compile_flags(output)[:2],
                                          '-print-file-name=' + lib])).resolve(strict=True)
            pins[str(p)] = sha(p)
        for tool in ('cc1', 'as', 'ld', 'collect2'):
            p = Path(run('locate-' + tool, [CC, '-print-prog-name=' + tool])).resolve(strict=True)
            pins[str(p)] = sha(p)
        for i, argv in enumerate(compile_recipe(output)):
            require(not Path(argv[-1]).exists(), 'Refusing old object')
            run(f'compile-{i:02d}', argv)
        run('link', link_recipe(output))
        elf = output / ELF_NAME
        for tool, args in (('objdump', ['-d']), ('readelf', ['-lW'])):
            p = CC.with_name(CC.name.replace('gcc', tool))
            pins[str(p.resolve())] = sha(p)
            run(tool, [p, *args, elf])
        for dep in output.glob('*.d'):
            for p in old.dependency_inputs(dep):
                require(str(p) not in pins or pins[str(p)] == sha(p), 'Compiler input drift')
                pins[str(p)] = sha(p)
        for name in ('expected.h', 'data.S', 'link.ld'):
            pins[str(output / name)] = sha(output / name)
        old.verify(pins)
        pinfile = output / 'source-pins.json'
        save(pinfile, pins)
        report = dict(schema=1, kind='boundary', workload=WORK, state='BUILT_NOT_EXECUTED',
            execution='NOT_RUN', target_executed=False, rtl_executed=False, performance_measured=False,
            seal_ready=True, post_pins_match=True, elf=str(elf), elf_sha256=sha(elf),
            sdk_head=SDK_COMMIT, sdk_tree=SDK_TREE, common_tree=old.COMMON_TREE, sdk_delta=SDK_DELTA,
            sdk_archive=str(inputs / 'sdk-b7c9e6c3c.tar'), sdk_archive_sha256=ARCHIVE_SHA,
            baseline_archive=str(inputs / 'baseline-785084122.tar'), baseline_archive_sha256=old.ARCHIVE_SHA,
            SDKpins={str(p.relative_to(inputs)): sha(p) for p in (inputs / 'software/akv').rglob('*')
                     if p.is_file()}, sdk_unmodified=True, assembly_unchanged=True, dirty_asm_excluded=True,
            all_runtime_objects_recompiled=True, objects_recompiled=16,
            objects=[c[-1] for c in compile_recipe(output)], compile_commands=str(output / 'commands.json'),
            source_pins=str(pinfile), source_pins_sha256=sha(pinfile), image_contract=old.IMAGE,
            capture=str(old.CAPTURE), payloads=old.PAYLOADS, harness_sha256=old.LEGACY[old.HARNESS],
            environment='Global getenv always NULL; harness-only requested controls route OFF/AUTO/OFF',
            runner=dict(entry=str(HERE / 'run.py'), owner=str(PARENT / 'run.py'),
                        owner_sha256=SEALED['run.py'], kind='boundary'),
            toolchain=dict(target=str(CC), host=str(HOST_CC), zcc=False),
            scope='New SDK functional/path/fallback boundary only; no performance or whole-model claim',
            artifacts={str(p): sha(p) for p in output.rglob('*') if p.is_file()})
        save(output / 'build.json', report)
        checker = load(HERE / 'check.py', 'integration_boundary_postbuild')
        report['elf_link_checks'] = checker.verify_build(output)['elf_link_checks']
        save(output / 'build.json', report)
        return report
    except BaseException as exc:
        save(output / 'build.json', dict(state='FAIL', execution='NOT_RUN', performance_measured=False,
                                       error=repr(exc)))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--seal-ready', action='store_true')
    a = parser.parse_args()
    r = build(a.output, seal_ready=a.seal_ready)
    print(json.dumps({k: r[k] for k in ('state', 'elf', 'elf_sha256', 'sdk_head')}))
