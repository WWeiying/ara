import copy
import unittest

import rebind_akv_column_boundary_719 as r


def fixtures():
    row = dict(width=2, checksum="test", bits="0x1")
    before = dict(design={}, input_hashes={}, tests=["/old/%d/code.vdb" % i for i in range(719)],
                  metrics={"branch":{r.c.software.SCOPE:row}})
    sample = copy.deepcopy(before)
    sample["tests"] = [str(r.c.RUN / "code.vdb")]
    sample["metrics"]["branch"][r.c.software.SCOPE]["bits"] = "0x2"
    return before, sample


class PopulationTest(unittest.TestCase):
    def test_exact719_prefix_and_independent_delta(self):
        before, sample = fixtures(); union, delta = r.population(before, sample)
        self.assertEqual(union["tests"], before["tests"]+sample["tests"])
        self.assertEqual(delta["metrics"]["branch"], 1)

    def test_timeout_old_VDB_rejected(self):
        before, sample = fixtures()
        before["tests"][0] = str(r.life.OUT / "akv-column-boundary-old-image-20261006-01/code.vdb")
        with self.assertRaises(ValueError): r.population(before, sample)

    def test_duplicate_candidate_rejected(self):
        before, sample = fixtures(); before["tests"][0] = sample["tests"][0]
        with self.assertRaises(ValueError): r.population(before, sample)

    def test_non719_population_rejected(self):
        before, sample = fixtures(); before["tests"].pop()
        with self.assertRaises(ValueError): r.population(before, sample)

    def test_shape_change_rejected(self):
        before, sample = fixtures(); sample["metrics"]["branch"][r.c.software.SCOPE]["width"] = 3
        with self.assertRaises(ValueError): r.population(before, sample)


if __name__ == "__main__":
    unittest.main()
