#!/usr/bin/env python3
"""Fresh archive-only SDK build. This module never invokes a simulator."""
import argparse
import hashlib
import io
import json
import re
import shlex
import struct
import subprocess
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
DATA = OUT / 'e2e_qwen3_f16_native_data_20261106_02'
CAPTURE = OUT / 'e2e_qwen3_f16_attention_capture_20261106_01'
SDK_COMMIT = '785084122af984c1dd3fd6318efaf70cdcb017e8'
SDK_TREE = '099017ee4f6543417e4d666a5e0958ce175defe5'
COMMON_TREE = '027626ca2e2524cafbcb61b5b44b70fce9ec1cff'
CC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
HOST_CC = Path('/usr/bin/clang')
OWN_FILES = ('build.py', 'main.c', 'check.py', 'test_eval.py', 'reference.c')
ORDER = [0, 1, 1, 0]
FILES = {'decode_query': 1024, 'decode_query_f16': 512, 'decode_key': 65536,
         'decode_value': 65536, 'decode_mask': 512, 'decode_golden': 1024}
DATA_SHA = dict(zip(FILES, (
    '41b57646f533871b4451ac59551a4dee06612380bb7761142b66a189625b4d77',
    '24bdf29c0111f117fdb3ec460de88b96740e3a26b81e456e4d5be0d7ea4c4b99',
    '5d14e468e7788e589bccd0b504f1d32d8b9401a020ac0089ef9debccb4d6695f',
    '64ae74fda7068fb06023c0c5333ac8227804067797cf6d2b9b0d623b0159b369',
    '93a3f03c46a985eed8e4e7fed4db158d1cad01bafc33ea6220eff7efbb9aff10',
    '908ccb771f8f03340e068512a2c826a89bfb8d94b170707497d7f5bd3d62868d')))
RECEIPT_SHA = '0fb5797dfed0d5d6bfaaf1e7b611f110b9b0a625fa1b67977ba86ce7a9e3581a'
DATA_PINS_SHA = 'd5b1da65ed2e689b02a82b9695c70a3a36331067927d0abb1a495bb7ddebde1d'
CAPTURE_SHA = 'd4ab9d3cd381a5e8831a7fe7cf9300f82cfc121d53f83868dfa4eab57dd1e985'
CAPTURE_PINS_SHA = '0d6fec94f66397ac469547b8c35a0772b686e02ae2c75cb94d3ccff0e2b17579'
NATIVE_SHA = '0be0c9b07fdbd8773ec85ef2b738bbcc65f657f322d65e77610609c968ee9316'
SHAPE = dict(batches=1, query_tokens=1, query_heads=2, kv_heads=1, head_dim=128,
             query_head_indices=[0, 1], kv_head_index=0, valid_tokens=137,
             kv_capacity=256, tile_tokens=64, tile_lengths=[64, 64, 9],
             output_elements=256, qk_scalar_fmas=2*137*128, pv_scalar_fmas=2*137*128)
IMAGE = dict(NrLane=4, VLEN=1024, AXI=128, L2sim_bytes=16*1024*1024,
             shared_integer_multiply=True, EnableSharedFma=0)


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fnv64(data):
    value = 14695981039346656037
    for byte in data:
        value = ((value ^ byte) * 1099511628211) & ((1 << 64) - 1)
    return value


# Includes all six outer guards, both raw-data guards, inactive workspace rows,
# D128 accumulator tails, and the SDK workspace's 32-byte trailing alignment gap.
MEMORY = dict(data_bytes=135168, data_hash=0x85ecf7bcc9e93f0e,
              query_hash=0x45ef121f05e2a5e9, guard_bytes=5736,
              guard_hash=fnv64(bytes([0xa5])*5736))


