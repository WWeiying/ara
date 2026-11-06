#!/usr/bin/env python3
"""Host-only, lossless payload headroom on one exact Qwen3 projection inventory."""
import argparse
import ast
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np


HERE = Path(__file__).resolve().parent
MAIN = HERE.parents[2]
VERIFY = Path('/home/wangwy/openproject/ara_dsa_signoff_integration')
OUT = VERIFY / 'verification/out/e2e_weight_supply_codec_study_20261106_01'
GRAPH = VERIFY / 'verification/out/e2e_output_graph_20261106_01'
GRAPH_PINS_SHA = '24c8d29cc5088d2b4d3b27651b3fc4f7ac4e7271b14b0fade10d58c21cead513'
TRACE = VERIFY / 'verification/out/e2e_trace_context_model_pair_20261106_01'
AUDIT = VERIFY / 'verification/out/e2e_trace_context_model_audit_20261106_01'
CAPTURE = VERIFY / 'verification/out/e2e_qwen3_projection_capture_20261106_03'
RECEIPT = MAIN / 'verification/performance/evidence/trace_context_model_20261106_01/result.json'
RECEIPT_SHA = 'c0079fe778bbd4b69de8cfa57dc128add6e06125212222b4837ddc00d5124024'
CAPTURE_RECEIPT = MAIN / 'verification/performance/evidence/qwen3_projection_capture_20261106_01/result.json'
CAPTURE_RECEIPT_SHA = '71558239b19f24a41dbb2d5667499c57f082960d2a73ee811350a2266cde6e29'
MODEL = Path('/home/wangwy/llama/models/Qwen3-1.7B-Q4_K_M.gguf')
MODEL_SHA = 'd2387ca2dbfee2ffabce7120d3770dadca0b293052bc2f0e138fdc940d9bc7b5'
WORKERS = ('e2e_rms_norm_vcs_20261106_01', 'e2e_rms_norm_campaign_20261106_01',
           'e2e_sdk_single_input_vcs_20261106_01', 'e2e_trace_context_model_pair_20261106_01')
OWNED = ('study_weight_supply_codec.py', 'test_weight_supply_codec.py')
SIZES = {'Q4_K': (144, 112), 'Q6_K': (210, 178)}
SUCCESS = 'QWEN3_WEIGHT_SUPPLY_CODEC_HOST_HEADROOM_STUDIED_NOT_IMPLEMENTED'
POPCOUNT = np.array([bin(i).count('1') for i in range(256)], dtype=np.uint8)
SUM_FIELDS = ('blocks', 'raw_bytes', 'residual_bits', 'residual_ones', 'nonzero_residual_bytes',
              'raw_block_modes', 'compressed_block_modes', 'all_raw_mode_bytes',
              'all_compressed_mode_bytes', 'selected_block_stream_bytes', 'panel_count',
              'panel_index_bytes', 'candidate_bytes_with_index', 'stored_bytes',
              'stored_panel_index_bytes', 'stored_block_mode_bytes',
              'best_zero_residual_bytes_with_index', 'restored_blocks')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write_new(path, data):
    with Path(path).open('x') as stream:
        json.dump(data, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


class Pins:
    def __init__(self):
        self.values = {}

    def pin(self, path, expected=None):
        path = Path(path).absolute()
        require(path == path.resolve(strict=True), 'Symlinked input: ' + str(path))
        actual = digest(path)
        require(expected is None or actual == expected, 'Identity mismatch: ' + str(path))
        require(str(path) not in self.values or self.values[str(path)] == actual,
                'Input drift: ' + str(path))
        self.values[str(path)] = actual
        return actual

    def verify(self):
        for path, sha in self.values.items():
            require(digest(path) == sha, 'Final input drift: ' + path)


def worker_inventory():
    observations = []
    for name in WORKERS:
        path = VERIFY / 'verification/out' / name / 'source-pins.json'
        pins = read(path)
        conflicts = [str(HERE / owned) for owned in OWNED if str(HERE / owned) in pins]
        require(not conflicts, 'New files sealed by worker: ' + repr(conflicts))
        observations.append(dict(path=str(path), sha256=digest(path), entries=len(pins),
                                 owned_conflicts=conflicts, inherited_documentation={
                                     k: v for k, v in pins.items()
                                     if Path(k).suffix.lower() in ('.md', '.markdown')}))
    return observations  # Observations only; do not pin mutable worker inventories.


def original_schema(source, weights):
    tree = ast.parse(source)
    assignments = [n for n in tree.body if isinstance(n, ast.Assign) and
                   any(isinstance(t, ast.Name) and t.id == 'PROJECTIONS' for t in n.targets)]
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'call_schema']
    require(len(assignments) == len(functions) == 1, 'Ambiguous original projection schema')
    namespace = dict(PROJECTIONS=ast.literal_eval(assignments[0].value), require=require)
    # Execute only the original pure schema function, not unrelated imported campaigns.
    module = ast.Module(body=functions, type_ignores=[])
    exec(compile(module, str(HERE / 'trace_context_model.py'), 'exec'), namespace)
    for row in weights:
        require(set(row) == {'tensor', 'k', 'n', 'type'} and
                type(row['k']) is type(row['n']) is int, 'Invalid schema field types')
    return {str(step): namespace['call_schema'](weights, step) for step in (0, 1)}


