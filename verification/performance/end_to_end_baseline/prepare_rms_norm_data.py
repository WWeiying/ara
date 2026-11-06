#!/usr/bin/env python3
"""Prepare reconstructed Qwen3 RMSNorm inputs; do not certify baseline equivalence."""
import argparse
import hashlib
import importlib
import json
import math
from pathlib import Path
import struct
import sys

import numpy as np


HERE = Path(__file__).resolve().parent
MAIN = HERE.parents[2]
VERIFY = Path('/home/wangwy/openproject/ara_dsa_signoff_integration')
OUT = VERIFY / 'verification/out/e2e_rms_norm_data_20261106_01'
CAPTURE = VERIFY / 'verification/out/e2e_qwen3_projection_capture_20261106_03'
GRAPH = VERIFY / 'verification/out/e2e_output_graph_20261106_01'
MODEL_RUN = VERIFY / 'verification/out/e2e_output_model_20261106_01'
MODEL = Path('/home/wangwy/llama/models/Qwen3-1.7B-Q4_K_M.gguf')
RECEIPT = MAIN / 'verification/performance/evidence/qwen3_projection_capture_20261106_01/result.json'
WORKER = VERIFY / 'verification/out/e2e_sdk_single_input_vcs_20261106_01/source-pins.json'
DECODE_RECEIPT = MAIN / 'verification/performance/evidence/decode_capture_20261106_01/result.json'
DECODE_AUDIT = VERIFY / 'verification/out/e2e_decode_capture_audit_20261106_01'
DECODE_RUN = VERIFY / 'verification/out/e2e_decode_capture_20261106_01'
DECODE_RECEIPT_SHA = '3fb54379f0e8978e3fee15673b16f9913a62cbd8a5b494f8e98ac5971600b3dc'
DECODE_EXPECTED_SHA = 'f718530b673014fe9720eaa5ccff5e9d29d37882fb17e6a7828cf3b9edfe7ed7'
DECODE_TOKEN = 22406
RECEIPT_SHA = '71558239b19f24a41dbb2d5667499c57f082960d2a73ee811350a2266cde6e29'
GRAPH_PINS_SHA = '24c8d29cc5088d2b4d3b27651b3fc4f7ac4e7271b14b0fade10d58c21cead513'
MODEL_SHA = 'd2387ca2dbfee2ffabce7120d3770dadca0b293052bc2f0e138fdc940d9bc7b5'
TOKENS = (32, 4621, 17654, 51435)
K, ROWS, VOCAB = 2048, 4, 151936
SUCCESS = 'REAL_QWEN3_RMS_NORM_DATA_PREPARED_NOT_VERIFIED'
GRAPH_SOURCES = (
    'src/models/qwen3.cpp', 'src/models/models.h',
    'src/llama-graph.cpp', 'src/llama-graph.h',
    'src/llama-model.cpp', 'src/llama-model.h',
    'src/llama-model-loader.cpp', 'src/llama-model-loader.h',
    'src/llama-hparams.cpp', 'src/llama-hparams.h',
    'src/llama-arch.cpp', 'src/llama-arch.h',
    'src/llama-context.cpp', 'src/llama-context.h', 'src/llama-batch.cpp',
    'ggml/src/ggml.c', 'ggml/include/ggml.h',
    'ggml/src/ggml-quants.c', 'ggml/src/ggml-quants.h',
    'ggml/src/ggml-cpu/ops.cpp', 'ggml/src/ggml-cpu/ops.h',
    'ggml/src/ggml-cpu/ggml-cpu.cpp', 'ggml/src/ggml-cpu/quants.c',
)


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
    """First observation is immutable, including at the final identity gate."""
    def __init__(self):
        self.values = {}

    def pin(self, path, expected=None):
        path = Path(path).absolute()
        require(path.resolve(strict=True) == path, 'Symlinked input: ' + str(path))
        value = digest(path)
        require(expected is None or value == expected, 'Identity mismatch: ' + str(path))
        require(str(path) not in self.values or self.values[str(path)] == value,
                'Input drift: ' + str(path))
        self.values[str(path)] = value
        return value

    def verify(self):
        for path, expected in self.values.items():
            require(digest(path) == expected, 'Final input drift: ' + path)


