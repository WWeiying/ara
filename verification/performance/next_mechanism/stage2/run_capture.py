#!/usr/bin/env python3
"""Collect eight real Qwen3 rows at two GGML boundaries, not performance."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import sys

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
PRIOR = OUT / 'e2e_qwen3_projection_capture_20261106_03'
MODEL = Path('/home/wangwy/llama/models/Qwen3-1.7B-Q4_K_M.gguf')
GGUF = OUT / 'e2e_output_graph_20261106_01/llama/gguf-py'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def verify(pins):
    for name, expected in pins.items():
        if sha(name) != expected:
            raise ValueError('Capture input/image drift: ' + name)


def parse(text, expected_tokens):
    if text.count('STAGE2_CAPTURE_DONE tensors=2 rows=8 stop=before_first_ffn_projection') != 1:
        raise ValueError('Incomplete or duplicate capture')
    token_rows = re.findall(r'^STAGE2_CAPTURE_TOKENS count=40 ids=([0-9,]+)$', text, re.M)
    if len(token_rows) != 1 or list(map(int, token_rows[0].split(','))) != expected_tokens:
        raise ValueError('Prompt token identity mismatch')
    sources = ('attn_norm-0', 'ffn_norm-0')
    shapes = re.findall(r'^STAGE2_CAPTURE_SHAPE source=(\S+) k=2048 rows=8 tokens=40 type=f32$', text, re.M)
    if shapes != list(sources):
        raise ValueError('Wrong tensor boundaries or geometry')
    payloads = {name: bytearray(8*2048*4) for name in sources}
    seen = set()
    for raw in (row for row in text.splitlines() if row.startswith('STAGE2_CAPTURE_DATA ')):
        row = re.fullmatch(r'STAGE2_CAPTURE_DATA source=(\S+) row=(\d+) offset=(\d+) bits=([0-9a-f]{128})', raw)
        if not row:
            raise ValueError('Malformed capture data')
        name, r, offset, bits = row.groups()
        r, offset = int(r), int(offset)
        identity = (name, r, offset)
        if name not in payloads or r >= 8 or offset >= 2048 or offset % 16 or identity in seen:
            raise ValueError('Out-of-range or duplicate capture data')
        seen.add(identity)
        words = [int(bits[i:i+8], 16) for i in range(0, 128, 8)]
        packed = struct.pack('<16I', *words)
        if not all(math.isfinite(value) for value in struct.unpack('<16f', packed)):
            raise ValueError('Nonfinite real activation')
        begin = (r*2048+offset)*4
        payloads[name][begin:begin+64] = packed
    if len(seen) != 2*8*128:
        raise ValueError('Missing capture data')
    for data in payloads.values():
        if len({bytes(data[i*8192:(i+1)*8192]) for i in range(8)}) != 8:
            raise ValueError('Input rows are not eight distinct model activations')
    return {name: bytes(data) for name, data in payloads.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.parent != OUT:
        parser.error('Use a unique direct signoff output child')
    out.mkdir(exist_ok=False)
    state = dict(state='PREPARING', performance_measured=False, whole_model_executed=False,
                 synthesis=False, rows=8, k=2048)
    pins, commands = {}, []
    previous = json.loads((PRIOR / 'source-pins.json').read_text())

    def pin(path, inherited=False):
        path = Path(path).resolve(strict=True)
        value = sha(path)
        if inherited and previous.get(str(path)) != value:
            raise ValueError('Archived compiler/library/model identity mismatch: ' + str(path))
        if str(path) in pins and pins[str(path)] != value:
            raise ValueError('Input changed during preparation: ' + str(path))
        pins[str(path)] = value

    def run(label, argv, bound=180):
        argv = list(map(str, argv))
        commands.append(dict(label=label, argv=argv, timeout_seconds=bound))
        save(out / 'commands.json', commands)
        state['state'] = label.upper()
        save(out / 'status.json', state)
        print('STAGE2_CAPTURE_' + label.upper(), flush=True)
        with (out / (label + '.log')).open('xb') as log:
            subprocess.run(argv, cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=bound, check=True)

    try:
        pin(PRIOR / 'source-pins.json')
        pin(PRIOR / 'commands.json')
        pin(PRIOR / 'result.json')
        pin(PRIOR / 'model-identity.json')
        old = json.loads((PRIOR / 'result.json').read_text())
        if old['state'] != 'REAL_QWEN3_PROJECTION_CAPTURED_NOT_BENCHMARKED' or old['activation']['rows'] != 4:
            raise ValueError('Unaccepted predecessor capture')
        inputs = out / 'inputs'
        inputs.mkdir()
        for name in ('capture_qwen3.cpp', 'run_capture.py'):
            pin(HERE / name)
            shutil.copyfile(HERE / name, inputs / name)
            pin(inputs / name)
        prior_commands = json.loads((PRIOR / 'commands.json').read_text())
        cc = next(row['argv'] for row in prior_commands if row['label'] == 'compile')[:]
        cc[cc.index('-c')+1] = str(inputs / 'capture_qwen3.cpp')
        cc[cc.index('-o')+1] = str(out / 'capture.o')
        pin(cc[0], True)
        dependencies = [value for i, value in enumerate(cc)
                        if i not in (cc.index('-c'), cc.index('-o'), cc.index('-o')+1)]
        run('deps', dependencies + ['-M', '-MT', 'object'])
        toolchain = Path('/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/host')
        for name in shlex.split((out / 'deps.log').read_text().replace('\\\n', ' ').split(':', 1)[1]):
            path = Path(name).resolve(strict=True)
            if str(path) in previous:
                pin(path, True)
            elif path.is_relative_to(toolchain) or path == inputs / 'capture_qwen3.cpp':
                pin(path)
            else:
                raise ValueError('Unreviewed transitive compiler input: ' + str(path))
        run('compile', cc)
        link = next(row['argv'] for row in prior_commands if row['label'] == 'link')[:]
        link[link.index(str(PRIOR / 'capture.o'))] = str(out / 'capture.o')
        link[link.index('-o')+1] = str(out / 'test')
        for name in link:
            if name.endswith('.a'):
                pin(name, True)
        for name in ('libc.a', 'libstdc++.a', 'libm.a', 'libgcc.a', 'libgcc_eh.a',
                     'libpthread.a', 'libdl.a', 'crt1.o', 'crti.o', 'crtbeginT.o', 'crtend.o', 'crtn.o'):
            runtime = subprocess.check_output([cc[0], '-print-file-name='+name], text=True).strip()
            pin(runtime, True)
        run('link', link)
        pin(out / 'test')
        listing = (PRIOR / 'initramfs.list').read_text()
        if listing.count(str(PRIOR / 'test')) != 1:
            raise ValueError('Unrecognized archived boot package')
        listing = listing.replace(str(PRIOR / 'test'), str(out / 'test'))
        (out / 'initramfs.list').write_text(listing)
        for row in listing.splitlines():
            fields = row.split()
            if fields[0] == 'file' and fields[1] != '/test':
                pin(fields[2], True)
        cpio = Path('/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio')
        pin(cpio, True)
        with (out / 'initramfs.cpio').open('xb') as stream:
            subprocess.run([str(cpio), str(out / 'initramfs.list')], stdout=stream, check=True, timeout=60)
        pin(out / 'initramfs.list')
        pin(out / 'initramfs.cpio')
        qemu = next(row['argv'] for row in prior_commands if row['label'] == 'qemu')[:]
        qemu[qemu.index('-initrd')+1] = str(out / 'initramfs.cpio')
        for path in (qemu[0], qemu[qemu.index('-bios')+1], qemu[qemu.index('-kernel')+1],
                     qemu[qemu.index('-drive')+1].split(',', 1)[0].removeprefix('file=')):
            pin(path, True)
        pin(MODEL, True)
        identity = json.loads((PRIOR / 'model-identity.json').read_text())
        if identity['sha256'] != sha(MODEL) or not identity['embedded_file_verified']:
            raise ValueError('Model identity differs from verified guest image')
        for path in GGUF.rglob('*.py'):
            pin(path, str(path.resolve()) in previous)
        save(out / 'source-pins.json', pins)
        verify(pins)
        run('qemu', qemu, 600)
        payloads = parse((out / 'qemu.log').read_text(), old['activation']['token_ids'])
        if payloads['attn_norm-0'][:32768] != (PRIOR / 'activation_f32.bin').read_bytes():
            raise ValueError('First four attention rows differ from the archived same-model capture')
        sys.path.insert(0, str(GGUF))
        from gguf import GGUFReader
        reader = GGUFReader(str(MODEL))
        tensors = {tensor.name: tensor for tensor in reader.tensors}
        views = []
        for op, source in (('attn_q', 'attn_norm-0'), ('ffn_gate', 'ffn_norm-0')):
            tensor = tensors['blk.0.' + op + '.weight']
            shape = list(map(int, tensor.shape))
            if len(shape) != 2 or shape[0] != 2048 or shape[1] < 128 or tensor.tensor_type.name != 'Q4_K':
                raise ValueError('Unexpected source weight shape/profile: ' + op)
            directory = out / op
            directory.mkdir()
            raw = tensor.data.view('uint8').reshape(-1)[:128*8*144].tobytes()
            if len(raw) != 128*8*144 or tensor.n_bytes != shape[1]*8*144:
                raise ValueError('Weight row storage mismatch')
            (directory / 'weight_q4_K.bin').write_bytes(raw)
            (directory / 'activation_f32.bin').write_bytes(payloads[source])
            metadata = dict(model_sha256=identity['sha256'], tensor=tensor.name, profile='Q4_K',
                original_weight_shape=shape, captured_weight_shape=[2048, 128],
                activation_shape=[2048, 8], source=source, distinct_rows=8,
                weight_sha256=sha(directory / 'weight_q4_K.bin'),
                activation_sha256=sha(directory / 'activation_f32.bin'))
            save(directory / 'operator.json', metadata)
            views.append(metadata)
        verify(pins)
        state.update(state='CAPTURED_NOT_BENCHMARKED', views=views, source_pins_match=True,
                     original_first_four_attention_rows_bit_exact=True)
    except Exception as exc:
        state.update(state='FAIL', error=str(exc))
    save(out / 'result.json', state)
    save(out / 'status.json', state)
    print('STAGE2_CAPTURE_' + state['state'], flush=True)
    return int(state['state'] == 'FAIL')


if __name__ == '__main__':
    raise SystemExit(main())
