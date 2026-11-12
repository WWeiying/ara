#!/usr/bin/env python3
"""Successor: explicit shipped-object rule for Linux 6.19 external modules."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT.parent/'ara_dsa_signoff_integration/verification/out'
PLATFORM = ROOT/'software/llama/platform/linux'
KERNEL = Path('/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/build/linux-6.19.6')
GNU = Path('/home/wangwy/llama/platforms/cva6-qemu/tools/bin')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--compute-output', type=Path, required=True)
    p.add_argument('--core-sha256', required=True)
    p.add_argument('--header-sha256', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    out, compute = a.output.resolve(), a.compute_output.resolve()
    assert out.parent == compute.parent == OUT and out.name.startswith('resident_deployment_module_')
    assert compute.name.startswith('resident_deployment_kernel_compute_') and not out.exists()
    core, header = compute/'module/sdk/ara_resident_compute_core.o', compute/'module/sdk/kernel_compute.h'
    assert sha(core) == a.core_sha256 and sha(header) == a.header_sha256
    assert sha(header) == sha(PLATFORM/'sdk/kernel_compute.h')
    out.mkdir()
    module = out/'module'
    (module/'sdk').mkdir(parents=True)
    pins = {str(core): sha(core), str(header): sha(header), str(Path(__file__).resolve()): sha(__file__)}
    for name in ('ara_resident_broker.c', 'ara_resident_uapi.h', 'job_layout.h'):
        source = PLATFORM/name
        pins[str(source)] = sha(source)
        shutil.copyfile(source, module/name)
        pins[str(module/name)] = sha(module/name)
    shutil.copyfile(header, module/'sdk/kernel_compute.h')
    shutil.copyfile(core, module/'ara_resident_compute_core.o_shipped')
    for target in (module/'sdk/kernel_compute.h', module/'ara_resident_compute_core.o_shipped'):
        pins[str(target)] = sha(target)
    (module/'Kbuild').write_text('obj-m += ara_resident.o\n'
        'ara_resident-y := ara_resident_broker.o ara_resident_compute_core.o\n'
        '$(obj)/ara_resident_compute_core.o: $(src)/ara_resident_compute_core.o_shipped\n'
        '\tcp $< $@\n')
    pins[str(module/'Kbuild')] = sha(module/'Kbuild')
    for name in ('.config', 'Module.symvers', 'include/generated/utsrelease.h'):
        pins[str(KERNEL/name)] = sha(KERNEL/name)
    commands = []

    def run(name, argv):
        result = subprocess.run(list(map(str, argv)), text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, cwd=out, timeout=300)
        (out/(name+'.log')).write_text(result.stdout)
        commands.append(dict(name=name, argv=list(map(str, argv)), returncode=result.returncode))
        assert not result.returncode, (name, result.stdout[-4000:])
        return result.stdout

    report = dict(state='FAIL', kernel_booted=False, module_loaded=False, board_executed=False)
    try:
        run('kbuild', ['make', '-C', KERNEL, 'M='+str(module), 'ARCH=riscv',
            'CROSS_COMPILE='+str(GNU/'riscv64-linux-'), '-j4', 'modules'])
        elf = module/'ara_resident.ko'
        attrs = run('elf', [GNU/'riscv64-linux-readelf', '-h', '-s', elf])
        assert 'RISC-V' in attrs and 'soft-float ABI' in attrs
        dis = run('disassembly', [GNU/'riscv64-linux-objdump', '-d', module/'ara_resident_broker.o'])
        ops = __import__('re').findall(r'^\s*[0-9a-f]+:\s+[0-9a-f]+\s+([a-z][a-z0-9_.]*)', dis, __import__('re').M)
        assert ops and not any(op.startswith(('v', 'f')) and op != 'fence' for op in ops)
        undefined = run('undefined', [GNU/'riscv64-linux-nm', '-u', elf])
        assert not any(name in undefined for name in ('expf', 'tanhf', 'fmaf', '__errno_location', '__libc'))
        assert all(sha(name) == value for name, value in pins.items())
        report.update(state='LINUX_MODULE_KBUILD_CHECKED_NOT_LOADED', module=str(elf),
            module_sha256=sha(elf), compute_object_sha256=sha(core), source_pins_match=True,
            broker_no_fp_vector_arithmetic=True, no_unresolved_libc_or_math=True)
    except Exception as error:
        report['error'] = repr(error)
    (out/'source-pins.json').write_text(json.dumps(pins, indent=2)+'\n')
    (out/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
    (out/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))
    return int(report['state']=='FAIL')


if __name__=='__main__':
    raise SystemExit(main())
