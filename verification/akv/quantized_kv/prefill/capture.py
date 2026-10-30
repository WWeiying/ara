#!/usr/bin/env python3
"""Capture real quantized Prefill tensors with an identity-checked host runtime."""
import argparse
import json
import math
import os
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / 'verification/qbs'))
from run_half_scale_soc import atomic_json, hashes, digest
from run_tile_context_engine import run_command


def validate(folder, kind):
    block = folder / 'prefill/block'
    tensors = {}
    for name in ('attn_q_input-0', 'attn_k_input-0', 'attn_v_input-0', 'attn_mask_input-0', 'kqv_out-0'):
        meta = json.loads((block / (name + '.json')).read_text())
        raw = (block / (name + '.bin')).read_bytes()
        if len(raw) != meta['nbytes']:
            raise ValueError('Tensor byte extent: ' + name)
        tensors[name] = (meta, raw)
    q, qdata = tensors['attn_q_input-0']
    k, _ = tensors['attn_k_input-0']; v, _ = tensors['attn_v_input-0']
    mask, raw = tensors['attn_mask_input-0']; golden, output = tensors['kqv_out-0']
    if (q['type'], k['type'], v['type'], mask['type'], golden['type']) != ('f32', kind, 'q8_0', 'f16', 'f32'):
        raise ValueError('Requested quantized types not captured')
    d, queries, heads, batch = q['shape']
    if d != 128 or queries <= 1 or batch != 1 or k['shape'][0] != d or v['shape'] != k['shape'] or heads % k['shape'][2]:
        raise ValueError('Unexpected Prefill geometry')
    if mask['shape'][0] != k['shape'][1] or mask['shape'][1] != queries or mask['strides'][0] != 2:
        raise ValueError('Mask geometry')
    visible = []
    for row in range(queries):
        start = row * mask['strides'][1]
        bits = struct.unpack_from('<' + 'H' * mask['shape'][0], raw, start)
        n = 0
        while n < len(bits) and bits[n] == 0:
            n += 1
        if n == 0 or any(b != 0xfc00 for b in bits[n:]):
            raise ValueError('Non-prefix mask')
        visible.append(n)
    if any(not math.isfinite(x) for data in (qdata, output) for (x,) in struct.iter_unpack('<f', data)):
        raise ValueError('Nonfinite model inputs/output')
    return dict(query_shape=q['shape'], key_shape=k['shape'], value_shape=v['shape'],
                output_shape=golden['shape'], visible_prefixes=visible,
                types=dict(query=q['type'], key=k['type'], value=v['type']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); out = args.output.resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'verification/out'):
        raise ValueError('Fresh output required')
    prior = ROOT / 'verification/out/akv-quantkv-host-capture-20261024-01'
    pins = json.loads((prior / 'build-artifacts.json').read_text())
    if hashes(map(Path, pins)) != pins:
        raise ValueError('Capture binary/library drift')
    model = Path('/home/wangwy/llama/models/Qwen3-1.7B-Q4_K_M.gguf')
    binary = prior / 'build/bin/llama-completion'
    pins.update(hashes([model, Path(__file__), prior / 'build-artifacts.json', prior / 'source-pins.json']))
    out.mkdir(parents=True)
    state = dict(state='PREPARING', pid=os.getpid(), child_pid=None, rtl_performance=False)
    env = {k: v for k, v in os.environ.items() if not k.startswith(('GGML_RISCV_', 'LLAMA_Q4KM_CAPTURE', 'AKV_')) and k != 'LD_PRELOAD'}
    env['LD_LIBRARY_PATH'] = str(prior / 'build/bin')
    results = {}
    try:
        for kind in ('q4_0', 'q8_0'):
            folder = out / kind
            folder.mkdir()
            command = list(map(str, [binary, '-m', model, '-p',
                'Explain how a processor reuses vector arithmetic units to accelerate language model attention while preserving numerical correctness.',
                '-n', '1', '-c', '256', '-b', '128', '-ub', '128', '-t', '8', '-tb', '8',
                '-no-cnv', '--load-mode', 'mmap', '--no-warmup', '--no-display-prompt', '--seed', '1', '--temp', '0',
                '-fa', 'on', '-ctk', kind, '-ctv', 'q8_0']))
            runenv = dict(env, LLAMA_Q4KM_CAPTURE_DIR=str(folder), LLAMA_Q4KM_CAPTURE_LAYER='0',
                          LLAMA_Q4KM_CAPTURE_PHASE='prefill', LLAMA_Q4KM_CAPTURE_PROFILE='attention_core')
            atomic_json(folder / 'command.json', dict(argv=command, capture_phase='prefill', model_sha256=pins[str(model)]))
            def started(pid):
                state.update(state='CAPTURING_' + kind, child_pid=pid)
                atomic_json(out / 'status.json', state)
            if run_command(command, folder / 'capture.log', 600, runenv, started):
                raise RuntimeError('Capture failed: ' + kind)
            results[kind] = validate(folder, kind)
        if hashes(map(Path, pins)) != pins:
            raise ValueError('Capture inputs changed')
        pins.update(hashes(p for p in out.rglob('*') if p.is_file() and p.suffix in ('.bin', '.json', '.log')))
        atomic_json(out / 'manifest.json', pins)
        state.update(state='PASS', captures=results, scope='Actual host Qwen3 quantized Prefill operands; not QBS or RTL acceptance')
    except BaseException as exc:
        state.update(state='FAIL', error=repr(exc)); raise
    finally:
        state['child_pid'] = None
        atomic_json(out / 'status.json', state); atomic_json(out / 'result.json', state)


if __name__ == '__main__':
    main()
