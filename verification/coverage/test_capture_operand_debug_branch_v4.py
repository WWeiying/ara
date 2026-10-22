import copy
import unittest

import capture_operand_debug_branch_v4 as successor
from test_capture_operand_debug_branch_v3 import NativeQuotedFieldTests


class ExactRecordOrderingTests(unittest.TestCase):
    def evidence(self):
        raw, config = NativeQuotedFieldTests().evidence()
        points = config["plan"]["scopes"]["top.requester"]["branch"]
        other = copy.deepcopy(points[0])
        other["point"]["vector"] = "0"
        other["coordinate"] = "3,0"
        points.append(other)
        lines = raw.decode().splitlines()
        header = "\n".join(lines[:2]) + "\n"
        a = "\n".join(lines[2:]) + "\n"
        b = a.replace("(4)", "(0)").replace(" 0,-,-", " 1,1,-")
        return (header + a + b).encode(), (header + b + a).encode(), config

    def test_order_only_change_is_equal(self):
        first, second, config = self.evidence()
        self.assertEqual(successor.bind_native(first, config), successor.bind_native(second, config))
        self.assertNotEqual(first, second)

    def test_signature_mutation_not_equal(self):
        first, second, config = self.evidence()
        changed = second.replace(b" 1,1,-", b" 1,0,-")
        self.assertNotEqual(successor.bind_native(first, config), successor.bind_native(changed, config))

    def test_duplicate_still_rejected(self):
        first, _, config = self.evidence()
        with self.assertRaises(ValueError):
            successor.bind_native(first + first, config)

    def test_actual_order_only_evidence(self):
        import json
        failed = successor.base.debug.OUT / "operand-debug-branch-pilot2-20261006-05"
        if not failed.exists():
            self.skipTest("host-local evidence absent")
        config = json.loads((failed / "config.json").read_bytes())
        self.assertEqual(successor.bind_native((failed / "first.el").read_bytes(), config),
                         successor.bind_native((failed / "second.el").read_bytes(), config))
        self.assertEqual(json.loads((failed / "status.json").read_bytes())["status"], "FAILED")


if __name__ == "__main__":
    unittest.main()
