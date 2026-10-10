import copy
import json
from pathlib import Path
import tempfile
import unittest

import admit_gap101a_offline as m


def fixtures():
    scope = "ara_tb.dut.i_ara_soc.i_system"
    before = dict(design={"design": "a"}, tests=["old%d" % i for i in range(715)], input_hashes={},
                  metrics={metric: {scope: dict(width=1, checksum="1", bits="0x0")} for metric in m.DELTA})
    single = copy.deepcopy(before)
    single["tests"] = [str(m.collector.RUN / "code.vdb")]
    for metric, gain in m.DELTA.items():
        single["metrics"][metric][scope]["bits"] = hex(gain)
    return before, single, m.bitmap.combine(before, single)


class AdmissionTests(unittest.TestCase):
    def test_exact_population(self):
        union, delta = m.population(*fixtures())
        self.assertEqual(len(union["tests"]), 716)
        self.assertEqual(delta["metrics"], m.DELTA)

    def test_failed_original_excluded(self):
        before, single, proposed = fixtures()
        before["tests"][0] = "/tmp/gap101-illegal-segment-store-old-image-20261006-01/code.vdb"
        with self.assertRaisesRegex(ValueError, "FAIL mixed"):
            m.population(before, single, proposed)

    def test_duplicate_rejected(self):
        before, single, proposed = fixtures()
        before["tests"][0] = single["tests"][0]
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            m.population(before, single, proposed)

    def test_wrong_union_rejected(self):
        before, single, proposed = fixtures()
        proposed["tests"][0], proposed["tests"][1] = proposed["tests"][1], proposed["tests"][0]
        with self.assertRaisesRegex(ValueError, "exact715"):
            m.population(before, single, proposed)

    def test_shape_drift_rejected(self):
        before, single, proposed = fixtures()
        next(iter(single["metrics"]["branch"].values()))["checksum"] = "2"
        with self.assertRaisesRegex(ValueError, "shape"):
            m.population(before, single, proposed)

    def test_pin_conflict_not_overwritten(self):
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            m.life.merge_pins({"/tmp/expected": "a" * 64}, {"/tmp/expected": "b" * 64})

    def test_bound_changed_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp).resolve() / "evidence.json"
            path.write_text(json.dumps({"ok": True}))
            expected = m.life.digest(path)
            m.bound(path, expected)
            path.write_text(json.dumps({"ok": False}))
            with self.assertRaisesRegex(ValueError, "changed"):
                m.bound(path, expected)

    def test_scalar_unknown_rejected(self):
        result = copy.deepcopy(m.collector.SCALAR_EXPECTED)
        result["stopped_at_unobservable"] = {"pc": "unknown"}
        with self.assertRaisesRegex(ValueError, "scalar contract"):
            m.collector.scalar_exact(result)

    def test_actual_tracer_tail_json_representation(self):
        rows = [dict(event="retire", cycle="12", pc="000000008000007a", insn="00a2b023")]
        text = ("10ns 12 M 000000008000007a 0 00a2b023\n"
                "10ns 12 M 000000008000007e 0 0000a001\n"
                "Exception @ 3, PC: 80002208, Cause: Illegal Instruction\n"
                "tval: 00000000e2050827\n")
        result = m.tracer_json(text, rows, {"g101a_bad_a": 0x80002208})
        self.assertEqual(result, json.loads(json.dumps(result)))
        self.assertEqual(result["tracer_tail"], [["12", "M", "000000008000007e", "0000a001"]])
        with self.assertRaisesRegex(ValueError, "tracer tail"):
            m.tracer_json(text.replace("0000a001", "00000013"), rows, {"g101a_bad_a": 0x80002208})


if __name__ == "__main__":
    unittest.main()