def original_source_hash(path, trace_pins, graph_pins):
    name = str(path)
    require(name in graph_pins, 'Source absent from original GRAPH manifest: ' + name)
    value = graph_pins[name]
    require(name not in trace_pins or trace_pins[name] == value,
            'Original GRAPH/trace source disagreement: ' + name)
    return value


def inputs(pins):
    pins.pin(RECEIPT, RECEIPT_SHA)
    receipt = read(RECEIPT)
    require(receipt['state'] == 'TRACE_CONTEXT_QWEN3_MODEL_PAIR_REAUDITED' and
            receipt['run'] == str(AUDIT), 'Unaccepted projection-schema receipt')
    pins.pin(AUDIT / 'result.json', receipt['result_sha256'])
    audit = read(AUDIT / 'result.json')
    require(audit['state'] == receipt['state'] and audit['report']['run'] == str(TRACE), 'Audit binding')
    for key in ('worker_result_sha256', 'source_pins_sha256'):
        require(audit['report'][key] == receipt[key], 'Audit/receipt identity disagreement')
    pins.pin(TRACE / 'result.json', receipt['worker_result_sha256'])
    pins.pin(TRACE / 'source-pins.json', receipt['source_pins_sha256'])
    result, sealed = read(TRACE / 'result.json'), read(TRACE / 'source-pins.json')
    require(result['state'] == 'TRACE_CONTEXT_MODEL_PAIR_FUNCTIONAL_PASS' and
            result['source_pins_sha256'] == receipt['source_pins_sha256'], 'Original schema worker binding')
    schema = TRACE / 'projection-schema.json'
    pins.pin(schema, sealed[str(schema)])
    require(result['artifacts'][str(schema)] == sealed[str(schema)], 'Schema artifact binding')
    schema_source = HERE / 'trace_context_model.py'
    pins.pin(schema_source, audit['collector_pins'][str(schema_source)])
    require(sealed[str(schema_source)] == audit['collector_pins'][str(schema_source)], 'Schema source binding')
    weights = read(schema)
    calls = original_schema(schema_source.read_text(), weights)
    pins.pin(CAPTURE_RECEIPT, CAPTURE_RECEIPT_SHA)
    capture = read(CAPTURE_RECEIPT)
    require(capture['run'] == str(CAPTURE), 'Wrong captured model')
    pins.pin(CAPTURE / 'result.json', capture['result_sha256'])
    pins.pin(CAPTURE / 'source-pins.json', capture['source_pins_sha256'])
    pins.pin(CAPTURE / 'model-identity.json', capture['model_identity_sha256'])
    identity = read(CAPTURE / 'model-identity.json')
    require(identity['path'] == str(MODEL) and identity['sha256'] == MODEL_SHA and
            identity['embedded_file_verified'] is True and identity['bytes'] == MODEL.stat().st_size and
            sealed[str(MODEL)] == MODEL_SHA and
            sealed[str(CAPTURE / 'model-identity.json')] == capture['model_identity_sha256'],
            'GGUF does not match the accepted embedded model')
    pins.pin(MODEL, MODEL_SHA)
    pins.pin(GRAPH / 'source-pins.json', GRAPH_PINS_SHA)
    graph_pins = read(GRAPH / 'source-pins.json')
    for rel in ('src/models/qwen3.cpp', 'src/llama-graph.cpp',
                'ggml/src/ggml-common.h', 'ggml/src/ggml-quants.c'):
        path = GRAPH / 'llama' / rel
        pins.pin(path, original_source_hash(path, sealed, graph_pins))
    root = GRAPH / 'llama/gguf-py'
    modules = {name: sha for name, sha in sealed.items()
               if Path(name).is_relative_to(root) and name.endswith('.py')}
    require(bool(modules), 'Missing original GGUF dependency closure')
    for name, sha in modules.items():
        pins.pin(name, sha)
    require(not any(name == 'gguf' or name.startswith('gguf.') for name in sys.modules),
            'GGUF already imported; use a fresh process')
    sys.path.insert(0, str(root))
    gguf = importlib.import_module('gguf')
    for name, module in tuple(sys.modules.items()):
        if name == 'gguf' or name.startswith('gguf.'):
            path = str(Path(module.__file__).resolve(strict=True))
            require(path in modules, 'Foreign/unpinned GGUF module: ' + path)
            pins.pin(path, modules[path])
    pins.pin(Path(sys.executable).resolve(strict=True))
    for name, module in tuple(sys.modules.items()):
        if name == 'numpy' or name.startswith('numpy.'):
            filename = getattr(module, '__file__', None)
            if filename:
                pins.pin(Path(filename).resolve(strict=True))
    reader = gguf.GGUFReader(str(MODEL), mode='r')
    require(reader.endianess == gguf.GGUFEndian.LITTLE and
            reader.fields['general.architecture'].contents() == 'qwen3', 'Wrong GGUF architecture/endian')
    return reader, weights, calls, identity


