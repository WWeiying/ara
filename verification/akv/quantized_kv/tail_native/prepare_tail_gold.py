#!/usr/bin/env python3
"""Independent tail gold from the exact archived production HOST GGML libraries."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import shlex
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
CAPTURE = ROOT / 'verification/out/akv-quantkv-host-capture-20261024-01'
SOURCE = Path('/home/wangwy/llama/llama-q4km-extract')
HEADERS = Path('/home/wangwy/llama/llama.cpp/ggml/include')
LIBS = CAPTURE / 'build/bin'
DEFAULT_OUT = ROOT / 'verification/out/akv-quantkv-tail-gold-20261024-01'
KINDS = ('q8_0', 'q4_0')
PUBLIC_HEADERS = ('ggml.h', 'ggml-backend.h', 'ggml-cpu.h', 'ggml-alloc.h')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    temp = path.with_name(path.name + '.partial')
    temp.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n')
    temp.replace(path)


def merge(pins, additions):
    for name, sha in additions.items():
        require(isinstance(name, str) and Path(name).is_absolute() and
                isinstance(sha, str) and re.fullmatch('[0-9a-f]{64}', sha), 'Invalid pin entry')
        require(name not in pins or pins[name] == sha, 'Conflicting pin: ' + name)
        pins[name] = sha


def pin(pins, *paths):
    merge(pins, {str(Path(p).absolute()): digest(p) for p in paths})


def verify(pins):
    for name, sha in pins.items():
        require(digest(name) == sha, 'Pinned input drift: ' + name)


def metadata_check(meta, kind, role):
    require(kind in KINDS, 'Unsupported key encoding')
    row = 72 if kind == 'q4_0' else 136
    expected = {
        'q': ('f32', [128, 1, 12, 1], [4, 512, 512, 6144], 6144),
        'k': (kind, [128, 256, 2, 1], [row // 4, row, 256 * row, 512 * row], 512 * row),
        'v': ('q8_0', [128, 256, 2, 1], [34, 136, 34816, 69632], 69632),
        'mask': ('f16', [256, 1, 1, 1], [2, 512, 512, 512], 512),
        'gold': ('f32', [1536, 1, 1, 1], [4, 6144, 6144, 6144], 6144),
    }[role]
    require((meta.get('type'), meta.get('shape'), meta.get('strides'), meta.get('nbytes')) == expected,
            'Unexpected capture metadata: ' + role)
    return expected[3]


def checked_archive():
    receipt = read_json(CAPTURE / 'result.json')
    require(receipt.get('state') == 'REAL_HOST_QUANTIZED_KV_CAPTURED' and
            digest(CAPTURE / 'source-pins.json') == receipt['source_pins_sha256'] and
            digest(CAPTURE / 'build-artifacts.json') == receipt['build_artifacts_sha256'], 'Archived capture receipt drift')
    original = read_json(CAPTURE / 'source-pins.json')
    pins = {}
    merge(pins, read_json(CAPTURE / 'build-artifacts.json'))
    verify(pins)
    require(pins.get(receipt['binary']) == receipt['binary_sha256'], 'Original capture binary mismatch')
    pin(pins, CAPTURE / 'result.json', CAPTURE / 'source-pins.json', CAPTURE / 'build-artifacts.json',
        CAPTURE / 'source-provenance.json')
    for name in PUBLIC_HEADERS:
        old, current = SOURCE / 'ggml/include' / name, HEADERS / name
        require(original.get(str(old)) == digest(old) and old.read_bytes() == current.read_bytes(),
                'Public header differs from archived build: ' + name)
        pin(pins, old, current)
    cache = (CAPTURE / 'build/CMakeCache.txt').read_text().splitlines()
    require('GGML_BACKEND_DL:BOOL=OFF' in cache and 'GGML_OPENMP:BOOL=OFF' in cache,
            'Archived host backend/threading policy differs')
    captures = {}
    for kind in KINDS:
        record = receipt['captures'][kind]
        require(record['state'] == 'REAL_HOST_CAPTURE_LAYOUT_CHECKED' and record['visible_tokens'] == 128,
                'Capture not accepted at visible128')
        merge(pins, record['file_sha256'])
        verify(record['file_sha256'])
        directory = CAPTURE / ('capture-k-' + kind + '-v-q8_0') / 'decode/block'
        names = {'q': 'attn_q_input-0', 'k': 'attn_k_input-0', 'v': 'attn_v_input-0',
                 'mask': 'attn_mask_input-0', 'gold': 'kqv_out-0'}
        for role, name in names.items():
            meta, raw = directory / (name + '.json'), directory / (name + '.bin')
            require(str(meta) in record['file_sha256'] and str(raw) in record['file_sha256'], 'Unpinned capture input')
            require(raw.stat().st_size == metadata_check(read_json(meta), kind, role), 'Capture byte extent differs')
        require((directory / 'attn_mask_input-0.bin').read_bytes() == bytes(256) + b'\x00\xfc' * 128,
                'Original mask not the exact visible128 prefix')
        for name in ('attn_q_input-0.bin', 'kqv_out-0.bin'):
            require(all(math.isfinite(x[0]) for x in struct.iter_unpack('<f', (directory / name).read_bytes())),
                    'Nonfinite captured Query/gold')
        captures[kind] = dict(directory=str(directory), file_sha256=record['file_sha256'])
    return receipt, original, pins, captures


def linked_libraries(text):
    """Parse Linux ldd output fail-closed, ignoring only its virtual vDSO."""
    linked = {}
    for raw in text.splitlines():
        line = raw.strip()
        if re.fullmatch(r'linux-vdso\.so\.\d+ \(0x[0-9a-f]+\)', line):
            continue
        match = re.fullmatch(r'(\S+) => (/\S+) \(0x[0-9a-f]+\)', line)
        if match:
            name, path = match.groups()
        else:
            match = re.fullmatch(r'(/\S+) \(0x[0-9a-f]+\)', line)
            require(match is not None, 'Unresolved or unexpected runtime library: ' + line)
            path = match[1]
            name = Path(path).name
        require(name not in linked, 'Duplicate linked library')
        linked[name] = str(Path(path).resolve(strict=True))
    for name in ('ggml', 'ggml-base', 'ggml-cpu'):
        soname = 'lib' + name + '.so.0'
        require(linked.get(soname) == str((LIBS / soname).resolve(strict=True)), 'Wrong archived library: ' + soname)
    return linked


def parse_reference(text, kind):
    require(kind in KINDS and 'TAIL_GOLD_FAIL' not in text, 'Reference failed')
    lines = [line for line in text.splitlines() if line.startswith('TAIL_GOLD_')]
    require(len(lines) == 4, 'Missing or extra reference records')
    errors = {}
    for line, visible in zip(lines[:3], (128, 5, 33)):
        pattern = (rf'TAIL_GOLD_OUTPUT kind={kind} visible={visible} outputs=1536 bytes=6144 '
                   rf'baseline={int(visible == 128)} max_abs=([0-9.e+-]+) inputs_unchanged=1')
        match = re.fullmatch(pattern, line)
        require(match is not None and math.isfinite(float(match[1])) and float(match[1]) >= 0,
                'Malformed reference output')
        errors[str(visible)] = float(match[1])
        require(visible == 128 or float(match[1]) == 0, 'Tail must not claim comparison with original golden')
    require(lines[3] == f'TAIL_GOLD_PASS kind={kind} graphs=3 outputs_per_graph=1536 reference=archived_host_ggml',
            'Missing reference completion')
    return errors


def output_record(path, kind, visible):
    raw = path.read_bytes()
    require(kind in KINDS and visible in (5, 33, 128) and len(raw) == 6144, 'Wrong golden extent')
    require(all(math.isfinite(x[0]) for x in struct.iter_unpack('<f', raw)), 'Nonfinite golden output')
    mask = bytes(visible * 2) + b'\x00\xfc' * (256 - visible)
    return dict(path=str(path), sha256=digest(path), bytes=6144, elements=1536,
                shape=[128, 12, 1, 1], dtype='float32_le', kind=kind, visible=visible,
                query_heads=12, kv_heads=2, head_dim=128, capacity=256, threads=1,
                scale_bits='3db504f3', mask_sha256=hashlib.sha256(mask).hexdigest(),
                reference='actual_archived_host_ggml_graph', native_execution=False)


def prepare(output):
    out = output.resolve()
    require(not any(out.is_relative_to(p) or p.is_relative_to(out) for p in (CAPTURE, SOURCE, HEADERS)),
            'Use a fresh independent output, not capture/source/library directories')
    out.mkdir(parents=True, exist_ok=False)
    commands = []
    env = dict(PATH='/usr/bin:/bin', LC_ALL='C', LANG='C', LD_LIBRARY_PATH=str(LIBS),
               OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')

    def execute(argv, name, timeout=120):
        argv = list(map(str, argv))
        commands.append(dict(argv=argv, cwd=str(out), environment=env, timeout=timeout))
        write_json(out / 'commands.json', commands)
        with (out / (name + '.log')).open('x') as log:
            result = subprocess.run(argv, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
        require(result.returncode == 0, f'{name} returned {result.returncode}')
        return (out / (name + '.log')).read_text()

    try:
        receipt, original, pins, captures = checked_archive()
        compiler = Path('/usr/bin/g++')
        pin(pins, HERE / 'tail_gold.cpp', Path(__file__), HERE / 'test_tail_gold.py',
            compiler, compiler.resolve(), Path(sys.executable).resolve(), Path('/usr/bin/ldd'))
        version = execute([compiler, '--version'], 'compiler-version')
        require('g++' in version and 'Free Software Foundation' in version, 'GNU host compiler required')
        for tool in ('cc1plus', 'collect2', 'ld'):
            path = Path(execute([compiler, '-print-prog-name=' + tool], 'compiler-tool-' + tool).strip())
            if not path.is_absolute():
                path = Path('/usr/bin') / path
            pin(pins, path.resolve(strict=True))
        binary = out / 'tail_gold'
        command = [str(compiler), '-std=c++17', '-O2', '-UNDEBUG', '-Wall', '-Wextra', '-Werror',
                   '-fno-fast-math', '-ffp-contract=off', '-frounding-math', '-I' + str(HEADERS),
                   str(HERE / 'tail_gold.cpp'), '-L' + str(LIBS), '-Wl,-rpath,' + str(LIBS),
                   '-lggml-cpu', '-lggml', '-lggml-base', '-pthread', '-lm', '-o', str(binary)]
        dependencies = execute([*command[:command.index('-L' + str(LIBS))], '-M', '-MT', 'object'], 'dependencies')
        for name in shlex.split(dependencies.replace('\\\n', ' ').split(':', 1)[1]):
            path = Path(name).resolve(strict=True)
            if path.is_relative_to(HEADERS):
                old = SOURCE / 'ggml/include' / path.relative_to(HEADERS)
                require(original.get(str(old)) == digest(old) and old.read_bytes() == path.read_bytes(),
                        'Transitive public header differs from archived source')
                pin(pins, old)
            pin(pins, path)
        verify(pins)
        execute(command, 'compile')
        linked = linked_libraries(execute(['/usr/bin/ldd', binary], 'linked-libraries'))
        # The loaded GGML objects must be original compiled artifacts, not merely
        # libraries with matching SONAMEs. Pin all other loader dependencies too.
        artifacts = read_json(CAPTURE / 'build-artifacts.json')
        for name, path in linked.items():
            if name.startswith('libggml'):
                require(artifacts.get(path) == digest(path), 'Loaded GGML object not in archived build receipt')
            pin(pins, Path(path))
        pin(pins, binary)
        write_json(out / 'linked-libraries.json', linked)
        verify(pins)
        write_json(out / 'source-pins.json', pins)
        source_sha = digest(out / 'source-pins.json')
        outputs, baseline128, raw_logs = {}, {}, []
        for kind in KINDS:
            text = execute([binary, kind, captures[kind]['directory'], out], 'reference-' + kind)
            raw_logs.append(text)
            parsed = parse_reference(text, kind)
            baseline = output_record(out / (kind + '-v128.bin'), kind, 128)
            expected = (Path(captures[kind]['directory']) / 'kqv_out-0.bin').read_bytes()
            actual = Path(baseline['path']).read_bytes()
            maximum = 0.0
            for (x,), (y,) in zip(struct.iter_unpack('<f', actual), struct.iter_unpack('<f', expected)):
                error = abs(x-y)
                require(error <= 0.004 + 0.002*abs(y), 'Independent prefix128 capture comparison failed')
                maximum = max(maximum, error)
            require(math.isclose(parsed['128'], maximum, rel_tol=1e-6, abs_tol=1e-12), 'Logged baseline error differs from bytes')
            baseline.update(capture_max_abs=maximum, absolute_tolerance=0.004, relative_tolerance=0.002)
            baseline128[kind] = baseline
            outputs[kind] = {str(v): output_record(out / (kind + '-v' + str(v) + '.bin'), kind, v) for v in (5, 33)}
        (out / 'raw_reference.log').write_text(''.join(raw_logs))
        require(linked_libraries(execute(['/usr/bin/ldd', binary], 'linked-libraries-after')) == linked,
                'Loaded-library resolution drift')
        verify(pins)
        require(digest(out / 'source-pins.json') == source_sha, 'Source pin receipt drift')
        result = dict(state='PASS', outputs=outputs, baseline128=baseline128, graphs=6,
                      source_pins_sha256=source_sha, post_pins_match=True, captures=captures,
                      capture_receipt_sha256=digest(CAPTURE / 'result.json'),
                      archived_build_artifacts_sha256=receipt['build_artifacts_sha256'],
                      archived_source_pins_sha256=receipt['source_pins_sha256'],
                      reference_binary=dict(path=str(binary), sha256=digest(binary)),
                      linked_libraries=linked, host_machine=platform.machine(),
                      raw_reference_log=str(out / 'raw_reference.log'),
                      raw_reference_log_sha256=digest(out / 'raw_reference.log'),
                      scope='Independent host-GGML full12-query-head/two-KV-head gold; mask prefixes5/33 derived from original128 capture',
                      native_execution=False, rtl_performance=False,
                      artifact_sha256={str(p): digest(p) for p in out.iterdir() if p.is_file()})
        write_json(out / 'result.json', result)
        print('TAIL_GOLD_PASS variants=4 baselines=2 outputs_per_file=1536 output=' + str(out))
        return result
    except BaseException as exc:
        write_json(out / 'result.json', dict(state='FAIL', error=repr(exc), native_execution=False))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUT)
    prepare(parser.parse_args().output)


if __name__ == '__main__':
    main()
