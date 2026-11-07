#!/usr/bin/env python3
"""Build only. No simulator, synthesis, archived baseline helper or old object."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
CAPTURE = OUT / 'e2e_decode_capture_20261106_01'
OLD_BUILD = OUT / 'e2e_decode_native_build_20261106_02'
LLAMA = Path('/home/wangwy/llama/llama.cpp')
TOOLCHAIN = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin')
RECEIPTS = {
    'result.json': '16a0b450843ba41276c4f56dfbd9abcf974020c6db97b19e1cda10b6864bf52f',
    'build.json': 'e8568f5735ef31c597819c3135dd1876760278ec4e1f62011b67e6d58f708b88',
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def crop_r4(data, source_n=128, first=0, n=64, kb=8, block_bytes=210):
    """Global R4: ((row // 4) * kb + kblock) * 4 + row % 4."""
    require(source_n > 0 and kb > 0 and block_bytes > 0 and n > 0 and
            first >= 0 and first % 4 == 0 and n % 4 == 0 and
            first + n <= source_n, 'Invalid R4 crop geometry')
    require(len(data) == ((source_n + 3) // 4 * 4) * kb * block_bytes,
            'R4 source length mismatch')
    result = bytearray(n * kb * block_bytes)
    for row in range(n):
        for kblock in range(kb):
            src = (((row + first) // 4 * kb + kblock) * 4 + (row + first) % 4) * block_bytes
            dst = ((row // 4 * kb + kblock) * 4 + row % 4) * block_bytes
            result[dst:dst + block_bytes] = data[src:src + block_bytes]
    return bytes(result)


def audit_capture(capture, old):
    evidence = {}
    documents = []
    for directory, name, selected in (
        (capture, 'result.json', ('attn_norm-0_f32.bin', 'attn_v.bin')),
        (old, 'build.json', ('activation_0.bin', 'part_1_r4.bin',
                             'part_1_expected.bin', 'profiles.bin')),
    ):
        receipt = directory / name
        require(digest(receipt) == RECEIPTS[name], 'Original receipt identity mismatch')
        record = json.loads(receipt.read_text())
        evidence[str(receipt)] = digest(receipt)
        pins = directory / 'source-pins.json'
        require(digest(pins) == record['source_pins_sha256'], 'Original pins changed')
        evidence[str(pins)] = digest(pins)
        for filename in selected:
            p = directory / filename
            require(digest(p) == record['artifacts'][str(p)], 'Original artifact mismatch: ' + str(p))
            evidence[str(p)] = digest(p)
        if 'elf' in record:
            p = Path(record['elf'])
            require(digest(p) == record['elf_sha256'], 'Original ELF changed')
            evidence[str(p)] = digest(p)
        documents.append(record)
    cap, build = documents
    a = cap['activation']
    require(a['phase'] == 'decode' and a['position'] == 40 and a['rows'] == 1 and
            a['prompt_tokens'] == 40 and a['input_differs_from_prefill'] is True,
            'Not real position40 single-token Decode')
    require(build['m'] == 1 and build['n'] == 128 and build['profiles'][1] == 2 and
            build['k'][1] == 2048 and build['parts'][1] == 'attn_v' and
            Path(build['capture']) == capture, 'Wrong original operator scope')
    require((capture / 'attn_norm-0_f32.bin').stat().st_size == 2048*4,
            'Activation K was truncated')
    require((old / 'activation_0.bin').stat().st_size == 8*292 and
            (old / 'part_1_expected.bin').stat().st_size == 128*4,
            'Wrong original data dimensions')
    require((old / 'profiles.bin').read_bytes()[4:8] == (2).to_bytes(4, 'little'),
            'Part1 is not profile2')
    return evidence


class Builder:
    def __init__(self, output):
        self.output = output
        self.commands = []
        self.pins = {}

    def pin(self, path):
        p = Path(path).absolute()
        h = digest(p)
        require(str(p) not in self.pins or self.pins[str(p)] == h, 'Source drift: ' + str(p))
        self.pins[str(p)] = h

    def run(self, label, argv, cwd=None):
        argv = [str(v) for v in argv]
        self.commands.append(dict(label=label, argv=argv, cwd=str(cwd or ROOT)))
        write_json(self.output / 'commands.json', self.commands)
        executable = shutil.which(argv[0])
        if executable:
            self.pin(executable)
        p = subprocess.run(argv, cwd=cwd or ROOT, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, check=False, timeout=120)
        (self.output / (label + '.log')).write_bytes(p.stdout)
        require(p.returncode == 0, 'Failed ' + label + ': ' + p.stdout.decode(errors='replace')[-4000:])
        return p.stdout

    def archive(self, repo, commit, paths, destination):
        name = destination.name
        archive = self.output / (name + '.tar')
        # git archive is a build input, never an additional development worktree.
        self.run(name + '-archive', ['git', '-C', repo, 'archive', '--format=tar',
                                     '-o', archive, commit, *paths])
        destination.mkdir(parents=True)
        with tarfile.open(archive) as tar:
            for member in tar.getmembers():
                require(not Path(member.name).is_absolute() and '..' not in Path(member.name).parts,
                        'Unsafe archive path')
                require(member.isdir() or member.isfile(), 'Nonregular archive member')
            tar.extractall(destination)
        self.pin(archive)

    def compile(self, cc, flags, source, obj):
        dep = obj.with_suffix('.d')
        self.run('compile-' + obj.stem, [cc, *flags, '-MD', '-MF', dep,
                                        '-c', source, '-o', obj])
        # GCC make dependencies can wrap or escape whitespace.
        import shlex
        text = dep.read_text().replace('\\\n', '')
        for item in shlex.split(text.split(':', 1)[1]):
            self.pin(item)
        self.pin(obj)


def build(args):
    output = args.output.resolve()
    require(output.parent == OUT.resolve() and
            re.fullmatch(r'chain_q6_[A-Za-z0-9_]+_20261107_[A-Za-z0-9_]+', output.name),
            'Output must be a new authorized chain_q6_*_20261107_* directory')
    require(not output.exists(), 'Refusing to reuse a build directory or old objects')
    evidence = audit_capture(CAPTURE, OLD_BUILD)
    output.mkdir()
    b = Builder(output)
    b.pins.update(evidence)
    for p in HERE.iterdir():
        if p.is_file():
            b.pin(p)
    b.pin(ROOT / 'AGENTS.md')
    sdk_commit = b.run('sdk-head', ['git', '-C', ROOT, 'rev-parse', 'HEAD']).decode().strip()
    llama_commit = b.run('llama-head', ['git', '-C', args.llama, 'rev-parse', 'HEAD']).decode().strip()
    inputs = output / 'inputs'
    sdk = inputs / 'sdk'
    llama = inputs / 'llama'
    b.archive(ROOT, sdk_commit, ['software/qbs', 'apps/common',
                                'verification/qbs/qbs_ref.c', 'verification/qbs/qbs_ref.h'], sdk)
    b.archive(args.llama, llama_commit, ['ggml/include', 'ggml/src'], llama)
    patch = sdk / 'software/qbs/integrations/llama-decode-sums.patch'
    b.pin(patch)
    b.run('llama-registered-patch', ['git', 'apply', '--no-index', '--check', patch], cwd=llama)
    b.run('llama-apply-patch', ['git', 'apply', '--no-index', patch], cwd=llama)
    for path in (sdk, llama):
        for p in path.rglob('*'):
            if p.is_file():
                b.pin(p)
    data = output / 'data'
    data.mkdir()
    weights = crop_r4((OLD_BUILD / 'part_1_r4.bin').read_bytes())
    (data / 'weights_r4.bin').write_bytes(weights)
    shutil.copyfile(CAPTURE / 'attn_norm-0_f32.bin', data / 'input_f32.bin')
    host = output / 'host_ref'
    host_flags = ['-std=c11', '-O2', '-fno-fast-math', '-ffp-contract=off',
                  '-frounding-math', '-Wall', '-Wextra', '-Werror',
                  '-I' + str(sdk / 'verification/qbs')]
    for source, name in ((HERE / 'host_ref.c', 'host_main'),
                         (sdk / 'verification/qbs/qbs_ref.c', 'host_qbs_ref')):
        b.compile(args.host_cc, host_flags, source, output / (name + '.o'))
    b.run('host-link', [args.host_cc, output / 'host_main.o', output / 'host_qbs_ref.o',
                        '-lm', '-o', host])
    b.run('host-reference', [host, CAPTURE / 'attn_norm-0_f32.bin', CAPTURE / 'attn_v.bin',
                            OLD_BUILD / 'activation_0.bin', OLD_BUILD / 'part_1_r4.bin',
                            OLD_BUILD / 'part_1_expected.bin', data / 'weights_r4.bin', data])
    build_id = hashlib.sha256(json.dumps(dict(
        sources=b.pins, sdk=sdk_commit, llama=llama_commit,
        data={p.name: digest(p) for p in data.iterdir()}), sort_keys=True).encode()).hexdigest()
    config = output / 'profile_config.h'
    config.write_text('#define Q6_BUILD_ID "' + build_id + '"\n')
    asm = output / 'data.S'
    asm.write_text('.section .rodata\n' + ''.join(
        '.balign 64\n.global ' + sym + '_before\n' + sym + '_before:\n.fill 64,1,165\n' +
        '.global ' + sym + '\n' + sym + ':\n.incbin "' + str(data / file) + '"\n' +
        '.global ' + sym + '_after\n' + sym + '_after:\n.fill 64,1,165\n'
        for sym, file in (('profile_input', 'input_f32.bin'), ('profile_weights', 'weights_r4.bin'),
                          ('profile_q8_expected', 'activation_q8.bin'), ('profile_expected', 'expected.bin'))))
    cc = args.toolchain / 'riscv64-unknown-elf-gcc'
    objdump = args.toolchain / 'riscv64-unknown-elf-objdump'
    for name in ('cc1', 'as', 'ld'):
        tool = b.run('locate-' + name, [cc, '-print-prog-name=' + name]).decode().strip()
        b.pin(Path(tool) if Path(tool).is_file() else shutil.which(tool))
    for name in ('libc.a', 'libm.a', 'libgcc.a', 'libnosys.a'):
        lib = b.run('locate-' + name, [cc, '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d',
                                      '-print-file-name=' + name]).decode().strip()
        b.pin(lib)
    common = sdk / 'apps/common'
    flags = ['-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-mcmodel=medany', '-mno-relax',
             '-O3', '-DNDEBUG', '-fno-fast-math', '-ffp-contract=off', '-fno-tree-vectorize',
             '-ffunction-sections', '-fdata-sections', '-DNR_LANES=4', '-DVLEN=1024',
             '-I' + str(common), '-I' + str(output), '-I' + str(sdk / 'software/qbs/include')]
    ggml = llama / 'ggml'
    quant_flags = ['-I' + str(ggml / p) for p in
                   ('include', 'src', 'src/ggml-cpu', 'src/ggml-cpu/arch/riscv')]
    sources = [(HERE / 'main.c', 'main'), (asm, 'data'),
               (ggml / 'src/ggml-cpu/arch/riscv/quants.c', 'llama_rvv_quants')]
    sources += [(common / n, Path(n).stem) for n in
                ('crt0.S', 'printf.c', 'string.c', 'serial.c', 'util.c', 'print_trap_cause.c')]
    sources += [(sdk / 'software/qbs/src' / n, Path(n).stem) for n in
                ('qbs_runtime.c', 'qbs_native_riscv.c')]
    objects = []
    for source, name in sources:
        obj = output / (name + '.o')
        extra = quant_flags if name == 'llama_rvv_quants' else []
        if name == 'main':
            extra += ['-Wall', '-Wextra', '-Werror']
        if name == 'string':
            extra += ['-fno-builtin']
        b.compile(cc, flags + extra, source, obj)
        objects.append(obj)
    elf = output / 'q6_decode.elf'
    link = output / 'link.ld'
    b.run('linker-script', [cc, '-E', '-P', '-x', 'c', '-DALIGNMENT=16',
                            common / 'arch.link.ld', '-o', link])
    b.pin(link)
    b.run('link', [cc, *flags, '-static', '-nostartfiles', '-nostdlib', *objects,
                   '-Wl,--gc-sections', '-Wl,-Map=' + str(output / 'link.map'), '-T', link,
                   '-Wl,--start-group', '-lm', '-lc', '-lgcc', '-lnosys', '-Wl,--end-group', '-o', elf])
    disasm = b.run('disassembly', [objdump, '-d', elf]).decode()
    quant = b.run('quant-disassembly', [objdump, '-d', '--disassemble=quantize_row_q8_K', elf]).decode()
    require(all(s in quant for s in ('vle32.v', 'vse8.v', 'vwredsum.vs', 'vfcvt.x.f.v')),
            'Linked quantizer is not the actual RVV implementation')
    trial = b.run('trial-disassembly', [objdump, '-d', '--disassemble=q6_decode_trial', elf]).decode()
    require(len(re.findall(r'\bfence\b', trial)) == 1 and
            'quantize_row_q8_K' in trial and 'qbs_execute_with_options' in trial,
            'Trial boundary fence/call audit failed')
    require('qbs_native_execute_command' in disasm, 'Native SDK executor not linked')
    for p in data.iterdir():
        b.pin(p)
    for p in (config, asm, elf, output / 'commands.json', host):
        b.pin(p)
    for path, sha in b.pins.items():
        require(digest(path) == sha, 'Build input changed during compile: ' + path)
    write_json(output / 'source-pins.json', b.pins)
    receipt = dict(
        state='BUILT_NOT_EXECUTED', performance_measured=False, rtl_executed=False,
        elf=str(elf), elf_sha256=digest(elf), build_id=build_id,
        source_pins=str(output / 'source-pins.json'),
        source_pins_sha256=digest(output / 'source-pins.json'), post_pins_match=True,
        sdk_repo=str(ROOT), sdk_commit=sdk_commit, sdk_ref='main workspace HEAD (ara_dsa)',
        llama_repo=str(args.llama), llama_commit=llama_commit,
        llama_patch=str(patch), llama_patch_sha256=digest(patch),
        capture_scope=dict(model='Qwen3', tensor='blk.0.attn_v.weight', phase='decode',
                           position=40, prompt_tokens=40, m=1, k=2048, n=64, source_n=128,
                           weight_profile=2, trials=2, commands_per_trial=2,
                           command_m=1, command_n=32, command_k_blocks=8,
                           whole_model=False, full_ggml=False, capture=str(CAPTURE),
                           source_build=str(OLD_BUILD)),
        golden='Current independent host qbs_ref, audited bit-exact against original first64',
        quantization='Actual llama RVV quantize_row_q8_K + SDK registered decode-sums patch',
        q8_bytes=2336, expected=str(data / 'expected.bin'), q8_expected=str(data / 'activation_q8.bin'),
        reused_objects=0, rebuilt_runtime_objects=len(objects),
        rebuilt_objects=[str(p) for p in objects],
        timing=dict(prep='Real full-K RVV quantization', admit='device query, encoding bind, plan, context admission',
                    execute='One qbs_execute_with_options, native pre-command fences/vsetvli/stores included',
                    drain='One final fence rw,rw per trial', intermediate_fences_added=0,
                    cold_weight_repack_included=False, uart_and_checks_outside_roi=True,
                    repeat='Same input/weights/work buffers; post-ROI snapshots/checks between calls; no cache flush'),
        memory_contract='Flat simulation RAM only, single blocking worker, Xaraqbs presence externally established; no FPGA NORMAL_MEMORY assertion',
        linker_contract='Archived apps/common/arch.link.ld, ALIGNMENT=16, 1MiB image region; stack reads owner SoC DRAM end',
        checker_entry=[sys.executable, '-B', str(HERE / 'check.py'), '--build', str(output / 'build.json'),
                       '--log', '<run.vcs.log>', '--output', '<new authorized output.json>'],
        checker_api='check_run(log_path: Path, build_dir: Path) -> dict',
        checker_scope='PASS requires full scope, bit-exact outputs/full Q8, CSR, raw guards, SDK call work and native counters/ROI; owner separately checks protocol and SoC image',
        artifacts={str(p): digest(p) for p in [elf, *data.iterdir(), output / 'commands.json',
                                              output / 'host-reference.log', output / 'quant-disassembly.log',
                                              output / 'trial-disassembly.log']})
    write_json(output / 'build.json', receipt)
    print(json.dumps(dict(build=str(output / 'build.json'), elf=str(elf), elf_sha256=digest(elf),
                          state=receipt['state']), indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--llama', type=Path, default=LLAMA)
    p.add_argument('--toolchain', type=Path, default=TOOLCHAIN)
    p.add_argument('--host-cc', default='/usr/bin/gcc')
    try:
        build(p.parse_args())
    except (ValueError, OSError, subprocess.SubprocessError) as e:
        raise SystemExit(str(e)) from e


if __name__ == '__main__':
    main()
