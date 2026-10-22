"""718 exact-prefix, identity, positive-gain and sealed-evidence rejection tests."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import admit_opivx_vsbc_offline as m


def fixtures():
    scope = "ara_tb.dut.i_ara_soc.i_system"
    before = dict(design={"design": "a"}, tests=["old%d" % i for i in range(717)], input_hashes={},
                  metrics={metric: {scope: dict(width=1, checksum="1", bits="0x0")} for metric in m.DELTA})
    single = deepcopy(before); single["tests"] = [str(m.c.RUN / "code.vdb")]
    for metric, gain in m.DELTA.items(): single["metrics"][metric][scope]["bits"] = hex(gain)
    return before, single, m.bitmap.combine(before, single)


class AdmissionTests(unittest.TestCase):
    def test_exact718(self):
        union, delta = m.population(*fixtures())
        self.assertEqual(len(union["tests"]), 718)
        self.assertEqual(delta["metrics"], m.DELTA)

    def test_prefix_reordered(self):
        before, single, proposed = fixtures(); proposed["tests"][0:2] = reversed(proposed["tests"][0:2])
        with self.assertRaises(ValueError): m.population(before, single, proposed)

    def test_baseline_removed(self):
        before, single, proposed = fixtures(); before["tests"].pop()
        with self.assertRaises(ValueError): m.population(before, single, proposed)

    def test_duplicate_vdb(self):
        before, single, proposed = fixtures(); before["tests"][0] = single["tests"][0]
        with self.assertRaises(ValueError): m.population(before, single, proposed)

    def test_extra_candidate(self):
        before, single, proposed = fixtures(); single["tests"].append("extra")
        with self.assertRaises(ValueError): m.population(before, single, proposed)

    def test_nonpass_original(self):
        before, single, proposed = fixtures(); before["tests"][0] = "/tmp/results/gap71_qbs_fault/work/code.vdb"
        with self.assertRaises(ValueError): m.population(before, single, proposed)

    def test_shape_drift(self):
        before, single, proposed = fixtures(); next(iter(single["metrics"]["line"].values()))["checksum"] = "2"
        with self.assertRaises(ValueError): m.population(before, single, proposed)

    def test_zero_delta(self):
        before, single, _ = fixtures()
        for row in single["metrics"].values(): next(iter(row.values()))["bits"] = "0x0"
        with self.assertRaises(ValueError): m.population(before, single, m.bitmap.combine(before, single))

    def test_duplicate_elf(self):
        with self.assertRaises(ValueError): m.elf_unique("/tmp/new.elf", "a" * 64, {"/tmp/old.elf": "a" * 64})

    def test_unique_elf(self):
        self.assertFalse(m.elf_unique("/tmp/new.elf", "b" * 64, {"/tmp/old.elf": "a" * 64})["duplicate_elf"])

    def test_conflicting_pin(self):
        with self.assertRaises(ValueError): m.life.merge_pins({"/tmp/pin": "a" * 64}, {"/tmp/pin": "b" * 64})

    def test_changed_seal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp).resolve() / "x.json"; path.write_text('{"ok":true}')
            h = m.life.digest(path); m.bound(path, h); path.write_text('{"ok":false}')
            with self.assertRaises(ValueError): m.bound(path, h)

    def test_actual_native_three_points(self):
        single = json.loads((m.CANDIDATE / "single-raw-bits.json").read_text())
        proof = m.coverage_identity(single)
        self.assertEqual([(p["metric"], p["raw_index"]) for p in proof["points"]],
                         [("branch", 968), ("line", 502), ("cond", 249)])
        self.assertFalse(proof["new_DVE_qualification"])

    def test_actual_oracle_no_prefix(self):
        pre = m.life.read_bound(m.c.runner.PRE / "preflight-manifest.json", m.c.PRE_SEAL)
        counts = m.c.reference_counts(m.c.software.parse_spike_commits(m.c.runner.PRE / "spike.trace"), pre["symbols"])
        scalar = json.loads((m.CANDIDATE / "scalar-comparison.json").read_text())
        m.c.scalar_exact(scalar, counts)
        scalar["skipped_unobservable_register_values"] = 1
        with self.assertRaises(ValueError): m.c.scalar_exact(scalar, counts)

    def test_actual_input_fingerprints(self):
        path = m.CANDIDATE / "status.json"
        m.bound(path, m.CANDIDATE_SEAL)
        self.assertEqual(m.AUTHORIZATION["source"], "PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL")


if __name__ == "__main__":
    unittest.main()