def worker_inventory():
    pins = read(WORKER)
    owned = [str(HERE / name) for name in ('prepare_rms_norm_data.py', 'test_rms_norm_data.py')]
    conflicts = [name for name in owned if name in pins]
    require(not conflicts, 'Owned source sealed by active worker: ' + repr(conflicts))
    # Record an observation, not a live pin on another worker's mutable inventory.
    return dict(path=str(WORKER), sha256=digest(WORKER), entries=len(pins),
                owned_conflicts=conflicts,
                inherited_documentation={k: v for k, v in pins.items()
                                         if Path(k).suffix.lower() in ('.md', '.markdown')})


def validate_capture(payload, metadata, receipt_metadata):
    require(metadata == receipt_metadata, 'Capture metadata differs from accepted receipt')
    require(type(metadata.get('k')) is int and metadata['k'] == K and
            type(metadata.get('rows')) is int and metadata['rows'] == ROWS and
            metadata.get('source') == 'attn_norm-0' and metadata.get('prompt_tokens') == 40 and
            metadata.get('complete_model_executed') is False and
            metadata.get('performance_measured') is False, 'Invalid capture shape/boundary')
    ids = metadata.get('token_ids')
    require(isinstance(ids, list) and len(ids) == 40 and
            all(type(t) is int and 0 <= t < VOCAB for t in ids) and
            tuple(ids[:ROWS]) == TOKENS, 'Wrong first-four token order')
    require(len(payload) == ROWS * K * 4, 'Truncated/oversized activation payload')
    require(np.isfinite(np.frombuffer(payload, dtype='<f4')).all(), 'Nonfinite activation')


def accepted_capture(pins):
    pins.pin(RECEIPT, RECEIPT_SHA)
    receipt = read(RECEIPT)
    require(receipt['state'] == 'REAL_QWEN3_PROJECTION_CAPTURED_NOT_BENCHMARKED' and
            receipt['run'] == str(CAPTURE) and receipt['post_pins_match'] is True and
            receipt['performance_measured'] is False, 'Unaccepted capture receipt')
    pins.pin(CAPTURE / 'result.json', receipt['result_sha256'])
    result = read(CAPTURE / 'result.json')
    require(result['state'] == receipt['state'] and result['post_pins_match'] is True and
            result['performance_measured'] is False, 'Capture result not accepted')
    pins.pin(CAPTURE / 'source-pins.json', receipt['source_pins_sha256'])
    require(result['source_pins_sha256'] == receipt['source_pins_sha256'], 'Capture pins binding')
    sealed = read(CAPTURE / 'source-pins.json')
    # Check every recorded capture artifact, including the log and model identity.
    for name, sha in result['artifacts'].items():
        path = Path(name)
        require(path.parent == CAPTURE, 'Escaping capture artifact')
        pins.pin(path, sha)
    require(sealed[str(MODEL)] == MODEL_SHA, 'Wrong captured GGUF pin')
    pins.pin(CAPTURE / 'model-identity.json', receipt['model_identity_sha256'])
    identity = read(CAPTURE / 'model-identity.json')
    require(identity['path'] == str(MODEL) and identity['sha256'] == MODEL_SHA and
            identity['embedded_file_verified'] is True and
            identity['guest'] == '/model/models/' + MODEL.name and
            identity['bytes'] == MODEL.stat().st_size, 'Captured model identity mismatch')
    pins.pin(MODEL, MODEL_SHA)
    require(sealed[str(CAPTURE / 'model-identity.json')] == receipt['model_identity_sha256'],
            'Model identity not bound to capture pins')
    for name in ('audit.py', 'check_projection_capture.py', 'capture_projection.cpp',
                 'run_projection_capture_v3.py'):
        pins.pin(HERE / name, sealed[str(HERE / name)])
    checker = importlib.import_module('check_projection_capture')
    require(Path(checker.__file__).resolve() == HERE / 'check_projection_capture.py',
            'Foreign capture checker')
    payload, metadata = checker.check((CAPTURE / 'qemu.log').read_text())
    validate_capture(payload, metadata, receipt['activation'])
    require(metadata == result['activation'], 'Capture result metadata mismatch')
    expected = (CAPTURE / 'activation_f32.bin').read_bytes()
    require(payload == expected, 'Capture checker bytes differ from activation file')
    sha = hashlib.sha256(expected).hexdigest()
    require(sha == receipt['activation_sha256'] == result['activation_sha256'],
            'Accepted activation hash mismatch')
    return expected, receipt, sealed, identity


