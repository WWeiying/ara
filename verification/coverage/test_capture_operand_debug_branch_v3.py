import copy
import unittest

import capture_operand_debug_branch_v3 as successor
from test_capture_operand_debug import fixture


class NativeQuotedFieldTests(unittest.TestCase):
    def evidence(self):
        config = fixture()
        scope = "top.requester"
        config["plan"]["scopes"][scope].pop("line")
        point = config["plan"]["scopes"][scope]["branch"][0]["point"]
        point["expressions"][0]["exprstr"] = '$test$plusargs("DEBUG")'
        expr = successor.quoted_field(point["expressions"][0]["exprstr"])
        raw = ('CHECKSUM: "11 22"\nINSTANCE: top.requester\nANNOTATION: "' + successor.base.debug.ANNOTATION +
               '"\nBranch 3 "88" "' + expr + '" (4) "' + expr + ' 0,-,-"\n').encode()
        return raw, config

    def test_exact_native_source_quoting(self):
        raw, config = self.evidence()
        before = copy.deepcopy(config)
        self.assertEqual(len(successor.bind_native(raw, config)), 1)
        self.assertEqual(config, before)

    def test_unescaped_wrong_string_and_unknown_escape_rejected(self):
        raw, config = self.evidence()
        for modified in (raw.replace(b'\\"', b'"'), raw.replace(b'DEBUG', b'OTHER'),
                         raw.replace(b'\\"DEBUG', b'\\nDEBUG')):
            with self.subTest(raw=modified), self.assertRaises(ValueError):
                successor.bind_native(modified, config)

    def test_extra_metric_and_checksum_rejected(self):
        raw, config = self.evidence()
        for modified in (raw.replace(b'"88"', b'"89"'), raw + b'Block 1 "1" "other"\n'):
            with self.assertRaises(ValueError):
                successor.bind_native(modified, config)

    def test_control_characters_not_accepted(self):
        with self.assertRaises(ValueError):
            successor.quoted_field("bad\nexpression")

    def test_actual_failed_first_export_binds_without_approving_it(self):
        failed = successor.base.debug.OUT / "operand-debug-branch-pilot2-20261006-04"
        if not failed.exists():
            self.skipTest("host-local actual evidence absent")
        import json
        config = json.loads((failed / "config.json").read_bytes())
        self.assertEqual(len(successor.bind_native((failed / "first.el").read_bytes(), config)), 2)
        self.assertEqual(json.loads((failed / "status.json").read_bytes())["status"], "FAILED")


if __name__ == "__main__":
    unittest.main()