def transform(blocks, profile):
    require(profile in SIZES, 'Unsupported codec profile')
    raw_size, _ = SIZES[profile]
    require(blocks.dtype == np.uint8 and blocks.ndim == 2 and blocks.shape[1] == raw_size,
            'Invalid raw block shape/type')
    count = len(blocks)
    if profile == 'Q4_K':
        q = blocks[:, 16:].reshape(count, 4, 32)
        codes = np.stack((q & 15, q >> 4), axis=2).reshape(count, 256)
        residual = 1 ^ ((codes >> 3) & 1) ^ ((codes >> 2) & 1)
        retained = ((codes[:, :, None] >> np.arange(3, dtype=np.uint8)) & 1).reshape(count, 768)
        fixed = np.concatenate((blocks[:, :16], np.packbits(retained, axis=1, bitorder='little')), axis=1)
    else:
        qh = blocks[:, 128:192].reshape(count, 2, 32)
        codes = np.stack([(qh >> shift) & 3 for shift in (0, 2, 4, 6)], axis=2).reshape(count, 256)
        residual = 1 ^ (codes >> 1) ^ (codes & 1)
        retained = np.packbits(codes >> 1, axis=1, bitorder='little')
        fixed = np.concatenate((blocks[:, :128], retained, blocks[:, 192:]), axis=1)
    return fixed, np.packbits(residual, axis=1, bitorder='little')


