#!/usr/bin/env python3
"""Build a real-input M4/M8 SDK projection pair; no simulator is launched."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
CAPTURE = OUT / 'stage2_qwen3_rows8_20261109_02'
BASE = ROOT / 'verification/performance/chain_profile/q6_decode/build.py'
LLAMA = Path('/home/wangwy/llama/llama.cpp')
TOOLCHAIN = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin')


def load_helper():
    spec = importlib.util.spec_from_file_location('projection_build_helper', BASE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def captured_inputs(operator, digest):
    receipt = json.loads((CAPTURE / 'result.json').read_text())
    if (receipt.get('state'), receipt.get('source_pins_match'), receipt.get('rows'), receipt.get('k')) != (
            'CAPTURED_NOT_BENCHMARKED', True, 8, 2048):
        raise ValueError('Eight-row real capture was not accepted')
    directory = CAPTURE / operator
    meta = json.loads((directory / 'operator.json').read_text())
    if meta not in receipt['views'] or meta['captured_weight_shape'] != [2048, 128] or (
            meta['activation_shape'] != [2048, 8] or meta['profile'] != 'Q4_K' or meta['distinct_rows'] != 8):
        raise ValueError('Capture geometry/type differs')
    for name, key in (('activation_f32.bin', 'activation_sha256'), ('weight_q4_K.bin', 'weight_sha256')):
        if digest(directory / name) != meta[key]:
            raise ValueError('Captured tensor changed: ' + name)
    return directory, meta


def build(args):
    base = load_helper()
    out = args.output.resolve()
    base.require(out.parent == OUT and not out.exists(), 'Fresh direct signoff output required')
    directory, meta = captured_inputs(args.operator, base.digest)
    out.mkdir()
    b = base.Builder(out)
    for path in (Path(__file__), HERE / 'projection_main.c', HERE / 'projection_host.c', BASE,
                 CAPTURE / 'result.json', directory / 'operator.json', directory / 'activation_f32.bin',
                 directory / 'weight_q4_K.bin'):
        b.pin(path)
    sdk_revision = b.run('sdk-head', ['git', '-C', ROOT, 'rev-parse', 'HEAD']).decode().strip()
    llama_revision = b.run('llama-head', ['git', '-C', LLAMA, 'rev-parse', 'HEAD']).decode().strip()
    sdk, llama = out / 'inputs/sdk', out / 'inputs/llama'
    b.archive(ROOT, sdk_revision, ['software/qbs', 'apps/common',
              'verification/qbs/qbs_ref.c', 'verification/qbs/qbs_ref.h'], sdk)
    b.archive(LLAMA, llama_revision, ['ggml/include', 'ggml/src'], llama)
    patch = sdk / 'software/qbs/integrations/llama-decode-sums.patch'
    b.run('llama-patch-check', ['git', 'apply', '--no-index', '--check', patch], cwd=llama)
    b.run('llama-patch', ['git', 'apply', '--no-index', patch], cwd=llama)
    for tree in (sdk, llama):
        for path in tree.rglob('*'):
            if path.is_file():
                b.pin(path)
    data = out / 'data'
    data.mkdir()
    host_flags = ['-std=c11', '-O2', '-fno-fast-math', '-ffp-contract=off', '-frounding-math',
                  '-Wall', '-Wextra', '-Werror', '-I' + str(sdk / 'verification/qbs')]
    for source, name in ((HERE / 'projection_host.c', 'host'),
                         (sdk / 'verification/qbs/qbs_ref.c', 'reference')):
        b.compile('/usr/bin/gcc', host_flags, source, out / (name + '.o'))
    host = out / 'host_ref'
    b.run('host-link', ['/usr/bin/gcc', out / 'host.o', out / 'reference.o', '-lm', '-o', host])
    b.run('host-reference', [host, directory / 'activation_f32.bin', directory / 'weight_q4_K.bin', args.n, data])
    build_id = hashlib.sha256(json.dumps(dict(sources=b.pins, sdk=sdk_revision, llama=llama_revision,
                  operator=args.operator, n=args.n), sort_keys=True).encode()).hexdigest()
    config = out / 'projection_config.h'
    config.write_text(f'#define PROJECTION_N {args.n}\n#define PROJECTION_ID "{build_id}"\n')
    assembly = out / 'data.S'
    assembly.write_text('.section .rodata\n' + ''.join(
        f'.balign 64\n.global {symbol}\n{symbol}:\n.incbin "{data / name}"\n'
        for symbol, name in (('projection_input', 'input_f32.bin'), ('projection_weights', 'weights_r4.bin'),
                            ('projection_expected_q8', 'expected_q8.bin'), ('projection_expected', 'expected.bin'),
                            ('projection_flags', 'flags.bin'))))
    cc, objdump = TOOLCHAIN / 'riscv64-unknown-elf-gcc', TOOLCHAIN / 'riscv64-unknown-elf-objdump'
    for name in ('cc1', 'as', 'ld'):
        path = b.run('locate-' + name, [cc, '-print-prog-name=' + name]).decode().strip()
        b.pin(Path(path) if Path(path).is_file() else shutil.which(path))
    for name in ('libc.a', 'libm.a', 'libgcc.a', 'libnosys.a'):
        path = b.run('locate-' + name, [cc, '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d',
                                       '-print-file-name=' + name]).decode().strip()
        b.pin(path)
    common = sdk / 'apps/common'
    flags = ['-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-mcmodel=medany', '-mno-relax',
             '-O3', '-DNDEBUG', '-fno-fast-math', '-ffp-contract=off', '-fno-tree-vectorize',
             '-ffunction-sections', '-fdata-sections', '-DNR_LANES=4', '-DVLEN=1024',
             '-I' + str(common), '-I' + str(out), '-I' + str(sdk / 'software/qbs/include')]
    ggml = llama / 'ggml'
    quant_flags = ['-I' + str(ggml / path) for path in
                   ('include', 'src', 'src/ggml-cpu', 'src/ggml-cpu/arch/riscv')]
    sources = [(HERE / 'projection_main.c', 'main'), (assembly, 'data'),
               (ggml / 'src/ggml-cpu/arch/riscv/quants.c', 'quantizer')]
    sources += [(common / name, Path(name).stem) for name in
                ('crt0.S', 'printf.c', 'string.c', 'serial.c', 'util.c', 'print_trap_cause.c')]
    sources += [(sdk / 'software/qbs/src' / name, Path(name).stem) for name in
                ('qbs_runtime.c', 'qbs_native_riscv.c')]
    objects = []
    for source, name in sources:
        extra = quant_flags if name == 'quantizer' else []
        if name == 'main':
            extra += ['-Wall', '-Wextra', '-Werror']
        if name == 'string':
            extra += ['-fno-builtin']
        obj = out / (name + '.o')
        b.compile(cc, flags + extra, source, obj)
        objects.append(obj)
    link = out / 'link.ld'
    b.run('linker-script', [cc, '-E', '-P', '-x', 'c', '-DALIGNMENT=16', common / 'arch.link.ld', '-o', link])
    elf = out / 'projection.elf'
    b.run('link', [cc, *flags, '-static', '-nostartfiles', '-nostdlib', *objects,
                   '-Wl,--gc-sections', '-Wl,-Map=' + str(out / 'link.map'), '-T', link,
                   '-Wl,--start-group', '-lm', '-lc', '-lgcc', '-lnosys', '-Wl,--end-group', '-o', elf])
    quant = b.run('quant-disassembly', [objdump, '-d', '--disassemble=quantize_row_q8_K', elf]).decode()
    base.require(all(op in quant for op in ('vle32.v', 'vse8.v', 'vwredsum.vs', 'vfcvt.x.f.v')),
                 'Expected actual RVV quantizer missing')
    trial = b.run('trial-disassembly', [objdump, '-d', '--disassemble=projection_trial', elf]).decode()
    base.require('quantize_row_q8_K' in trial and 'qbs_execute_with_options' in trial and
                 len(re.findall(r'\bfence\b', trial)) == 1, 'Unexpected trial boundaries/calls')
    for path in (host, config, assembly, elf, link, out / 'commands.json', *data.iterdir()):
        b.pin(path)
    for path, digest in b.pins.items():
        base.require(base.digest(path) == digest, 'Source changed during build: ' + path)
    base.write_json(out / 'source-pins.json', b.pins)
    base.write_json(out / 'build.json', dict(state='BUILT_NOT_EXECUTED', elf=str(elf),
        elf_sha256=base.digest(elf), build_id=build_id, sdk_revision=sdk_revision, llama_revision=llama_revision,
        source_pins_sha256=base.digest(out / 'source-pins.json'), post_pins_match=True,
        operator=args.operator, capture=str(CAPTURE), provenance=meta, m=8, k=2048, n=args.n,
        trials=[4, 8, 8, 4], golden='Independent ordered qbs_ref; no captured GGML projection golden',
        context_replay=False, context_note='M4/M8 full-K activation bytes exceed unchanged 4672-byte context',
        cold_weight_repack_in_roi=False, quant_pack_plan_execute_drain_in_roi=True,
        full_software_call=True, whole_model=False, full_output_width=args.n == meta['original_weight_shape'][1],
        software_outputs=8*args.n, rtl_executed=False, performance_measured=False))
    print('BUILT_NOT_EXECUTED ' + str(out / 'build.json'), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('output', type=Path)
    parser.add_argument('--operator', choices=('attn_q', 'ffn_gate'), required=True)
    parser.add_argument('--n', type=int, choices=(32, 64, 96, 128), required=True)
    build(parser.parse_args())
