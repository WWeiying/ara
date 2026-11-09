#!/usr/bin/env python3
"""GNU software/oracle build only. There is intentionally no simulator action."""
import argparse
import io
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tarfile

sys.dont_write_bytecode = True
from cases import OWN, PV_INSN, QBS_INSN, SCHEMA
from generate import BASE, HERE, OUT, ROOT, generate, load, require, sha, verify

SDK = 'b7c9e6c3c1f8c5e469c130f46ec5bbfaf37a55d1'
SOC = OUT/'resident_pv_soc_build_20261109_03'
CC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
PREFIX = str(CC).removesuffix('gcc')
ENV = dict(PATH='/usr/bin:/bin', HOME='/home/wangwy', LC_ALL='C', PYTHONDONTWRITEBYTECODE='1')


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2)+'\n')


def elf_word(path, address):
    raw = Path(path).read_bytes()
    require(raw[:7] == b'\x7fELF\x02\x01\x01', 'Not ELF64 little-endian')
    hdr = struct.unpack_from('<16sHHIQQQIHHHHHH', raw)
    require(hdr[2] == 243 and hdr[9] == 56, 'Wrong RISC-V ELF/program-header format')
    for i in range(hdr[10]):
        p = struct.unpack_from('<IIQQQQQQ', raw, hdr[5]+i*hdr[9])
        if p[0] == 1 and p[3] <= address < p[3]+p[5]-3:
            return struct.unpack_from('<I', raw, p[2]+address-p[3])[0]
    raise ValueError('Instruction address outside ELF LOAD segment')