def restore(fixed, residual, profile):
    require(profile in SIZES, 'Unsupported codec profile')
    raw_size, fixed_size = SIZES[profile]
    count = len(fixed)
    require(fixed.dtype == residual.dtype == np.uint8 and fixed.shape == (count, fixed_size) and
            residual.shape == (count, 32), 'Invalid transformed planes')
    r = np.unpackbits(residual, axis=1, bitorder='little')
    raw = np.empty((count, raw_size), dtype=np.uint8)
    if profile == 'Q4_K':
        bits = np.unpackbits(fixed[:, 16:], axis=1, bitorder='little').reshape(count, 256, 3)
        codes = bits[:, :, 0] | (bits[:, :, 1] << 1) | (bits[:, :, 2] << 2)
        codes |= (1 ^ r ^ bits[:, :, 2]) << 3
        q = codes.reshape(count, 4, 2, 32)
        raw[:, :16] = fixed[:, :16]
        raw[:, 16:] = (q[:, :, 0] | (q[:, :, 1] << 4)).reshape(count, 128)
    else:
        high = np.unpackbits(fixed[:, 128:160], axis=1, bitorder='little')
        codes = ((high << 1) | (1 ^ r ^ high)).reshape(count, 2, 4, 32)
        qh = codes[:, :, 0] | (codes[:, :, 1] << 2) | (codes[:, :, 2] << 4) | (codes[:, :, 3] << 6)
        raw[:, :128], raw[:, 128:192], raw[:, 192:] = fixed[:, :128], qh.reshape(count, 64), fixed[:, 160:]
    return raw


def encode_block(raw, profile):
    require(profile in SIZES and len(raw) == SIZES[profile][0], 'Invalid block length/profile')
    fixed, residual = transform(np.frombuffer(raw, dtype=np.uint8).reshape(1, -1), profile)
    mask = residual[0] != 0
    bitmap = np.packbits(mask, bitorder='little').tobytes()
    encoded = b'\x01' + fixed.tobytes() + bitmap + residual[0, mask].tobytes()
    raw_mode = b'\x00' + raw
    return encoded if len(encoded) < len(raw_mode) else raw_mode  # RAW wins ties.


def decode_block(encoded, profile):
    require(profile in SIZES and bool(encoded), 'Invalid encoded block/profile')
    raw_size, fixed_size = SIZES[profile]
    if encoded[0] == 0:
        require(len(encoded) == raw_size + 1, 'Truncated/oversized RAW block')
        return encoded[1:]
    require(encoded[0] == 1 and len(encoded) >= 1 + fixed_size + 4, 'Bad mode/truncated block')
    fixed = np.frombuffer(encoded[1:1 + fixed_size], dtype=np.uint8).reshape(1, fixed_size)
    bitmap = np.frombuffer(encoded[1 + fixed_size:1 + fixed_size + 4], dtype=np.uint8)
    mask = np.unpackbits(bitmap, bitorder='little').astype(bool)
    values = np.frombuffer(encoded[1 + fixed_size + 4:], dtype=np.uint8)
    require(len(values) == int(mask.sum()) and (values != 0).all(), 'Malformed residual byte suppression')
    residual = np.zeros((1, 32), dtype=np.uint8)
    residual[0, mask] = values
    return restore(fixed, residual, profile).tobytes()


def finish_tensor(histogram, ones, restored, profile):
    raw_size, fixed_size = SIZES[profile]
    hist = np.asarray(histogram)
    require(hist.dtype.kind in 'iu' and hist.shape == (33,) and (hist >= 0).all(),
            'Invalid nonzero-byte histogram')
    hist = hist.astype(np.int64, copy=False)
    blocks = int(hist.sum())
    require(blocks > 0 and restored == blocks and 0 <= ones <= blocks * 256, 'Incomplete restoration')
    nnz = np.arange(33, dtype=np.int64)
    nonzero_bytes = int((nnz * hist).sum())
    require(nonzero_bytes <= ones <= nonzero_bytes * 8, 'Residual bit/byte counts disagree')
    compressed = fixed_size + 5 + nnz
    raw_mode = raw_size + 1
    stream = int((np.minimum(compressed, raw_mode) * hist).sum())
    panels = (blocks + 7) // 8
    candidate, raw = stream + 4 * panels, blocks * raw_size
    require(stream < 2**32, 'Panel stream exceeds 32-bit offset capacity')
    fallback = candidate >= raw
    return dict(blocks=blocks, raw_bytes=raw, residual_bits=blocks * 256, residual_ones=int(ones),
                residual_density=float(ones / (blocks * 256)), nonzero_byte_histogram=hist.tolist(),
                nonzero_residual_bytes=nonzero_bytes,
                raw_block_modes=int(hist[compressed >= raw_mode].sum()),
                compressed_block_modes=int(hist[compressed < raw_mode].sum()),
                all_raw_mode_bytes=blocks * raw_mode,
                all_compressed_mode_bytes=int((compressed * hist).sum()),
                selected_block_stream_bytes=stream, panel_count=panels, panel_index_bytes=4 * panels,
                candidate_bytes_with_index=candidate, tensor_raw_fallback=fallback,
                stored_bytes=raw if fallback else candidate, stored_panel_index_bytes=0 if fallback else 4 * panels,
                stored_block_mode_bytes=0 if fallback else blocks,
                best_zero_residual_bytes_with_index=min(raw, blocks * (fixed_size + 5) + 4 * panels),
                restored_blocks=restored, full_bytes_roundtrip_verified=True)


