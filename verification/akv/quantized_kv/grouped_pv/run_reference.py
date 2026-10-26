#!/usr/bin/env python3
"""Build and run the explicit RVV leaf against its scalar oracle in QEMU.

Functional only. Source inputs must be frozen before invocation. No SDK edits,
VCS, hardware timing, model execution, or production promotion.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PLATFORM = Path('/home/wangwy/llama/platforms/cva6-qemu')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    temporary = path.with_suffix(path.suffix + '.partial')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--vlen', type=int, choices=(256, 1024), default=1024)
    args = parser.parse_args()
    out = args.output.absolute()
    if out.exists() or out != out.resolve() or not out.is_relative_to(ROOT/'verification/out'):
        raise ValueError('Use a new independent verification/out directory')
    out.mkdir(parents=True)
    cc = PLATFORM/'tools/bin/riscv64-linux-gcc'
    qemu = ROOT/'verification/out/qbs-native-qemu-build-20261023/qemu-10.2.0-build/qemu-system-riscv64'
    cpio = PLATFORM/'sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio'
    kernel, firmware = PLATFORM/'images/Image', PLATFORM/'images/fw_dynamic.bin'
    init = HERE.parent/'ggml_live/init.c'
    paths = [Path(__file__).resolve(), HERE/'kernel.h', HERE/'test_kernel.c',
             cc.resolve(strict=True), qemu, cpio, kernel, firmware, init]
    pins = {str(p): sha(p) for p in paths}
    save(out/'input-pins.json', pins)
    environment = dict(HOME='/home/wangwy', PATH='/usr/bin:/bin', LANG='C.UTF-8')
    state = dict(state='PREPARING', pid=os.getpid(), child_pid=None, vlen=args.vlen,
                 functional_only=True, rtl_performance=False)

    def unchanged():
        for name, digest in pins.items():
            if sha(Path(name)) != digest:
                raise ValueError('Input drift: ' + name)

    def run(argv, name, bound, stdout=None):
        save(out/(name+'.command.json'), dict(argv=list(map(str, argv)), timeout=bound))
        state.update(state=name.upper(), child_pid=None)
        save(out/'status.json', state)
        with (out/(name+'.log')).open('wb') as log:
            child = subprocess.Popen(list(map(str, argv)), cwd=out, env=environment,
                                     stdout=stdout if stdout is not None else log, stderr=log,
                                     start_new_session=True)
            state['child_pid'] = child.pid
            save(out/'status.json', state)
            try:
                rc = child.wait(timeout=bound)
            except BaseException:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
                raise
            finally:
                state['child_pid'] = None
            if rc:
                raise RuntimeError(f'{name} returned {rc}')
        unchanged()

    started = time.monotonic()
    try:
        run([cc, '-O2', '-static', '-march=rv64gcv', '-mabi=lp64d',
             '-fno-tree-vectorize', '-fno-fast-math', '-ffp-contract=off',
             '-frounding-math', '-Wall', '-Wextra', '-Werror',
             HERE/'test_kernel.c', '-lm', '-o', out/'test'], 'build', 120)
        run([cc, '-O2', '-static', '-march=rv64gc', '-mabi=lp64d',
             init, '-o', out/'init'], 'init-build', 120)
        listing = out/'initramfs.list'
        listing.write_text('dir /dev 755 0 0\n'
                           'nod /dev/console 600 0 0 c 5 1\n'
                           f'file /init {out / "init"} 755 0 0\n'
                           f'file /test {out / "test"} 755 0 0\n')
        with (out/'initramfs.cpio').open('wb') as stream:
            run([cpio, listing], 'cpio', 60, stream)
        pins.update({str(p): sha(p) for p in
                     (out/'test', out/'init', listing, out/'initramfs.cpio')})
        save(out/'input-pins.json', pins)
        run([qemu, '-M', 'virt', '-cpu', f'rv64,v=true,vlen={args.vlen},elen=64',
             '-smp', '1', '-m', '512M', '-display', 'none', '-monitor', 'none',
             '-serial', 'stdio', '-bios', firmware, '-kernel', kernel,
             '-initrd', out/'initramfs.cpio', '-append',
             'console=ttyS0 rdinit=/init'], 'qemu', 600)
        log = (out/'qemu.log').read_text().replace('\r\n', '\n')
        markers = [line for line in log.splitlines() if line.startswith('GROUPED_PV_PASS')]
        expected = 'GROUPED_PV_PASS backend=RVV cases=13824 invalid=17 csr=fcsr_vcsr rounding=RNE'
        if (markers != [expected] or
                log.splitlines().count('GUEST_TEST_EXIT=0') != 1 or
                re.search(r'^FAIL\b|Kernel panic|GUEST_TEST_EXIT=[1-9]', log, re.M)):
            raise ValueError('Missing successful explicit-RVV test/guest termination')
        unchanged()
        result = dict(state='PASS', functional_only=True, rtl_performance=False,
                      vlen=args.vlen, marker=markers[0], input_pins_sha256=sha(out/'input-pins.json'),
                      log_sha256=sha(out/'qemu.log'), elf_sha256=sha(out/'test'),
                      source_pre_post_match=True, seconds=time.monotonic()-started)
        save(out/'result.json', result)
        state.update(state='PASS', child_pid=None)
    except BaseException as exc:
        state.update(state='FAIL', child_pid=None, error=repr(exc))
        save(out/'result.json', state)
        raise
    finally:
        save(out/'status.json', state)


if __name__ == '__main__':
    main()