def import_original_gguf(pins, capture_pins):
    pins.pin(MODEL_RUN / 'source-pins.json', capture_pins[str(MODEL_RUN / 'source-pins.json')])
    model_pins = read(MODEL_RUN / 'source-pins.json')
    pins.pin(GRAPH / 'result.json', model_pins[str(GRAPH / 'result.json')])
    pins.pin(GRAPH / 'source-pins.json', GRAPH_PINS_SHA)
    graph_pins = read(GRAPH / 'source-pins.json')
    for name in GRAPH_SOURCES:
        path = GRAPH / 'llama' / name
        pins.pin(path, graph_pins[str(path)])
        if str(path) in capture_pins:
            require(graph_pins[str(path)] == capture_pins[str(path)], 'Graph/capture source disagreement')
    root = GRAPH / 'llama/gguf-py'
    expected_modules = {name: sha for name, sha in capture_pins.items()
                        if Path(name).is_relative_to(root) and name.endswith('.py')}
    require(expected_modules, 'Missing original imported GGUF dependencies')
    for name, sha in expected_modules.items():
        pins.pin(name, sha)
    require(not any(name == 'gguf' or name.startswith('gguf.') for name in sys.modules),
            'GGUF already imported; use a fresh process')
    sys.path.insert(0, str(root))
    gguf = importlib.import_module('gguf')
    for name, module in tuple(sys.modules.items()):
        if name == 'gguf' or name.startswith('gguf.'):
            path = str(Path(module.__file__).resolve(strict=True))
            require(path in expected_modules, 'Unpinned/foreign GGUF dependency: ' + path)
            pins.pin(path, expected_modules[path])
    return gguf


def validate_decode_metadata(payload, metadata):
    require(metadata.get('phase') == 'decode' and
            type(metadata.get('input_token')) is int and metadata['input_token'] == DECODE_TOKEN and
            type(metadata.get('rows')) is int and metadata['rows'] == 1 and
            metadata.get('position') == 40 and metadata.get('prompt_tokens') == 40 and
            metadata.get('sources') == ['attn_norm-0', 'ffn_norm-0', 'ffn_swiglu-0', 'result_norm'] and
            metadata.get('complete_prefill_executed') is True and
            metadata.get('complete_decode_executed') is False and
            metadata.get('performance_measured') is False and
            metadata.get('input_differs_from_prefill') is True,
            'Invalid real Decode metadata')
    require(len(payload) == K * 4 and np.isfinite(np.frombuffer(payload, dtype='<f4')).all(),
            'Truncated/nonfinite Decode payload')