def validate_data(directory=DATA, capture=CAPTURE):
    directory, capture = Path(directory), Path(capture)
    checked = {}

    def pin(path, expected):
        require(path.is_file() and sha(path) == expected, 'Data identity: ' + str(path))
        checked[str(path.resolve())] = expected

    pin(directory / 'result.json', RECEIPT_SHA)
    pin(directory / 'source-pins.json', DATA_PINS_SHA)
    pin(capture / 'result.json', CAPTURE_SHA)
    pin(capture / 'source-pins.json', CAPTURE_PINS_SHA)
    receipt = json.loads((directory / 'result.json').read_text())
    phase = receipt['phases']['decode']
    require(all(phase[k] == v for k, v in dict(query_tokens=1, query_heads=2,
        kv_heads=1, head_dim=128, kv_capacity=256, visible_prefixes=[137],
        mapped_head_indices=[0, 1], mapped_kv_head_index=0).items()) and
        receipt['scale_bits'] == 1035273459, 'Capture shape/head/scale mismatch')
    for name, size in FILES.items():
        p = directory / (name + '.bin')
        pin(p, DATA_SHA[name])
        require(p.stat().st_size == size, 'Data size: ' + name)
        require(receipt['artifacts'][str(DATA / p.name)] == DATA_SHA[name], 'Receipt mismatch')
    q = struct.unpack('<256f', (directory / 'decode_query.bin').read_bytes())
    require(b''.join(struct.pack('<e', x) for x in q) ==
            (directory / 'decode_query_f16.bin').read_bytes(), 'Q conversion mismatch')
    mask = struct.unpack('<256e', (directory / 'decode_mask.bin').read_bytes())
    require(all(x == 0 for x in mask[:137]) and
            all(x == -float('inf') for x in mask[137:]), 'Mask mismatch')
    original = json.loads((capture / 'result.json').read_text())['artifacts']
    block = capture / 'capture/decode/block'
    for dst, role, heads, tokens in (
        ('decode_query', 'attn_q_input', 2, 1), ('decode_key', 'attn_k_input', 1, 256),
        ('decode_value', 'attn_v_input', 1, 256), ('decode_golden', 'kqv_out', 2, 1),
        ('decode_mask', 'attn_mask_input', 1, 1)):
        for suffix in ('.json', '.bin'):
            p = block / (role + '-0' + suffix)
            pin(p, original[str(CAPTURE / 'capture/decode/block' / p.name)])
        meta = json.loads((block / (role + '-0.json')).read_text())
        raw = (block / (role + '-0.bin')).read_bytes()
        size = 4 if dst in ('decode_query', 'decode_golden') else 2
        require(meta['type'] == ('f32' if size == 4 else 'f16') and
                len(raw) == meta['nbytes'], 'Capture dtype/size mismatch')
        if dst == 'decode_mask':
            mapped = raw[:512]
        else:
            mapped = bytearray()
            for head in range(heads):
                for token in range(tokens):
                    offset = (head * 128 * size + token * meta['strides'][1]
                              if dst == 'decode_golden' else
                              token * meta['strides'][1] + head * meta['strides'][2])
                    mapped.extend(raw[offset:offset + 128*size])
        require(mapped == (directory / (dst + '.bin')).read_bytes(), 'Capture mapping: ' + dst)
    return checked


def memory_expected(data=DATA):
    require(fnv64((Path(data) / 'decode_query_f16.bin').read_bytes()) == MEMORY['query_hash'],
            'Frozen query FNV mismatch')
    return dict(MEMORY)


def expected_header(memory):
    return ''.join('#define PAIR_EXPECT_' + key.upper() + ' UINT64_C(0x%x)\n' % value
                   for key, value in memory.items())


def data_assembly(data, native):
    lines = ['.section .rodata.akv_pair,"a",@progbits', '.balign 64',
             '.global data_guard_before', 'data_guard_before:', '.fill 64,1,0xa5',
             '.global data_begin', 'data_begin:']
    for name in [*FILES, 'native_golden']:
        p = native if name == 'native_golden' else data / (name + '.bin')
        lines += ['.balign 64', '.global ' + name, name + ':', '.incbin ' + json.dumps(str(p))]
    lines += ['.global data_end', 'data_end:', '.global data_guard_after',
              'data_guard_after:', '.fill 64,1,0xa5', '.section .note.GNU-stack,"",@progbits']
    return '\n'.join(lines) + '\n'


def unpack_archive(archive, inputs):
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        members = tar.getmembers()
        require(all((m.isfile() or m.isdir()) and not Path(m.name).is_absolute() and
                    '..' not in Path(m.name).parts for m in members), 'Unsafe archive')
        tar.extractall(inputs, filter='data')


def dependency_inputs(path):
    text = Path(path).read_text().replace('\\\n', ' ')
    require(': ' in text, 'Malformed compiler dependency inventory')
    return [Path(p).resolve() for p in shlex.split(text.split(': ', 1)[1])]


