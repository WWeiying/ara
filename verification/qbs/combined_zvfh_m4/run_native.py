#!/usr/bin/env python3
"""Run the sealed combined-Zvfh quantizer gate; QEMU is functional only."""
import argparse
import json
import os
from pathlib import Path
import signal
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from run_half_scale_soc import atomic_json, digest, hashes
from run_tile_context_engine import run_command
from run_ggml_segmented import verify_native_build
from check_native import check_output


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    build = a.build.resolve(strict=True)
    report = json.loads((build / 'build.json').read_text())
    pins = json.loads((build / 'manifest.json').read_text())
    if (report['state'] != 'READY' or digest(build / 'manifest.json') != report['manifest_sha256']
            or hashes(map(Path, pins)) != pins):
        raise ValueError('Build inputs/artifacts changed')
    root = HERE.parents[2]
    qemu = root / 'verification/out/qbs-native-qemu-build-20261023/qemu-10.2.0-build/qemu-system-riscv64'
    platform = Path('/home/wangwy/llama/platforms/cva6-qemu')
    sources = [Path(name) for name in verify_native_build(qemu)]
    sources += [qemu, platform / 'images/Image', platform / 'images/fw_dynamic.bin',
                build / 'build.json', build / 'manifest.json']
    for module in tuple(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name and Path(name).resolve().is_relative_to(root):
            sources.append(Path(name).resolve())
    pins.update(hashes(sources))
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    atomic_json(out / 'manifest.json', pins)
    state = dict(state='PREPARING', pid=os.getpid(), child_pid=None)

    def save():
        atomic_json(out / 'status.json', state)

    def started(pid):
        state.update(state='RUNNING', child_pid=pid)
        save()

    def interrupted(sig, _frame):
        raise InterruptedError(f'Signal {sig}')

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    save()
    try:
        command = list(map(str, [qemu, '-M', 'virt', '-cpu',
            'rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=true',
            '-smp', '1', '-m', '512M', '-display', 'none', '-monitor', 'none', '-serial', 'stdio',
            '-bios', platform / 'images/fw_dynamic.bin', '-kernel', platform / 'images/Image',
            '-initrd', build / 'initramfs.cpio', '-append', 'console=ttyS0 rdinit=/init']))
        atomic_json(out / 'command.json', command)
        log = out / 'qemu.log'
        if run_command(command, log, 900, os.environ.copy(), started):
            raise RuntimeError('QEMU failed or timed out')
        state.update(state='CHECKING', child_pid=None)
        save()
        checked = check_output(log.read_text())
        if hashes(map(Path, pins)) != pins:
            raise ValueError('Execution inputs changed')
        checked.update(log_sha256=digest(log), manifest_sha256=digest(out / 'manifest.json'))
        atomic_json(out / 'result.json', checked)
        state.update(state='PASS')
    except BaseException as exc:
        state.update(state='FAIL', error=repr(exc))
        raise
    finally:
        state['child_pid'] = None
        save()


if __name__ == '__main__':
    main()