def accepted_decode(pins, capture_pins):
    pins.pin(DECODE_RECEIPT, DECODE_RECEIPT_SHA)
    receipt = read(DECODE_RECEIPT)
    require(receipt['state'] == 'REAL_QWEN3_DECODE_CAPTURE_REAUDITED' and
            receipt['run'] == str(DECODE_AUDIT) and receipt['native_emulator_postchecked'] is True and
            receipt['performance_measured'] is False, 'Unaccepted Decode receipt')
    pins.pin(DECODE_AUDIT / 'result.json', receipt['result_sha256'])
    audit = read(DECODE_AUDIT / 'result.json')
    require(audit['state'] == receipt['state'] and audit['run'] == str(DECODE_RUN) and
            audit['worker_result_sha256'] == receipt['worker_result_sha256'] and
            audit['source_pins_sha256'] == receipt['source_pins_sha256'] and
            audit['payload_sha256'] == receipt['payload_sha256'], 'Decode audit binding')
    for name, sha in audit['audit_pins'].items():
        pins.pin(name, sha)
    pins.pin(DECODE_RUN / 'result.json', receipt['worker_result_sha256'])
    pins.pin(DECODE_RUN / 'source-pins.json', receipt['source_pins_sha256'])
    result = read(DECODE_RUN / 'result.json')
    require(result['state'] == 'REAL_QWEN3_DECODE_CAPTURED_NOT_BENCHMARKED' and
            result['post_pins_match'] is True and result['performance_measured'] is False and
            result['source_pins_sha256'] == receipt['source_pins_sha256'], 'Decode worker state')
    sealed = read(DECODE_RUN / 'source-pins.json')
    require(sealed[str(MODEL)] == capture_pins[str(MODEL)] == MODEL_SHA and
            sealed[str(CAPTURE / 'model-identity.json')] == capture_pins[str(CAPTURE / 'model-identity.json')],
            'Decode GGUF/embedded-model binding differs from Prefill')
    for name, sha in result['artifacts'].items():
        require(Path(name).parent == DECODE_RUN, 'Escaping Decode artifact')
        pins.pin(name, sha)
    for name in ('capture_decode.cpp', 'run_decode_capture.py', 'decode_capture.py'):
        pins.pin(HERE / name, sealed[str(HERE / name)])
    for name in ('src/models/qwen3.cpp', 'src/llama-graph.cpp'):
        path = str(GRAPH / 'llama' / name)
        require(sealed[path] == capture_pins[path], 'Decode model graph differs')
    pins.pin(CAPTURE / 'qemu.log', sealed[str(CAPTURE / 'qemu.log')])
    pins.pin(DECODE_RUN / 'qemu.log', audit['log_sha256'])
    checker = importlib.import_module('decode_capture')
    require(Path(checker.__file__).resolve() == HERE / 'decode_capture.py', 'Foreign Decode checker')
    payloads, metadata = checker.check((DECODE_RUN / 'qemu.log').read_text(),
                                       (CAPTURE / 'qemu.log').read_text())
    require(metadata == audit['activation'] == result['activation'], 'Decode checker metadata drift')
    for key in ('prompt_tokens', 'input_token', 'position', 'rows', 'complete_prefill_executed',
                'complete_decode_executed', 'performance_measured'):
        require(metadata[key] == receipt[key], 'Decode receipt metadata: ' + key)
    for name, payload in payloads.items():
        require((DECODE_RUN / (name + '_f32.bin')).read_bytes() == payload and
                hashlib.sha256(payload).hexdigest() == receipt['payload_sha256'][name],
                'Decode checker payload differs: ' + name)
    payload = payloads['attn_norm-0']
    validate_decode_metadata(payload, metadata)
    require(hashlib.sha256(payload).hexdigest() == DECODE_EXPECTED_SHA, 'Wrong Decode expected hash')
    return payload, dict(accepted_receipt=str(DECODE_RECEIPT), receipt_sha256=DECODE_RECEIPT_SHA,
                         audit_run=str(DECODE_AUDIT), audit_result_sha256=receipt['result_sha256'],
                         capture_run=str(DECODE_RUN), worker_result_sha256=receipt['worker_result_sha256'],
                         source_pins_sha256=receipt['source_pins_sha256'], metadata=metadata)


def tensor(reader, name, shape, qtype):
    matches = [t for t in reader.tensors if t.name == name]
    require(len(matches) == 1, 'Missing/duplicate tensor: ' + name)
    t = matches[0]
    require(tuple(map(int, t.shape)) == shape, 'Invalid tensor shape: ' + name)
    require(t.tensor_type == qtype, 'Invalid tensor type: ' + name)
    return t


