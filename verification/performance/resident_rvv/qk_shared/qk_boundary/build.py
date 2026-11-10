#!/usr/bin/env python3
"""Build architectural QK firmware and independent vectors, never starts EDA."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

sys.dont_write_bytecode = True
import cases
from generate import HERE, ROOT, OUT, generate, load, need, sha, verify
import elf as elf_reader

ORIGINAL = OUT / 'resident_pv_soc_boundary_build_20261109_02'
ARCHIVE = OUT / 'akv_pair_integration_build_20261107_01/inputs/sdk-auto.tar'
HELPER = ROOT / 'software/akv/experimental/resident_attention/qk.S'
CC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
SDK = 'b7c9e6c3c1f8c5e469c130f46ec5bbfaf37a55d1'
OWN = ('cases.py', 'generate.py', 'elf.py', 'build.py', 'main.c', 'issue.S',
       'check.py', 'run.py', 'test_boundary.py', 'README.md')
EXTERNAL = {
    ORIGINAL / 'build.json': '7a6ba64e77c7fa4d6ce52602d992484d83c8b844d631dfd4cd9f2d8c41fb751c',
    ARCHIVE: '4e8f357070fdacd739fbace2fd3347106e5d5afcd278c6380b27624f61a06c72',
    HELPER: '3def49b4e6a76d32c178363a9ddd31f092a6158253844b771efef13d8f62056f',
    ORIGINAL / 'inputs/soc_boundary/trap.S': 'd6b2c83ad6eb2fbac11e9083da8e148feb7d7505cfbfe2dca5be41e8e29296ee',
}


def save(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')


def build(out):
    need(out.parent == OUT and not out.exists(), 'Use unique direct signoff output')
    verify(EXTERNAL)
    out.mkdir()
    report = dict(state='FAIL', execution='NOT_RUN', eda_started=False, hardware_acceptance=False)
    commands = []
    pins = {str(p): v for p, v in EXTERNAL.items()}
    try:
        inputs = out / 'inputs'
        inputs.mkdir()
        shutil.copyfile(ARCHIVE, inputs / 'sdk-auto.tar')
        with tarfile.open(ARCHIVE) as tar:
            need(all((m.isdir() or m.isfile()) and not Path(m.name).is_absolute() and
                     '..' not in Path(m.name).parts for m in tar.getmembers()), 'Unsafe SDK archive')
            tar.extractall(inputs, filter='data')
        local = inputs / 'qk_boundary'
        local.mkdir()
        for name in OWN:
            p = HERE / name
            pins[str(p)] = sha(p)
            shutil.copyfile(p, local / name)
        shutil.copyfile(HELPER, inputs / 'resident_qk.S')
        for name, source in (('trap.S', ORIGINAL / 'inputs/soc_boundary/trap.S'),
                             ('compat.c', ORIGINAL / 'inputs/soc_boundary/compat.c'),
                             ('link.ld', ORIGINAL / 'inputs/link.ld')):
            old = json.loads((ORIGINAL / 'build.json').read_text())
            need(sha(source) == old['artifacts'][str(source)], 'Original frozen source drift')
            pins[str(source)] = sha(source)
            shutil.copyfile(source, inputs / name)
        vectors = generate(out / 'vectors')
        pins.update(vectors['source_pins'])

        def run(label, argv):
            argv = list(map(str, argv))
            proc = subprocess.run(argv, cwd=out, text=True, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, timeout=180,
                                  env=dict(PATH='/usr/bin:/bin', HOME='/home/wangwy', LC_ALL='C'))
            (out / (label + '.log')).write_text(proc.stdout)
            commands.append(dict(label=label, argv=argv, returncode=proc.returncode))
            save(out / 'commands.json', commands)
            need(proc.returncode == 0, label + ' failed: ' + proc.stdout[-3000:])
            return proc.stdout

        flags = ['-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-mcmodel=medany', '-mno-relax',
                 '-O2', '-fno-fast-math', '-ffp-contract=off', '-fno-tree-vectorize', '-ffreestanding',
                 '-fno-builtin', '-fno-tree-loop-distribute-patterns', '-ffunction-sections', '-fdata-sections',
                 '-std=gnu11', '-Wall', '-Wextra', '-DNR_LANES=4', '-DVLEN=1024',
                 '-DPRINTF_DISABLE_SUPPORT_FLOAT', '-I' + str(inputs / 'apps/common'),
                 '-I' + str(inputs / 'software/akv/include'), '-I' + str(out / 'vectors')]
        common = inputs / 'apps/common'
        sources = [local / 'main.c', local / 'issue.S', inputs / 'resident_qk.S', inputs / 'trap.S',
                   inputs / 'compat.c', *(common / n for n in
                     ('crt0.S', 'printf.c', 'string.c', 'serial.c', 'util.c', 'print_trap_cause.c'))]
        objects = []
        for i, src in enumerate(sources):
            obj = out / (f'{i:02d}_' + src.stem + '.o')
            run('compile-' + obj.stem, [CC, *flags, '-MD', '-MF', obj.with_suffix('.d'), '-c', src, '-o', obj])
            objects.append(obj)
        binary = out / 'resident_qk_boundary.elf'
        run('link', [CC, *flags[:4], '-static', '-nostdlib', '-nostartfiles', *objects,
                     '-Wl,--gc-sections', '-Wl,-Map=' + str(out / 'link.map'), '-T', inputs / 'link.ld',
                     '-Wl,--start-group', '-lc', '-lgcc', '-lnosys', '-Wl,--end-group', '-o', binary])
        prefix = str(CC).removesuffix('gcc')
        run('disassembly', [prefix + 'objdump', '-d', '-M', 'no-aliases,numeric', binary])
        c = elf_reader.contract(binary.read_bytes())
        need(all(c['words'][elf_reader.pc(c, name)] == word for name, word in cases.WORDS.items()), 'QK PC/encoding drift')
        lo, hi = elf_reader.extent(c, 'akv_experimental_resident_qk')
        need(sum(c['words'][p] == cases.QK for p in range(lo, hi, 4)) == 1, 'Parent helper not linked exactly')
        for name in ('boundary_trap', 'qk_issue', 'qk_pv_once'):
            elf_reader.extent(c, name)
        run('host-tests', [sys.executable, '-B', local / 'test_boundary.py', '--build', out])
        for tool in (CC, Path(prefix + 'objdump'), Path(sys.executable).resolve()):
            pins[str(tool)] = sha(tool)
        for tool in ('cc1', 'as', 'ld'):
            p = Path(run('locate-' + tool, [CC, '-print-prog-name=' + tool]).strip()).resolve()
            pins[str(p)] = sha(p)
        for library in ('libc.a', 'libgcc.a', 'libnosys.a'):
            p = Path(run('locate-' + library, [CC, *flags[:2], '-print-file-name=' + library]).strip()).resolve()
            pins[str(p)] = sha(p)
        for dep in out.glob('*.d'):
            names = dep.read_text().replace('\\\n', ' ').split(':', 1)[1].split()
            for name in names:
                p = Path(name).resolve()
                need(p.is_relative_to(inputs) or p.is_relative_to(out / 'vectors') or
                     p.is_relative_to(CC.parents[1]), 'Unsealed compiler include: ' + name)
                pins[str(p)] = sha(p)
        pins.update({str(p): sha(p) for p in (*inputs.rglob('*'), *(out / 'vectors').rglob('*')) if p.is_file()})
        verify(pins)
        save(out / 'source-pins.json', pins)
        report.update(state='QK_BOUNDARY_SOFTWARE_BUILT_NOT_EXECUTED', sdk_commit=SDK,
                      elf=str(binary), elf_sha256=sha(binary), scenarios=23, direct_attempts=35,
                      successful_qk=24, rejected_qk=12, helper_calls=1, pv_calls=2,
                      source_pins_sha256=sha(out / 'source-pins.json'), post_pins_match=True)
    except Exception as exc:
        report['error'] = repr(exc)
    report['artifacts'] = {str(p): sha(p) for p in out.rglob('*') if p.is_file()}
    save(out / 'build.json', report)
    need(report['state'] != 'FAIL', 'Build failed, preserved ' + str(out))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = build(args.output.resolve())
    print(json.dumps({k: v for k, v in result.items() if k != 'artifacts'}, sort_keys=True))
