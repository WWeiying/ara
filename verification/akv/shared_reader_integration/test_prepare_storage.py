import json
from pathlib import Path
import tempfile
import unittest

import prepare as reader
import prepare_storage as storage


class StorageOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = (reader.ROOT / reader.MODULES["akv"]).read_text()
        cls.reader_only = reader.engine(cls.original, "akv")
        cls.changed = storage.transform_engine(cls.reader_only)

    def test_exact_scope_outside_instance_replacement(self):
        a, _, _ = storage.instance(self.reader_only, "akv_context", "i_context")
        _, b, _ = storage.instance(self.reader_only, "akv_v2_context", "i_v2_context")
        c, d, _ = storage.instance(self.changed, "akv_unified_context", "i_unified_context")
        comment = "  // Unified payload only; command, metadata, replay and fault FSM are unchanged.\n"
        self.assertEqual(self.reader_only[:a-len(storage.BUSY_ASSIGN)], self.changed[:c-len(comment)])
        self.assertEqual(self.reader_only[b:], self.changed[d:])
        self.assertNotIn("akv_context i_context", self.changed)
        self.assertNotIn("akv_v2_context i_v2_context", self.changed)
        self.assertEqual(self.changed.count("akv_unified_context i_unified_context"), 1)

    def test_every_old_port_preserved(self):
        _, _, actual = storage.instance(self.changed, "akv_unified_context", "i_unified_context")
        expected = {"abort_i": "read_fault_valid && read_fault_ready",
                    "legacy_row_bytes_i": "9'(payload_row_bytes)",
                    "write_busy_o": "context_write_busy"}
        for module, instance, mapping in (
                ("akv_context", "i_context", storage.LEGACY_PORTS),
                ("akv_v2_context", "i_v2_context", storage.V2_PORTS)):
            _, _, old = storage.instance(self.reader_only, module, instance)
            expected.update({new: old[key] for key, new in mapping.items()})
        self.assertEqual(actual, expected)
        self.assertNotIn("assign context_write_busy", self.changed)

    def test_live_head_dim_before_payload_and_fault_state_unchanged(self):
        self.assertIn("if (state_q == AKV_ENGINE_VALIDATE) begin\n        if (descriptor_valid) begin\n"
                      "          context_q_rows_q <= descriptor.q_rows;\n"
                      "          context_head_dim_q <= descriptor.head_dim;", self.changed)
        self.assertIn("assign payload_row_bytes = context_head_dim_q << 1;", self.changed)
        self.assertIn("read_range_bytes = RangeBytesWidth'(payload_row_bytes);", self.changed)
        anchor = "  assign replay_request_fire ="
        self.assertEqual(self.reader_only[self.reader_only.index(anchor):],
                         self.changed[self.changed.index(anchor):])

    def test_unknown_or_duplicated_ports_rejected(self):
        mutations = [self.reader_only.replace(".write_slot_i", ".other_slot_i", 1),
                     self.reader_only.replace("    .write_slot_i   (context_write_slot),",
                                              "    .write_slot_i(context_write_slot),\n"
                                              "    .write_slot_i(context_write_slot),", 1),
                     self.reader_only.replace("context_head_dim_q << 1", "command_head_dim_i << 1", 1),
                     self.reader_only.replace(storage.BUSY_ASSIGN, ""), self.changed]
        for index, text in enumerate(mutations):
            with self.subTest(mutation=index), self.assertRaises(ValueError):
                storage.transform_engine(text)

    def test_filelist_order_unchanged_except_three_modules(self):
        engine, support = Path("/private/engine.sv"), Path("/private/support")
        lines = ["+define+EXISTING", "/private/akv_pkg.sv", str(engine), "/private/vlsu.sv"]
        actual = storage.storage_filelist(lines, engine, support)
        inserted = [str(support / p.name) for p in reversed(storage.SUPPORT)]
        self.assertEqual(actual, lines[:2] + inserted + lines[2:])
        self.assertNotIn("unified_storage_tb.sv", "\n".join(actual))
        for bad in (lines + [str(engine)], lines[:2], actual):
            with self.assertRaises(ValueError):
                storage.storage_filelist(bad, engine, support)

    def test_shared_reader_and_qbs_transform_stays_identical(self):
        self.assertEqual(self.reader_only[:self.reader_only.index("  always_comb begin\n    unique case (read_data_tag.role)")],
                         self.changed[:self.changed.index("  always_comb begin\n    unique case (read_data_tag.role)")])
        for name in ("shared_wave.py", "sharedwave_checker.py", "admission_assertions.svh"):
            text = (reader.HERE / name).read_text()
            self.assertNotIn("i_akv_engine.i_context.", text)
            self.assertNotIn("i_akv_engine.i_v2_context.", text)
        self.assertNotIn("i_context.", self.reader_only)
        self.assertNotIn("i_v2_context.", self.reader_only)

    def test_actual_two_profile_proof(self):
        pins, receipts = storage.accepted_units()
        self.assertEqual(set(receipts), {"tc", "macro"})
        for path in storage.SUPPORT:
            self.assertEqual(pins[str(path)], reader.digest(path))
        models = [p for p in pins if "/VERILOG/" in p]
        self.assertEqual(len(models), 3)
        self.assertTrue(any("64x256" in p for p in models))

    def test_conflicting_pin_rejected(self):
        self.assertEqual(storage.merge_pins({"a": "1"}, {"a": "1", "b": "2"}), {"a": "1", "b": "2"})
        with self.assertRaises(ValueError):
            storage.merge_pins({"a": "1"}, {"a": "2"})

    def test_wrong_snapshot_type_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp)
            (snapshot / "manifest.json").write_text(json.dumps({"state": "PREPARED_NOT_COMPILED"}))
            with self.assertRaises(ValueError):
                storage.validate_snapshot(snapshot)


if __name__ == "__main__":
    unittest.main()
