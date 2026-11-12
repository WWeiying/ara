"""Prepare one frozen Refact pair; run only after separate parent review."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
sys.dont_write_bytecode = True
from portable_model_check import check, LIMITS

ROOT = Path('/home/wangwy/openproject/ara_dsa')
HERE = Path(__file__).resolve().parent
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
UNIFIED = OUT / 'enablement_unified_build_20261111_01'
BUILD = UNIFIED / 'build'
PLATFORM = Path('/home/wangwy/llama/platforms/cva6-qemu')
MODEL = Path('/home/wangwy/llama/models/portability/refact-1_6b-Q4_K_M.gguf')
DISK = ROOT / 'hardware/qbs_akv_portability_stage2_20260907_r4/refact.ext4'
GATES = OUT / 'stage5_qemu_four_gates_20261110_03/result.json'
ALIBI = OUT / 'enablement_portable_alibi_20261111_02/result.json'
MODEL_SHA = '241741c3bb51c99d53ecb2e1891b66e8058e99876e07e82d21f050deb2f090c9'
ORIGINAL = 'c44e8090df973dd5ec2e21527b19e435dbdef17cdde2ff6fc5dca7a25006c49e'
CPU = 'rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=true,xaraakv=true,xaraakv-resident=true'
OWN = ('portable_model_run.py', 'portable_model_check.py', 'portable_model_test.py',
       'portable_model_init.c', 'portable_model_observe.cpp', 'portable_model_metadata.py')


def require(ok, why):
    if not ok:
        raise ValueError(why)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def verify(pins):
    for path, digest in pins.items():
        require(sha(path) == digest, 'Pin drift: ' + path)


def prepare(out):
    require(out.parent == OUT and out.name.startswith('enablement_portable_model_') and not out.exists(), 'Fresh output required')
    delivery = read(UNIFIED / 'delivery.json')
    require(delivery['state'] == 'FROZEN_UNIFIED_LLAMA_DELIVERED_BY_INDEPENDENT_AUDIT' and
            delivery['source_and_image_pins_match'] and delivery['programs']['llama-simple']['sha256'] == ORIGINAL,
            'Unified receipt not accepted')
    alibi = read(ALIBI)
    require(alibi['state'] == 'ALIBI_GNU14_GLIBC_PROBE_CHECKED' and alibi['coefficient_bits_equal'] and
            alibi['coefficient_fcsr_equal'] and alibi['post_pins_match'], 'ALiBi coefficient gate')
    pins = {}
    for name, key in (('source-pins.json', 'source_pins_sha256'), ('compile-source-pins.json', 'compile_source_pins_sha256'),
                      ('artifact-pins.json', 'artifact_pins_sha256')):
        path = UNIFIED / name
        require(sha(path) == delivery[key], 'Unified pin receipt identity')
        inherited = read(path)
        verify(inherited)
        for p, digest in inherited.items():
            require(p not in pins or pins[p] == digest, 'Inherited pin conflict')
            pins[p] = digest
        pins[str(path)] = sha(path)
    out.mkdir()
    inputs = out / 'inputs'
    inputs.mkdir()
    commands = []
    env = {k: v for k, v in os.environ.items() if not k.startswith(('GGML_', 'AKV_'))}
    env.update(LC_ALL='C', LANG='C', PYTHONDONTWRITEBYTECODE='1')

    def pin(path):
        path = Path(path).absolute()
        value = sha(path)
        require(str(path) not in pins or pins[str(path)] == value, 'Pin drift: ' + str(path))
        pins[str(path)] = value

    def run(label, argv, cwd=out, timeout=300, extra_env=None):
        argv = list(map(str, argv))
        pin(Path(shutil.which(argv[0]) or argv[0]))
        with (out / (label + '.log')).open('x') as log:
            done = subprocess.run(argv, cwd=cwd, env={**env, **(extra_env or {})},
                stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=timeout)
        commands.append(dict(label=label, argv=argv, cwd=str(cwd), returncode=done.returncode))
        require(done.returncode == 0, 'Preparation failed: ' + label)
        return (out / (label + '.log')).read_text()

    report = dict(state='FAIL', model_executed=False, performance_measured=False)
    try:
        for name in OWN:
            pin(HERE / name)
            shutil.copyfile(HERE / name, inputs / name)
        for path in (UNIFIED / 'delivery.json', UNIFIED / 'build-audit.json', GATES, ALIBI):
            pin(path)
        run('checker-tests', [sys.executable, '-B', inputs / 'portable_model_test.py'])
        info = json.loads(run('gguf-metadata', ['/usr/bin/python3', '-B', inputs / 'portable_model_metadata.py', MODEL],
            extra_env=dict(PYTHONPATH='/home/wangwy/llama/llama.cpp/gguf-py')))
        for path in info.pop('metadata_reader_dependencies'):
            pin(path)
        require((info['embedding'], info['q_heads'], info['kv_heads'], info['head_dim'], info['layers']) == (2048, 32, 1, 64, 32),
                'Unexpected Refact geometry')
        require(info['vocabulary'] > 0 and sha(MODEL) == MODEL_SHA, 'Model identity/metadata')
        pin(MODEL)
        pin(DISK)
        info.update(path=str(MODEL), sha256=MODEL_SHA, disk=str(DISK), disk_sha256=sha(DISK))
        save(out / 'model.json', info)
        run('disk-extract', ['/usr/sbin/debugfs', '-R', 'dump /models/' + MODEL.name + ' ' + str(out / 'disk-model.gguf'), DISK])
        require(sha(out / 'disk-model.gguf') == MODEL_SHA, 'Read-only disk/model payload differs')
        (out / 'disk-model.gguf').unlink()
        header = inputs / 'portable_model_config.h'
        header.write_text('#define PORTABLE_MODEL_VOCAB ' + str(info['vocabulary']) + 'u\n#define PORTABLE_MODEL_PATH ' +
                          json.dumps('/model/models/' + MODEL.name) + '\n')
        cc = PLATFORM / 'tools/bin/riscv64-linux-gcc'
        cxx = cc.with_name('riscv64-linux-g++')
        flags = ['-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-O2', '-static', '-fno-fast-math', '-ffp-contract=off']
        source = UNIFIED / 'inputs/llama'
        original_link = shlex.split((BUILD / 'examples/simple/CMakeFiles/llama-simple.dir/link.txt').read_text())
        original_link[original_link.index('-o')+1] = str(out / 'original-relinked')
        run('original-relink', original_link, BUILD / 'examples/simple')
        require(sha(out / 'original-relinked') == ORIGINAL, 'Frozen objects do not reproduce original ELF')
        run('observe-compile', [cxx, *flags, '-fno-tree-vectorize', '-fno-tree-slp-vectorize',
            '-I' + str(source / 'include'), '-I' + str(source / 'ggml/include'), '-c', inputs / 'portable_model_observe.cpp',
            '-o', out / 'observe.o'])
        link = list(original_link)
        link[link.index('-o')+1] = str(out / 'test')
        at = link.index('-o')
        link[at:at] = [str(out / 'observe.o'), '-Wl,--wrap=llama_decode', '-Wl,--wrap=llama_sampler_sample']
        run('observe-link', link, BUILD / 'examples/simple')
        require(sha(out / 'test') != ORIGINAL, 'Observed ELF identity must be distinct')
        names = run('symbols', [cc.with_name('riscv64-linux-nm'), '-S', '-C', out / 'test'])
        symbols = {}
        for key, symbol in (('qbs', 'qbs_native_execute_command'), ('features', 'akv_attention_execute_v2_with_features_native_auto')):
            matches = [line.split()[0] for line in names.splitlines() if line.endswith(' ' + symbol)]
            require(len(matches) == 1, 'Missing/ambiguous native symbol: ' + symbol)
            symbols[key] = int(matches[0], 16)
        save(out / 'symbols.json', symbols)
        run('init-compile', [cc, *flags, '-Wall', '-Wextra', '-Werror', '-fno-tree-vectorize', '-fno-tree-slp-vectorize',
            '-I' + str(inputs), inputs / 'portable_model_init.c', '-o', out / 'init'])
        run('observed-readelf', [cc.with_name('riscv64-linux-readelf'), '-h', '-l', '-d', out / 'test'])
        listing = out / 'initramfs.list'
        listing.write_text(''.join('dir /' + name + ' 0755 0 0\n' for name in ('dev', 'proc', 'model')) +
            'dir /tmp 1777 0 0\n' + ''.join('file /' + name + ' ' + str(out / name) + ' 0755 0 0\n' for name in ('init', 'test')))
        cpio = PLATFORM / 'sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio'
        pin(cpio)
        with (out / 'initramfs.cpio').open('xb') as stream:
            subprocess.run([cpio, listing], stdout=stream, check=True, timeout=30)
        gate = read(GATES)
        require(gate['state'] == 'NATIVE_QEMU_FOUR_GATES_CHECKED', 'QEMU gate state')
        qemu = Path(gate['executable'])
        require(sha(qemu) == gate['executable_sha256'] == '1f4619e1573ed6626b259912d6780ac9d40e8cca8ed38ec32694a0b1d399388a', 'QEMU identity')
        bios, kernel = PLATFORM / 'images/fw_dynamic.bin', PLATFORM / 'images/Image'
        for path in (qemu, bios, kernel):
            pin(path)
        command = [str(qemu), '-M', 'virt', '-cpu', CPU, '-smp', '1', '-m', '4G', '-display', 'none',
            '-monitor', 'none', '-serial', 'stdio', '-bios', str(bios), '-kernel', str(kernel), '-initrd', str(out / 'initramfs.cpio'),
            '-drive', 'file=' + str(DISK) + ',if=virtio,format=raw,readonly=on', '-append', 'console=ttyS0 rdinit=/init',
            '-d', 'exec,nochain', '-dfilter', ','.join(hex(pc) + '+1' for pc in symbols.values())]
        save(out / 'qemu-command.json', command)
        contract = dict(model=info, arms=['PORTABLE=0', 'PORTABLE=unset (profile AUTO)'], same_observed_elf=True,
            original_elf_sha256=ORIGINAL, observed_elf_sha256=sha(out / 'test'), prompt='The answer is', predict=2, threads=1,
            only_policy_difference='GGML_RISCV_AKV_PORTABLE', limits=LIMITS, prefill_full_logits_bitwise_equal=True,
            decode_full_vocabulary_metrics=True, generated_tokens_top1_csr_equal=True, qbs_native_work_equal=True,
            qbs_emulated_commands=0, expected_portable_decode_ops=32, expected_portable_groups=128,
            expected_native_features_entries=128, off_akv_execution=0, tag4_required=False, stdout_guest_file_then_print=True,
            timeout_seconds=1800, automatic_retry=False, model_executed=False, launch_requires_parent_review=True,
            rtl_timing=False, performance_acceptance=False, panel_performance_accepted=False)
        save(out / 'contract.json', contract)
        save(out / 'prepare-commands.json', commands)
        for path in out.rglob('*'):
            if path.is_file():
                pin(path)
        verify(pins)
        save(out / 'source-pins.json', pins)
        report.update(state='PREPARED_NOT_EXECUTED', post_pins_match=True, source_pins_sha256=sha(out / 'source-pins.json'),
            contract_sha256=sha(out / 'contract.json'), original_elf_sha256=ORIGINAL, observed_elf_sha256=sha(out / 'test'),
            vocabulary=info['vocabulary'], logits_to_compare=2*info['vocabulary'], timeout_seconds=1800,
            same_elf_two_arms=True, checker_tests_passed=True)
    except BaseException as exc:
        report['error'] = repr(exc)
        raise
    finally:
        save(out / 'prepare.json', report)
    print(json.dumps(report, sort_keys=True), flush=True)


def execute(out, review):
    require(HERE == out / 'inputs' and sha(out / 'source-pins.json') == review, 'Unreviewed frozen runner')
    require(not (out / 'attempt.json').exists(), 'No retry')
    unit = 'enablement-portable-model-' + out.name + '.service'
    pid = subprocess.check_output(['systemctl', '--user', 'show', unit, '--property=MainPID', '--value'], text=True).strip()
    group = Path('/proc/self/cgroup').read_text()
    require(pid == str(os.getpid()) and '/' + unit in group, 'Direct systemd ownership required')
    save(out / 'attempt.json', dict(pid=os.getpid(), unit=unit, automatic_retry=False))
    result = dict(state='FAIL', performance_measured=False, rtl_timing=False, fpga_acceptance=False, model_executed=True)
    child = None
    try:
        pins = read(out / 'source-pins.json')
        verify(pins)
        with (out / 'guest.log').open('xb') as log:
            child = subprocess.Popen(read(out / 'qemu-command.json'), cwd=out, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
            require(Path('/proc/' + str(child.pid) + '/cgroup').read_text() == group, 'QEMU cgroup')
            save(out / 'qemu-process.json', dict(pid=child.pid, cgroup=group))
            require(child.wait(timeout=1800) == 0, 'QEMU failed')
        with (out / 'guest.log').open() as stream:
            proof = check(stream, read(out / 'symbols.json'), read(out / 'model.json'))
        verify(pins)
        result.update(state='FULL_LLAMA_PORTABLE_REFACT_PAIR_CHECKED', post_pins_match=True, proof=proof)
    except BaseException as exc:
        if child is not None and child.poll() is None:
            child.kill(); child.wait()
        result['error'] = repr(exc)
    result.update(source_pins_sha256=review, guest_log_sha256=sha(out / 'guest.log') if (out / 'guest.log').exists() else None)
    save(out / 'result.json', result)
    print(json.dumps(result, sort_keys=True), flush=True)
    return result['state'] != 'FULL_LLAMA_PORTABLE_REFACT_PAIR_CHECKED'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('action', choices=('prepare', 'run'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--review-sha256')
    args = parser.parse_args()
    out = args.output.resolve()
    if args.action == 'prepare':
        prepare(out)
    else:
        raise SystemExit(execute(out, args.review_sha256))
