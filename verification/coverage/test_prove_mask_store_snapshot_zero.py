import unittest

import prove_mask_store_snapshot_zero as p


class SourceProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.texts = dict(
            package=(p.ROOT / 'hardware/include/ara_pkg.sv').read_text(),
            sequencer=(p.OUT / 'old-image-source-evidence-20261006-01/lane_sequencer.sv').read_text(),
            requester=(p.ROOT / 'hardware/src/lane/operand_requester.sv').read_text(),
            lane=(p.ROOT / 'hardware/src/lane/lane.sv').read_text())

    def reject(self, key, old, new):
        texts = dict(self.texts)
        self.assertIn(old, texts[key])
        texts[key] = texts[key].replace(old, new, 1)
        with self.assertRaises(ValueError):
            p.source_contract(**texts)

    def test_actual_frozen_write_ledger(self):
        result = p.source_contract(**self.texts)
        self.assertEqual(result['literal_lines'], dict(MaskM=[539, 631, 657, 744, 903, 1107], StA=[721]))

    def test_enum_role_swap(self):
        self.reject('package', 'MaskM, StA, SlideAddrGenA', 'SlideAddrGenA, StA, MaskM')

    def test_whole_literal_replay_override(self):
        self.reject('sequencer', "operand_request[StA] = '{", "operand_request[StA] = '{source_snapshot_replay:1'b1,")

    def test_direct_field_override(self):
        texts = dict(self.texts)
        texts['sequencer'] += "\noperand_request[MaskM].source_snapshot_replay = 1'b1;\n"
        with self.assertRaises(ValueError):
            p.source_contract(**texts)

    def test_dynamic_port_override(self):
        texts = dict(self.texts)
        texts['sequencer'] += "\noperand_request[q].source_snapshot_replay = 1'b1;\n"
        with self.assertRaises(ValueError):
            p.source_contract(**texts)

    def test_queue_reset_nonzero(self):
        self.reject('sequencer', "operand_request_o       <= '0;", "operand_request_o <= '1;")

    def test_metadata_reset_nonzero(self):
        self.reject('requester', "requester_metadata_q[requester_index] <= '0;",
                    "requester_metadata_q[requester_index] <= '1;")

    def test_metadata_direct_replay_override(self):
        texts = dict(self.texts)
        texts['requester'] += "\nrequester_metadata_d[requester_index].source_snapshot_replay = 1'b1;\n"
        with self.assertRaises(ValueError):
            p.source_contract(**texts)

    def test_metadata_wrong_input(self):
        self.reject('requester', 'source_snapshot_replay: operand_request_i[requester_index].source_snapshot_replay,',
                    "source_snapshot_replay: 1'b1,")

    def test_route_alias(self):
        self.reject('lane', '.operand_request_i        (operand_request         )',
                    '.operand_request_i        (other_request           )')

    def test_replay_valid_ungated(self):
        self.reject('requester', 'if (requester_metadata_q[requester_index].source_snapshot_replay) begin',
                    "if (1'b1) begin")

    def test_comments_cannot_supply_writes(self):
        texts = dict(self.texts)
        texts['sequencer'] += "\n// operand_request[MaskM].source_snapshot_replay = 1'b1;\n"
        p.source_contract(**texts)

    def test_actual_compiled_roles_and_protected_port8(self):
        import json
        bits = json.loads((p.BASE / 'combined-bits.json').read_bytes())
        design = p.context.s.Design(p.context.old.BUILD / 'sim/simv.vdb')
        candidates, protected = p.compiled_points(design, bits)
        self.assertEqual(len(candidates), 32)
        self.assertEqual({r['port'] for r in candidates}, {6, 7})
        self.assertTrue(all(not r['hit_before'] for r in candidates))
        self.assertTrue(any(r['port'] == 8 and r['hit_before'] for r in protected))


if __name__ == '__main__':
    unittest.main()
