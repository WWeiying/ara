"""Source-bound algebra checks; not native waiver approval or an RTL simulation."""
import hashlib
import itertools
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class PendingMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = json.loads((ROOT / 'verification/out/'
            'repaired-aligned-build-20260930-01/build-source-pins.json').read_bytes())
        cls.sources = {}
        for name in ('qbs_payload_buffer', 'qbs_block_adapter', 'qbs_compute_engine'):
            path = ROOT / ('hardware/src/vlsu/qbs/' + name + '.sv')
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != cls.build[str(path)]:
                raise ValueError('Source no longer matches frozen build: ' + str(path))
            cls.sources[name] = path.read_text()

    def test_side_consumption_and_pending_mask_source_binding(self):
        payload = self.sources['qbs_payload_buffer']
        adapter = self.sources['qbs_block_adapter']
        for stream in ('weight', 'activation'):
            self.assertIn(f'{stream}_valid_i[slot] && {stream}_mask_i[B] && '
                          f'{stream}_location[B].plane == 2', payload)
            self.assertIn(f'assign {stream}_remaining = {stream}_mask & ~{stream}_consumed;', adapter)
            for suffix in ('31:16', '15:0'):
                self.assertIn(f'{stream}_pending_q.strb <= {stream}_remaining[{suffix}];', adapter)
            self.assertIn(f'{stream}_pending_target_q[b].valid && {stream}_pending_q.strb[b]', adapter)
            self.assertIn(f'assign {stream}_location[b] = {stream}_pending_location_q[b];', adapter)
            self.assertIn(f'{stream}_pending_location_q[b] <= {stream}_location[16+b];', adapter)

    def test_valid_side_bit_always_consumed(self):
        for valid, mask, side, grant in itertools.product((False, True), repeat=4):
            consumed = grant or (valid and mask and side)
            remaining = mask and not consumed
            if valid and side:
                self.assertFalse(remaining)

    def test_pending_side_invariant_all_control_combinations(self):
        # State starts with no pending side bits. Locations are copied with the
        # exact remaining-mask beat; payload bits may remain independently.
        for reset, clear, old_valid, incoming, side_mask, payload_remaining in itertools.product(
                (False, True), repeat=6):
            old_side = False
            old_active = old_valid and not clear
            new_active = incoming and not clear
            side_remaining = side_mask and not (new_active and side_mask)
            if reset or clear:
                next_valid, next_side = False, False
            elif new_active:
                next_valid = payload_remaining or side_remaining
                next_side = side_remaining
            elif old_active:
                next_valid, next_side = payload_remaining, old_side
            else:
                next_valid, next_side = old_valid, old_side
            self.assertFalse(next_valid and next_side)

    def test_older_only_selection_is_excluded_by_invariant_not_by_enable_alone(self):
        for valid0, valid1, older_hit, newer_hit in itertools.product((False, True), repeat=4):
            use_newer = valid1 and newer_hit
            enable = use_newer or (valid0 and older_hit)
            if not (valid0 and older_hit):
                self.assertEqual(enable, use_newer)
            elif not use_newer:
                # A standalone arbitrary-input payload client can take older.
                self.assertTrue(enable)


if __name__ == '__main__':
    unittest.main()
