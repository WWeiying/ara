"""Bounded host-only preparation tests; no model execution or output directory writes."""
from copy import deepcopy
from enum import IntEnum
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

import prepare_rms_norm_data as p
from check_projection_capture import check


class Quant(IntEnum):
    F32 = 0
    Q4_K = 12
    Q6_K = 14


class Value(IntEnum):
    FLOAT32 = 6
    STRING = 8


class Field:
    def __init__(self, value, kind):
        self.value, self.types = value, [kind]

    def contents(self):
        return self.value


def metadata():
    return dict(k=2048, rows=4, prompt_tokens=40,
                token_ids=list(p.TOKENS) + list(range(36)), source='attn_norm-0',
                complete_model_executed=False, performance_measured=False)


def decode_metadata():
    return dict(phase='decode', prompt_tokens=40, input_token=p.DECODE_TOKEN, position=40, rows=1,
                sources=['attn_norm-0', 'ffn_norm-0', 'ffn_swiglu-0', 'result_norm'],
                complete_prefill_executed=True, complete_decode_executed=False,
                performance_measured=False, input_differs_from_prefill=True)


def log_fixture():
    text = 'PROJECTION_CAPTURE_TOKENS count=40 ids=' + ','.join(map(str, metadata()['token_ids'])) + '\n'
    text += 'PROJECTION_CAPTURE_SHAPE source=attn_norm-0 k=2048 rows=4 tokens=40 type=f32\n'
    for row in range(4):
        for offset in range(0, 2048, 16):
            bits = ''.join(f'{struct.unpack("<I", struct.pack("<f", row + offset + i + 0.5))[0]:08x}'
                           for i in range(16))
            text += f'PROJECTION_CAPTURE_DATA row={row} offset={offset} bits={bits}\n'
    return text + 'PROJECTION_CAPTURE_DONE bytes=32768 stop=before_first_projection performance=not_measured\n'


def fake_model():
    row_bytes = p.K // 256 * 144
    raw = np.zeros((p.VOCAB, row_bytes), dtype=np.uint8)
    for i, token in enumerate(p.TOKENS):
        raw[token, :] = i + 1
    raw[p.DECODE_TOKEN, :] = 9
    emb = SimpleNamespace(name='token_embd.weight', tensor_type=Quant.Q4_K,
                          shape=np.array([p.K, p.VOCAB]), n_elements=p.K * p.VOCAB,
                          n_bytes=raw.nbytes, data=raw)
    weights = np.arange(p.K, dtype=np.float32)
    norm = SimpleNamespace(name='blk.0.attn_norm.weight', tensor_type=Quant.F32,
                           shape=np.array([p.K]), n_elements=p.K, n_bytes=weights.nbytes,
                           data=weights)
    reader = SimpleNamespace(tensors=[emb, norm], endianess='little', fields={
        'general.architecture': Field('qwen3', Value.STRING),
        'qwen3.attention.layer_norm_rms_epsilon': Field(float(np.float32(1e-6)), Value.FLOAT32)})
    calls = []

    def decode(data, kind):
        calls.append((data.shape, kind, data.nbytes))
        if kind == Quant.F32:
            return data.view(np.float32)
        return np.repeat(data[:, :1].astype(np.float32), p.K, axis=1)

    gguf = SimpleNamespace(GGMLQuantizationType=Quant, GGUFValueType=Value,
                           GGUFEndian=SimpleNamespace(LITTLE='little'),
                           GGML_QUANT_SIZES={Quant.Q4_K: (256, 144)}, dequantize=decode)
    return reader, gguf, calls


