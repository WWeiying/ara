#!/usr/bin/env python3
"""Add finite native-scale QBSCMD1 edges using the unchanged C reference.

API: read_source(); transform(source) -> (clone, edits); prepare(output).
Run the clone as GENERATOR OUTPUT --mixed-scale-edges for the extra cases.
Without this option the original generator and its RNG stream are unchanged.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = ROOT / 'verification/qbs/qbs_command_vectors.c'
REFERENCE = ROOT / 'verification/qbs/qbs_ref.c'
RUNS = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
OUT = RUNS / 'e2e_mixed_scale_edges_20261106_01'
OLD_VECTORS = RUNS / 'e2e_wide_compute_20261106_01/vectors-matrix1.txt'
OLD_SHA = 'dc1ab0b04a27766ecda5bdc09eb589f566e77faecd52ac9e764f8bd47d00c883'
OWNED = ('mixed_scale_edge_vectors.py', 'test_mixed_scale_edge_vectors.py')
FROZEN = {
    SOURCE: 'da2ac980cdcc9ec97cdc06d72511b4a708f0bc9ff5ca3226027411551be34c2e',
    REFERENCE: 'adf815ed88e50d3f9d23dbb8fab2baa959d8d5aaebcd6f15cbd7a347678f423a',
    ROOT / 'verification/qbs/qbs_ref.h': 'bee076dc0d1ee7a154ed3dc837a1bcd1d77bd57fec8c3099e13eb0e58d733928',
    ROOT / 'apps/common/qbs_abi.h': '691fcc9c0a674193c5f4879e43e9fb72404e822a39dd6037444ae75a2387dada',
}
ACTIVATIONS = (
    (0x00000000, 0x80000000, 0x00000001, 0x80000001,
     0x007fffff, 0x807fffff, 0x00800000, 0x80800000),
    (0x00800000, 0x00800001, 0x01000000, 0x06ffffff,
     0x07000000, 0x07800000, 0x387fffff, 0x38800000),
    (0x3f7fffff, 0x3f800000, 0x3f800001, 0x40000000,
     0xbf7fffff, 0xbf800000, 0xbf800001, 0xc0000000),
    (0x78000000, 0x7dffffff, 0x7e000000, 0x7e800000,
     0x7f000000, 0x7f7fffff, 0xff000000, 0xff7fffff),
)
WEIGHTS = ((0x3c01, 0x0000), (0x0000, 0x3c01), (0xbc01, 0x8000), (0x8000, 0xbc01),
           (0x0001, 0x3c01), (0x3c01, 0x8001), (0x03ff, 0x0400), (0x7bff, 0x83ff))
OVERFLOW_WEIGHTS = ((0x3c01, 0), (0, 0x3c01), (0xbc01, 0x8000), (0x8000, 0xbc01),
                    (0x0001, 0), (0, 0x0001), (0x0400, 0), (0, 0x7bff))
CASES = 10


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(path):
    return sha(Path(path).read_bytes())


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def read_source(path=SOURCE):
    text = Path(path).read_text()
    require(sha(text.encode()) == FROZEN[SOURCE], 'Exact original C generator required')
    return text


def _table(rows, width):
    return ',\n'.join('    {' + ', '.join(f'0x{value:0{width}x}u' for value in row) + '}' for row in rows)


def _definitions():
    return '''/* Finite native-scale edge inputs; no change to the reference arithmetic. */
static int mixed_scale_edges_enabled;
static const uint32_t mixed_scale_activation_bits[4][8] = {
''' + _table(ACTIVATIONS, 8) + '''
};
static const uint16_t mixed_scale_weights[8][2] = {
''' + _table(WEIGHTS, 4) + '''
};
static const uint16_t mixed_scale_overflow_weights[8][2] = {
''' + _table(OVERFLOW_WEIGHTS, 4) + '''
};

static int mixed_scale_patch(unsigned case_id, unsigned profile,
                             unsigned m, unsigned n, unsigned k_blocks,
                             uint8_t *weights, uint8_t *activations) {
  if (!mixed_scale_edges_enabled) return 0;
  const int nx_only = case_id >= 8;
  const unsigned expected_profile = case_id == 8 ? QBS_WEIGHT_PROFILE_Q6_K
                                                 : QBS_WEIGHT_PROFILE_Q4_K;
  if (case_id >= 10 || profile != expected_profile ||
      m != 4 || n != 8 || k_blocks != 2) return 1;
  const unsigned family = case_id / 2u;
  for (unsigned row = 0; row < n; ++row) {
    for (unsigned kb = 0; kb < k_blocks; ++kb) {
      if (case_id == 8) {
        qbs_block_q6_k_t *weight = (qbs_block_q6_k_t *)(weights +
            ((size_t)row * k_blocks + kb) * sizeof(qbs_block_q6_k_t));
        weight->d = 0x3c01u;
        memset(weight->ql, 0x11, sizeof(weight->ql));
        memset(weight->qh, 0x55, sizeof(weight->qh));
        memset(weight->scales, 1, sizeof(weight->scales));
        continue;
      }
      qbs_block_q4_k_t *weight = (qbs_block_q4_k_t *)(weights +
          ((size_t)row * k_blocks + kb) * sizeof(qbs_block_q4_k_t));
      if (nx_only) {
        weight->d = 0x3c01u;
        weight->dmin = 0;
      } else {
        const uint16_t *pair = family == 3 ? mixed_scale_overflow_weights[row]
                                          : mixed_scale_weights[row];
        /* Swap finite ports across K except in the deliberate overflow family. */
        weight->d = pair[family == 3 ? 0 : kb];
        weight->dmin = pair[family == 3 ? 1 : 1u - kb];
      }
      memset(weight->scales, 0x11, sizeof(weight->scales));
      memset(weight->qs, 0x11, sizeof(weight->qs));
    }
  }
  for (unsigned ctx = 0; ctx < m; ++ctx) {
    for (unsigned kb = 0; kb < k_blocks; ++kb) {
      qbs_block_q8_k_t *activation = (qbs_block_q8_k_t *)(activations +
          ((size_t)ctx * k_blocks + kb) * sizeof(qbs_block_q8_k_t));
      const uint32_t bits = nx_only ? 0x3f800001u : mixed_scale_activation_bits[family][ctx * 2u + kb];
      memcpy(&activation->d, &bits, sizeof(bits));
      memset(activation->qs, nx_only ? 0 : 1, sizeof(activation->qs));
      for (unsigned group = 0; group < 16; ++group) activation->bsums[group] = nx_only ? 0 : 16;
    }
  }
  return 0;
}

'''


def transform(source):
    """Exact-anchor clone; returns reversible edits, never changes the input file."""
    require(sha(source.encode()) == FROZEN[SOURCE], 'Source drift before clone')
    definition = 'static int emit_case_data(FILE *output, unsigned case_id, unsigned profile,\n'
    layout = '  if (weight_layout == QBS_WEIGHT_LAYOUT_ROW_MAJOR) {\n'
    allowed = '      !(argc == 3 && strcmp(argv[2], "--context-suite") == 0)) {'
    branch = '  if (argc == 3) {\n'
    hook = '''  if (mixed_scale_patch(case_id, profile, m, n, k_blocks,
                        row_weights, row_activations)) {
    fprintf(stderr, "mixed-scale edge geometry mismatch\\n");
    return 1;
  }

'''
    mode = '''  if (argc == 3 && strcmp(argv[2], "--mixed-scale-edges") == 0) {
    mixed_scale_edges_enabled = 1;
    fprintf(output, "QBSCMD1 10\\n");
    int failed = 0;
    for (unsigned id = 0; id < 10; ++id)
      failed |= emit_case(output, id, id == 8 ? QBS_WEIGHT_PROFILE_Q6_K : QBS_WEIGHT_PROFILE_Q4_K,
          id % 2u ? QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR : QBS_WEIGHT_LAYOUT_ROW_MAJOR,
          id % 2u ? QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED : QBS_ACTIVATION_LAYOUT_ROW_MAJOR,
          4, 8, 2);
    if (fclose(output)) failed = 1;
    if (!failed) printf("MIXED_SCALE_EDGES_PASS cases=10 M=4 N=8 Kb=2 finite_inputs=1 nx_only=2\\n");
    return failed ? 1 : 0;
  }
'''
    replacements = [
        ('definitions', definition, _definitions() + definition),
        ('native-input-hook-before-repack', layout, hook + layout),
        ('optional-cli-mode', allowed,
         '      !(argc == 3 && (strcmp(argv[2], "--context-suite") == 0 ||\n'
         '                      strcmp(argv[2], "--mixed-scale-edges") == 0))) {'),
        ('extra-only-dispatch', branch, mode + branch),
    ]
    result, edits = source, []
    for label, old, new in replacements:
        require(result.count(old) == 1, 'Exact anchor count: ' + label)
        result = result.replace(old, new, 1)
        edits.append(dict(label=label, before=old, after=new, count=1))
    restored = result
    for edit in reversed(edits):
        require(restored.count(edit['after']) == 1, 'Ambiguous reverse edit')
        restored = restored.replace(edit['after'], edit['before'], 1)
    require(restored == source, 'Clone is not exactly reversible')
    return result, edits


def gen_recipe(source, executable, compiler=None):
    compiler = compiler or shutil.which('gcc', path='/usr/bin:/bin') or shutil.which('gcc')
    require(compiler is not None, 'Host gcc required')
    # Preserve argv[0]: resolving a gcc-named ccache symlink loses driver dispatch.
    return [str(Path(compiler).absolute()), '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror',
            '-pedantic', '-ffp-contract=off', '-frounding-math', '-fno-fast-math',
            '-I' + str(SOURCE.parent), str(source), str(REFERENCE), '-lm', '-o', str(executable)]


def _records(text):
    require(text.endswith('\n'), 'Final vector newline required')
    lines = text.splitlines()
    require(lines and re.fullmatch(r'QBSCMD1 [1-9][0-9]*', lines[0]), 'QBSCMD1 header')
    count = int(lines[0].split()[1])
    chunks, current = [], []
    for line in lines[1:]:
        require(line and line == line.strip(), 'Blank/noncanonical vector line')
        if line.startswith('CMD '):
            require(not current, 'Missing command END')
        else:
            require(current, 'Content outside command')
        current.append(line)
        if line == 'END':
            chunks.append(current)
            current = []
    require(not current and len(chunks) == count, 'Incomplete command count')
    for ordinal, rows in enumerate(chunks):
        require(rows[0].split()[1] == str(ordinal), 'Command ordinal')
    return chunks


def append_vectors(original, extras):
    """Preserve every old body line; change only HEADER count and extra CMD IDs.

    This does not change counter modes. For a matrix1 campaign, first call
    matrix_vectors(extras); never relabel the entire old suite as new coverage.
    """
    old, new = _records(original), _records(extras)
    added = []
    for index, rows in enumerate(new, len(old)):
        words = rows[0].split()
        words[1] = str(index)
        added.extend([' '.join(words), *rows[1:]])
    return f'QBSCMD1 {len(old) + len(new)}\n' + original.split('\n', 1)[1] + '\n'.join(added) + '\n'


def matrix_vectors(extras):
    """Only adapt the known M4/Q4,Q6 counter declarations to WideMatrixDot=1."""
    rows = []
    for line in extras.splitlines():
        if line.startswith('C '):
            require(line in ('C 4 2304 2336 16384 16384 512 384 64',
                             'C 4 3360 2336 16384 16384 512 192 64'), 'Native C work declaration drift')
            fields = line.split()
            fields[6] = '256'
            line = ' '.join(fields)
        rows.append(line)
    return '\n'.join(rows) + '\n'


def parse_extras(text, matrix=False):
    """Strictly check every emitted native byte against the declared edge table."""
    from run_wide_compute import parse_vectors
    shapes = parse_vectors(text, matrix=matrix)
    chunks = _records(text)
    require(len(shapes) == CASES, 'Expected ten edge cases')
    for index, (shape, rows) in enumerate(zip(shapes, chunks)):
        require((shape['profile'], shape['m'], shape['n'], shape['kb'], shape['wl'], shape['al']) ==
                (2 if index == 8 else 1, 4, 8, 2, 1 + index % 2, 1 + index % 2), 'Edge geometry/layout')
        weights = {}
        activations = {}
        kb = base = None
        for line in rows:
            fields = line.split()
            if fields[0] == 'T':
                kb, base = int(fields[1]), int(fields[2])
            elif fields[0] in ('A', 'W'):
                target, offset, mask = int(fields[1]), int(fields[2]), int(fields[3], 16)
                require(offset % 16 == 0, 'Beat alignment')
                payload = bytes.fromhex(fields[4])[::-1]
                size = (210 if index == 8 else 144) if fields[0] == 'W' else 292 if shape['al'] == 1 else 1168
                require(mask == (1 << min(16, size - offset)) - 1 and not any(payload[mask.bit_length():]),
                        'Exact final strobe/zero pad')
                store = weights if fields[0] == 'W' else activations
                owner = (kb, base + target) if fields[0] == 'W' else (kb, target)
                block = store.setdefault(owner, bytearray(size))
                block[offset:offset + mask.bit_length()] = payload[:mask.bit_length()]
        family = index // 2
        for (block_k, row), data in weights.items():
            if index == 8:
                require(data == bytes([0x11]) * 128 + bytes([0x55]) * 64 + bytes([1]) * 16 +
                        struct.pack('<H', 0x3c01), 'NX-only Q6 native bytes')
                continue
            if index == 9:
                require(data == struct.pack('<HH', 0x3c01, 0) + bytes([0x11]) * 140, 'NX-only Q4 native bytes')
                continue
            pair = (OVERFLOW_WEIGHTS if family == 3 else WEIGHTS)[row]
            d, dmin = pair if family == 3 or block_k == 0 else pair[::-1]
            require(data == struct.pack('<HH', d, dmin) + bytes([0x11]) * 140, 'Weight native bytes')
            require(all((bits & 0x7c00) != 0x7c00 for bits in (d, dmin)), 'Nonfinite weight forbidden')
        for block_k in range(2):
            for ctx in range(4):
                bits = 0x3f800001 if index >= 8 else ACTIVATIONS[family][ctx * 2 + block_k]
                if shape['al'] == 1:
                    data = activations[block_k, ctx]
                    scale = data[:4]
                    qs = data[4:260]
                    bsums = data[260:]
                else:
                    data = activations[block_k, 0]
                    scale = data[ctx * 4:ctx * 4 + 4]
                    qs = data[16 + ctx:1040:4]
                    bsums = b''.join(data[1040 + group * 8 + ctx * 2:1042 + group * 8 + ctx * 2]
                                     for group in range(16))
                require(scale == struct.pack('<I', bits) and qs == bytes([0 if index >= 8 else 1]) * 256 and
                        bsums == struct.pack('<16h', *([0 if index >= 8 else 16] * 16)),
                        'Activation scale/qs/bsums native bytes')
                require(bits & 0x7f800000 != 0x7f800000, 'Nonfinite activation forbidden')
        require(shape['flags'] & ~7 == 0, 'Unexpected NV/DZ from finite noncancelling fixtures')
        require(all((bits & 0x7fffffff) <= 0x7f800000 for bits in shape['outputs'].values()),
                'NaN output needs a separate contract; do not canonicalize silently')
        if index >= 8:
            require(shape['flags'] == 1 and set(shape['outputs'].values()) == {0},
                    'NX-only oracle must have all +0 outputs and exactly NX, no masked flags')
    require(any(shape['flags'] & 2 for shape in shapes) and any(shape['flags'] & 4 for shape in shapes),
            'Missing actual oracle underflow/overflow flags')
    return shapes


def ownership():
    path = RUNS / 'e2e_qwen3_f16_phase_vcs_20261106_01/source-pins.json'
    inventory = json.loads(path.read_text())
    require(not any(str(HERE / name) in inventory for name in OWNED), 'New helper already consumed')
    return dict(path=str(path), sha256=digest(path), entries=len(inventory), owned_conflicts=[])


def prepare(output=OUT):
    output = Path(output).absolute()
    require(output.is_relative_to(RUNS) and output.resolve() == output and not output.exists(),
            'Fresh sole-verification output required')
    observation = ownership()
    output.mkdir()
    pins, commands = {}, []
    result = dict(state='MIXED_SCALE_EDGE_PREPARATION_FAIL', host_only=True, target_executed=False,
                  rtl_tested=False, performance_measured=False)
    def pin(path, expected=None):
        path = Path(path).resolve(strict=True)
        actual = digest(path)
        require(expected is None or actual == expected, 'Input identity mismatch: ' + str(path))
        require(str(path) not in pins or pins[str(path)] == actual, 'Input drift: ' + str(path))
        pins[str(path)] = actual
    def command(argv, label):
        row = dict(label=label, argv=list(map(str, argv)), cwd=str(output))
        commands.append(row)
        completed = subprocess.run(row['argv'], cwd=output, capture_output=True, timeout=90, check=False)
        (output / (label + '.stdout')).write_bytes(completed.stdout)
        (output / (label + '.stderr')).write_bytes(completed.stderr)
        row['returncode'] = completed.returncode
        write(output / (label + '.command.json'), row)
        require(completed.returncode == 0, 'Host command failed: ' + label)
        return completed.stdout.decode()
    try:
        for path, expected in FROZEN.items():
            pin(path, expected)
        pin(OLD_VECTORS, OLD_SHA)
        pin(HERE / 'run_wide_compute.py')
        for name in OWNED:
            pin(HERE / name)
            (output / name).write_bytes((HERE / name).read_bytes())
        clone, edits = transform(read_source())
        original = output / 'original.c'
        generated = output / 'edge-generator.c'
        original.write_text(read_source())
        generated.write_text(clone)
        write(output / 'transform.json', dict(original_sha256=FROZEN[SOURCE], clone_sha256=sha(clone.encode()), edits=edits))
        compiler = gen_recipe(generated, output / 'generator')[0]
        pin(compiler)
        pin(Path(sys.executable))
        for name, source in (('original-generator', original), ('generator', generated)):
            recipe = gen_recipe(source, output / name, compiler)
            for i, item in enumerate((source, REFERENCE)):
                deps = command([*recipe[:recipe.index(str(source))], '-M', '-MT', 'object', item], f'{name}-deps-{i}')
                for header in shlex.split(deps.replace('\\\n', ' ').split(':', 1)[1]):
                    pin(output / header if not Path(header).is_absolute() else header)
            command(recipe, name + '-compile')
        command([sys.executable, '-B', HERE / OWNED[1]], 'unit-tests')
        for mode, args in (('default', []), ('context', ['--context-suite'])):
            for exe in ('original-generator', 'generator'):
                command([output / exe, output / (exe + '-' + mode + '.txt'), *args], exe + '-' + mode)
            require((output / ('original-generator-' + mode + '.txt')).read_bytes() ==
                    (output / ('generator-' + mode + '.txt')).read_bytes(), 'Original output/RNG changed: ' + mode)
        command([output / 'generator', output / 'extras-native.txt', '--mixed-scale-edges'], 'generate-extras')
        extras = (output / 'extras-native.txt').read_text()
        shapes = parse_extras(extras)
        matrix = matrix_vectors(extras)
        (output / 'extras-matrix1.txt').write_text(matrix)
        parse_extras(matrix, matrix=True)
        old = OLD_VECTORS.read_text()
        require(len(_records(old)) == 66, 'Accepted old suite count')
        combined = append_vectors(old, matrix)
        require(combined.split('\n', 1)[1].startswith(old.split('\n', 1)[1]), 'Old suite body changed')
        from run_wide_compute import parse_vectors
        require(len(parse_vectors(combined, matrix=True)) == 76, 'Combined parser/workload count')
        (output / 'combined-matrix1-76.txt').write_text(combined)
        write(output / 'cases.json', [dict(case=s['case'], profile=s['profile'], weight_layout=s['wl'],
              activation_layout=s['al'], m=s['m'], n=s['n'], k_blocks=s['kb'], native_fflags=s['flags'],
              outputs=s['outputs'], counters=s['counters']) for s in shapes])
        write(output / 'input-tables.json', dict(
            activation_bits_by_family=[[f'{bits:08x}' for bits in row] for row in ACTIVATIONS],
            half_weight_pairs=[[f'{bits:04x}' for bits in row] for row in WEIGHTS],
            overflow_half_weight_pairs=[[f'{bits:04x}' for bits in row] for row in OVERFLOW_WEIGHTS],
            activation_index='context * 2 + k_block', family='case_id // 2',
            weight_index='row; swap d/dmin on second K block except overflow family',
            quantized_activation=1, activation_bsum16=16, q4_payload_byte='11', q4_scale_byte='11',
            nx_only_cases=[dict(case=8, profile='Q6_K'), dict(case=9, profile='Q4_K')],
            nx_only_activation_bits='3f800001', nx_only_half_d='3c01', nx_only_half_dmin='0000',
            nx_only_activation_qs=0, nx_only_activation_bsum16=0, nx_only_outputs='00000000', nx_only_fflags='01'))
        write(output / 'ownership.json', observation)
        for path, expected in pins.items():
            require(digest(path) == expected, 'Post-preparation input drift: ' + path)
        write(output / 'source-pins.json', pins)
        write(output / 'commands.json', commands)
        result.update(state='MIXED_SCALE_EDGE_HOST_ORACLES_PREPARED_NOT_RTL_VERIFIED',
                      cases=10, profiles=['Q4_K', 'Q6_K'], m=4, n=8, k_blocks=2, k_elements=512,
                      weight_layouts=[1, 2], activation_layouts=[1, 2], finite_inputs_only=True,
                      nan_canonicalization=False, fflags_preserved=True,
                      native_fflags=[shape['flags'] for shape in shapes],
                      original_default_and_context_byte_identical=True,
                      old_suite_cases=66, combined_cases=76, old_suite_body_byte_identical=True,
                      old_suite_sha256=OLD_SHA, source_pins_sha256=digest(output / 'source-pins.json'),
                      extra_outputs=320, extra_tiles=40, extra_fp_uops=3648, extra_updates=640,
                      nx_only_cases=[8, 9], nx_only_outputs_zero_and_flags_nx=True,
                      counter_modes=dict(native='WideMatrixDot=0', matrix1='WideMatrixDot=1; only C dot counter differs'),
                      api=dict(read_source='read_source(path=SOURCE)', transform='transform(source) -> (source, edits)',
                               recipe='gen_recipe(source, executable, compiler=None)',
                               run='GENERATOR OUTPUT --mixed-scale-edges',
                               append='append_vectors(old66, matrix_vectors(extras_native))'),
                      limits=['Finite native-scale integration edges, not model inputs or RTL acceptance',
                              'All nine profiles and prior real-input/counter checks remain in the untouched old 66 cases',
                              'Overflow may produce signed Inf outputs; no NaN payload normalization or fflags masking',
                              'K continuation, signed zero and both-port mixed admission need the subsequent RTL consumer'],
                      artifacts={str(path): digest(path) for path in sorted(output.iterdir()) if path.is_file()})
        write(output / 'result.json', result)
        return result
    except Exception as exc:
        result['error'] = str(exc)
        write(output / 'result.json', result)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    args = parser.parse_args()
    report = prepare(args.output)
    print(json.dumps(dict(state=report['state'], output=str(args.output),
                          result_sha256=digest(args.output / 'result.json'))))
