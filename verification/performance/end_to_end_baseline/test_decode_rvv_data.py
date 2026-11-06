import hashlib
from pathlib import Path
import random
import re
import unittest

import decode_rvv_data as codec


def destination(row, block, byte, blocks):
    tile = (row // 32 * blocks + block) * 4608
    lane = row % 32
    if byte < 2:
        return tile + 2 * lane + byte
    if byte < 4:
        return tile + 64 + 2 * lane + byte - 2
    if byte < 16:
        return tile + 128 + (byte - 4) * 32 + lane
    return tile + 512 + (byte - 16) * 32 + lane


class DecodeRvvDataTests(unittest.TestCase):
    def test_random_roundtrip_both_directions_all_requested_shapes(self):
        rng = random.Random(0x443332)
        for n in (32, 64, 128):
            for k in (256, 2048):
                with self.subTest(n=n, k=k):
                    raw = rng.randbytes(n * (k // 256) * 144)
                    packed = codec.pack_q4_r32(raw, n, k)
                    self.assertIsInstance(packed, bytes)
                    self.assertEqual(len(packed), len(raw))
                    self.assertEqual(codec.unpack_q4_r32(packed, n, k), raw)
                    arbitrary_packed = rng.randbytes(len(raw))
                    self.assertEqual(codec.pack_q4_r32(
                        codec.unpack_q4_r32(arbitrary_packed, n, k), n, k), arbitrary_packed)

    def test_every_byte_independent_field_offsets_and_tile_order(self):
        n, k, blocks = 128, 2048, 8
        raw = random.Random(713).randbytes(n * blocks * 144)
        packed = codec.pack_q4_r32(raw, n, k)
        seen = bytearray(len(raw))
        for row in range(n):
            for block in range(blocks):
                for byte in range(144):
                    target = destination(row, block, byte, blocks)
                    self.assertEqual(seen[target], 0)
                    seen[target] = 1
                    self.assertEqual(packed[target], raw[(row * blocks + block) * 144 + byte])
        self.assertEqual(seen, bytes([1]) * len(raw))

    def test_inverse_against_independently_constructed_layout(self):
        n, k, blocks = 64, 768, 3
        raw = random.Random(123).randbytes(n * blocks * 144)
        expected = bytearray(len(raw))
        for row in range(n):
            for block in range(blocks):
                for byte in range(144):
                    expected[destination(row, block, byte, blocks)] = raw[(row * blocks + block) * 144 + byte]
        self.assertEqual(codec.pack_q4_r32(raw, n, k), expected)
        self.assertEqual(codec.unpack_q4_r32(expected, n, k), raw)

    def test_adversarial_bit_patterns_and_half_fields_preserved(self):
        for value in (0, 255, 0x55, 0xaa):
            raw = bytes([value]) * (64 * 8 * 144)
            self.assertEqual(codec.pack_q4_r32(raw, 64, 2048), raw)
            self.assertEqual(codec.unpack_q4_r32(raw, 64, 2048), raw)
        raw = bytearray(32 * 144)
        half_patterns = (b"\x00\x80", b"\x01\x7c", b"\xff\x7f", b"\x01\x00")
        for row in range(32):
            raw[row * 144:row * 144 + 2] = half_patterns[row % 4]
            raw[row * 144 + 2:row * 144 + 4] = half_patterns[(row + 1) % 4]
            raw[row * 144 + 4:row * 144 + 16] = bytes((row + b * 17) % 256 for b in range(12))
            raw[row * 144 + 16:row * 144 + 144] = bytes((row * 7 + b) % 256 for b in range(128))
        packed = codec.pack_q4_r32(raw, 32, 256)
        self.assertEqual(packed[:64], b"".join(half_patterns[row % 4] for row in range(32)))
        self.assertEqual(packed[64:128], b"".join(half_patterns[(row + 1) % 4] for row in range(32)))
        self.assertEqual(codec.unpack_q4_r32(packed, 32, 256), raw)

    def test_buffers_are_not_modified_or_aliased(self):
        raw = bytearray(random.Random(8).randbytes(32 * 144))
        original = bytes(raw)
        packed = codec.pack_q4_r32(memoryview(raw), 32, 256)
        self.assertEqual(raw, original)
        packed_buffer = bytearray(packed)
        restored = codec.unpack_q4_r32(memoryview(packed_buffer), 32, 256)
        self.assertEqual(packed_buffer, packed)
        raw[:] = bytes(len(raw))
        packed_buffer[:] = bytes(len(packed_buffer))
        self.assertEqual(restored, original)
        self.assertEqual(codec.unpack_q4_r32(packed, 32, 256), original)

    def test_invalid_geometry_and_type_rejected(self):
        for function in (codec.pack_q4_r32, codec.unpack_q4_r32):
            for n, k in ((0, 256), (-32, 256), (1, 256), (31, 256), (33, 256),
                         (32, 0), (32, -256), (32, 255), (32, 257),
                         (True, 256), (32, False), (32.0, 256), (32, 256.0), ("32", 256)):
                with self.subTest(function=function.__name__, n=n, k=k), self.assertRaises(ValueError):
                    function(b"", n, k)
            for payload in (None, "x", 4608, [0] * 4608):
                with self.assertRaises(TypeError):
                    function(payload, 32, 256)
            for payload in (b"", bytes(4607), bytes(4609), bytes(32 * 210)):
                with self.assertRaises(ValueError):
                    function(payload, 32, 256)
            for payload in (memoryview(bytes(9216))[::2],
                            memoryview(bytes(4608)).cast("B", shape=(32, 144)),
                            memoryview(bytes(4608)).cast("H")):
                with self.assertRaises(ValueError):
                    function(payload, 32, 256)

    def test_frozen_original_source_fields_and_order(self):
        sources = {}
        for name, sha in codec.SOURCE_PINS.items():
            data = Path(name).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), sha)
            sources[Path(name).name] = data.decode("utf-8")
        header = sources["repack.h"]
        declaration = re.search(r"struct block_q4_Kx32_ara\s*\{(.*?)\};", header, re.S).group(1)
        self.assertEqual(" ".join(declaration.split()),
            "ggml_half d[32]; ggml_half dmin[32]; uint8_t scales[K_SCALE_SIZE * 32]; "
            "uint8_t qs[(QK_K / 2) * 32];")
        source = sources["repack.cpp"]
        start = source.index("static block_q4_Kx32_ara make_block_q4_Kx32_ara(")
        end = source.index("static block_q2_Kx8", start)
        original = source[start:end]
        for statement in (
            "out.d[row]    = in[row].GGML_COMMON_AGGR_U.GGML_COMMON_AGGR_S.d;",
            "out.dmin[row] = in[row].GGML_COMMON_AGGR_U.GGML_COMMON_AGGR_S.dmin;",
            "out.scales[byte * 32 + row] = in[row].scales[byte];",
            "out.qs[byte * 32 + row] = in[row].qs[byte];",
            "for (size_t row_base = 0; row_base < rows; row_base += rows_per_tile)",
            "for (size_t block = 0; block < blocks_per_row; ++block)",
            "input[(row_base + row) * blocks_per_row + block]",
            "*output++ = make_block_q4_Kx32_ara(rows_for_block);",
        ):
            self.assertIn(statement, original)


if __name__ == "__main__":
    unittest.main()
