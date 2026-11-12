"""Bounded full llama-simple check: explicit options versus default selection."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent/'ara_dsa_signoff_integration/verification/out'
PLATFORM = Path('/home/wangwy/llama/platforms/cva6-qemu')
GATES = OUT/'stage5_qemu_four_gates_20261110_03/result.json'
GATES_SHA = 'd1fe3d705d1caa1923536eff66a6e4fa51030d180e2db01c1724ccc1a4f211d0'


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def check_log(path):
    mode = None
    qbs, akv = [{}, {}], [None, None]
    with path.open() as stream:
        for raw in stream:
            line = raw.strip()
            if line.startswith('AUTO_MODEL_BEGIN '):
                mode = int(line.split('=')[1])
                require(mode in (0, 1), 'Unknown arm')
            elif line.startswith('GGML_RISCV_QBS_EXEC '):
                fields = dict(w.split('=', 1) for w in line.split()[1:])
                kind = fields.pop('type')
                require(mode is not None and kind not in qbs[mode], 'Unscoped/duplicate QBS summary')
                row = {k: int(v) for k, v in fields.items()}
                require(row['native_qbexec'] > 0 and row['emulated_commands'] == 0,
                        'Missing native QBS work or emulated route')
                qbs[mode][kind] = row
            elif line.startswith('GGML_RISCV_AKV_COVERAGE '):
                fields = dict(w.split('=', 1) for w in line.split()[1:])
                require(mode is not None and akv[mode] is None, 'Unscoped/duplicate AKV summary')
                akv[mode] = {k: int(v) for k, v in fields.items()}
            elif line.startswith('AUTO_MODEL_LOGITS_PASS '):
                require(line == 'AUTO_MODEL_LOGITS_PASS records=2 values=98304 bitwise=1',
                        'Unexpected/incomplete logits comparison')
                check_log.logits_seen += 1
            elif line.startswith('GUEST_TEST_EXIT='):
                require(line == 'GUEST_TEST_EXIT=0', 'Guest program failure')
                check_log.exits += 1
    require(qbs[0] and qbs[0] == qbs[1], 'Default and explicit QBS work differs')
    require(akv[0] and akv[0] == akv[1] and akv[0]['executed_ops'] > 0,
            'Missing/different native Attention work')
    require(check_log.logits_seen == check_log.exits == 1, 'Missing/duplicate terminal checks')
    return dict(logits_compared=98304, qbs=qbs[0], akv=akv[0], bitwise_equal=True)


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--elf-sha256', required=True)
    args = parser.parse_args()
    out, elf = args.output.resolve(), args.executable.resolve()
    require(out.parent == OUT and out.name.startswith('llama_auto_model_') and not out.exists(),
            'Fresh independent output required')
    out.mkdir()
    result = dict(state='FAIL', performance_measured=False, fpga_acceptance=False)
    try:
        require(sha(elf) == args.elf_sha256 and sha(GATES) == GATES_SHA, 'Unreviewed ELF/gates')
        gates = json.loads(GATES.read_text())
        qemu = Path(gates['executable'])
        require(sha(qemu) == gates['executable_sha256'], 'Native instruction model drift')
        source = Path(__file__).with_name('auto_model_init.c')
        # Buildroot's wrapper selects the real compiler from argv[0].
        cc = PLATFORM/'tools/bin/riscv64-linux-gcc'
        cpio = PLATFORM/'sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio'
        disk = PLATFORM/'images/smollm2-q4km.ext4'
        inputs = [Path(__file__).resolve(), source, elf, qemu, cc.resolve(), cpio,
                  PLATFORM/'images/fw_dynamic.bin', PLATFORM/'images/Image', disk, GATES]
        pins = {str(path): sha(path) for path in inputs}
        require(pins[str(disk)] == 'cdcfde87b3e1ace02c02d3ffa49f85ff59b946ceda5821a6f77ec0225edc82e0',
                'Model disk identity differs')
        save(out/'source-pins.json', pins)
        with (out/'compile.log').open('x') as log:
            subprocess.run([str(cc), '-static', '-O2', '-Wall', '-Wextra', '-Werror',
                            '-fno-tree-vectorize', '-fno-tree-slp-vectorize',
                            str(source), '-o', str(out/'init')],
                           check=True, stdout=log, stderr=subprocess.STDOUT, timeout=60)
        listing = ''.join('dir /%s 0755 0 0\n' % name for name in ('dev', 'proc', 'model'))
        listing += 'dir /tmp 1777 0 0\nfile /init %s 0755 0 0\nfile /test %s 0755 0 0\n' % (out/'init', elf)
        (out/'initramfs.list').write_text(listing)
        with (out/'initramfs.cpio').open('xb') as image:
            subprocess.run([str(cpio), str(out/'initramfs.list')], stdout=image, check=True, timeout=60)
        command = [str(qemu), '-M', 'virt', '-cpu',
            'rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=true,xaraakv=true,xaraakv-resident=true',
            '-smp', '1', '-m', '4G', '-display', 'none', '-monitor', 'none', '-serial', 'stdio',
            '-bios', str(PLATFORM/'images/fw_dynamic.bin'), '-kernel', str(PLATFORM/'images/Image'),
            '-initrd', str(out/'initramfs.cpio'), '-drive',
            'file='+str(disk)+',if=virtio,format=raw,readonly=on',
            '-append', 'console=ttyS0 rdinit=/init']
        save(out/'command.json', command)
        pins.update({str(path): sha(path) for path in
                     (out/'init', out/'initramfs.list', out/'initramfs.cpio', out/'command.json')})
        require(all(sha(Path(path)) == digest for path, digest in pins.items()), 'Preparation drift')
        save(out/'execution-pins.json', pins)
        with (out/'guest.log').open('xb') as log:
            child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                cwd=out, env=dict(PATH='/usr/bin:/bin', HOME=str(out), LANG='C', LC_ALL='C'))
            save(out/'process.json', dict(pid=child.pid, parent=os.getpid()))
            try:
                require(Path('/proc/self/cgroup').read_text() == Path('/proc/%d/cgroup' % child.pid).read_text(),
                        'QEMU escaped the worker service')
                require(child.wait(timeout=1800) == 0, 'QEMU process failed')
            finally:
                if child.poll() is None:
                    child.kill(); child.wait()
        check_log.logits_seen = check_log.exits = 0
        result['proof'] = check_log(out/'guest.log')
        require(all(sha(Path(path)) == digest for path, digest in pins.items()), 'Input drift')
        result.update(state='FULL_LLAMA_DEFAULTS_MODEL_CHECKED', post_pins_match=True,
                      executable_sha256=args.elf_sha256, guest_log_sha256=sha(out/'guest.log'))
    except BaseException as exc:
        result['error'] = repr(exc)
    save(out/'result.json', result)
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0 if result['state'] == 'FULL_LLAMA_DEFAULTS_MODEL_CHECKED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