def build(output):
    output = Path(output).resolve()
    require(output.parent == OUT and re.fullmatch('resident_pv_soc_boundary_build_[A-Za-z0-9_-]+', output.name)
            and not output.exists(), 'Use a fresh direct signoff boundary-build output')
    output.mkdir()
    report = dict(state='FAIL', execution='NOT_RUN', eda_started=False, hardware_acceptance=False)
    commands = []
    try:
        e = load(HERE.parent/'soc_eval/experiment.py', 'boundary_soc_contract')
        soc, pins = e.checked_soc(SOC)
        meta, sdk_pins = e.baseline()
        require(meta['sdk_new'] == SDK, 'Wrong archived SDK contract')
        e.merge(pins, sdk_pins)
        e.merge(pins, {str(HERE/n): sha(HERE/n) for n in OWN})
        before = dict(pins)
        inputs = output/'inputs'
        inputs.mkdir()
        archive = BASE/'inputs/sdk-auto.tar'
        require(sha(archive) == '4e8f357070fdacd739fbace2fd3347106e5d5afcd278c6380b27624f61a06c72',
                'Wrong sealed SDK/common archive')
        shutil.copyfile(archive, inputs/'sdk-auto.tar')
        with tarfile.open(fileobj=io.BytesIO(archive.read_bytes())) as tar:
            members = tar.getmembers()
            require(all((m.isfile() or m.isdir()) and not Path(m.name).is_absolute() and
                        '..' not in Path(m.name).parts for m in members), 'Unsafe archived SDK')
            tar.extractall(inputs, filter='data')
        owned = inputs/'soc_boundary'
        owned.mkdir()
        for name in OWN:
            shutil.copyfile(HERE/name, owned/name)
        shutil.copyfile(HERE.parent/'pv_prepare/prepare.S', inputs/'prepare.S')
        shutil.copyfile(BASE.parent/'akv_pair_eval_build_20261107_01/link.ld', inputs/'link.ld')
        vectors = generate(output/'vectors')
        e.merge(pins, vectors['source_pins'])
        e.merge(pins, {str(p): sha(p) for p in inputs.rglob('*') if p.is_file()})
        e.merge(pins, {str(p): sha(p) for p in (output/'vectors').iterdir()})

        def run(label, argv, extra_env=None):
            env = dict(ENV, **(extra_env or {}))
            proc = subprocess.run(list(map(str, argv)), cwd=output, env=env, text=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
            log = output/(label+'.log')
            log.write_text(proc.stdout)
            commands.append(dict(label=label, argv=list(map(str, argv)), cwd=str(output),
                                 env=env, returncode=proc.returncode))
            save(output/'commands.json', commands)
            require(proc.returncode == 0, label+' failed: '+proc.stdout[-4000:])
            return proc.stdout

        flags = ['-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-mcmodel=medany', '-mno-relax',
                 '-O2', '-fno-fast-math', '-ffp-contract=off', '-fno-tree-vectorize',
                 '-ffreestanding', '-fno-builtin', '-fno-tree-loop-distribute-patterns',
                 '-ffunction-sections', '-fdata-sections', '-std=gnu11', '-Wall', '-Wextra',
                 '-DNR_LANES=4', '-DVLEN=1024', '-DPRINTF_DISABLE_SUPPORT_FLOAT',
                 '-I'+str(inputs/'software/akv/include'), '-I'+str(inputs/'apps/common'),
                 '-I'+str(output/'vectors')]
        for tool in (CC, Path(PREFIX+'objdump'), Path(PREFIX+'readelf'), Path(PREFIX+'nm'), Path(sys.executable).resolve()):
            pins[str(tool)] = sha(tool)
        for tool in ('cc1', 'as', 'ld'):
            p = Path(run('locate-'+tool, [CC, '-print-prog-name='+tool]).strip()).resolve()
            pins[str(p)] = sha(p)
        for lib in ('libc.a', 'libgcc.a', 'libnosys.a'):
            p = Path(run('locate-'+lib, [CC, *flags[:2], '-print-file-name='+lib]).strip()).resolve()
            pins[str(p)] = sha(p)
        common = inputs/'apps/common'
        sources = [owned/'main.c', owned/'pv.S', owned/'trap.S', owned/'compat.c', inputs/'prepare.S',
                   *[common/n for n in ('crt0.S', 'printf.c', 'string.c', 'serial.c', 'util.c', 'print_trap_cause.c')]]
        objects = []
        for i, src in enumerate(sources):
            obj = output/f'{i:02d}_{src.stem}.o'
            run('compile-'+obj.stem, [CC, *flags, '-MD', '-MF', obj.with_suffix('.d'), '-c', src, '-o', obj])
            objects.append(obj)
        elf = output/'resident_pv_boundary.elf'
        run('link', [CC, *flags[:4], '-static', '-nostdlib', '-nostartfiles', *objects,
                     '-Wl,--gc-sections', '-Wl,-Map='+str(output/'link.map'), '-T', inputs/'link.ld',
                     '-Wl,--start-group', '-lc', '-lgcc', '-lnosys', '-Wl,--end-group', '-o', elf])
        run('disassembly', [PREFIX+'objdump', '-d', '-M', 'no-aliases,numeric', elf])
        run('segments', [PREFIX+'readelf', '-lW', elf])
        symbols = run('symbols', [PREFIX+'nm', '-n', elf])
        names = {parts[2]: int(parts[0], 16) for line in symbols.splitlines()
                 if len(parts := line.split()) == 3 and re.fullmatch('[0-9a-fA-F]+', parts[0])}
        expected = {'boundary_pv_fault_pc': PV_INSN, 'boundary_pv_rd2_pc': 0x0485715b,
                    'boundary_pv_vs2v4_pc': 0x0445705b, 'boundary_pv_alias_pc': 0x0485745b}
        require(all(elf_word(elf, names[n]) == insn for n, insn in expected.items()), 'Wrong dynamic PV instruction word')
        require(all(n in names for n in ('rvtest_init', 'boundary_trap', 'resident_pv_prepare', 'boundary_compat')),
                'Missing real helper/trap/postlude linkage')
        old, _ = e.contract.sealed_modules()
        dep_inputs = set()
        for dep in output.glob('*.d'):
            dep_inputs.update(old.dependency_inputs(dep))
        for path in dep_inputs:
            require(not path.is_relative_to(ROOT/'software') and not path.is_relative_to(ROOT/'apps') and
                    not path.is_relative_to(ROOT/'hardware'), 'Live SDK/common/RTL compiler dependency')
            if str(path) not in pins:
                require(path.is_relative_to(CC.parents[1]), 'Unexpected unpinned compiler dependency: '+str(path))
                pins[str(path)] = sha(path)
        run('host-tests', [sys.executable, '-B', HERE/'test_boundary.py', '-v'],
            {'PV_BOUNDARY_VECTORS': str(output/'vectors/vectors.json'), 'PV_BOUNDARY_BUILD': str(output)})
        verify(before)
        verify(pins)
        post, _ = e.checked_soc(SOC)
        require(post == soc, 'SoC03 changed during GNU build')
        save(output/'source-pins.json', pins)
        artifacts = {str(p): sha(p) for p in output.rglob('*') if p.is_file() and p.name != 'build.json'}
        report.update(state='BOUNDARY_SOFTWARE_BUILT_NOT_EXECUTED', schema=SCHEMA, sdk_commit=SDK,
                      soc_build=str(SOC), configuration=soc['configuration'], image_pins=soc['image_pins'],
                      pv_scenarios=21, compat_postludes=1, successful_pv=21, rejected_pv=12,
                      frontend_rejected=9, backend_rejected=3, elf=str(elf), elf_sha256=sha(elf),
                      recovery_contract=dict(same_context=11, released_no_context_reload=1,
                                             full_commands=22, release_commands=22,
                                             hardware_reset_or_reload_to_mask_failure=False),
                      fault_pc={str(v): names[k] for k, v in expected.items()},
                      source_pins_sha256=sha(output/'source-pins.json'), artifacts=artifacts,
                      pending='Parent review; no VCS preparation/launch authorized', post_pins_match=True)
        for p in inputs.rglob('*'):
            if p.is_file(): p.chmod(0o444)
    except BaseException as exc:
        report['error'] = repr(exc)
    save(output/'build.json', report)
    require(report['state'] == 'BOUNDARY_SOFTWARE_BUILT_NOT_EXECUTED', 'Build failed; retained '+str(output))
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--parent-reviewed', action='store_true', required=True)
    args = p.parse_args()
    result = build(args.output)
    print(json.dumps({k: v for k, v in result.items() if k not in ('artifacts', 'image_pins')}, indent=2))