def build(output, cc=CC, data=DATA):
    output, cc, data = Path(output).resolve(), Path(cc).resolve(), Path(data).resolve()
    require(output.parent == OUT.resolve() and
            re.fullmatch(r'akv_pair_eval_build_\d{8}_\w+', output.name), 'Output ownership restriction')
    require(not output.exists(), 'Use a fresh output directory')
    require(cc == CC.resolve(), 'Only the pinned GNU install/riscv-gcc is allowed')
    require(data == DATA.resolve(), 'Only the accepted real data is allowed')
    pins = validate_data(data)
    pins.update({str(HERE / name): sha(HERE / name) for name in OWN_FILES})

    def git(*args):
        return subprocess.check_output(['git', '-C', str(ROOT), *args])

    require(git('rev-parse', SDK_COMMIT + ':software/akv').decode().strip() == SDK_TREE and
            git('rev-parse', SDK_COMMIT + ':apps/common').decode().strip() == COMMON_TREE and
            git('rev-parse', '640862d2d:software/akv').decode().strip() == SDK_TREE,
            'SDK/runtime version contract drift')
    output.mkdir(parents=True)
    inputs = output / 'inputs'
    inputs.mkdir()
    archive = git('archive', SDK_COMMIT, 'software/akv', 'apps/common')
    archive_file = inputs / 'sdk-785084122.tar'
    archive_file.write_bytes(archive)
    unpack_archive(archive, inputs)
    sdk, common = inputs / 'software/akv', inputs / 'apps/common'
    sdk_pins = {str(p.relative_to(inputs)): sha(p) for p in sdk.rglob('*') if p.is_file()}
    pins.update({str(p): sha(p) for p in inputs.rglob('*') if p.is_file()})
    commands = []

    def run(label, argv):
        argv = list(map(str, argv))
        proc = subprocess.run(argv, cwd=output, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, timeout=180, env=None)
        log = output / (label + '.log')
        log.write_text(proc.stdout)
        commands.append(dict(label=label, argv=argv, cwd=str(output),
                             returncode=proc.returncode, log=str(log)))
        (output / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        require(proc.returncode == 0, label + ' failed: ' + proc.stdout[-3000:])
        return proc.stdout.strip()

    for tool in (cc, HOST_CC.resolve()):
        pins[str(tool)] = sha(tool)
    run('gnu-version', [cc, '--version'])
    run('clang-version', [HOST_CC, '--version'])
    run('hosttests', [sys.executable, '-B', HERE / 'test_eval.py', '-v'])
    run('reference-compile', [HOST_CC, '-std=gnu11', '-O2', '-fno-fast-math',
        '-ffp-contract=off', '-MD', '-MF', output / 'reference.d', HERE / 'reference.c',
        '-lm', '-o', output / 'reference'])
    native = output / 'native_golden.bin'
    run('reference-run', [output / 'reference', data, native])
    require(sha(native) == NATIVE_SHA, 'Native tile64 oracle drift')
    memory = memory_expected(data)
    require(fnv64(b''.join((data / (n + '.bin')).read_bytes() for n in FILES) +
                  native.read_bytes()) == memory['data_hash'], 'Frozen full-data FNV mismatch')
    (output / 'expected.h').write_text(expected_header(memory))
    (output / 'data.S').write_text(data_assembly(data, native))
    linker = (common / 'arch.link.ld').read_text()
    require(linker.count('LENGTH = 0x00100000') == 1, 'Linker template drift')
    (output / 'link.ld').write_text(linker.replace('ALIGNMENT', '16').replace(
        'LENGTH = 0x00100000', 'LENGTH = 0x01000000'))
    flags = ['-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-mcmodel=medany', '-mno-relax',
             '-O3', '-DNDEBUG', '-fno-fast-math', '-ffp-contract=off', '-fno-tree-vectorize',
             '-ffunction-sections', '-fdata-sections', '-std=gnu11', '-Wall', '-Wextra',
             '-Wno-unknown-pragmas', '-DNR_LANES=4', '-DVLEN=1024', '-DAKV_REFILL_OVERLAP=0',
             '-I' + str(sdk / 'include'), '-I' + str(common), '-I' + str(output)]
    for lib in ('libm.a', 'libc.a', 'libgcc.a', 'libnosys.a'):
        p = Path(run('locate-' + lib, [cc, *flags[:2], '-print-file-name=' + lib])).resolve()
        pins[str(p)] = sha(p)
    for tool in ('cc1', 'as', 'ld'):
        p = Path(run('locate-' + tool, [cc, '-print-prog-name=' + tool])).resolve()
        pins[str(p)] = sha(p)
    sources = [HERE / 'main.c', output / 'data.S',
               *[common / n for n in ('crt0.S', 'printf.c', 'string.c', 'serial.c',
                                      'util.c', 'print_trap_cause.c')],
               *[sdk / 'src' / n for n in ('akv_runtime.c', 'akv_decode.c', 'akv_features.c',
                   'akv_prefill_reference.c', 'akv_native_riscv.c', 'akv_v2_native_riscv.c',
                   'akv_v2_attention_rvv.S', 'akv_attention_rvv.S')]]
    objects = []
    for index, source in enumerate(sources):
        obj = output / ('%02d_%s.o' % (index, source.stem))
        require(not obj.exists(), 'Refusing old object')
        extra = (['-ffreestanding', '-fno-builtin', '-fno-tree-loop-distribute-patterns']
                 if source.name == 'string.c' else [])
        run('compile-' + obj.stem, [cc, *flags, *extra, '-MD', '-MF', obj.with_suffix('.d'),
                                    '-c', source, '-o', obj])
        objects.append(obj)
    elf = output / 'akv_pair_eval.elf'
    run('link', [cc, *flags[:4], '-static', '-nostdlib', '-nostartfiles', *objects,
        '-Wl,--gc-sections', '-Wl,-Map=' + str(output / 'link.map'), '-T', output / 'link.ld',
        '-Wl,--start-group', '-lm', '-lc', '-lgcc', '-lnosys', '-Wl,--end-group', '-o', elf])
    for label, tool, args in [('disassembly', 'objdump', ['-d']), ('segments', 'readelf', ['-lW'])]:
        binary = cc.with_name(cc.name.replace('gcc', tool))
        pins[str(binary.resolve())] = sha(binary)
        run(label, [binary, *args, elf])
    for depfile in output.glob('*.d'):
        for p in dependency_inputs(depfile):
            digest = sha(p)
            require(str(p) not in pins or pins[str(p)] == digest, 'Compiler input drift')
            pins[str(p)] = digest
    for name in ('expected.h', 'data.S', 'link.ld', 'native_golden.bin'):
        pins[str(output / name)] = sha(output / name)
    require(all(sha(p) == digest for p, digest in pins.items()), 'Input drift during build')
    pinfile = output / 'source-pins.json'
    pinfile.write_text(json.dumps(pins, indent=2, sort_keys=True) + '\n')
    manifest = dict(schema=1, state='BUILT_NOT_EXECUTED', target_executed=False,
        rtl_executed=False, performance_measured=False, elf=str(elf), elf_sha256=sha(elf),
        source_pins=str(pinfile), source_pins_sha256=sha(pinfile), sdk_head=SDK_COMMIT,
        sdk_tree=SDK_TREE, common_tree=COMMON_TREE, SDKpins=sdk_pins,
        sdk_archive=str(archive_file), sdk_archive_sha256=sha(archive_file),
        dirty_asm_excluded=True, sdk_unmodified=True, all_runtime_objects_recompiled=True,
        objects_recompiled=len(objects), objects=list(map(str, objects)),
        compile_commands=str(output / 'commands.json'), shape=SHAPE, order=ORDER,
        memory_expected=memory, image_contract=IMAGE, data=str(data), capture=str(CAPTURE),
        toolchain=dict(target=str(cc), host=str(HOST_CC), zcc=False),
        environment=dict(AKV_PAIR_HEADS='trial 0/1/1/0; all other names return NULL'),
        initial_csr=dict(fcsr=0, vcsr=0, vstart=0),
        total_roi='F32->F16 Q conversion + device query + decode plan/execute + final drain',
        instrumentation='None in SDK; four complete uninstrumented native calls',
        required_plusargs=['+AKV_PERF', '+AKV_SUMMARY', '+VECTOR_TRACE=<path>'],
        golden=dict(captured=str(data / 'decode_golden.bin'),
                    captured_sha256=DATA_SHA['decode_golden'], native_tile64=str(native),
                    native_tile64_sha256=NATIVE_SHA, capture_atol=0.003, capture_rtol=0.02,
                    native_atol=0.0002, native_rtol=0.003),
        checker=dict(entry=str(HERE / 'check.py'), function='check_run(log_path, build_dir)',
                     required_vector_api='check_vector_workcounts(vector_trace_path, build_dir)',
                     independent_image_and_uvm_required=True),
        artifacts={str(p): sha(p) for p in sorted(output.rglob('*')) if p.is_file()})
    (output / 'build.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cc', type=Path, default=CC)
    args = parser.parse_args()
    result = build(args.output, args.cc)
    print(json.dumps({k: result[k] for k in ('state', 'elf', 'elf_sha256', 'sdk_head')}))


if __name__ == '__main__':
    main()
