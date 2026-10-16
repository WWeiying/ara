"""Add DDR2 to a known-working Linux bundle, preserving DDR1 exclusions."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def run(*args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, **kwargs)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def enable_ddr2(dtb):
    def get(node, prop):
        return run('fdtget', '-t', 'x', dtb, node, prop,
                   capture_output=True, text=True).stdout.split()
    if get('/', '#address-cells') != ['2'] or get('/', '#size-cells') != ['2']:
        raise ValueError('Expected 64-bit root address/size cells')
    expected = ['0', '80000000', '0', '7eff0000']
    if get('/memory@80000000', 'reg') != expected:
        raise ValueError('Unexpected original DDR1 range; refuse to change reservations')
    nodes = run('fdtget', '-l', dtb, '/', capture_output=True, text=True).stdout.split()
    if any(x.startswith('memory@') and x != 'memory@80000000' for x in nodes):
        raise ValueError('Additional memory nodes require manual review')
    run('fdtput', '-t', 'x', dtb, '/memory@80000000', 'reg',
        *expected, '1', '0', '0', '80000000')
    assert get('/memory@80000000', 'reg') == expected + ['1', '0', '0', '80000000']


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--sdk', type=Path, default=Path('/home/wangwy/openproject/cva6/cva6-sdk'))
    p.add_argument('--llama', type=Path, help='Optional RISC-V static llama-simple executable')
    p.add_argument('--model', type=Path, help='Optional Qwen3 GGUF, requires --llama')
    a = p.parse_args()
    if bool(a.llama) != bool(a.model):
        p.error('--llama and --model must be supplied together')
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    originals = {}
    for name in ('ara_vcu118.dtb', 'initramfs.cpio', 'Image', 'fw_jump.elf'):
        src = a.source / name
        originals[name] = sha256_file(src)
        shutil.copy2(src, out / name)
    dtb = out / 'ara_vcu118.dtb'
    enable_ddr2(dtb)
    cross = str(a.sdk / 'buildroot/output/host/bin/riscv64-buildroot-linux-gnu-')
    overlay = out / 'overlay'
    overlay.mkdir()
    run(cross + 'gcc', '-O2', '-Wall', '-Wextra', '-Werror', '-static',
        Path(__file__).with_name('ddr_pages.c'), '-o', overlay / 'ddr_pages')
    run(cross + 'strip', overlay / 'ddr_pages')
    names = ['ddr_pages']
    extra = {}
    if a.model:
        with a.model.open('rb') as f:
            if f.read(4) != b'GGUF':
                raise ValueError('Model is not GGUF')
        for src, name in ((a.llama, 'llama-simple'), (a.model, 'qwen3.gguf')):
            shutil.copy2(src, overlay / name)
            extra[name] = sha256_file(src)
            names.append(name)
    run('cpio', '-o', '-A', '-H', 'newc', '-F', out / 'initramfs.cpio',
        input=('\n'.join(names)+'\n').encode(), cwd=overlay)
    end = 0x88000000 + (out / 'initramfs.cpio').stat().st_size
    if end >= 0xfeff0000:
        raise ValueError('Initramfs exceeds loader range')
    run('fdtput', '-t', 'x', dtb, '/chosen', 'linux,initrd-end', '0', f'{end:x}')
    run('make', '-j4', '-C', a.sdk / 'buildroot/output/build/opensbi-1.7',
        f'O={out / "opensbi"}', 'PLATFORM=generic', 'PLATFORM_RISCV_XLEN=64',
        f'CROSS_COMPILE={cross}', 'FW_TEXT_START=0x80000000', f'FW_FDT_PATH={dtb}',
        'FW_JUMP=y', 'FW_DYNAMIC=n', 'FW_PAYLOAD=n',
        'FW_JUMP_ADDR=0x80200000', 'FW_JUMP_FDT_ADDR=0x80100000')
    shutil.copy2(out / 'opensbi/platform/generic/firmware/fw_jump.elf', out / 'fw_jump.elf')
    run(cross + 'strip', '--strip-debug', out / 'fw_jump.elf')
    files = {}
    for name in originals:
        files[name] = sha256_file(out / name)
    (out / 'manifest.json').write_text(json.dumps(dict(source=originals, files=files,
        ddr1=[0x80000000, 0xfeff0000], ddr2=[0x100000000, 0x180000000],
        kernel_unchanged=files['Image'] == originals['Image'], extra_files=extra,
        hardware_validated=False), indent=2)+'\n')
    print('BUNDLE', out)


if __name__ == '__main__':
    main()
