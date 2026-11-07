#!/usr/bin/env python3
"""Prepare a fresh, archive-pinned F16 Decode ELF. Never starts an RTL tool."""
import argparse
import hashlib
import io
import json
import re
import struct
import subprocess
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
DATA = OUT / 'e2e_qwen3_f16_native_data_20261106_02'
CAPTURE = OUT / 'e2e_qwen3_f16_attention_capture_20261106_01'
CC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
HOST_CC = Path('/usr/bin/clang')
FILES = {'decode_query': 1024, 'decode_query_f16': 512, 'decode_key': 65536,
         'decode_value': 65536, 'decode_mask': 512, 'decode_golden': 1024}
SHAPE = dict(batches=1, query_tokens=1, query_heads=2, kv_heads=1, head_dim=128,
             query_head_indices=[0, 1], kv_head_index=0,
             valid_tokens=137, kv_capacity=256, tile_tokens=64,
             tile_lengths=[64, 64, 9], full=1, refill=2, release=1,
             qk_scalar_fmas=2*137*128, pv_scalar_fmas=2*137*128,
             k_column_commands=2*128*3, v_row_commands=2*137,
             score_elements=2*137, output_elements=256)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fnv64(data):
    value = 14695981039346656037
    for byte in data:
        value = ((value ^ byte) * 1099511628211) & ((1 << 64) - 1)
    return value


def require(value, message):
    if not value:
        raise ValueError(message)


def instrument(source):
    """Exact additive edits, confined to the original nonsegmented Decode path."""
    first = source.index('akv_status_t akv_attention_execute_v2_with_features_native(')
    last = source.index('\nakv_status_t akv_attention_execute_v2_native(', first)
    body = source[first:last]
    edits = []

    def add(anchor, inserted, before=True):
        nonlocal body
        require(body.count(anchor) == 1, 'SDK observation anchor changed: ' + anchor)
        replacement = inserted + anchor if before else anchor + inserted
        body = body.replace(anchor, replacement)
        edits.append((replacement, anchor))

    add('    if (tile_start == 0u)\n',
        '    const unsigned f16_slot = (tile_start / AKV_V2_TILE_TOKENS) * 4u;\n'
        '    F16_BEGIN(f16_slot);\n')
    add('      issue_refill(tile_start);\n',
        '    F16_END(f16_slot);\n    F16_BEGIN(f16_slot + 1u);\n', False)
    add('    apply_scale_mask_and_softmax(mask_bits, scale, workspace, tile_start,\n',
        '    F16_END(f16_slot + 1u);\n    F16_BEGIN(f16_slot + 2u);\n')
    add('                                 tile_tokens, q_rows, features);\n',
        '    F16_END(f16_slot + 2u);\n    F16_BEGIN(f16_slot + 3u);\n', False)
    add('          workspace->old_scale, tile_tokens, q_rows, head_dim);\n    }\n',
        '    F16_END(f16_slot + 3u);\n', False)
    add('  issue_release();\n', '  F16_BEGIN(12);\n')
    add('  store_outputs(output, output_row_stride_bytes, workspace, q_rows, head_dim);\n',
        '  F16_END(12);\n', False)
    restored = body
    for replacement, anchor in reversed(edits):
        require(restored.count(replacement) == 1, 'Ambiguous reverse edit')
        restored = restored.replace(replacement, anchor)
    require(restored == source[first:last], 'Non-additive SDK transform')
    transformed = '#include "probe.h"\n' + source[:first] + body + source[last:]
    require(transformed.count('fence') == source.count('fence'), 'Added a fence')
    return transformed, dict(reversible=True, edits=len(edits),
                             arithmetic_unchanged=True, added_fences=0,
                             source_sha256=hashlib.sha256(source.encode()).hexdigest())


