#!/usr/bin/env python3
"""Load the frozen broker in bounded QEMU boots; legacy INFO4 must stay zero."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import time

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
MODULE = OUT / 'resident_deployment_module_20261112_02'
QEMU = OUT / 'stage5_qemu_build_20261110_07/qemu-system-riscv64'
IMAGES = Path('/home/wangwy/llama/platforms/cva6-qemu/images')
KERNEL = Path('/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/build/linux-6.19.6')
GNU = Path('/home/wangwy/llama/platforms/cva6-qemu/tools/bin')
CLIENT = ROOT / 'software/llama/platform/linux'
CPU = 'rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=true,xaraakv=true,xaraakv-resident=true'
EXPECTED = {
    MODULE / 'module/ara_resident.ko': 'ffece01d2818d76109d282e122c4bd8006aa0ac9703b670380222b2848da5929',
    QEMU: '1f4619e1573ed6626b259912d6780ac9d40e8cca8ed38ec32694a0b1d399388a',
    IMAGES / 'Image': '716aef49389b25a0a3f4deac47de0bb69467a10f1057041cecd0f0621fbbf285',
    IMAGES / 'fw_dynamic.bin': '30e855897b24423232a6859ca8f29441f37a5a445d84735e943cb4ae2c752182',
    CLIENT / 'client_v2.c': '84b94dfac17dc50445fd8c7aa99196d5d756468b46dc76a9b93865fa29654b1b',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def config(text):
    result = {}
    for line in text.splitlines():
        if line.startswith('CONFIG_'):
            k, v = line.split('=', 1)
            result[k] = v
        elif line.startswith('# CONFIG_') and line.endswith(' is not set'):
            result[line[2:-11]] = 'n'
    return result


def cpio(entries):
    result = bytearray()
    for ino, (name, mode, data, major, minor) in enumerate(entries + [('TRAILER!!!', 0, b'', 0, 0)], 1):
        encoded = name.encode() + b'\0'
        fields = [ino, mode, 0, 0, 1, 0, len(data), 0, 0, major, minor, len(encoded), 0]
        result += b'070701' + ''.join(f'{v:08x}' for v in fields).encode() + encoded
        result += b'\0' * (-len(result) % 4)
        result += data
        result += b'\0' * (-len(result) % 4)
    result += b'\0' * (-len(result) % 512)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    require(out.parent == OUT and out.name.startswith('resident_deployment_linux_smoke_') and not out.exists(),
            'Use a fresh direct signoff output directory')
    out.mkdir()
    inputs = out / 'inputs'
    inputs.mkdir()
    commands, pins = [], {}
    report = dict(state='FAIL', module_loaded=False, linux_executed=False, board_executed=False,
                  resident_arithmetic_executed=False, full_model_executed=False, guests=[])

    def save(name, obj):
        (out / name).write_text(json.dumps(obj, indent=2, sort_keys=True) + '\n')

    def run(name, argv, timeout=30, binary=False):
        argv = list(map(str, argv))
        started = time.monotonic()
        try:
            r = subprocess.run(argv, cwd=out, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
            record = dict(name=name, argv=argv, returncode=r.returncode,
                          elapsed_seconds=round(time.monotonic() - started, 3), timeout_seconds=timeout)
            commands.append(record)
            if binary:
                (out / (name + '.bin')).write_bytes(r.stdout)
                (out / (name + '.stderr.log')).write_bytes(r.stderr)
            else:
                (out / (name + '.log')).write_bytes(r.stdout + r.stderr)
            require(r.returncode == 0, name + ' failed: ' + r.stderr.decode(errors='replace')[-2000:])
            return r.stdout if binary else (r.stdout + r.stderr).decode(errors='replace')
        except subprocess.TimeoutExpired as e:
            (out / (name + '.log')).write_bytes((e.stdout or b'') + (e.stderr or b''))
            commands.append(dict(name=name, argv=argv, timed_out=True, timeout_seconds=timeout))
            raise

    def freeze(source, name):
        source = Path(source)
        target = inputs / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        pins[str(source)] = pins[str(target)] = sha(source)
        require(sha(target) == pins[str(source)], 'Copy identity drift: ' + str(source))
        return target

    try:
        for path, digest in EXPECTED.items():
            require(sha(path) == digest, 'Frozen identity mismatch: ' + str(path))
            pins[str(path)] = digest
        inherited = json.loads((MODULE / 'source-pins.json').read_text())
        for path, digest in inherited.items():
            require(sha(path) == digest, 'Module source pin drift: ' + path)
            pins[path] = digest
        pins[str(MODULE / 'source-pins.json')] = sha(MODULE / 'source-pins.json')
        pins[str(MODULE / 'result.json')] = sha(MODULE / 'result.json')
        image_data = (IMAGES / 'Image').read_bytes()
        require(b'Linux version 6.19.6 ' in image_data and b'6.19.6 SMP mod_unload riscv\0' in image_data,
                'Image release/vermagic mismatch')
        embedded = run('image-config', [KERNEL / 'scripts/extract-ikconfig', IMAGES / 'Image'])
        local = (KERNEL / '.config').read_text()
        old, new = config(embedded), config(local)
        differences = {k: [old.get(k), new.get(k)] for k in old.keys() | new.keys() if old.get(k) != new.get(k)}
        require(differences == {'CONFIG_RISCV_PROBE_UNALIGNED_ACCESS': ['y', 'n'],
                               'CONFIG_RISCV_EMULATED_UNALIGNED_ACCESS': ['n', 'y']},
                'Unreviewed Image/build-config differences: ' + repr(differences))
        for key in ('CONFIG_MODULES', 'CONFIG_MODULE_UNLOAD', 'CONFIG_FPU', 'CONFIG_RISCV_ISA_V', 'CONFIG_SMP'):
            require(old.get(key) == 'y', 'Kernel lacks ' + key)
        require(old.get('CONFIG_MODVERSIONS') == old.get('CONFIG_MODULE_SIG') == 'n', 'Unexpected module ABI enforcement')
        require(old.get('CONFIG_PREEMPT_RT', 'n') == old.get('CONFIG_RISCV_ISA_V_PREEMPTIVE', 'n') == 'n',
                'Unsupported vector scope config')
        (out / 'image-config.diff').write_text(''.join(difflib.unified_diff(
            embedded.splitlines(True), local.splitlines(True), fromfile='Image embedded config', tofile='module build config')))
        mod = freeze(MODULE / 'module/ara_resident.ko', 'ara_resident.ko')
        metadata = run('module-info', [GNU / 'riscv64-linux-readelf', '-p', '.modinfo', mod])
        require('vermagic=6.19.6 SMP mod_unload riscv' in metadata, 'Module vermagic mismatch')
        undefined = run('module-undefined', [GNU / 'riscv64-linux-nm', '-u', mod])
        names = re.findall(r'\bU (\S+)', undefined)
        exports = {line.split()[1] for line in (KERNEL / 'Module.symvers').read_text().splitlines()}
        require(names and all(n in exports and n.encode() + b'\0' in image_data for n in names),
                'Missing module import in Image/build exports')
        report['qualification'] = dict(image_release='6.19.6', vermagic='6.19.6 SMP mod_unload riscv',
            embedded_config_sha256=hashlib.sha256(embedded.encode()).hexdigest(),
            config_matches_except_explicit_unaligned_options=differences, module_import_count=len(names),
            image_is_not_current_build_tree_image=True, runtime_module_load_required=True)
        freeze(__file__, 'run.py')
        for name in ('init.c', 'start.S'):
            freeze(HERE / name, name)
        for name in ('client_v2.c', 'client_rv64.S', 'client.h', 'job_layout.h', 'ara_resident_uapi.h'):
            freeze(CLIENT / name, name)
        require(sha(inputs / 'ara_resident_uapi.h') == sha(MODULE / 'module/ara_resident_uapi.h'), 'UAPI drift')
        for name in ('gcc', 'readelf', 'nm', 'objdump'):
            pins[str((GNU / ('riscv64-linux-' + name)).resolve())] = sha((GNU / ('riscv64-linux-' + name)).resolve())
        flags = ['-O2', '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-march=rv64gc', '-mabi=lp64d',
                 '-mcmodel=medany', '-mno-relax', '-msmall-data-limit=0', '-ffreestanding', '-fno-builtin',
                 '-fno-stack-protector', '-fno-tree-vectorize', '-fno-tree-slp-vectorize', '-nostdlib', '-static',
                 '-I' + str(inputs), '-Wl,-e,_start', '-Wl,--build-id=none']
        elf = out / 'init.elf'
        run('init-build', [GNU / 'riscv64-linux-gcc', *flags, inputs / 'start.S', inputs / 'init.c',
                          inputs / 'client_v2.c', inputs / 'client_rv64.S', '-o', elf])
        elf_info = run('init-elf', [GNU / 'riscv64-linux-readelf', '-h', '-l', elf])
        require('RISC-V' in elf_info and 'INTERP' not in elf_info, 'Init must be static RV64 ELF')
        run('init-disassembly', [GNU / 'riscv64-linux-objdump', '-d', elf])
        archive = out / 'initramfs.cpio'
        archive.write_bytes(cpio([('dev', 0o040755, b'', 0, 0), ('proc', 0o040755, b'', 0, 0),
            ('sys', 0o040755, b'', 0, 0), ('dev/console', 0o020600, b'', 5, 1),
            ('init', 0o100755, elf.read_bytes(), 0, 0), ('ara_resident.ko', 0o100644, mod.read_bytes(), 0, 0)]))
        for path in (elf, archive):
            pins[str(path)] = sha(path)
        save('source-pins.json', pins)
        for cpus in (1, 2):
            dtb = out / f'virt-{cpus}.dtb'
            base = [QEMU, '-M', 'virt', '-cpu', CPU, '-smp', cpus, '-m', '256M',
                    '-display', 'none', '-monitor', 'none', '-serial', 'stdio', '-bios', IMAGES / 'fw_dynamic.bin',
                    '-kernel', IMAGES / 'Image']
            dump = base.copy()
            dump[2] = 'virt,dumpdtb=' + str(dtb)
            run(f'dump-dtb-{cpus}', dump, timeout=15)
            tool = GNU / 'fdtput'
            run(f'dtb-node-{cpus}', [tool, '-c', dtb, '/ara-resident'])
            for name, kind, values in (
                ('compatible', 's', ['pulp,ara-resident-attention-v1']), ('status', 's', ['okay']),
                ('pulp,nr-lanes', 'x', ['4']), ('pulp,vlen-bits', 'x', ['400']),
                ('pulp,hart-id', 'x', ['0', '0']), ('pulp,ram-base', 'x', ['0', '80000000']),
                ('pulp,ram-size', 'x', ['0', '10000000'])):
                run(f'dtb-{cpus}-{name.replace(",", "-")}', [tool, '-t', kind, dtb, '/ara-resident', name, *values])
            for name in ('dma-coherent', 'pulp,firmware-preserves-accelerator'):
                run(f'dtb-{cpus}-{name.replace(",", "-")}', [tool, dtb, '/ara-resident', name])
            dts = run(f'virt-{cpus}-dts', [GNU / 'dtc', '-I', 'dtb', '-O', 'dts', dtb])
            require('memory@80000000' in dts and 'pulp,ara-resident-attention-v1' in dts, 'Wrong virt DT')
            pins[str(dtb)] = sha(dtb)
            save('source-pins.json', pins)
            trace = out / f'guest-{cpus}.trace'
            cmd = base + ['-dtb', dtb, '-initrd', archive, '-append',
                f'console=ttyS0 rdinit=/init panic=0 loglevel=6 resident_smoke_cpus={cpus}',
                '-trace', 'enable=akv_arch_*,file=' + str(trace)]
            log = run(f'guest-{cpus}', cmd, timeout=180)
            report['linux_executed'] = True
            report['module_loaded'] |= 'CHECK name=finit_module rc=0 expected=0 PASS' in log
            require(f'RESIDENT_LINUX_SMOKE_PASS cpus={cpus} ' in log and ' errors=0' in log,
                    f'Guest {cpus} failed; retain original log')
            require(not re.search(r'CHECK .* FAIL|Kernel panic|Oops:|Unknown symbol|disagrees about version', log),
                    f'Guest {cpus} kernel/check failure')
            events = trace.read_text()
            queries = [(int(a), int(b, 16)) for a, b in re.findall(r'akv_arch_info index=(\d+) result=0x([0-9a-f]+)', events)]
            require('akv_arch_begin' not in events, 'Unexpected accelerator computation command')
            csr = 'CLIENT_V2_CSR_TESTS PASS' in log
            if cpus == 1:
                expected_rounds = 3 if csr else 2
                require([a for a, _ in queries] == list(range(5)) * expected_rounds,
                        'Single-hart legal requests did not reach real kernel INFO0..4')
                require(all(value == 0 for index, value in queries if index == 4), 'Old INFO4 unexpectedly nonzero')
            else:
                require(not queries, 'Two-hart request reached INFO despite before-execution rejection')
            guest = dict(cpus=cpus, state='PASS', actual_info4_zero_reads=sum(i == 4 for i, _ in queries),
                info_queries=[dict(index=i, value=f'{v:016x}') for i, v in queries],
                client_v2_csr_checked=csr, no_resident_commands=True,
                raw_log_sha256=sha(out / f'guest-{cpus}.log'), trace_sha256=sha(trace), dtb_sha256=sha(dtb))
            report['guests'].append(guest)
            save('result.json', report)
        require(all(sha(path) == digest for path, digest in pins.items()), 'Source/image identity drift')
        report.update(state='QEMU_LINUX_MODULE_NEGATIVE_LIFECYCLE_PASS', source_pins_match=True,
                      module_sha256=sha(mod), init_elf_sha256=sha(elf), initramfs_sha256=sha(archive),
                      real_kernel_scope_cap4_decline=True, smp_before_execution_decline=True,
                      qemu_only_trusted_dt=True, current_kernel_build_config_is_not_image_config=True)
    except Exception as error:
        report['error'] = repr(error)
    save('source-pins.json', pins)
    save('commands.json', commands)
    save('result.json', report)
    print(json.dumps(report, sort_keys=True), flush=True)
    return int(report['state'] == 'FAIL')


if __name__ == '__main__':
    raise SystemExit(main())
