#!/usr/bin/env python3
"""Independent transfer-grid assertions for SDK reader floors/protocol checking."""
import hashlib
from pathlib import Path
import unittest

import supply_footprint as f


def transfer_grid(address, length, step):
    """Reference: enumerate touched transfer cells, then greedily group AXI ARs."""
    cells = list(range(address//step*step, (address+length+step-1)//step*step, step))
    groups = []
    for cell in cells:
        if not groups or len(groups[-1]) == 256 or cell//4096 != groups[-1][0]//4096:
            groups.append([])
        groups[-1].append(cell)
    return groups


class SupplyFootprintTests(unittest.TestCase):
    def assert_grid(self, address, length, physical, step):
        actual = f.plan_range(address, length, physical_bits=physical, transfer_bytes=step)
        grid = transfer_grid(address, length, step)
        self.assertEqual(len(actual), len(grid))
        for burst, cells in zip(actual, grid):
            left, right = max(address, cells[0]), min(address+length, cells[-1]+step)
            self.assertEqual((burst.ar_address, burst.beats, burst.ar_size, burst.ar_len),
                             (cells[0], len(cells), step.bit_length()-1, len(cells)-1))
            self.assertEqual((burst.cursor, burst.range_offset, burst.payload_bytes), (left, left-address, right-left))
            self.assertEqual((burst.first_lane, burst.first_transfer_byte), (left % (physical//8), left % step))
            self.assertEqual((burst.footprint_bytes, burst.footprint_end), (len(cells)*step, cells[-1]+step))
            self.assertLessEqual(burst.beats, 256)
            self.assertEqual(burst.ar_address//4096, (burst.footprint_end-1)//4096)
        return actual

    def test_actual_planner_source_pin(self):
        root = Path(__file__).resolve().parents[3]
        self.assertEqual(hashlib.sha256((root/f.REFERENCE_RTL).read_bytes()).hexdigest(), f.REFERENCE_RTL_SHA256)

    def test_all_page_offsets_native_workloads(self):
        # Includes every bus phase, both physical halves, exact page endings
        # and all possible first/last-page splits of these native byte lengths.
        for physical in (128, 256):
            for length, step in ((16, 16), (292, 16), (576, physical//8), (840, physical//8)):
                for offset in range(4096):
                    self.assert_grid(0x10000+offset, length, physical, step)

    def test_aligned_native_goldens(self):
        for physical, q4, q6 in ((128, 36, 53), (256, 18, 27)):
            for profile, beats, payload in (('Q4_K', q4, 576), ('Q6_K', q6, 840)):
                summary = f.summarize(f.qbs_request('weights', 0x10000, physical_bits=physical, profile=profile))
                self.assertEqual(summary, dict(ar_count=1, r_beats=beats, payload_bytes=payload,
                                               footprint_bytes=beats*(physical//8)))
            self.assertEqual(f.summarize(f.qbs_request('activation', 0x10000, physical_bits=physical)),
                             dict(ar_count=1, r_beats=19, payload_bytes=292, footprint_bytes=304))
            self.assertEqual(f.summarize(f.qbs_request('header', 0x10000, physical_bits=physical)),
                             dict(ar_count=1, r_beats=1, payload_bytes=16, footprint_bytes=16))

    def test_phase_beats_not_merely_ceil_payload(self):
        for physical, profile, phase, beats in ((128, 'Q4_K', 1, 37), (256, 'Q4_K', 1, 19),
                                              (128, 'Q6_K', 9, 54), (256, 'Q6_K', 25, 28)):
            request = f.qbs_request('weights', 0x10000+phase, physical_bits=physical, profile=profile)
            self.assertEqual(f.summarize(request)['r_beats'], beats)
            self.assertGreater(beats, (request[0].payload_bytes+physical//8-1)//(physical//8))
        self.assertEqual(f.summarize(f.qbs_request('activation', 0x1000d, physical_bits=256))['r_beats'], 20)

    def test_256_narrow_upper_half_is_not_extra_transfer_head(self):
        b, = f.plan_range(0x1010, 16, physical_bits=256, transfer_bytes=16)
        self.assertEqual((b.first_lane, b.first_transfer_byte, b.ar_address, b.beats), (16, 0, 0x1010, 1))
        self.assertEqual(b.footprint_bytes, 16)
        self.assertNotEqual((b.first_lane+16+15)//16, b.beats)
        self.assertNotEqual(b.ar_address, 0x1010//32*32)

    def test_narrow_steps_toggle_bus_halves_and_compact(self):
        bursts = self.assert_grid(0x101d, 49, 256, 16)
        beats = [beat for burst in bursts for beat in burst.payload_beats()]
        self.assertEqual([b.first_lane for b in beats], [29, 0, 16, 0])
        self.assertEqual([b.payload_bytes for b in beats], [3, 16, 16, 14])
        self.assertEqual([b.range_offset for b in beats], [0, 3, 19, 35])
        self.assertEqual([b.compacted_strb for b in beats], [7, 65535, 65535, 16383])
        self.assertEqual([b.physical_word_address for b in beats], [0x1000, 0x1020, 0x1020, 0x1040])
        self.assertEqual([b.rlast for b in beats], [False, False, False, True])

    def test_every_payload_byte_and_prefix_strobe(self):
        for physical in (128, 256):
            for phase in range(32):
                for length, step in ((16, 16), (292, 16), (576, physical//8), (840, physical//8)):
                    start = 0x1ff0+phase
                    seen = []
                    for burst in self.assert_grid(start, length, physical, step):
                        beats = burst.payload_beats()
                        self.assertEqual(len(beats), burst.beats)
                        for beat in beats:
                            self.assertTrue(0 < beat.payload_bytes <= step)
                            self.assertLessEqual(beat.first_lane+beat.payload_bytes, physical//8)
                            self.assertEqual(beat.compacted_strb, (1 << beat.payload_bytes)-1)
                            seen.extend(range(beat.physical_word_address+beat.first_lane,
                                              beat.physical_word_address+beat.first_lane+beat.payload_bytes))
                    self.assertEqual(seen, list(range(start, start+length)))

    def test_page_split_and_exact_page_end(self):
        for physical in (128, 256):
            bursts = self.assert_grid(0x1ff0, 840, physical, physical//8)
            self.assertEqual([b.payload_bytes for b in bursts], [16, 824])
            self.assertEqual([b.range_offset for b in bursts], [0, 16])
            self.assertEqual(bursts[0].footprint_end, 0x2000)
            b, = self.assert_grid(0x1ff0, 16, physical, 16)
            self.assertEqual((b.beats, b.footprint_end), (1, 0x2000))

    def test_max_burst_limit_where_page_limit_does_not_mask_it(self):
        # At transfer sizes 16/32, a 4 KiB page already bounds bursts to <=256
        # beats. Legal byte/8-byte transfers independently exercise AXI LEN.
        for physical in (128, 256):
            self.assertEqual([b.beats for b in self.assert_grid(0x1003, 600, physical, 1)], [256, 256, 88])
            bursts = self.assert_grid(0x1003, 4096, physical, 8)
            self.assertEqual([b.payload_bytes for b in bursts], [2045, 2048, 3])
            self.assertEqual([b.beats for b in bursts], [256, 256, 1])
            self.assert_grid(0x1fff, 65535, physical, 16)

    def test_fixed_mode_and_per_range_distinguished(self):
        for role in ('header', 'descriptor', 'activation'):
            narrow = f.qbs_request(role, 0x1010, physical_bits=256)
            wrong = f.qbs_request(role, 0x1010, physical_bits=256, per_range=False)
            self.assertTrue(all(b.transfer_bytes == 16 for b in narrow))
            self.assertTrue(all(b.transfer_bytes == 32 for b in wrong))
            self.assertNotEqual(narrow, wrong)
        for role, profile in (('header', None), ('activation', None), ('weights', 'Q6_K')):
            self.assertEqual(f.qbs_request(role, 0x1010, physical_bits=128, profile=profile),
                             f.qbs_request(role, 0x1010, physical_bits=128, profile=profile, per_range=False))

    def test_tail_row_counts_keep_native_bytes(self):
        for profile, native in (('Q4_K', 144), ('Q6_K', 210)):
            for rows in range(1, 5):
                bursts = f.qbs_request('weights', 0x1ffd, physical_bits=256, profile=profile, rows=rows)
                self.assertEqual(f.summarize(bursts)['payload_bytes'], rows*native)
                self.assertEqual(bursts, f.plan_range(0x1ffd, rows*native, physical_bits=256, transfer_bytes=32))

    def test_separate_requests_are_not_deduplicated_as_bus_words(self):
        first = f.qbs_request('header', 0x1000, physical_bits=256)
        second = f.qbs_request('header', 0x1010, physical_bits=256)
        self.assertEqual(f.summarize(first+second), dict(ar_count=2, r_beats=2, payload_bytes=32, footprint_bytes=32))
        self.assertEqual(first[0].payload_beats()[0].physical_word_address,
                         second[0].payload_beats()[0].physical_word_address)

    def test_invalid_ranges_and_impossible_transfer_rejected(self):
        for args in ((0, 0, 128, 16), (-1, 1, 128, 16), (1 << 64, 1, 128, 16),
                     ((1 << 64)-1, 2, 128, 16), (0, 65536, 256, 32),
                     (0, 1, 128, 32), (0, 1, 256, 24), (0, 1, 64, 8), (0, 1, 256, 0)):
            with self.assertRaises(ValueError):
                f.plan_range(args[0], args[1], physical_bits=args[2], transfer_bytes=args[3])
        for args in (('weights', 'Q8_0', 4), ('weights', 'Q6_K', 0), ('weights', 'Q4_K', 5),
                     ('activation', 'Q4_K', 4), ('unknown', None, 4)):
            with self.assertRaises(ValueError):
                f.qbs_request(args[0], 0x1000, physical_bits=256, profile=args[1], rows=args[2])


if __name__ == '__main__':
    unittest.main()