class CaptureTests(unittest.TestCase):
    def test_checker_and_metadata_agree(self):
        payload, meta = check(log_fixture())
        p.validate_capture(payload, meta, metadata())
        self.assertEqual(len(payload), 32768)

    def test_reject_shape_type_and_truncated_log(self):
        text = log_fixture()
        for broken in (text.replace('k=2048', 'k=1024'), text.replace('type=f32', 'type=f16'),
                       text.replace('row=1 offset=0', 'row=0 offset=0'), text[:-128],
                       text.replace('bits=', 'bits=0', 1)):
            with self.subTest(broken=broken[:50]), self.assertRaises(ValueError):
                check(broken)

    def test_reject_token_order_even_when_both_metadata_copies_agree(self):
        meta = metadata()
        meta['token_ids'][:2] = meta['token_ids'][1::-1]
        with self.assertRaisesRegex(ValueError, 'token order'):
            p.validate_capture(bytes(32768), meta, deepcopy(meta))

    def test_reject_metadata_drift_and_payload_length(self):
        for key, value in (('rows', 3), ('k', 2047), ('source', 'norm-0'),
                           ('complete_model_executed', True), ('k', 2048.0)):
            meta = metadata()
            meta[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                p.validate_capture(bytes(32768), meta, deepcopy(meta))
        for payload in (bytes(32764), bytes(32772), struct.pack('<f', float('nan')) * 8192):
            with self.assertRaises(ValueError):
                p.validate_capture(payload, metadata(), metadata())


class DecodeTests(unittest.TestCase):
    def test_accept_real_decode_scope_and_reject_prefill_relabel(self):
        payload = struct.pack('<f', 1.0) * 2048
        p.validate_decode_metadata(payload, decode_metadata())
        for key, value in (('input_token', p.TOKENS[0]), ('input_token', 22406.0), ('rows', 4),
                           ('phase', 'prefill'), ('position', 0), ('complete_prefill_executed', False),
                           ('complete_decode_executed', True), ('input_differs_from_prefill', False),
                           ('performance_measured', True)):
            meta = decode_metadata()
            meta[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'Decode metadata'):
                p.validate_decode_metadata(payload, meta)

    def test_reject_truncated_oversized_nonfinite_decode(self):
        for payload in (bytes(8188), bytes(8196), struct.pack('<f', float('inf')) * 2048):
            with self.assertRaisesRegex(ValueError, 'Decode payload'):
                p.validate_decode_metadata(payload, decode_metadata())


class ReconstructionTests(unittest.TestCase):
    def setUp(self):
        # Keep storage small while preserving token IDs and quantized block geometry.
        self.constants = patch.multiple(p, K=256, VOCAB=51436)
        self.constants.start()
        self.addCleanup(self.constants.stop)
        self.reader, self.gguf, self.calls = fake_model()

    def test_only_four_rows_reach_dequantize_in_exact_order(self):
        inputs, weights, eps, details = p.reconstruct(self.reader, self.gguf)
        values = np.frombuffer(inputs, dtype='<f4').reshape(4, p.K)
        np.testing.assert_array_equal(values[:, 0], [1, 2, 3, 4])
        self.assertEqual(self.calls, [((4, 144), Quant.Q4_K, 576), ((256,), Quant.F32, 1024)])
        self.assertEqual(len(weights), p.K * 4)
        self.assertEqual(len(eps), 4)
        self.assertEqual(struct.unpack('<f', eps)[0], details['epsilon'])

    def test_decode_is_its_own_single_selected_token_not_prefill_row(self):
        values, selected_bytes = p.embedding_rows(self.reader, self.gguf, (p.DECODE_TOKEN,))
        self.assertEqual(values.shape, (1, p.K))
        self.assertTrue((values == 9).all())
        self.assertEqual(selected_bytes, 144)
        self.assertEqual(self.calls, [((1, 144), Quant.Q4_K, 144)])
        self.assertEqual(len(p.f32_bytes(values, (1, p.K))), p.K * 4)
        with self.assertRaisesRegex(ValueError, 'token order/type'):
            p.embedding_rows(self.reader, self.gguf, (p.TOKENS[0],))

    def test_invalid_embedding_shape_type_duplicate_and_truncation(self):
        emb = self.reader.tensors[0]
        for attr, value in (('shape', np.array([p.VOCAB, p.K])), ('tensor_type', Quant.Q6_K),
                            ('n_bytes', emb.n_bytes - 1), ('data', emb.data[:-1]),
                            ('n_elements', emb.n_elements - 1)):
            original = getattr(emb, attr)
            with self.subTest(attr=attr), self.assertRaises(ValueError):
                setattr(emb, attr, value)
                p.reconstruct(self.reader, self.gguf)
            setattr(emb, attr, original)
        self.reader.tensors.append(emb)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            p.reconstruct(self.reader, self.gguf)

    def test_invalid_norm_type_shape_and_truncation(self):
        norm = self.reader.tensors[1]
        for attr, value in (('shape', np.array([p.K, 1])), ('tensor_type', Quant.Q4_K),
                            ('data', norm.data[:-1]), ('n_bytes', norm.n_bytes - 4)):
            original = getattr(norm, attr)
            with self.subTest(attr=attr), self.assertRaises(ValueError):
                setattr(norm, attr, value)
                p.reconstruct(self.reader, self.gguf)
            setattr(norm, attr, original)

    def test_invalid_epsilon_arch_endian_and_tokens(self):
        key = 'qwen3.attention.layer_norm_rms_epsilon'
        for value in (-1.0, 0.0, float('nan'), float('inf'), '1e-6'):
            self.reader.fields[key].value = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                p.reconstruct(self.reader, self.gguf)
        self.reader.fields[key] = Field(1e-6, Value.STRING)
        with self.assertRaisesRegex(ValueError, 'non-f32'):
            p.reconstruct(self.reader, self.gguf)
        self.reader.fields[key] = Field(1e-6, Value.FLOAT32)
        for tokens in (p.TOKENS[::-1], (32, 4621, 17654), (32.0, 4621, 17654, 51435)):
            with self.assertRaises(ValueError):
                p.reconstruct(self.reader, self.gguf, tokens)
        self.reader.endianess = 'big'
        with self.assertRaisesRegex(ValueError, 'endian'):
            p.reconstruct(self.reader, self.gguf)
        self.reader.endianess = 'little'
        self.reader.fields['general.architecture'].value = 'llama'
        with self.assertRaisesRegex(ValueError, 'Qwen3'):
            p.reconstruct(self.reader, self.gguf)

    def test_nonfinite_decode_rejected(self):
        self.gguf.dequantize = lambda data, kind: np.full((4, p.K), np.nan, dtype=np.float32)
        with self.assertRaisesRegex(ValueError, 'decoded f32'):
            p.reconstruct(self.reader, self.gguf)


class OwnershipTests(unittest.TestCase):
    def test_first_pin_is_not_replaced_by_drift(self):
        pins = p.Pins()
        path = Path(__file__).resolve()
        with patch.object(p, 'digest', side_effect=['a' * 64, 'b' * 64, 'b' * 64]):
            pins.pin(path)
            with self.assertRaisesRegex(ValueError, 'Input drift'):
                pins.pin(path)
            self.assertEqual(pins.values[str(path)], 'a' * 64)
            with self.assertRaisesRegex(ValueError, 'Final input drift'):
                pins.verify()

    def test_active_worker_conflict(self):
        with patch.object(p, 'read', return_value={str(p.HERE / 'prepare_rms_norm_data.py'): 'pin'}):
            with self.assertRaisesRegex(ValueError, 'sealed'):
                p.worker_inventory()

    def test_authorized_expansion_refuses_arbitrary_prior_data(self):
        with patch.object(p, 'digest', return_value='wrong'), \
                patch.object(Path, 'mkdir') as mkdir, patch.object(Path, 'rename') as rename:
            with self.assertRaisesRegex(ValueError, 'unconsumed Prefill-only'):
                p.archive_prefill_only(p.OUT)
            mkdir.assert_not_called()
            rename.assert_not_called()

    def test_refuse_other_or_existing_output_without_writes(self):
        with self.assertRaisesRegex(ValueError, 'assigned fresh output'):
            p.prepare(p.MAIN / 'not-allowed')
        with patch.object(p, 'worker_inventory', return_value={}), \
                patch.object(Path, 'mkdir', side_effect=FileExistsError), \
                patch.object(p, 'write_new') as write:
            with self.assertRaises(FileExistsError):
                p.prepare(p.OUT)
            write.assert_not_called()


if __name__ == '__main__':
    unittest.main()
