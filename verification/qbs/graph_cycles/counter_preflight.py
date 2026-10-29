#!/usr/bin/env python3
"""Check Linux rdcycle permissions, not simulated hardware performance."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PLATFORM = Path('/home/wangwy/llama/platforms/cva6-qemu')
BOOT_OPTION = 'sysctl.kernel.perf_user_access=2'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(ROOT / 'verification/out'):
        raise ValueError('Output must be an independent verification/out directory')
    out.mkdir(exist_ok=False)
    source = HERE / 'counter_preflight.c'
    cc = PLATFORM / 'tools/bin/riscv64-linux-gcc'
    cpio = PLATFORM / 'sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio'
    recipe = ROOT / 'verification/out/graph-cycles-model-20261029-02/qemu.command.json'
    command = json.loads(recipe.read_text())['argv']
    inputs = [source, HERE / 'linux_counter.h', Path(__file__), cc.resolve(), cpio, recipe,
              Path(command[0]), Path(command[command.index('-kernel') + 1]),
              Path(command[command.index('-bios') + 1])]
    pins = {str(p): digest(p) for p in inputs}
    (out / 'source-pins.json').write_text(json.dumps(pins, indent=2) + '\n')
    result = dict(state='FAIL', performance_measured=False, cases={})

    def run(argv, name, timeout):
        (out / (name + '.command.json')).write_text(json.dumps([str(x) for x in argv], indent=2) + '\n')
        with (out / (name + '.log')).open('w') as log:
            subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=timeout)

    try:
        run([cc, '-march=rv64gc', '-mabi=lp64d', '-O2', '-static', source, '-o', out / 'init'], 'compile', 60)
        (out / 'initramfs.list').write_text(
            f'dir /dev 0755 0 0\nnod /dev/console 0600 0 0 c 5 1\n'
            f'dir /proc 0755 0 0\nfile /init {out / "init"} 0755 0 0\n')
        with (out / 'initramfs.cpio').open('wb') as image:
            subprocess.run([cpio, out / 'initramfs.list'], stdout=image, check=True, timeout=30)
        command[command.index('-initrd') + 1] = str(out / 'initramfs.cpio')
        index = command.index('-drive')
        del command[index:index + 2]
        for name, option in [('default', ''), ('legacy', ' ' + BOOT_OPTION)]:
            argv = list(command)
            argv[argv.index('-append') + 1] = 'console=ttyS0 rdinit=/init' + option
            run(argv, name, 120)
            text = (out / (name + '.log')).read_text()
            if name == 'default':
                if 'COUNTER_ACCESS mode=1' not in text or 'COUNTER_CHILD exit=-1 signal=4' not in text:
                    raise ValueError('Default policy did not reject rdcycle as expected')
                if 'COUNTER_READ' in text:
                    raise ValueError('Unexpected default counter read')
            else:
                match = re.search(r'COUNTER_READ begin=(\d+) end=(\d+)', text)
                if ('COUNTER_ACCESS mode=2' not in text or 'COUNTER_EVENT active=1' not in text
                        or 'COUNTER_CHILD exit=0 signal=0' not in text
                        or not match or int(match[2]) <= int(match[1])):
                    raise ValueError('Configured user counter access failed')
            result['cases'][name] = dict(state='PASS', log_sha256=digest(out / (name + '.log')))
        if any(digest(p) != h for p, h in pins.items()):
            raise ValueError('Preflight input drift')
        result.update(state='PASS', boot_option=BOOT_OPTION, post_pins_match=True)
    except BaseException as exc:
        result['error'] = repr(exc)
        raise
    finally:
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