def validate_data(directory, capture=CAPTURE):
    receipt = json.loads((directory / 'result.json').read_text())
    phase = receipt['phases']['decode']
    require((phase['head_dim'], phase['query_heads'], phase['kv_heads'],
             phase['visible_prefixes'], phase['kv_capacity']) == (128, 2, 1, [137], 256),
            'Not the original Decode137 capture')
    require(receipt['scale_bits'] == 1035273459, 'Scale contract changed')
    for name, size in FILES.items():
        p = directory / (name + '.bin')
        require(p.stat().st_size == size and
                receipt['artifacts'].get(str(p)) == sha(p), 'Data identity: ' + name)
    q = struct.unpack('<256f', (directory / 'decode_query.bin').read_bytes())
    require(b''.join(struct.pack('<e', x) for x in q) ==
            (directory / 'decode_query_f16.bin').read_bytes(), 'Q conversion mismatch')
    mask = struct.unpack('<256e', (directory / 'decode_mask.bin').read_bytes())
    require(all(x == 0 for x in mask[:137]) and all(x == -float('inf') for x in mask[137:]),
            'Visible137 mask mismatch')
    # Recheck the original GGML strided source, not only a materializer receipt.
    block = capture / 'capture/decode/block'
    for dst, role, heads, count in [('decode_query', 'attn_q_input', 2, 1),
                                    ('decode_key', 'attn_k_input', 1, 256),
                                    ('decode_value', 'attn_v_input', 1, 256),
                                    ('decode_golden', 'kqv_out', 2, 1)]:
        meta = json.loads((block / (role + '-0.json')).read_text())
        raw = (block / (role + '-0.bin')).read_bytes()
        itemsize = 4 if dst in ('decode_query', 'decode_golden') else 2
        rows = []
        for h in range(heads):
            for token in range(count):
                # GGML Q/K/V: [D, token, head, batch]; output: [D, head, token, batch].
                offset = (h * 128 * itemsize + token * meta['strides'][1]
                          if dst == 'decode_golden' else
                          token * meta['strides'][1] + h * meta['strides'][2])
                rows.append(raw[offset:offset + 128 * itemsize])
        require(b''.join(rows) == (directory / (dst + '.bin')).read_bytes(),
                'Original capture mapping mismatch: ' + dst)
    raw_mask = (block / 'attn_mask_input-0.bin').read_bytes()
    require(raw_mask[:512] == (directory / 'decode_mask.bin').read_bytes(), 'Capture mask mismatch')
    return receipt