def embedding_path_config(reader):
    sources = {name: (GRAPH / 'llama' / name).read_text() for name in (
        'src/models/qwen3.cpp', 'src/llama-graph.cpp', 'src/llama-hparams.h',
        'src/llama-model.cpp', 'src/llama-context.cpp', 'src/llama-batch.cpp')}
    fixture = (HERE / 'capture_projection.cpp').read_text()
    scale_keys = [name for name in reader.fields
                  if 'embedding' in name.lower() and 'scale' in name.lower()]
    require(not scale_keys, 'Unexpected GGUF embedding-scale metadata')
    require('float f_embedding_scale = 0.0f;' in sources['src/llama-hparams.h'] and
            'f_embedding_scale' not in sources['src/models/qwen3.cpp'] and
            'hparams.f_embedding_scale =' not in sources['src/llama-model.cpp'],
            'Qwen3 embedding-scale source contract changed')
    require('cur = ggml_get_rows(ctx0, tok_embd, inp->tokens);' in sources['src/llama-graph.cpp'] and
            'if (hparams.f_embedding_scale != 0.0f' in sources['src/llama-graph.cpp'] and
            'loras(std::make_unique<llama_adapter_loras>())' in sources['src/llama-context.cpp'],
            'Embedding/LoRA source contract changed')
    require('/*.kv_overrides                =*/ nullptr' in sources['src/llama-model.cpp'] and
            'auto mp = llama_model_default_params(); mp.n_gpu_layers = 0;' in fixture and
            'auto cp = llama_context_default_params();' in fixture and
            'llama_batch_get_one(tokens.data(), count)' in fixture and
            'lora' not in fixture.lower() and 'kv_overrides' not in fixture,
            'Capture has model overrides or adapter configuration')
    decode_fixture = ''.join((HERE / 'capture_decode.cpp').read_text().split())
    decode_environment = (DECODE_RUN / 'capture_environment.h').read_text()
    require('automp=llama_model_default_params();mp.n_gpu_layers=0;' in decode_fixture and
            'autocp=llama_context_default_params();' in decode_fixture and
            'llama_batch_get_one(&token,1)' in decode_fixture and
            all('lora' not in text.lower() and 'kv_overrides' not in text
                for text in (decode_fixture, decode_environment)),
            'Decode capture has model overrides or adapters')
    return dict(embedding_scale=0.0, embedding_scale_applied=False,
                gguf_embedding_scale_keys=scale_keys, lora_applied=False,
                model_kv_overrides=False, input_path='token IDs -> ggml_get_rows',
                evidence='Pinned Qwen3/hparams/model/context/graph and accepted capture fixture; '
                         'default zero scale, empty context adapters, no override/LoRA API calls '
                         'in either Prefill or Decode capture')


def f32_bytes(values, shape):
    require(values.shape == shape and values.dtype == np.dtype('float32') and
            np.isfinite(values).all(), 'Invalid decoded f32 shape/type/values')
    return values.astype('<f4', copy=False).tobytes(order='C')


def reconstruct(reader, gguf, token_ids=TOKENS):
    require(tuple(token_ids) == TOKENS and all(type(t) is int for t in token_ids),
            'Invalid reconstruction token order/type')
    require(reader.endianess == gguf.GGUFEndian.LITTLE, 'Expected little-endian GGUF')
    arch = reader.fields.get('general.architecture')
    require(arch is not None and arch.types == [gguf.GGUFValueType.STRING] and
            arch.contents() == 'qwen3', 'Not a Qwen3 model')
    field = reader.fields.get('qwen3.attention.layer_norm_rms_epsilon')
    require(field is not None and field.types == [gguf.GGUFValueType.FLOAT32],
            'Missing/non-f32 RMS epsilon')
    epsilon = field.contents()
    require(isinstance(epsilon, float) and math.isfinite(epsilon) and epsilon > 0,
            'Invalid RMS epsilon')
    norm = tensor(reader, 'blk.0.attn_norm.weight', (K,), gguf.GGMLQuantizationType.F32)
    inputs, selected_bytes = embedding_rows(reader, gguf, token_ids)
    require(norm.data.nbytes == norm.n_bytes == K * 4 and norm.n_elements == K,
            'Truncated norm weight storage')
    weights = gguf.dequantize(norm.data, norm.tensor_type)
    return (f32_bytes(inputs, (ROWS, K)), f32_bytes(weights, (K,)),
            struct.pack('<f', epsilon),
            dict(embedding_type='Q4_K', embedding_shape=[K, VOCAB],
                 selected_quantized_bytes=selected_bytes, dequantized_embedding_rows=ROWS,
                 norm_weight_type=norm.tensor_type.name, epsilon=epsilon))


