#!/usr/bin/env python3
"""GNU-host-only, pinned real Q6_K M4/N64/K8960 panel data preparation."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CAPTURE = Path('/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m')
OP = Path('prefill/operators/blk_0_ffn_down_weight')
ACCEPTED = ROOT / 'verification/out/qbs-matrix-reuse-pair-20261023-01'
STATUS_SHA = 'e0db546be16ae499ef8eb95a68b157df843ff2c283eb952ea3e759de3760f749'
VECTOR_SHA = '7588ed840d8ca3cd60502f4b6635997fc14355091a79cd91e23c09d12f7fb5fb'
REPLAY_SHA = 'cdbd76b652ae2d1f70f0e722075ec58c2a469a39fa64ecdabd235ed0ca43dc6b'
CAPTURE_PINS = {
    'weight_q6_K.bin': '1e535b29e678b4e85e9c00375a2585a1fab58dc014a133fd2eba9546dbbe3882',
    'weight_q6_K.json': '893fac11707733da7c5066a5920a414c9a4d8cec7d17854c5afc851ac6711536',
    'activation_f32.bin': 'af8243490827e3271c6f38cbbf96bf71b7b8b4dcf6724080bac01873d42342b9',
    'activation_f32.json': '76a876839d31f4b59eb9487b364ba0617a63c1760a923984dd8fec64a944a1be',
    'output_f32.bin': 'f8a411ac89f8a81541ec3fac535571b7b01d55c168af4781bc876cac481d6baf',
    'output_f32.json': '2f6b42e4a9011579bcd3c3fa0c5c3b87daaf3fcbfa38aeab324ba3be5b26187c',
    'operator.json': '0394a6e16d955da084c806aee8a04e7cc27176801903e7a704938c0c98b31678',
}
FLAGS = ['-std=c11', '-O2', '-g0', '-Wall', '-Wextra', '-Werror', '-pedantic',
         '-fno-fast-math', '-ffp-contract=off', '-frounding-math',
         '-fexcess-precision=standard']
ENV = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'TZ': 'UTC', 'SOURCE_DATE_EPOCH': '0'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def check_pins(pins):
    for path, expected in pins.items():
        require(sha(path) == expected, 'input hash changed: ' + str(path))


def validate_capture(root):
    base = root / OP
    pins = {str(base / name): value for name, value in CAPTURE_PINS.items()}
    pins[str(root / 'replay/manifest.json')] = REPLAY_SHA
    check_pins(pins)
    shapes = {
        'weight_q6_K': ('q6_K', [8960, 1536, 1, 1], [210, 7350, 11289600, 11289600], 11289600),
        'activation_f32': ('f32', [8960, 15, 1, 1], [4, 35840, 537600, 537600], 537600),
        'output_f32': ('f32', [1536, 15, 1, 1], [4, 6144, 92160, 92160], 92160),
    }
    replay = json.loads((root / 'replay/manifest.json').read_text())
    for name, (kind, shape, strides, size) in shapes.items():
        meta = json.loads((base / (name + '.json')).read_text())
        require((meta['type'], meta['shape'], meta['strides'], meta['nbytes']) ==
                (kind, shape, strides, size), 'capture geometry: ' + name)
        require((base / (name + '.bin')).stat().st_size == size, 'capture size: ' + name)
        entries = [r for r in replay['tensor_integrity'] if r['data'] == str(OP / (name + '.bin'))]
        require(len(entries) == 1 and entries[0]['sha256'] == CAPTURE_PINS[name + '.bin']
                and entries[0]['nbytes'] == size, 'capture manifest identity: ' + name)
    op = json.loads((base / 'operator.json').read_text())
    require(op == dict(op='GGML_OP_MUL_MAT', phase='prefill', weight='blk.0.ffn_down.weight',
                       weight_type='q6_K', activation_quantization='Q8_K', result_type='F32'),
            'capture operator identity')
    for name in ('model.json', 'validation/host-all.log'):
        pins[str(root / name)] = sha(root / name)
    return pins


def crop_llama(raw):
    require(len(raw) == 92160, 'llama capture size')
    return b''.join(raw[r * 6144:r * 6144 + 256] for r in range(4))


def accepted_data(text):
    lines = text.splitlines()
    require(lines[:2] == ['QBSCMD1 1', 'CMD 0 2 2 2 4 32 35 01'], 'accepted vector command')
    result, seen = bytearray(40880), bytearray(40880)
    outputs = {}
    tile = None
    for line in lines[2:]:
        if line.startswith('T '):
            tile = tuple(map(int, line.split()[1:]))
        elif line == 'ENDT':
            tile = None
        elif line.startswith('A '):
            match = re.fullmatch(r'A 0 (\d+) ffff ([0-9a-f]{32})', line)
            require(match is not None and tile is not None and len(tile) == 3 and
                    0 <= tile[0] < 35 and tile[1:] == (0, 4), 'accepted activation record')
            offset = int(match[1])
            require(offset % 16 == 0 and 0 <= offset < 1168, 'accepted activation offset')
            at = tile[0] * 1168 + offset
            require(not any(seen[at:at+16]), 'duplicate accepted activation')
            result[at:at+16] = bytes.fromhex(match[2])[::-1]
            seen[at:at+16] = bytes([1]) * 16
        elif line.startswith('O '):
            match = re.fullmatch(r'O (\d+) ([0-9a-f]{8})', line)
            require(match is not None and int(match[1]) not in outputs, 'accepted output record')
            outputs[int(match[1])] = int(match[2], 16)
    require(all(seen) and set(outputs) == set(range(128)), 'accepted vector coverage')
    return bytes(result), struct.pack('<128I', *(outputs[i] for i in range(128)))


def stripe_records():
    records, offset = [], 0
    for index, k0 in enumerate(range(0, 35, 4)):
        blocks = min(4, 35-k0)
        records.append(dict(index=index, k_start=k0, k_blocks=blocks,
                            weight_offsets=[offset, offset + 32*blocks*210],
                            weight_bytes_per_panel=32*blocks*210,
                            activation_offset=k0*1168, activation_bytes=blocks*1168))
        offset += 64*blocks*210
    require(offset == 470400, 'stripe span')
    return records


def verify_artifacts(out, capture):
    original = (capture / OP / 'weight_q6_K.bin').read_bytes()[:470400]
    require((out / 'weight_row.bin').read_bytes() == original, 'weight crop bytes')
    require((out / 'activation_f32.bin').read_bytes() ==
            (capture / OP / 'activation_f32.bin').read_bytes()[:143360], 'activation crop bytes')
    require((out / 'llama_f32.bin').read_bytes() ==
            crop_llama((capture / OP / 'output_f32.bin').read_bytes()), 'llama global stride')
    full = (out / 'weight_full_r4.bin').read_bytes()
    striped = (out / 'weight_striped_r4.bin').read_bytes()
    require(len(full) == len(striped) == 470400, 'R4 lengths')
    for panel in range(2):
        require((out / f'full_n{panel*32:02d}_r4.bin').read_bytes() ==
                full[panel*235200:(panel+1)*235200], 'full panel file')
        for r in range(32):
            for k in range(35):
                source = ((panel*32+r)*35+k)*210
                target = panel*235200+((r//4*35+k)*4+r%4)*210
                require(original[source:source+210] == full[target:target+210], 'full R4 block bytes')
    reconstructed, visited = bytearray(470400), set()
    for stripe in stripe_records():
        kb, k0 = stripe['k_blocks'], stripe['k_start']
        for panel in range(2):
            off = stripe['weight_offsets'][panel]
            size = stripe['weight_bytes_per_panel']
            require((out / f"stripe{stripe['index']:02d}_n{panel*32:02d}_r4.bin").read_bytes()
                    == striped[off:off+size], 'stripe panel file')
            for r in range(32):
                for k in range(kb):
                    logical = (panel*32+r)*35+k0+k
                    target = off+((r//4*kb+k)*4+r%4)*210
                    require(logical not in visited, 'duplicate stripe block')
                    visited.add(logical)
                    reconstructed[logical*210:(logical+1)*210] = striped[target:target+210]
    require(len(visited) == 2240 and reconstructed == original, 'stripe reconstruction bytes')
    row = (out / 'activation_q8k_row.bin').read_bytes()
    packed = (out / 'activation_q8k_m4.bin').read_bytes()
    require(len(row) == len(packed) == 40880, 'quantized activation length')
    for r in range(4):
        for k in range(35):
            source, target = (r*35+k)*292, k*1168
            require(row[source:source+4] == packed[target+4*r:target+4*r+4], 'M4 scale')
            require(row[source+4:source+260] == packed[target+16+r:target+1040:4], 'M4 quants')
            for g in range(16):
                aux = row[source+260+2*g:source+262+2*g]
                quant = struct.unpack('<16b', row[source+4+16*g:source+20+16*g])
                require(sum(quant) == struct.unpack('<h', aux)[0], 'Q8_K bsums')
                at = target+1040+2*(g*4+r)
                require(aux == packed[at:at+2], 'M4 bsums layout')
    expected = (out / 'expected_f32.bin').read_bytes()
    panel = (out / 'expected_panel_f32.bin').read_bytes()
    require(len(expected) == len(panel) == 1024, 'oracle output length')
    for r in range(4):
        for p in range(2):
            require(expected[(r*64+p*32)*4:(r*64+p*32+32)*4] ==
                    panel[(p*128+r*32)*4:(p*128+r*32+32)*4], 'oracle output order')
    oracle = json.loads((out / 'oracle.json').read_text())
    require(oracle['state'] == 'PASS' and oracle['outputs'] == 256 and
            oracle['weight_bytes_checked'] == 470400 and oracle['logical_blocks_checked'] == 2240,
            'oracle work')
    require(len(oracle['panel_fflags']) == 2 and
            all(type(f) is int and 0 <= f <= 31 for f in oracle['panel_fflags']) and
            oracle['fflags'] == (oracle['panel_fflags'][0] | oracle['panel_fflags'][1]), 'oracle flags')
    actual = struct.unpack('<256f', expected)
    llama = struct.unpack('<256f', (out / 'llama_f32.bin').read_bytes())
    require(all(math.isfinite(x) for x in (*actual, *llama)), 'nonfinite oracle')
    errors = [abs(a-b) for a, b in zip(actual, llama)]
    relative = [d/max(abs(b), 1e-30) for d, b in zip(errors, llama)]
    mismatch = sum(d > 0.002+0.002*abs(b) for d, b in zip(errors, llama))
    llama_bytes = (out / 'llama_f32.bin').read_bytes()
    bit_mismatch = sum(expected[i:i+4] != llama_bytes[i:i+4]
                       for i in range(0, 1024, 4))
    require(mismatch == oracle['llama_mismatches'] == 0 and
            bit_mismatch == oracle['llama_bit_mismatches'] and
            max(errors) == oracle['max_abs'] and max(relative) == oracle['max_rel'] and
            oracle['atol'] == oracle['rtol'] == 0.002, 'llama comparison report')
    return oracle


def export_header(out, oracle):
    blobs = {'activation_f32': 143360, 'weight_row': 470400, 'weight_full_r4': 470400,
             'weight_striped_r4': 470400, 'activation_q8k_row': 40880,
             'activation_q8k_m4': 40880, 'expected_f32': 1024,
             'expected_panel_f32': 1024, 'llama_f32': 1024}
    lines = ['/* Reference-derived Q8_K, not production GGML preparation. */',
             '#ifndef QBS_VRF_PANEL_DATA_H', '#define QBS_VRF_PANEL_DATA_H',
             '#include <stdint.h>',
             'enum { PANEL_M=4, PANEL_N=64, PANEL_K=8960, PANEL_K_BLOCKS=35, PANEL_STRIPES=9 };',
             'typedef struct { uint32_t k_start, k_blocks, weight_offset[2],',
             '    weight_bytes, activation_offset, activation_bytes; } panel_stripe_t;',
             'static const panel_stripe_t panel_stripes[9] = {']
    for s in stripe_records():
        lines.append('  {%d, %d, {%d, %d}, %d, %d, %d},' %
                     (s['k_start'], s['k_blocks'], *s['weight_offsets'], s['weight_bytes_per_panel'],
                      s['activation_offset'], s['activation_bytes']))
    lines += ['};', 'static const uint32_t panel_full_weight_offset[2] = {0, 235200};',
              'static const uint32_t panel_expected_fflags[2] = {%d, %d};' % tuple(oracle['panel_fflags']),
              '#define PANEL_EXPECTED_FFLAGS %du' % oracle['fflags']]
    asm = ['.section .rodata', '.section .note.GNU-stack,"",@progbits', '.section .rodata']
    for name, size in blobs.items():
        lines.append(f'extern const unsigned char panel_{name}[{size}];')
        require('"' not in str(out / (name+'.bin')), 'assembly path quoting')
        asm += ['.balign 64', f'.global panel_{name}', f'panel_{name}:',
                f'.incbin "{out / (name + ".bin")}"', f'.size panel_{name}, {size}']
    lines += ['#endif', '']
    (out / 'panel_data.h').write_text('\n'.join(lines))
    (out / 'panel_data.S').write_text('\n'.join(asm) + '\n')


def prepare(out, capture=CAPTURE, accepted=ACCEPTED, gcc=Path('/usr/bin/gcc')):
    out, capture, accepted, gcc = [Path(p).resolve() for p in (out, capture, accepted, gcc)]
    out.mkdir(parents=True, exist_ok=False)
    commands = []
    def run(args, log, timeout=120):
        command = list(map(str, args))
        commands.append(dict(argv=command, cwd=str(ROOT), timeout_seconds=timeout))
        dump(out / 'commands.json', commands)
        result = subprocess.run(command, cwd=ROOT, env=ENV, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=timeout, check=False)
        (out / log).write_text(result.stdout)
        require(result.returncode == 0, f'command failed ({result.returncode}): {log}')
        return result.stdout
    try:
        pins = validate_capture(capture)
        pins[str(accepted / 'status.json')] = STATUS_SHA
        vector = accepted / 'q6_K_m4a/input.vectors'
        pins[str(vector)] = VECTOR_SHA
        check_pins(pins)
        prior = json.loads((accepted / 'status.json').read_text())
        require(prior['state'] == 'PASS' and
                prior['cases']['q6_K_m4a']['coordinates'] == [0, 4, 0, 32, 8960] and
                prior['cases']['q6_K_m4a']['vector_sha256'] == VECTOR_SHA, 'accepted vector provenance')
        for name, expected in CAPTURE_PINS.items():
            entries = [v for p, v in prior['sources_and_inputs'].items()
                       if p.endswith('/inputs/q6_K/' + name)]
            require(entries == [expected], 'accepted capture provenance: ' + name)
        accepted_activation, accepted_output = accepted_data(vector.read_text())
        version = run([gcc, '--version'], 'gcc-version.log')
        macros = run([gcc, '-dM', '-E', '-x', 'c', '/dev/null'], 'gcc-macros.log')
        require('gcc ' in version.lower() and '__GNUC__' in macros and '__clang__' not in macros,
                'GNU GCC host compiler required')
        sources = [HERE / 'generate.c', HERE.parent / 'qbs_ref.c']
        dependencies = set(sources) | set(HERE.glob('*')) | {
            gcc, Path(sys.executable).resolve(), Path('/usr/bin/bash')}
        for config in ('/etc/ld.so.cache', '/etc/ld.so.preload'):
            if Path(config).is_file():
                dependencies.add(Path(config))
        for index, source in enumerate(sources):
            dep = run([gcc, *FLAGS, '-M', '-MT', 'dependency', source], f'deps{index}.log')
            dependencies.update(Path(p).resolve() for p in shlex.split(dep.replace('\\\n', ' ').split(':', 1)[1]))
        for name in ('cc1', 'collect2', 'as', 'ld'):
            path = run([gcc, '-print-prog-name=' + name], f'tool-{name}.log').strip()
            dependencies.add(Path(path if '/' in path else shutil.which(path, path=ENV['PATH'])).resolve())
        specs = Path(run([gcc, '-print-file-name=specs'], 'gcc-specs-path.log').strip())
        if specs.is_file():
            dependencies.add(specs.resolve())
        run([gcc, '-dumpspecs'], 'gcc-specs.log')
        # Static linking makes every generator execution dependency an archived input.
        for name in ('crt1.o', 'crti.o', 'crtbeginT.o', 'crtend.o', 'crtn.o',
                     'libgcc.a', 'libgcc_eh.a', 'libc.a', 'libc_nonshared.a', 'libm.a', 'libmvec.a'):
            path = Path(run([gcc, '-print-file-name=' + name], f'lib-{name}.log').strip()).resolve()
            require(path.is_file(), 'missing static host library: ' + name)
            dependencies.add(path)
            raw = path.read_bytes()
            if not raw.startswith((b'!<arch>', b'\x7fELF')):
                for token in re.findall(r'/[^\s()]+', raw.decode()):
                    candidate = Path(token)
                    if candidate.is_file():
                        dependencies.add(candidate.resolve())
        for module in tuple(sys.modules.values()):
            path = getattr(module, '__file__', None)
            if path and Path(path).is_file():
                dependencies.add(Path(path).resolve())
        tool_paths = [p for p in dependencies if p.is_file() and p.read_bytes()[:4] == b'\x7fELF']
        for index, tool in enumerate(sorted(tool_paths)):
            commands.append(dict(argv=['/usr/bin/ldd', str(tool)], cwd=str(ROOT), timeout_seconds=30))
            dump(out / 'commands.json', commands)
            result = subprocess.run(['/usr/bin/ldd', str(tool)], env=ENV, text=True,
                                    cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
            (out / f'tool-libraries-{index}.log').write_text(result.stdout)
            require(result.returncode == 0 or 'not a dynamic executable' in result.stdout or
                    'statically linked' in result.stdout, 'tool runtime discovery')
            for token in re.findall(r'(/[^\s()]+)', result.stdout):
                if Path(token).is_file():
                    dependencies.add(Path(token).resolve())
        dependencies.add(Path('/usr/bin/ldd'))
        pins.update({str(p): sha(p) for p in dependencies if p.is_file()})
        check_pins(pins)
        dump(out / 'inputs-before.json', pins)
        run([gcc, *FLAGS, '-static', '-Wl,--build-id=none', '-Wl,-t', *sources,
             '-lm', '-o', out / 'generate'], 'compile.log')
        trace = (out / 'compile.log').read_text().splitlines()
        for line in trace:
            if line.startswith('/') and Path(line).is_file():
                require(str(Path(line).resolve()) in pins, 'unpinned linker input: ' + line)
        check_pins(pins)
        pins[str(out / 'generate')] = sha(out / 'generate')
        base = capture / OP
        (out / 'weight_row.bin').write_bytes((base / 'weight_q6_K.bin').read_bytes()[:470400])
        (out / 'activation_f32.bin').write_bytes((base / 'activation_f32.bin').read_bytes()[:143360])
        (out / 'llama_f32.bin').write_bytes(crop_llama((base / 'output_f32.bin').read_bytes()))
        log = run([out / 'generate', out], 'generate.log')
        require(re.fullmatch(r'PANEL_DATA_PASS outputs=256 weight_bytes=470400 stripes=9 fflags=\d+\n', log)
                is not None, 'generator terminal protocol')
        oracle = verify_artifacts(out, capture)
        require((out / 'activation_q8k_m4.bin').read_bytes() == accepted_activation,
                'reference quantization differs from accepted vector A')
        require((out / 'expected_panel_f32.bin').read_bytes()[:512] == accepted_output and
                oracle['panel_fflags'][0] == 1, 'full-K panel0 differs from accepted oracle')
        export_header(out, oracle)
        check_pins(pins)
        dump(out / 'inputs-after.json', pins)
        artifacts = {p.name: dict(bytes=p.stat().st_size, sha256=sha(p))
                     for p in sorted(out.iterdir()) if p.is_file()}
        manifest = dict(state='PASS', schema_version=1, shape=dict(m=4, n=64, k=8960, k_blocks=35),
                        capture=str(capture / OP), input_rows=[0, 4], output_columns=[0, 64],
                        capture_output_stride_bytes=6144, accepted_vector=str(vector),
                        quantizer='qbs_ref_quantize_q8_k; reference-derived, NOT production GGML',
                        oracle='qbs_ref_execute full K35; row-major and R4 agree bytewise/fflags',
                        numerical_comparison=oracle, stripes=stripe_records(),
                        output_order='expected_f32/llama_f32: [input][N64]; expected_panel_f32: [panel][input][N32]',
                        weight_order='full: [N32 panel][R4 group][K35][row4]; striped: [K stripe][N32 panel][R4 group][localK][row4]',
                        timing_scope='DATA ONLY. Future matrix phase includes all dispatch, seed, replay, commit, stores and spills. Production preparation must be measured separately; no runtime-preparation or performance claim.',
                        static_work=dict(outputs=256, products=2293760, baseline_commands=2,
                                         striped_commands=18, weight_bytes=470400,
                                         baseline_activation_payload_bytes=81760,
                                         striped_activation_payload_bytes=40880),
                        environment=ENV, python=sys.version, inputs=pins, artifacts=artifacts,
                        generator_sha256=sha(out / 'generate'))
        dump(out / 'manifest.json', manifest)
        dump(out / 'status.json', dict(state='PASS', manifest_sha256=sha(out / 'manifest.json')))
        return manifest
    except BaseException as error:
        dump(out / 'status.json', dict(state='FAIL', error=repr(error)))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--capture-root', type=Path, default=CAPTURE)
    parser.add_argument('--accepted-run', type=Path, default=ACCEPTED)
    parser.add_argument('--gcc', type=Path, default=Path('/usr/bin/gcc'))
    args = parser.parse_args()
    result = prepare(args.output, args.capture_root, args.accepted_run, args.gcc)
    print(json.dumps(dict(state=result['state'], manifest=str(args.output.resolve() / 'manifest.json'))))


if __name__ == '__main__':
    main()