def build(output, cc=CC, data=DATA):
    output = output.resolve()
    require(output.parent == OUT.resolve() and
            re.fullmatch(r'chain_f16_\w+_20261107_\w+', output.name), 'Output ownership restriction')
    require(not output.exists(), 'Use a fresh build directory')
    validate_data(data)
    head = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    output.mkdir(parents=True)
    inputs = output / 'inputs'
    inputs.mkdir()
    archive = subprocess.check_output(['git', '-C', str(ROOT), 'archive', head,
                                       'software/akv', 'apps/common'])
    archive_file = inputs / 'main-head.tar'
    archive_file.write_bytes(archive)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        members = tar.getmembers()
        require(all(m.isfile() or m.isdir() for m in members), 'Unexpected archive link')
        require(all(not Path(m.name).is_absolute() and '..' not in Path(m.name).parts
                    for m in members), 'Unsafe archive member')
        tar.extractall(inputs, filter='data')
    sdk = inputs / 'software/akv'
    common = inputs / 'apps/common'
    sdk_pins = {str(p.relative_to(inputs)): sha(p) for p in sorted(sdk.rglob('*')) if p.is_file()}
    source_pins = {str(p): sha(p) for p in sorted(HERE.rglob('*'))
                   if p.is_file() and '__pycache__' not in p.parts}
    for p in sorted(inputs.rglob('*')):
        if p.is_file(): source_pins[str(p)] = sha(p)
    for name in FILES:
        p = data / (name + '.bin')
        source_pins[str(p)] = sha(p)
    for p in (data / 'result.json', data / 'source-pins.json', ROOT / 'AGENTS.md',
              CAPTURE / 'result.json', CAPTURE / 'source-pins.json'):
        source_pins[str(p)] = sha(p)
    for p in sorted((CAPTURE / 'capture/decode/block').iterdir()):
        source_pins[str(p)] = sha(p)
    commands = []

    def run(label, argv):
        argv = list(map(str, argv))
        proc = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, timeout=120, cwd=output)
        (output / (label + '.log')).write_text(proc.stdout)
        commands.append(dict(label=label, argv=argv, returncode=proc.returncode))
        (output / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        require(proc.returncode == 0, label + ' failed: ' + proc.stdout[-3000:])
        return proc.stdout.strip()

    for tool in (cc, HOST_CC): source_pins[str(tool.resolve())] = sha(tool.resolve())
    run('unit-tests', [sys.executable, '-B', '-m', 'unittest', 'discover',
                       '-s', HERE / 'tests', '-v'])
    run('host-reference-build', [HOST_CC, '-std=gnu11', '-O2', '-fno-fast-math',
        '-ffp-contract=off', HERE / 'reference.c', '-lm', '-o', output / 'reference'])
    run('host-reference', [output / 'reference', data, output / 'native_golden.bin'])
    memory_expected = dict(
        data_hash=fnv64(b''.join((data / (n + '.bin')).read_bytes() for n in FILES) +
                        (output / 'native_golden.bin').read_bytes()),
        query_hash=fnv64((data / 'decode_query_f16.bin').read_bytes()),
        guard_bytes=5704, guard_hash=fnv64(bytes([0xa5]) * 5704))
    transformed, transform = instrument((sdk / 'src/akv_v2_native_riscv.c').read_text())
    profiled = sdk / 'src/chain_f16_profile.c'
    profiled.write_text(transformed)
    (output / 'transform.json').write_text(json.dumps(transform, indent=2) + '\n')
    assembly = ['.section .rodata.chain_f16,"a",@progbits', '.balign 64',
                '.global data_begin', 'data_begin:']
    for name in [*FILES, 'native_golden']:
        p = output / 'native_golden.bin' if name == 'native_golden' else data / (name + '.bin')
        assembly.extend(['.balign 64', '.global ' + name, name + ':', '.incbin ' + json.dumps(str(p))])
    assembly.extend(['.global data_end', 'data_end:', '.section .note.GNU-stack,"",@progbits'])
    (output / 'data.S').write_text('\n'.join(assembly) + '\n')
    linker = (common / 'arch.link.ld').read_text().replace('ALIGNMENT', '16')
    require(linker.count('LENGTH = 0x00100000') == 1, 'Linker template changed')
    (output / 'link.ld').write_text(linker.replace('LENGTH = 0x00100000', 'LENGTH = 0x01000000'))
    flags = ['-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-mcmodel=medany', '-mno-relax',
             '-O3', '-DNDEBUG', '-fno-fast-math', '-ffp-contract=off', '-fno-tree-vectorize',
             '-ffunction-sections', '-fdata-sections', '-std=gnu11', '-Wall', '-Wextra',
             '-Wno-unknown-pragmas', '-DNR_LANES=4', '-DVLEN=1024',
             '-I' + str(sdk / 'include'), '-I' + str(common), '-I' + str(HERE)]
    objects = []
    sources = [HERE / 'main.c', output / 'data.S',
               *[common / n for n in ('crt0.S', 'printf.c', 'string.c', 'serial.c',
                                      'util.c', 'print_trap_cause.c')],
               *[sdk / 'src' / n for n in ('akv_runtime.c', 'akv_decode.c', 'akv_features.c',
                  'akv_prefill_reference.c', 'akv_native_riscv.c', 'akv_v2_native_riscv.c',
                  'akv_v2_attention_rvv.S', 'akv_attention_rvv.S')], profiled]
    for src in sources:
        obj = output / (src.stem + '.o')
        extra = []
        if src.name == 'string.c':
            extra += ['-ffreestanding', '-fno-builtin', '-fno-tree-loop-distribute-patterns']
        if src == profiled:
            extra += ['-Dakv_attention_execute_v2_native=f16_profile_execute',
                '-Dakv_attention_execute_v2_with_features_native=f16_profile_with_features',
                '-Dakv_attention_execute_v2_prefill_native=f16_profile_prefill_unused']
        run('compile-' + src.stem, [cc, *flags, *extra, '-MMD', '-MF', obj.with_suffix('.d'),
                                     '-c', src, '-o', obj])
        objects.append(obj)
    elf = output / 'chain_f16_decode.elf'
    run('link', [cc, *flags[:4], '-static', '-nostdlib', '-nostartfiles', *objects,
        '-Wl,--gc-sections', '-Wl,-Map=' + str(output / 'link.map'), '-T', output / 'link.ld',
        '-Wl,--start-group', '-lm', '-lc', '-lgcc', '-lnosys', '-Wl,--end-group', '-o', elf])
    run('disassembly', [cc.with_name(cc.name.replace('gcc', 'objdump')), '-d', elf])
    run('segments', [cc.with_name(cc.name.replace('gcc', 'readelf')), '-lW', elf])
    for lib in ('libm.a', 'libc.a', 'libgcc.a', 'libnosys.a'):
        p = Path(run('locate-' + lib, [cc, '-print-file-name=' + lib])).resolve()
        source_pins[str(p)] = sha(p)
    for tool in ('cc1', 'as', 'ld'):
        p = Path(run('locate-' + tool, [cc, '-print-prog-name=' + tool])).resolve()
        source_pins[str(p)] = sha(p)
    for p in (profiled, output / 'data.S', output / 'link.ld', output / 'native_golden.bin'):
        source_pins[str(p)] = sha(p)
    require(all(sha(p) == h for p, h in source_pins.items()), 'Source drift during build')
    (output / 'source-pins.json').write_text(json.dumps(source_pins, indent=2) + '\n')
    manifest = dict(state='BUILT_NOT_EXECUTED', target_executed=False, rtl_executed=False,
        performance_measured=False, elf=str(elf), elf_sha256=sha(elf), SDKpins=sdk_pins,
        sdk_head=head, sdk_archive=str(archive_file), sdk_archive_sha256=sha(archive_file),
        dirty_asm_excluded=True, all_runtime_objects_recompiled=True,
        objects_recompiled=len(objects), shape=SHAPE, order=[0, 1, 1, 0],
        memory_expected=memory_expected, required_plusargs=['+AKV_PERF', '+AKV_SUMMARY'],
        baseline='Uninstrumented main HEAD C/runtime/assembly; experimental getenv flags OFF',
        profile='Additive reversible C-only stamps; same arithmetic and same assembly object',
        total_roi='F32->F16 Q conversion + device query + akv_decode_execute + final drain',
        phase_semantics='Issue-side intervals; no new inter-stage drains/fences; not hardware-exclusive latency',
        probe_overhead='Measured ABBA profile-minus-baseline and 8 empty stamp/store samples; never assumed zero',
        image_contract=dict(NrLane=4, VLEN=1024, AXI=128, L2sim_bytes=16*1024*1024,
                            shared_integer_multiply=True, EnableSharedFma=0),
        golden=dict(captured=str(data / 'decode_golden.bin'),
                    captured_sha256=sha(data / 'decode_golden.bin'),
                    native_tile64=str(output / 'native_golden.bin'),
                    native_tile64_sha256=sha(output / 'native_golden.bin'),
                    capture_atol=0.003, capture_rtol=0.02, native_atol=0.0002, native_rtol=0.003,
                    note='Original golden retained; host native approximation is not target acceptance'),
        checker=dict(entry=str(HERE / 'check.py'),
                     function='check_run(log_path: Path, build_dir: Path) -> dict',
                     argv=['python3', str(HERE / 'check.py'), '--build', str(output / 'build.json'),
                           '--log', '<completed-worker-console-log>'],
                     protocol_check='Main agent must independently check exact ELF/image and custom command trace'),
        source_pins=str(output / 'source-pins.json'), source_pins_sha256=sha(output / 'source-pins.json'),
        artifacts={str(p): sha(p) for p in sorted(output.iterdir()) if p.is_file()})
    (output / 'build.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cc', type=Path, default=CC)
    args = p.parse_args()
    result = build(args.output, args.cc)
    print(json.dumps({k: result[k] for k in ('state', 'elf', 'elf_sha256', 'sdk_head')}))


if __name__ == '__main__':
    main()
