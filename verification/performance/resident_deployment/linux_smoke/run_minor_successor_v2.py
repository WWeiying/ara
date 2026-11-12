#!/usr/bin/env python3
"""Successor for Linux dynamic misc minors; keep all ioctl/capability checks."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
HERE = Path(__file__).resolve().parent
ANCESTOR = OUT / 'resident_deployment_linux_smoke_20261112_024227'
MINOR_FAILURE = OUT / 'resident_deployment_linux_smoke_20261112_025911'
AUDIT_SHA = 'cf5b1fe8ebd60bf818062faca853b6daca298e748a0036ac088ab36b7db87582'
INIT_SHA = '8b3cea75ca352d4ffd1d91ebfdeaf8c99bc9d2f96c401fee044e967ec98db22c'
DTB_SHA = '1f090f91c14818915130eae7995ce7f6544350fb69984f2b0a78f35e15ba4e02'
GNU = Path('/home/wangwy/llama/platforms/cva6-qemu/tools/bin')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def unpack(data):
    entries, offset = [], 0
    while True:
        require(data[offset:offset + 6] == b'070701', 'Only the original newc archive is supported')
        fields = [int(data[offset + 6 + i * 8:offset + 14 + i * 8], 16) for i in range(13)]
        offset += 110
        name = data[offset:offset + fields[11]]
        require(name.endswith(b'\0'), 'Bad cpio filename')
        offset = (offset + fields[11] + 3) & ~3
        payload = data[offset:offset + fields[6]]
        require(len(payload) == fields[6], 'Truncated cpio payload')
        offset = (offset + fields[6] + 3) & ~3
        entries.append((name, fields, payload))
        if name == b'TRAILER!!!\0':
            require(not any(data[offset:]), 'Unexpected data after cpio trailer')
            return entries


def pack(entries):
    data = bytearray()
    for name, fields, payload in entries:
        fields = fields.copy()
        fields[6] = len(payload)
        data += b'070701' + ''.join(f'{v:08x}' for v in fields).encode() + name
        data += b'\0' * (-len(data) % 4)
        data += payload
        data += b'\0' * (-len(data) % 4)
    data += b'\0' * (-len(data) % 512)
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--module', required=True, type=Path)
    parser.add_argument('--module-sha256', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--smp2', action='store_true', help='Also boot an independent two-CPU virt DT')
    args = parser.parse_args()
    out, module = args.output.resolve(), args.module.resolve()
    require(out.parent == OUT and out.name.startswith('resident_deployment_linux_smoke_') and not out.exists(),
            'Fresh direct signoff output required')
    require(module.name == 'ara_resident.ko' and module.parent.name == 'module' and
            module.parent.parent.parent == OUT and module.parent.parent.name.startswith('resident_deployment_module_'),
            'Use a frozen signoff module build')
    require(re.fullmatch('[0-9a-f]{64}', args.module_sha256) is not None, 'Explicit SHA256 required')
    out.mkdir()
    inputs = out / 'inputs'
    inputs.mkdir()
    pins, commands = {}, []
    report = dict(state='FAIL', ancestor=str(ANCESTOR), ancestor_state='FAIL',
        original_failed_report_unchanged=True, module_loaded=False, linux_executed=False,
        resident_arithmetic_executed=False, board_executed=False, full_model_executed=False,
        init_recompiled=True, kernel_recompiled=False, qemu_rebuilt=False, guests=[])

    def save(name, obj):
        (out / name).write_text(json.dumps(obj, indent=2, sort_keys=True) + '\n')

    def pin(path, expected=None):
        actual = sha(path)
        require(expected is None or actual == expected, 'Identity mismatch: ' + str(path))
        pins[str(path)] = actual

    def copy(source, name, expected=None):
        pin(source, expected)
        target = inputs / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        pin(target, pins[str(source)])
        return target

    def run(name, argv, timeout=30):
        argv = list(map(str, argv))
        started = time.monotonic()
        try:
            result = subprocess.run(argv, cwd=out, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
            log = result.stdout + result.stderr
            commands.append(dict(name=name, argv=argv, returncode=result.returncode,
                elapsed_seconds=round(time.monotonic() - started, 3), timeout_seconds=timeout))
            (out / (name + '.log')).write_bytes(log)
            require(result.returncode == 0, name + ' returned ' + str(result.returncode))
            return log.decode(errors='replace')
        except subprocess.TimeoutExpired as error:
            (out / (name + '.log')).write_bytes((error.stdout or b'') + (error.stderr or b''))
            commands.append(dict(name=name, argv=argv, timed_out=True, timeout_seconds=timeout))
            raise

    try:
        copy(__file__, 'run_minor_successor_v2.py')
        tool_failure = OUT / 'resident_deployment_linux_smoke_20261112_030654'
        for name in ('result.json', 'host-device-build.log'):
            pin(tool_failure / name)
        require('cannot find /usr/lib64/libubsan.so.1.0.0' in (tool_failure / 'host-device-build.log').read_text(),
                'Unexpected host compiler predecessor failure')
        report['host_compiler_successor_reason'] = 'GCC libubsan unavailable; same UBSan checks with existing Clang toolchain'
        for name in ('result.json', 'commands.json', 'source-pins.json', 'guest-1.log'):
            pin(MINOR_FAILURE / name)
        minor_report = json.loads((MINOR_FAILURE / 'result.json').read_text())
        require(minor_report['state'] == 'FAIL' and minor_report['module_loaded'], 'Wrong minor failure ancestry')
        minor_log = (MINOR_FAILURE / 'guest-1.log').read_text()
        require('MISC_DEV 10:258' in minor_log and 'CHECK name=mknod rc=-1 expected=0 FAIL' in minor_log,
                'Missing original harness failure')
        report['minor_failure_ancestor'] = str(MINOR_FAILURE)
        pin(ANCESTOR / 'failure-audit.json', AUDIT_SHA)
        audit = json.loads((ANCESTOR / 'failure-audit.json').read_text())
        require(audit['state'] == 'UNAVAILABLE_FROZEN_MODULE_REJECTED_R_RISCV_ALIGN' and
                audit['original_run_state'] == 'FAIL', 'Wrong predecessor evidence')
        for name, digest in audit['artifacts'].items():
            pin(ANCESTOR / name, digest)
        require(sha(ANCESTOR / 'init.elf') == INIT_SHA and sha(ANCESTOR / 'virt-1.dtb') == DTB_SHA,
                'Predecessor init/DT identity mismatch')
        baseline_pins = json.loads((ANCESTOR / 'source-pins.json').read_text())
        for path, digest in baseline_pins.items():
            if Path(path).is_relative_to(ANCESTOR):
                pin(path, digest)
        inherited_commands = json.loads((ANCESTOR / 'commands.json').read_text())
        baseline = next(c['argv'] for c in inherited_commands if c['name'] == 'guest-1')
        qemu = Path(baseline[0])
        image = Path(baseline[baseline.index('-kernel') + 1])
        bios = Path(baseline[baseline.index('-bios') + 1])
        for path in (qemu, image, bios):
            pin(path, baseline_pins[str(path)])
        pin(module, args.module_sha256)
        build = module.parent.parent
        build_result = json.loads((build / 'result.json').read_text())
        require(build_result['state'] == 'LINUX_MODULE_KBUILD_CHECKED_NOT_LOADED' and
                build_result['module_sha256'] == args.module_sha256, 'Unaccepted successor module build')
        pin(build / 'result.json')
        pin(build / 'source-pins.json')
        for path, digest in json.loads((build / 'source-pins.json').read_text()).items():
            pin(path, digest)
        replacement = copy(module, 'ara_resident.ko', args.module_sha256)
        metadata = run('module-info', [GNU / 'riscv64-linux-readelf', '-p', '.modinfo', replacement])
        require('vermagic=6.19.6 SMP mod_unload riscv' in metadata, 'Module vermagic mismatch')
        relocs = run('module-relocations', [GNU / 'riscv64-linux-readelf', '-rW', replacement])
        require('R_RISCV_ALIGN' not in relocs and 'R_RISCV_RELAX' not in relocs,
                'Successor module still contains ALIGN/RELAX')
        require(sha(build / 'module/ara_resident_uapi.h') == sha(ANCESTOR / 'inputs/ara_resident_uapi.h'),
                'Inherited init UAPI is incompatible')
        previous_elf = copy(ANCESTOR / 'init.elf', 'init_previous.elf', INIT_SHA)
        for name in ('start.S', 'client_v2.c', 'client_rv64.S', 'client.h', 'job_layout.h', 'ara_resident_uapi.h'):
            copy(ANCESTOR / 'inputs' / name, name, baseline_pins[str(ANCESTOR / 'inputs' / name)])
        for name in ('init_v2.c', 'device_numbers.h', 'test_device_numbers.c'):
            copy(HERE / name, name)
        (out / 'init-device-number.diff').write_text(''.join(difflib.unified_diff(
            (ANCESTOR / 'inputs/init.c').read_text().splitlines(True),
            (inputs / 'init_v2.c').read_text().splitlines(True), fromfile='frozen init.c', tofile='init_v2.c')))
        host = out / 'host-devices'
        run('host-device-build', ['/usr/lib64/ccache/clang', '-O2', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
            '-fsanitize=undefined', '-fno-sanitize-recover=all', '-I' + str(inputs),
            inputs / 'test_device_numbers.c', '-o', host])
        host_log = run('host-devices', [host])
        require('DEVICE_NUMBERS_PASS roundtrips=5 actual_10_258=0x100a02 bounds=PASS malformed=6' in host_log,
                'Host device encoding checks failed')
        report['host_device_roundtrips'] = 5
        elf = inputs / 'init.elf'
        build_command = next(c['argv'] for c in inherited_commands if c['name'] == 'init-build')
        build_command = [word.replace(str(ANCESTOR / 'inputs'), str(inputs))
            .replace(str(ANCESTOR / 'init.elf'), str(elf)) for word in build_command]
        build_command = [str(inputs / 'init_v2.c') if word == str(inputs / 'init.c') else word for word in build_command]
        run('init-device-number-build', build_command)
        info = run('init-elf', [GNU / 'riscv64-linux-readelf', '-h', '-l', elf])
        require('RISC-V' in info and 'INTERP' not in info, 'Init must stay static RV64')
        pin(elf)
        dtb1 = copy(ANCESTOR / 'virt-1.dtb', 'virt-1.dtb', DTB_SHA)
        entries = unpack((ANCESTOR / 'initramfs.cpio').read_bytes())
        require(sum(name == b'ara_resident.ko\0' for name, _, _ in entries) == 1, 'Ambiguous original module entry')
        require(next(data for name, _, data in entries if name == b'init\0') == previous_elf.read_bytes(), 'Init/cpio mismatch')
        changed = [(name, fields, replacement.read_bytes() if name == b'ara_resident.ko\0' else elf.read_bytes() if name == b'init\0' else data)
                   for name, fields, data in entries]
        archive = out / 'initramfs.cpio'
        archive.write_bytes(pack(changed))
        decoded = unpack(archive.read_bytes())
        require(len(decoded) == len(entries), 'Changed cpio entry count')
        for before, after in zip(entries, decoded):
            require(before[0] == after[0], 'Changed cpio ordering')
            require(before[1][:6] + before[1][7:] == after[1][:6] + after[1][7:], 'Changed cpio metadata')
            require(before[0] in (b'ara_resident.ko\0', b'init\0') or before[2] == after[2], 'Changed unrelated cpio content')
        pin(archive)
        report.update(module_sha256=args.module_sha256, init_elf_sha256=sha(elf), single_cpu_dtb_sha256=DTB_SHA,
            initramfs_sha256=sha(archive), cpio_only_init_and_module_changed=True, previous_init_elf_sha256=INIT_SHA, no_align_or_relax_relocations=True,
            qualification=json.loads((ANCESTOR / 'result.json').read_text())['qualification'])
        for cpus in ((1, 2) if args.smp2 else (1,)):
            dtb = dtb1
            command = baseline.copy()
            command[command.index('-smp') + 1] = str(cpus)
            if cpus == 2:
                dtb = out / 'virt-2.dtb'
                dump = command[:command.index('-dtb')]
                dump[dump.index('-M') + 1] = 'virt,dumpdtb=' + str(dtb)
                run('dump-dtb-2', dump, timeout=15)
                tool = GNU / 'fdtput'
                run('dtb-node-2', [tool, '-c', dtb, '/ara-resident'])
                for name, kind, values in (
                    ('compatible', 's', ['pulp,ara-resident-attention-v1']), ('status', 's', ['okay']),
                    ('pulp,nr-lanes', 'x', ['4']), ('pulp,vlen-bits', 'x', ['400']),
                    ('pulp,hart-id', 'x', ['0', '0']), ('pulp,ram-base', 'x', ['0', '80000000']),
                    ('pulp,ram-size', 'x', ['0', '10000000'])):
                    run('dtb-2-' + name.replace(',', '-'), [tool, '-t', kind, dtb, '/ara-resident', name, *values])
                for name in ('dma-coherent', 'pulp,firmware-preserves-accelerator'):
                    run('dtb-2-' + name.replace(',', '-'), [tool, dtb, '/ara-resident', name])
                pin(dtb)
                run('virt-2-dts', [GNU / 'dtc', '-I', 'dtb', '-O', 'dts', dtb])
            command[command.index('-dtb') + 1] = str(dtb)
            command[command.index('-initrd') + 1] = str(archive)
            command[command.index('-append') + 1] = baseline[baseline.index('-append') + 1].replace(
                'resident_smoke_cpus=1', 'resident_smoke_cpus=' + str(cpus))
            trace = out / f'guest-{cpus}.trace'
            command[command.index('-trace') + 1] = 'enable=akv_arch_*,file=' + str(trace)
            save('source-pins.json', pins)
            log = run('guest-' + str(cpus), command, timeout=180)
            report['linux_executed'] = True
            report['module_loaded'] |= 'CHECK name=finit_module rc=0 expected=0 PASS' in log
            require(f'RESIDENT_LINUX_SMOKE_PASS cpus={cpus} ' in log and ' errors=0' in log,
                    'Guest failed: preserve its original log')
            require(not re.search(r'CHECK .* FAIL|Kernel panic|Oops:|Unknown symbol|unexpected relocation', log),
                    'Guest kernel/check failure')
            events = trace.read_text()
            queries = [(int(i), int(v, 16)) for i, v in re.findall(r'akv_arch_info index=(\d+) result=0x([0-9a-f]+)', events)]
            require('akv_arch_begin' not in events, 'Unexpected accelerator computation command')
            csr = 'CLIENT_V2_CSR_TESTS PASS' in log
            if cpus == 1:
                require([i for i, _ in queries] == list(range(5)) * (3 if csr else 2),
                        'Expected real repeated kernel INFO0..4 queries')
                require(all(v == 0 for i, v in queries if i == 4), 'Old INFO4 unexpectedly nonzero')
            else:
                require(not queries, 'SMP rejection happened after INFO execution')
            report['guests'].append(dict(cpus=cpus, state='PASS', client_v2_csr_checked=csr,
                info_queries=[dict(index=i, value=f'{v:016x}') for i, v in queries],
                raw_log_sha256=sha(out / f'guest-{cpus}.log'), trace_sha256=sha(trace), dtb_sha256=sha(dtb),
                no_resident_commands=True))
            save('result.json', report)
        require(all(sha(path) == digest for path, digest in pins.items()), 'Source/artifact identity drift')
        report.update(state='QEMU_LINUX_MODULE_NEGATIVE_LIFECYCLE_PASS', source_pins_match=True,
                      real_kernel_scope_cap4_decline=True, smp_before_execution_decline=args.smp2)
    except Exception as error:
        report['error'] = repr(error)
    save('source-pins.json', pins)
    save('commands.json', commands)
    save('result.json', report)
    print(json.dumps(report, sort_keys=True), flush=True)
    return int(report['state'] == 'FAIL')


if __name__ == '__main__':
    raise SystemExit(main())
