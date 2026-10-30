#!/usr/bin/env python3
import unittest

from run_tile_context_engine import check_log, check_geometry


LOG = """QBS configuration response_gap=0 context_suite=1
QBS end-to-end case 0 PASS profile=6 M=4 N=32 Kb=28 layouts=2/2 cycles=5662
QBS next-block fault/replay PASS kind=0
QBS next-block fault/replay PASS kind=1
QBS next-block fault/replay PASS kind=2
QBS next-block reset/replay PASS
QBS activation context FILL/REUSE/RELEASE PASS case=0 M=4 Kb=28 bytes=3808 fill_cycles=5905 reuse_cycles=5653
QBS engine PASS: 1 functional cases
"""
LOG += "".join(f"QBS context weight fault/retry PASS case=0 release={release} kind={kind}\n"
               for release in range(2) for kind in range(3))


class CheckedLogTests(unittest.TestCase):
    def test_complete(self):
        result = check_log(LOG, 1, 1, 0)
        self.assertEqual(result["direct"][0][-1], 5662)
        self.assertEqual(result["contexts"][0][-2:], (5905, 5653))

    def test_reject_incomplete_or_mislabelled(self):
        for altered in (
            LOG + "Fatal: failed assertion\n",
            LOG + "QBS engine PASS: 1 functional cases\n",
            LOG.replace("response_gap=0", "response_gap=4"),
            LOG.replace("M=4 N=32", "M=8 N=32"),
            LOG.replace("QBS next-block fault/replay PASS kind=2\n", ""),
            LOG.replace("QBS next-block reset/replay PASS\n", ""),
            LOG.replace("QBS engine PASS: 1 functional cases\n", ""),
            LOG.replace("RELEASE PASS case=0", "RELEASE PASS case=1"),
            LOG.replace("bytes=3808", "bytes=4352"),
            LOG.replace("PASS case=0 release=1 kind=2", "PASS case=0 release=1 kind=1"),
            LOG.replace("QBS context weight fault/retry PASS case=0 release=0 kind=0\n", ""),
        ):
            with self.subTest(log=altered), self.assertRaises(ValueError):
                check_log(altered, 1, 1, 0)

    def test_geometry_is_bound_to_input(self):
        direct = check_log(LOG, 1, 1, 0)["direct"]
        vector = "QBSCMD1 1\nCMD 0 6 2 2 4 32 28 01\n"
        check_geometry(vector, direct)
        for changed in (vector.replace("32 28", "16 28"),
                        vector.replace("0 6", "1 6"), vector + vector, ""):
            with self.subTest(vector=changed), self.assertRaises(ValueError):
                check_geometry(changed, direct)


if __name__ == "__main__":
    unittest.main()