def embedding_rows(reader, gguf, token_ids):
    require(tuple(token_ids) in (TOKENS, (DECODE_TOKEN,)) and
            all(type(t) is int and 0 <= t < VOCAB for t in token_ids),
            'Invalid embedding token order/type')
    embedding = tensor(reader, 'token_embd.weight', (K, VOCAB), gguf.GGMLQuantizationType.Q4_K)
    block, size = gguf.GGML_QUANT_SIZES[embedding.tensor_type]
    require(K % block == 0, 'Embedding block geometry')
    row_bytes = K // block * size
    raw = embedding.data
    require(raw.dtype == np.dtype('uint8') and raw.flags.c_contiguous and
            raw.nbytes == embedding.n_bytes == row_bytes * VOCAB and
            embedding.n_elements == K * VOCAB, 'Truncated/invalid embedding storage')
    raw = raw.reshape(VOCAB, row_bytes)
    # Slice while quantized. Never pass the complete embedding to dequantize.
    selected = np.ascontiguousarray(raw[list(token_ids), :])
    inputs = gguf.dequantize(selected, embedding.tensor_type)
    return inputs, selected.nbytes


def pin_python_dependencies(pins):
    pins.pin(Path(sys.executable).resolve(strict=True))
    for name, module in tuple(sys.modules.items()):
        path = getattr(module, '__file__', None)
        if path and (name == 'numpy' or name.startswith('numpy.')):
            pins.pin(Path(path).resolve(strict=True))


def archive_prefill_only(output):
    """One authorized pre-consumer expansion, not a general output-reuse switch."""
    expected = {
        'data.json': '00c318482229def2f0bd7d15234010d50617cdddb84d188278c48c30c434672f',
        'source-pins.json': '437903e7fd98010b218f145845dad1c5b0d99ebb361cf8fe882cc86792aafb42',
        'result.json': 'd270d61bbaef4944a27899debcbcfad8e2090c32187726d146a5f5822c722a3c',
    }
    for name, sha in expected.items():
        require(digest(output / name) == sha, 'Not the unconsumed Prefill-only preparation: ' + name)
    report = read(output / 'result.json')
    require(report['state'] == SUCCESS and report['timing_allowed'] is False and
            report['upstream_baseline_bitexact_verified'] is False, 'Prior data already consumed/verified')
    require({str(path) for path in output.iterdir()} == set(report['artifacts']) | {str(output / 'result.json')},
            'Output has foreign/consumer files; cannot expand')
    for name, sha in report['artifacts'].items():
        require(digest(name) == sha, 'Prior preparation artifact drift: ' + name)
    archive = output / 'prefill-only-preparation'
    archive.mkdir(exist_ok=False)
    for name in (*expected, 'worker-pin-inventory.json'):
        (output / name).rename(archive / name)
    return archive


