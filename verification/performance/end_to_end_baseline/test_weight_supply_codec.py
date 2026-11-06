"""In-memory reversible codec and accounting tests; no EDA, model run or file writes."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

import study_weight_supply_codec as c


def packed(bits):
    out = bytearray((len(bits) + 7) // 8)
    for index, bit in enumerate(bits):
        out[index // 8] |= int(bit) << (index % 8)
    return bytes(out)


def scalar_planes(raw, profile):
    if profile == 'Q4_K':
        codes = [(raw[16 + group * 32 + lane] >> shift) & 15
                 for group in range(4) for shift in (0, 4) for lane in range(32)]
        fixed = raw[:16] + packed([(q >> bit) & 1 for q in codes for bit in range(3)])
        residual = packed([1 ^ ((q >> 3) & 1) ^ ((q >> 2) & 1) for q in codes])
    else:
        codes = [(raw[128 + half * 32 + lane] >> shift) & 3
                 for half in range(2) for shift in (0, 2, 4, 6) for lane in range(32)]
        fixed = raw[:128] + packed([q >> 1 for q in codes]) + raw[192:]
        residual = packed([1 ^ (q >> 1) ^ (q & 1) for q in codes])
    return fixed, residual


def with_residual(residual, profile):
    bits = [(byte >> bit) & 1 for byte in residual for bit in range(8)]
    raw = bytearray(range(c.SIZES[profile][0]))
    for index, r in enumerate(bits):
        if profile == 'Q4_K':
            group, within = divmod(index, 64)
            high, lane = divmod(within, 32)
            at, shift, code = 16 + group * 32 + lane, high * 4, (1 ^ r) << 3
            raw[at] = (raw[at] & ~(15 << shift)) | (code << shift)
        else:
            half, within = divmod(index, 128)
            pair, lane = divmod(within, 32)
            at, shift, code = 128 + half * 32 + lane, pair * 2, 2 | r
            raw[at] = (raw[at] & ~(3 << shift)) | (code << shift)
    return bytes(raw)


class RoundtripTests(unittest.TestCase):
    def test_scalar_reference_and_vectorized_full_block_restoration(self):
        rng = np.random.default_rng(20261106)
        for profile, (size, fixed_size) in c.SIZES.items():
            raw = rng.integers(0, 256, size=(257, size), dtype=np.uint8)
            fixed, residual = c.transform(raw, profile)
            self.assertEqual(fixed.shape, (257, fixed_size))
            self.assertEqual(residual.shape, (257, 32))
            np.testing.assert_array_equal(c.restore(fixed, residual, profile), raw)
            for index in range(257):
                f, r = scalar_planes(raw[index].tobytes(), profile)
                self.assertEqual(fixed[index].tobytes(), f)
                self.assertEqual(residual[index].tobytes(), r)

    def test_random_and_all_repeated_byte_patterns_serialized_roundtrip(self):
        rng = np.random.default_rng(19)
        for profile, (size, _) in c.SIZES.items():
            samples = [bytes([value]) * size for value in range(256)]
            samples += [row.tobytes() for row in rng.integers(0, 256, size=(256, size), dtype=np.uint8)]
            for raw in samples:
                encoded = c.encode_block(raw, profile)
                self.assertEqual(c.decode_block(encoded, profile), raw)
                fixed, residual = scalar_planes(raw, profile)
                self.assertEqual(len(encoded), min(1 + size, 1 + len(fixed) + 4 + sum(b != 0 for b in residual)))

    def test_every_nonzero_count_and_raw_tie_at_28(self):
        for profile, (size, fixed_size) in c.SIZES.items():
            for nnz in range(33):
                residual = bytes([0x7e]) * nnz + bytes(32 - nnz)
                raw = with_residual(residual, profile)
                self.assertEqual(scalar_planes(raw, profile)[1], residual)
                encoded = c.encode_block(raw, profile)
                self.assertEqual(encoded[0], int(nnz < 28))
                self.assertEqual(len(encoded), min(size + 1, fixed_size + 5 + nnz))
                self.assertEqual(c.decode_block(encoded, profile), raw)

    def test_sparse_byte_bitmap_order_and_untouched_metadata(self):
        residual = bytearray(32)
        for index, value in ((0, 1), (7, 128), (8, 17), (31, 255)):
            residual[index] = value
        for profile, (_, fixed_size) in c.SIZES.items():
            raw = with_residual(residual, profile)
            encoded = c.encode_block(raw, profile)
            self.assertEqual(encoded[0], 1)
            self.assertEqual(encoded[1 + fixed_size:5 + fixed_size], bytes([0x81, 0x01, 0x00, 0x80]))
            self.assertEqual(encoded[5 + fixed_size:], bytes([1, 128, 17, 255]))
            restored = c.decode_block(encoded, profile)
            self.assertEqual(restored, raw)
            if profile == 'Q4_K':
                self.assertEqual(restored[:16], raw[:16])
            else:
                self.assertEqual(restored[:128] + restored[192:], raw[:128] + raw[192:])

    def test_truncation_extra_bytes_invalid_mode_and_zero_suppressed_value(self):
        for profile in c.SIZES:
            raw = with_residual(bytes([5]) + bytes(31), profile)
            encoded = c.encode_block(raw, profile)
            for length in range(len(encoded)):
                with self.assertRaises(ValueError):
                    c.decode_block(encoded[:length], profile)
            for malformed in (encoded + b'x', b'\x02' + encoded[1:], encoded[:-1] + b'\0',
                              b'\0' + raw[:-1], b'\0' + raw + b'x'):
                with self.assertRaises(ValueError):
                    c.decode_block(malformed, profile)

    def test_invalid_raw_shape_type_profile_and_transformed_plane(self):
        for raw in (np.zeros((1, 143), dtype=np.uint8), np.zeros((1, 144), dtype=np.uint16),
                    np.zeros(144, dtype=np.uint8)):
            with self.assertRaises(ValueError):
                c.transform(raw, 'Q4_K')
        with self.assertRaises(ValueError):
            c.encode_block(bytes(144), 'Q8_0')
        with self.assertRaises(ValueError):
            c.restore(np.zeros((1, 112), dtype=np.uint8), np.zeros((1, 31), dtype=np.uint8), 'Q4_K')


class AccountingTests(unittest.TestCase):
    def test_mode_and_four_byte_panel_costs(self):
        for profile, (size, fixed) in c.SIZES.items():
            hist = [0] * 33
            hist[0], hist[32] = 4, 4
            stats = c.finish_tensor(hist, 4 * 256, 8, profile)
            self.assertEqual(stats['selected_block_stream_bytes'], 4 * (fixed + 5) + 4 * (size + 1))
            self.assertEqual(stats['panel_count'], 1)
            self.assertEqual(stats['panel_index_bytes'], 4)
            self.assertEqual(stats['candidate_bytes_with_index'], stats['selected_block_stream_bytes'] + 4)
            self.assertEqual(stats['stored_block_mode_bytes'], 8)
            self.assertEqual(stats['raw_block_modes'], 4)
            self.assertEqual(stats['compressed_block_modes'], 4)
            self.assertFalse(stats['tensor_raw_fallback'])

    def test_tensor_raw_fallback_and_no_index_or_mode_charges_on_raw_tensor(self):
        for profile, (size, _) in c.SIZES.items():
            hist = [0] * 33
            hist[32] = 9
            stats = c.finish_tensor(hist, 9 * 256, 9, profile)
            self.assertTrue(stats['tensor_raw_fallback'])
            self.assertEqual(stats['stored_bytes'], size * 9)
            self.assertEqual(stats['panel_index_bytes'], 8)
            self.assertEqual(stats['stored_panel_index_bytes'], 0)
            self.assertEqual(stats['stored_block_mode_bytes'], 0)

    def test_aggregate_keeps_per_tensor_fallback_not_profile_level_fallback(self):
        hist = [0] * 33
        hist[32] = 8
        raw = c.finish_tensor(hist, 2048, 8, 'Q4_K')
        hist[32], hist[0] = 0, 8
        compressed = c.finish_tensor(hist, 0, 8, 'Q4_K')
        total = c.aggregate([raw, compressed])
        self.assertEqual(total['stored_bytes'], raw['raw_bytes'] + compressed['stored_bytes'])
        self.assertEqual(total['tensor_raw_fallbacks'], 1)
        self.assertEqual(total['stored_panel_index_bytes'], 4)
        self.assertGreater(total['best_zero_residual_bytes_with_index'] / total['raw_bytes'], 0.5)

    def test_invalid_histogram_and_unrestored_or_impossible_bit_counts(self):
        hist = [0] * 33
        hist[32] = 8
        for values, ones, restored in ((hist, 0, 8), (hist, 2048, 7), (hist, 2049, 8),
                                       ([0] * 32, 0, 0), ([0.0] * 33, 0, 0), ([-1] * 33, 0, 0)):
            with self.assertRaises(ValueError):
                c.finish_tensor(values, ones, restored, 'Q4_K')

    def test_report_geometry_and_accounting_drift(self):
        rows = []
        for index in range(197):
            profile = 'Q4_K' if index % 2 else 'Q6_K'
            hist = [8] + [0] * 32
            stats = c.finish_tensor(hist, 0, 8, profile)
            rows.append(dict(tensor=f'test.{index}', profile=profile, k=2048, n=1,
                             tensor_bytes=stats['raw_bytes'], **stats))
        profiles = {p: c.aggregate([r for r in rows if r['profile'] == p]) for p in c.SIZES}
        total = c.aggregate(rows)
        c.verify_statistics(rows, profiles, total)
        for key in ('stored_bytes', 'panel_index_bytes', 'restored_blocks'):
            broken = deepcopy(rows)
            broken[0][key] += 1
            with self.assertRaises(ValueError):
                c.verify_statistics(broken, profiles, total)


class BoundariesTests(unittest.TestCase):
    def test_original_graph_manifest_supplies_missing_trace_sources_without_relaxing_pins(self):
        path = Path('/original/ggml-quants.c')
        self.assertEqual(c.original_source_hash(path, {}, {str(path): 'locked'}), 'locked')
        self.assertEqual(c.original_source_hash(path, {str(path): 'locked'}, {str(path): 'locked'}), 'locked')
        with self.assertRaisesRegex(ValueError, 'disagreement'):
            c.original_source_hash(path, {str(path): 'different'}, {str(path): 'locked'})
        with self.assertRaisesRegex(ValueError, 'absent'):
            c.original_source_hash(path, {str(path): 'locked'}, {})

    def test_original_schema_order_and_negative_shape_profile_token_embedding(self):
        # Read-only extraction of the same sealed schema source; no campaign imports.
        source = (c.HERE / 'trace_context_model.py').read_text()
        weights = c.read(c.TRACE / 'projection-schema.json')
        calls = c.original_schema(source, weights)
        self.assertEqual(len(calls['0']), 197)
        self.assertEqual([w['tensor'] for w in weights[:3]],
                         ['blk.0.attn_q.weight', 'blk.0.attn_v.weight', 'blk.0.attn_k.weight'])
        self.assertEqual(calls['1'][-1]['output_rows'], 151936)
        for key, value in (('k', 1024), ('k', 2048.0), ('type', 'q8_0'), ('tensor', 'token_embd.weight')):
            broken = deepcopy(weights)
            broken[0][key] = value
            with self.assertRaises(ValueError):
                c.original_schema(source, broken)
        with self.assertRaises(ValueError):
            c.original_schema(source, weights[1:] + weights[:1])

    def test_frozen_pin_cannot_be_replaced(self):
        pins, path = c.Pins(), Path(__file__).resolve()
        with patch.object(c, 'digest', side_effect=['a', 'b', 'b']):
            pins.pin(path)
            with self.assertRaises(ValueError):
                pins.pin(path)
            self.assertEqual(pins.values[str(path)], 'a')
            with self.assertRaises(ValueError):
                pins.verify()

    def test_fresh_output_and_worker_conflict(self):
        with self.assertRaises(ValueError):
            c.run(c.MAIN / 'not-allowed')
        with patch.object(c, 'read', return_value={str(c.HERE / c.OWNED[0]): 'pin'}):
            with self.assertRaisesRegex(ValueError, 'sealed by worker'):
                c.worker_inventory()
        with patch.object(c, 'worker_inventory', return_value=[]), \
                patch.object(Path, 'mkdir', side_effect=FileExistsError), \
                patch.object(c, 'write_new') as write:
            with self.assertRaises(FileExistsError):
                c.run(c.OUT)
            write.assert_not_called()


if __name__ == '__main__':
    unittest.main()
