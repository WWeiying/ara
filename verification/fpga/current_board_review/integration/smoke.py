#!/usr/bin/env python3
"""Compile existing RVV/custom smoke software privately with non-ZCC LLVM."""
import argparse
from pathlib import Path
import shutil
import subprocess

from prepare import ROOT, save, sha

RVV = ('vadd', 'vslideup', 'vslidedown', 'vrgather', 'vmseq', 'vfredosum', 'vfwredosum')
CUSTOM = {'qbs_control_smoke': 'QBS control smoke (enabled): PASS',
          'akv_context_smoke': 'AKV context smoke: PASS',
          'qbs_akv_handoff_smoke': 'QBS/AKV handoff smoke: PASS'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source_root = out / 'sources'
    source_root.mkdir()
    llvm = ROOT / 'install/riscv-llvm'
    cc = (llvm / 'bin/clang').resolve(strict=True)
    if any(name in str(cc).lower() for name in ('zcc', 'terapines')):
        raise ValueError('forbidden compiler')
    source_paths = {f'rvv_{name}': Path(f'apps/riscv-tests/isa/rv64uv/{name}.c') for name in RVV}
    source_paths.update({name: Path(f'apps/{name}/main.c') for name in CUSTOM})
    files = {ROOT / p for p in source_paths.values()}
    runtime = ['crt0.S', 'printf.c', 'string.c', 'serial.c', 'util.c', 'print_trap_cause.c']
    files.update(ROOT / 'apps/common' / name for name in [*runtime, 'link_sim_2m.ld'])
    for directory in ('apps/common', 'apps/include', 'apps/riscv-tests/isa/macros'):
        files.update((ROOT / directory).rglob('*.h'))
    before = {str(path): sha(path) for path in files}
    for path in files:
        target = source_root / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        if sha(target) != before[str(path)]:
            raise ValueError('software source changed while copying')
    if before != {str(path): sha(path) for path in files}:
        raise ValueError('software source drift')
    pins = {str(p.relative_to(source_root)): sha(p) for p in source_root.rglob('*') if p.is_file()}
    save(source_root / 'provenance.json', dict(files=pins, original_sources=before,
         scope='unmodified existing normal RVV/custom smoke sources; no Linux boot'))
    flags = ['--target=riscv64-unknown-elf', '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d',
             '-mno-relax', '-mcmodel=medany', '-O3', '-fno-vectorize', '-fno-slp-vectorize',
             '-fno-common', '-fno-builtin-printf', '-ffunction-sections', '-fdata-sections',
             '-DNR_LANES=4', '-DVLEN=1024']
    for directory in ('apps/common', 'apps/include', 'apps/riscv-tests/isa/macros/vector',
                      'apps/riscv-tests/isa/macros/scalar'):
        flags += ['-I' + str(source_root / directory)]
    commands, objects = [], []

    def execute(command):
        commands.append([str(x) for x in command])
        save(out / 'commands.json', commands)
        subprocess.run(command, check=True)

    for name in runtime:
        obj = out / (name + '.o')
        execute([str(cc), *flags, '-c', str(source_root / 'apps/common' / name), '-o', str(obj)])
        objects.append(str(obj))
    programs = {}
    for name, relative in source_paths.items():
        elf = out / (name + '.elf')
        execute([str(cc), *flags, '-fuse-ld=lld', '-nostdlib', '-static',
                 '-Wl,--gc-sections', '-Wl,--build-id=none',
                 '-T', str(source_root / 'apps/common/link_sim_2m.ld'),
                 str(source_root / relative), *objects,
                 '-L' + str(llvm / 'lib/generic'), '-lclang_rt.builtins-riscv64', '-o', str(elf)])
        with (out / (name + '.dis')).open('w') as log:
            subprocess.run([str(llvm / 'bin/llvm-objdump'), '-d', str(elf)], check=True, stdout=log)
        marker = CUSTOM[name] if name in CUSTOM else 'PASSED: ' + str(source_root / relative) + '!'
        programs[name] = dict(path=str(elf), sha256=sha(elf), pass_markers=[marker])
    save(out / 'programs.json', dict(schema_version=1, backend='vcs-soc', programs=programs,
         compiler=dict(path=str(cc), sha256=sha(cc)), prepared=str(source_root),
         provenance_sha256=sha(source_root / 'provenance.json'), vcs_started=False))
    print(f'Compiled {len(programs)} existing smoke programs; no VCS run: {out}')


if __name__ == '__main__':
    main()