def prepare(output, finalize_decode=False):
    output = Path(output).absolute()
    require(output == OUT and output.resolve() == OUT, 'Only assigned fresh output allowed')
    inventory = worker_inventory()
    archive = archive_prefill_only(output) if finalize_decode else None
    if not finalize_decode:
        output.mkdir(exist_ok=False)  # No general retry/overwrite path.
    pins = Pins()
    config = None
    report = dict(state='RMS_NORM_DATA_PREPARATION_FAILED', performance_measured=False,
                  upstream_baseline_bitexact_verified=False, timing_allowed=False,
                  inputs_are_captured=False, expected_is_captured=True)
    try:
        for name in ('prepare_rms_norm_data.py', 'test_rms_norm_data.py'):
            pins.pin(HERE / name)
        if archive:
            for path in sorted(archive.iterdir()):
                pins.pin(path)
            report['superseded_prefill_only_preparation'] = str(archive)
            report['prior_preparation_use'] = 'Preserved original manifests; no inherited current-source PASS'
        write_new(output / 'worker-pin-inventory.json', inventory)
        expected, receipt, capture_pins, identity = accepted_capture(pins)
        decode_expected, decode_provenance = accepted_decode(pins, capture_pins)
        gguf = import_original_gguf(pins, capture_pins)
        pin_python_dependencies(pins)
        reader = gguf.GGUFReader(str(MODEL), mode='r')
        path_config = embedding_path_config(reader)
        inputs, weights, epsilon, details = reconstruct(reader, gguf)
        decode_values, decode_selected_bytes = embedding_rows(reader, gguf, (DECODE_TOKEN,))
        decode_inputs = f32_bytes(decode_values, (1, K))
        payloads = {'input_f32.bin': inputs, 'norm_weight_f32.bin': weights,
                    'expected_f32.bin': expected, 'epsilon.bin': epsilon,
                    'decode_input_f32.bin': decode_inputs, 'decode_expected_f32.bin': decode_expected}
        for name, payload in payloads.items():
            if archive and name in ('input_f32.bin', 'norm_weight_f32.bin', 'expected_f32.bin', 'epsilon.bin'):
                require((output / name).read_bytes() == payload, 'Original Prefill payload differs: ' + name)
                continue
            with (output / name).open('xb') as stream:
                stream.write(payload)
        config = dict(state=SUCCESS, k=K, rows=ROWS, token_ids=list(TOKENS), epsilon=details['epsilon'],
                      schema_version=2, decode_token=DECODE_TOKEN, decode_rows=1,
                      decode_selected_quantized_bytes=decode_selected_bytes,
                      total_dequantized_embedding_rows=ROWS + 1,
                      decode_provenance=decode_provenance,
                      dtype='f32', byte_order='little', layout='row_major',
                      operation='ggml_rms_norm(input, epsilon) * blk.0.attn_norm.weight',
                      input_provenance='GGUF dequantized token rows; reconstructed, not captured',
                      expected_provenance='Exact accepted attn_norm-0 activation_f32.bin bytes',
                      baseline_requirement='Actual upstream norm baseline must reproduce both expected_f32.bin and decode_expected_f32.bin bit-exactly before timing',
                      upstream_baseline_bitexact_verified=False, timing_allowed=False,
                      model_identity=identity, capture_run=str(CAPTURE),
                      accepted_receipt=str(RECEIPT), accepted_receipt_sha256=RECEIPT_SHA,
                      capture_result_sha256=receipt['result_sha256'],
                      graph_provenance_state=read(GRAPH / 'result.json')['state'],
                      graph_provenance_use='source identity only; no inherited graph execution PASS',
                      embedding_path_config=path_config,
                      **{key: value for key, value in details.items() if key != 'epsilon'})
        config['workloads'] = {
            'prefill': dict(phase='prefill', k=K, rows=ROWS, token_ids=list(TOKENS),
                            input_file='input_f32.bin', expected_file='expected_f32.bin'),
            'decode': dict(phase='decode', k=K, rows=1, token_ids=[DECODE_TOKEN], position=40,
                           input_file='decode_input_f32.bin', expected_file='decode_expected_f32.bin'),
        }
        config['files'] = {name: dict(bytes=len(value), sha256=hashlib.sha256(value).hexdigest())
                           for name, value in payloads.items()}
        pins.verify()
        report.update(state=SUCCESS, post_pins_match=True, k=K, rows=ROWS,
                      token_ids=list(TOKENS), epsilon=details['epsilon'], decode_token=DECODE_TOKEN,
                      schema_version=2, decode_rows=1)
    except Exception as exc:
        report.update(error=repr(exc), post_pins_match=False)
    # Write the original observations once, including on failure; never repin drift.
    write_new(output / 'source-pins.json', pins.values)
    report['source_pins_sha256'] = digest(output / 'source-pins.json')
    if report['state'] == SUCCESS:
        config['source_pins_sha256'] = report['source_pins_sha256']
        config['artifacts'] = {str(output / name): info['sha256']
                               for name, info in config['files'].items()}
        config['artifacts'][str(output / 'source-pins.json')] = report['source_pins_sha256']
        write_new(output / 'data.json', config)
        report['data_sha256'] = digest(output / 'data.json')
    report['artifacts'] = {str(p): digest(p) for p in sorted(output.rglob('*')) if p.is_file()}
    write_new(output / 'result.json', report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    parser.add_argument('--finalize-decode', action='store_true',
                        help='One authorized expansion of the exact initial unconsumed data receipt')
    args = parser.parse_args(argv)
    report = prepare(args.output, finalize_decode=args.finalize_decode)
    print(json.dumps(report, indent=2))
    return 0 if report['state'] == SUCCESS else 1


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    sys.exit(main())
