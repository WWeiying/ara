"""One bounded GNU/QEMU diagnostic; read frozen archives, never rebuild production."""
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PLATFORM = Path('/home/wangwy/llama/platforms/cva6-qemu')
GGML = Path('/home/wangwy/llama/llama.cpp/ggml')
PRODUCTION = ROOT / 'verification/out/grouped-pv-model-build-20261026-01'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def expected_digest(nonzero):
    qs = [j % 255 - 127 if nonzero else 0 for j in range(256)]
    data = struct.pack('<f256b16h', float(nonzero), *qs,
                       *(sum(qs[j:j+16]) for j in range(0, 256, 16)))
    value = 14695981039346656037
    for byte in data:
        value = ((value ^ byte) * 1099511628211) & ((1 << 64) - 1)
    return f'{value:016x}'


def main():
    if len(sys.argv) != 2:
        raise ValueError('usage: run.py NEW_OUTPUT_DIRECTORY')
    out = Path(sys.argv[1]).resolve()
    if not out.is_relative_to(HERE):
        raise ValueError('All output must remain inside vcsr_diagnostic')
    out.mkdir(exist_ok=False)
    tools = PLATFORM / 'tools/bin'
    cc, cxx, objdump = [tools / ('riscv64-linux-' + name) for name in ('gcc', 'g++', 'objdump')]
    libs = [PRODUCTION / ('llama/ggml/src/lib' + name + '.a')
            for name in ('ggml', 'ggml-cpu', 'ggml-base')]
    qemu = ROOT / 'verification/out/qbs-native-qemu-build-20261023/qemu-10.2.0-build/qemu-system-riscv64'
    cpio = PLATFORM / 'sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio'
    model = PRODUCTION / 'quant-kv-model-grouped'
    files = [*libs, qemu, cpio, model, PLATFORM / 'images/Image', PLATFORM / 'images/fw_dynamic.bin',
             HERE / 'native.c', HERE / 'init.c', Path(__file__), cc.resolve(), cxx.resolve(), objdump.resolve(),
             PRODUCTION / 'compile_commands.json', GGML / 'src/ggml-cpu/arch/riscv/quants.c',
             *GGML.rglob('*.h')]
    pins = {str(path): sha(path) for path in files}
    save(out / 'inputs.json', pins)
    commands = []

    def run(command, label, timeout=120):
        command = list(map(str, command))
        commands.append(dict(label=label, command=command, timeout=timeout))
        save(out / 'commands.json', commands)
        with (out / (label + '.log')).open('x') as stream:
            process = subprocess.Popen(command, cwd=out, stdout=stream, stderr=subprocess.STDOUT)
            save(out / 'status.json', dict(state='RUNNING', stage=label, child_pid=process.pid))
            print(f'{label}: pid={process.pid}', flush=True)
            try:
                code = process.wait(timeout=timeout)
            except BaseException:
                process.kill()
                process.wait()
                raise
            if code:
                raise RuntimeError(f'{label}: exit={code}')

    includes = [flag for directory in ('include', 'src', 'src/ggml-cpu')
                for flag in ('-isystem', GGML / directory)]
    run([cc, '-std=c11', '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-O2', '-fno-fast-math',
         '-ffp-contract=off', '-fno-tree-vectorize', '-Wall', '-Wextra', '-Werror',
         *includes, '-c', HERE / 'native.c', '-o', out / 'native.o'], 'compile')
    run([cxx, '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-static', out / 'native.o',
         *libs, '-lm', '-ldl', '-pthread', '-Wl,-Map=' + str(out / 'native.map'),
         '-o', out / 'native'], 'link')
    run([cc, '-march=rv64gc', '-mabi=lp64d', '-static', '-O2', '-Wall', '-Wextra', '-Werror',
         HERE / 'init.c', '-o', out / 'init'], 'compile-init')
    for label, binary in (('diagnostic-disasm', out / 'native'), ('model-disasm', model)):
        run([objdump, '-d', '--disassemble=quantize_row_q8_K', binary], label)
        if not re.search(r'csrwi\s+vxrm,1', (out / (label + '.log')).read_text()):
            raise ValueError(f'{label}: expected VXRM write absent')
    listing = out / 'initramfs.list'
    listing.write_text('\n'.join(['dir /dev 755 0 0', 'nod /dev/console 600 0 0 c 5 1',
                                  f'file /init {out / "init"} 755 0 0',
                                  f'file /native {out / "native"} 755 0 0']) + '\n')
    with (out / 'initramfs.cpio').open('xb') as stream:
        subprocess.run([cpio, listing], stdout=stream, check=True, timeout=30)
    run([qemu, '-M', 'virt', '-cpu', 'rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=true',
         '-smp', '1', '-m', '512M', '-display', 'none', '-monitor', 'none', '-serial', 'stdio',
         '-bios', PLATFORM / 'images/fw_dynamic.bin', '-kernel', PLATFORM / 'images/Image',
         '-initrd', out / 'initramfs.cpio', '-append', 'console=ttyS0 rdinit=/init'], 'qemu', 120)
    log = (out / 'qemu.log').read_text()
    expected = []
    for initial in (5, 4):
        for nonzero in (0, 1):
            actual = (2 | (initial & 1)) if nonzero else initial
            expected.append(f'VCSR_DIAG_CASE kind={"nonzero" if nonzero else "zero"} '
                            f'before_vcsr={initial} after_vcsr={actual} before_fcsr=9 after_fcsr=9 '
                            f'bytes=1 input=1 canaries=1 digest={expected_digest(nonzero)}')
    expected += ['VCSR_DIAG_PASS cases=4', 'VCSR_DIAG_GUEST_EXIT=0']
    records = [line.strip() for line in log.splitlines() if 'VCSR_DIAG' in line]
    if records != expected or re.search(r'Kernel panic|Illegal instruction|Assertion .*failed', log):
        raise ValueError('Diagnostic hypothesis/checks not confirmed; preserve raw log')
    if any(sha(path) != value for path, value in pins.items()):
        raise ValueError('Pinned input drift')
    artifacts = {str(path): sha(path) for path in out.iterdir()
                 if path.is_file() and path.name != 'status.json'}
    save(out / 'result.json', dict(state='PASS', scope='QEMU functional diagnostic only',
         records=records, inputs_sha256=sha(out / 'inputs.json'), artifacts=artifacts))
    save(out / 'status.json', dict(state='PASS', child_pid=None))
    print('\n'.join(records), flush=True)


if __name__ == '__main__':
    main()
