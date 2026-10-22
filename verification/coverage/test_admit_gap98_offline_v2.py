import copy
import unittest
from unittest.mock import patch

import admit_gap98_offline_v2 as m


class UopTests(unittest.TestCase):
    def setUp(self):
        self.rows = m.commit_rows(m.old.RUN / "commit_trace.csv")
        self.vector = m.old.RUN / "vector_trace.csv"

    def test_actual32(self):
        result = m.uop_audit(self.rows, self.vector)
        self.assertEqual(result["allocations"], 32)
        self.assertEqual(result["completions"], 32)
        self.assertEqual(m.handshakes(self.rows)["requests"], 48)

    def changed(self, event, field, value):
        rows = copy.deepcopy(self.rows)
        next(r for r in rows if r["event"] == event)[field] = value
        with self.assertRaises(ValueError):
            m.uop_audit(rows, self.vector)

    def test_wrong_command(self):
        self.changed("uop_alloc", "insn", 0x13)

    def test_wrong_seq(self):
        self.changed("uop_done", "order", 0)

    def test_wrong_tid(self):
        self.changed("uop_done", "trans_id", 7)

    def test_wrong_vid(self):
        self.changed("uop_done", "port", 7)

    def test_wrong_timing(self):
        self.changed("uop_done", "cycle", 0)

    def test_missing_completion(self):
        rows = copy.deepcopy(self.rows)
        rows.remove(next(r for r in rows if r["event"] == "uop_done"))
        with self.assertRaises(ValueError):
            m.uop_audit(rows, self.vector)

    def test_duplicate_alloc(self):
        rows = copy.deepcopy(self.rows)
        i = next(i for i, r in enumerate(rows) if r["event"] == "uop_alloc")
        rows.insert(i + 1, dict(rows[i]))
        with self.assertRaises(ValueError):
            m.uop_audit(rows, self.vector)

    def test_vector_disagreement(self):
        rows = m.old.common.read_csv(self.vector, m.old.common.VECTOR_FIELDS)
        next(r for r in rows if r["event"] == "done")["cycle"] = "0"
        with patch.object(m.old.common, "read_csv", return_value=rows), self.assertRaises(ValueError):
            m.uop_audit(self.rows, self.vector)

    def test_wrong_vector_register(self):
        rows = copy.deepcopy(self.rows)
        first = next(r for r in rows if r["event"] == "arch_start" and r["insn"] & 127 == 7)
        first["insn"] ^= 1 << 7
        with self.assertRaises(ValueError):
            m.uop_audit(rows, self.vector)

    def test_trap_is_not_accepted(self):
        self.changed("uop_alloc", "trap", 1)

    def test_commit_unknown_and_trap_rejected(self):
        original = m.old.common.read_csv(m.old.RUN / "commit_trace.csv", m.old.common.COMMIT_FIELDS)
        for field, value in (("event", "future_unknown"), ("trap", "1")):
            rows = [dict(original[0], **{field: value})]
            with self.subTest(field=field), patch.object(m.old.common, "read_csv", return_value=rows), self.assertRaises(ValueError):
                m.commit_rows(m.old.RUN / "commit_trace.csv")


if __name__ == "__main__":
    unittest.main()