def aggregate(rows):
    require(bool(rows), 'Empty aggregate')
    result = {key: sum(row[key] for row in rows) for key in SUM_FIELDS}
    result.update(tensors=len(rows), tensor_raw_fallbacks=sum(row['tensor_raw_fallback'] for row in rows),
                  nonzero_byte_histogram=np.array([r['nonzero_byte_histogram'] for r in rows],
                                                 dtype=np.int64).sum(axis=0).tolist())
    result.update(residual_density=result['residual_ones'] / result['residual_bits'],
                  payload_fraction=result['stored_bytes'] / result['raw_bytes'],
                  payload_saved_bytes=result['raw_bytes'] - result['stored_bytes'],
                  payload_saved_percent=100 * (1 - result['stored_bytes'] / result['raw_bytes']))
    return result


def verify_statistics(rows, profiles, total):
    require(len(rows) == 197 and len({r['tensor'] for r in rows}) == 197, 'Incomplete tensor inventory')
    for row in rows:
        check = finish_tensor(row['nonzero_byte_histogram'], row['residual_ones'],
                              row['restored_blocks'], row['profile'])
        require(all(row[k] == v for k, v in check.items()), 'Tensor accounting mismatch: ' + row['tensor'])
        require(row['blocks'] * 256 == row['k'] * row['n'] and
                row['blocks'] % 8 == 0 and row['tensor_bytes'] == row['raw_bytes'], 'Tensor geometry mismatch')
    require(profiles == {p: aggregate([r for r in rows if r['profile'] == p]) for p in SIZES},
            'Profile accounting mismatch')
    require(total == aggregate(rows), 'Global accounting mismatch')


def study_tensor(tensor, row, chunk_blocks, deadline):
    profile = row['type'].upper()
    raw_size, _ = SIZES[profile]
    require(tensor.tensor_type.name == profile and tuple(map(int, tensor.shape)) == (row['k'], row['n']),
            'GGUF/profile-schema mismatch: ' + row['tensor'])
    require(row['k'] % 2048 == 0 and tensor.n_elements == row['k'] * row['n'] and
            tensor.n_bytes == tensor.n_elements // 256 * raw_size and
            tensor.data.dtype == np.uint8 and tensor.data.flags.c_contiguous and
            tensor.data.nbytes == tensor.n_bytes, 'Truncated/non-block-aligned projection storage')
    blocks = tensor.data.reshape(-1, raw_size)
    hist, ones, restored = np.zeros(33, dtype=np.int64), 0, 0
    h = hashlib.sha256()
    for begin in range(0, len(blocks), chunk_blocks):
        require(time.monotonic() < deadline, 'Host study wall-time bound exceeded')
        raw = blocks[begin:begin + chunk_blocks]
        h.update(raw.tobytes())
        fixed, residual = transform(raw, profile)
        presence = np.packbits(residual != 0, axis=1, bitorder='little')
        mask = np.unpackbits(presence, axis=1, bitorder='little').astype(bool)
        suppressed_values = residual[mask]
        rebuilt = np.zeros_like(residual)
        rebuilt[mask] = suppressed_values
        require(np.array_equal(residual, rebuilt) and np.array_equal(raw, restore(fixed, rebuilt, profile)),
                'Lossy actual block transform/restoration: ' + row['tensor'])
        nonzero = np.count_nonzero(residual, axis=1)
        hist += np.bincount(nonzero, minlength=33)
        ones += int(POPCOUNT[residual].sum(dtype=np.uint64))
        restored += len(raw)
    return dict(tensor=row['tensor'], profile=profile, k=row['k'], n=row['n'],
                tensor_bytes=int(tensor.n_bytes), tensor_data_offset=int(tensor.data_offset),
                raw_sha256=h.hexdigest(), **finish_tensor(hist, ones, restored, profile))


def run(output, chunk_blocks=8192, max_seconds=420):
    output = Path(output).absolute()
    nested_attempt = output.parent == OUT and output.name in {f'attempt-{i:02d}' for i in range(1, 100)}
    require((output == OUT or nested_attempt) and output.resolve() == output,
            'Only assigned fresh output or independent nested attempt allowed')
    require(type(chunk_blocks) is int and 1 <= chunk_blocks <= 65536 and 30 <= max_seconds <= 600,
            'Invalid host bounds')
    inventory = worker_inventory()
    output.mkdir(exist_ok=False)
    start, pins = time.monotonic(), Pins()
    report = dict(state='WEIGHT_SUPPLY_CODEC_STUDY_FAILED', host_only=True, analysis_only=True,
                  performance_measured=False, codec_implemented=False, isa_changed=False,
                  rtl_changed=False, bus_throughput_measured=False, dc_area_measured=False)
    try:
        if nested_attempt:
            prior = OUT / 'result.json'
            sha = pins.pin(prior)
            require(read(prior)['state'] == 'WEIGHT_SUPPLY_CODEC_STUDY_FAILED',
                    'Nested recovery requires preserved original failure')
            report['prior_failed_attempt'] = dict(result=str(prior), sha256=sha,
                                                 use='Preserved failure, not a functional PASS')
        write_new(output / 'worker-pin-inventory.json', inventory)
        snapshot = output / 'source-snapshot'
        snapshot.mkdir()
        for name in OWNED:
            sha = pins.pin(HERE / name)
            with (snapshot / name).open('xb') as stream:
                stream.write((HERE / name).read_bytes())
            pins.pin(snapshot / name, sha)
        with (output / 'unit-tests.log').open('xb') as log:
            test = subprocess.run([sys.executable, '-B', HERE / 'test_weight_supply_codec.py'],
                                  stdout=log, stderr=subprocess.STDOUT, timeout=120, check=False)
        require(test.returncode == 0, 'Host codec tests failed')
        reader, weights, calls, identity = inputs(pins)
        write_new(output / 'projection-schema.json', weights)
        write_new(output / 'call-order.json', calls)
        by_name = {}
        for tensor in reader.tensors:
            require(tensor.name not in by_name, 'Duplicate GGUF tensor: ' + tensor.name)
            by_name[tensor.name] = tensor
        require(all(row['tensor'] in by_name for row in weights), 'Missing actual projection')
        output_tensor, embedding = by_name['output.weight'], by_name['token_embd.weight']
        shared = (output_tensor.data_offset == embedding.data_offset and
                  output_tensor.n_bytes == embedding.n_bytes)
        rows = []
        with (output / 'tensor-progress.jsonl').open('x') as progress:
            for index, row in enumerate(weights):
                stats = study_tensor(by_name[row['tensor']], row, chunk_blocks, start + max_seconds)
                stats['call_index'] = index
                rows.append(stats)
                progress.write(json.dumps(stats, sort_keys=True) + '\n')
                progress.flush()
        profiles = {p: aggregate([r for r in rows if r['profile'] == p]) for p in SIZES}
        total = aggregate(rows)
        verify_statistics(rows, profiles, total)
        study = dict(state=SUCCESS, model_identity=identity, projection_tensors=197,
                     unique_projection_bytes_counted_once=True, embedding_included_separately=False,
                     output_embedding_shared_storage_identity=shared,
                     chunk_blocks=chunk_blocks, host_wall_time_bound_seconds=max_seconds,
                     bit_order='little within bytes; GGML logical weight order',
                     codec=dict(Q4_K='qs[16:144]: lower three bits retained (96B), original metadata 16B; residual=1^b3^b2',
                                Q6_K='qh[128:192]: high bit retained (32B), other original bytes 146B; residual=1^b1^b0',
                                residual='256 bits packed to 32B; 4B little-bit-order presence bitmap + nonzero bytes',
                                block_mode='1B RAW=0 or compressed=1; choose smaller including mode, RAW on ties',
                                panel_index='4B per 8 original blocks, tensor-relative 32-bit stream offset; rows aligned to panels',
                                tensor_fallback='Use original raw tensor, no block modes/index, if candidate >= original bytes',
                                omitted_costs='Tensor dispatch metadata, alignment/burst padding, global headers, decoder buffers/area/energy'),
                     validation='Every actual block fully restored including metadata, retained planes and suppressed residual bytes; '
                                'serialized block codec tested randomly/adversarially; full compressed stream not emitted',
                     total=total,
                     interpretation=dict(memory_payload_headroom_only=True, measured_speedup=None,
                                         existing_adapter_decoded_bytes_per_cycle=16,
                                         local_decoded_acceptance_bytes_per_cycle_needed=32,
                                         physical_port_upgrade_not_replaced=True,
                                         best_zero_residual_payload_fraction=total['best_zero_residual_bytes_with_index'] / total['raw_bytes'],
                                         encoded_16B_port_can_supply_32B_per_cycle_even_at_best_case=
                                         total['best_zero_residual_bytes_with_index'] * 2 <= total['raw_bytes'],
                                         priority='Wider physical supply plus local 32B acceptance for a 32B/cycle objective; '
                                                  'this codec cannot provide 2:1 compression even at zero residual',
                                         secondary_codec_direction='Only a secondary memory-payload investigation; decoder throughput/cost unknown'
                                         if total['stored_bytes'] < total['raw_bytes'] else
                                         'No net payload benefit on this inventory; do not pursue this codec here',
                                         scope='One exact Qwen3-1.7B Q4_K_M GGUF and these Q4_K/Q6_K projections only; '
                                               'no other-model/quantization, real-bus, DC-area, FPGA or timing claim'))
        write_new(output / 'tensors.json', rows)
        write_new(output / 'profiles.json', profiles)
        write_new(output / 'study.json', study)
        verify_statistics(read(output / 'tensors.json'), read(output / 'profiles.json'), read(output / 'study.json')['total'])
        pins.verify()
        report.update(state=SUCCESS, post_pins_match=True, complete_actual_byte_restoration=True,
                      artifact_accounting_checked=True, projections=197, blocks=total['blocks'],
                      raw_bytes=total['raw_bytes'], stored_bytes=total['stored_bytes'],
                      payload_saved_percent=total['payload_saved_percent'], tensor_raw_fallbacks=total['tensor_raw_fallbacks'])
    except Exception as exc:
        report.update(error=repr(exc), post_pins_match=False)
    report['host_study_wall_seconds'] = time.monotonic() - start
    write_new(output / 'source-pins.json', pins.values)
    report['source_pins_sha256'] = digest(output / 'source-pins.json')
    report['artifacts'] = {str(path): digest(path) for path in sorted(output.rglob('*')) if path.is_file()}
    write_new(output / 'result.json', report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    parser.add_argument('--chunk-blocks', type=int, default=8192)
    parser.add_argument('--max-seconds', type=int, default=420)
    args = parser.parse_args(argv)
    result = run(args.output, args.chunk_blocks, args.max_seconds)
    print(json.dumps(result, indent=2))
    return 0 if result['state'] == SUCCESS else 1


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    sys.exit(main())
