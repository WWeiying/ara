import unittest

from run_context_projection import (ACT_BYTES, WEIGHT_BYTES, TILES,
                                    check_projection, vector_identity)


class ProjectionCheckerTest(unittest.TestCase):
    def fixture(self):
        vector = f"QBSCMD1 {TILES}\n"
        log = "QBS configuration response_gap=0 context_suite=0\n"
        for i in range(TILES):
            vector += (f"CMD {i} 6 2 2 4 32 28 00\n"
                       f"W 0 0 ffff {i:032x}\nA 0 0 ffff 1234\nEND\n")
            access = 1 if i == 0 else 3 if i == TILES - 1 else 2
            saved = 0 if i == 0 else ACT_BYTES
            log += (f"QBS end-to-end case {i} PASS profile=6 M=4 N=32 Kb=28 "
                    f"layouts=2/2 cycles=1000\n"
                    f"QBS projection tile PASS tile={i} access={access} M=4 N=32 Kb=28 "
                    f"cycles=900 payload={16 + WEIGHT_BYTES + ACT_BYTES - saved} saved={saved}\n")
        direct = TILES * (16 + WEIGHT_BYTES + ACT_BYTES)
        saved = (TILES - 1) * ACT_BYTES
        log += (f"QBS projection PASS tiles=28 M=4 N=896 Kb=28 direct_cycles=28000 "
                f"context_cycles=25200 direct_payload={direct} "
                f"context_payload={direct-saved} saved={saved}\n"
                "QBS engine PASS: 28 functional cases\n")
        return log, vector

    def test_accepts_complete_sequence(self):
        log, vector = self.fixture()
        result = check_projection(log, vector, 0)
        self.assertEqual(result["totals"][8], 102816)

    def test_rejects_partial_bad_totals_and_modes(self):
        log, vector = self.fixture()
        for broken in (log + "Fatal: failure\n", log + log,
                       log.replace("context_cycles=25200", "context_cycles=1"),
                       log.replace("tile=27 access=3", "tile=27 access=2"),
                       log.replace("tile=0 access=1", "tile=0 access=2"),
                       log.replace("case 8 PASS", "case 9 PASS"),
                       log.replace("response_gap=0", "response_gap=4"),
                       log.replace("engine PASS", "engine PENDING")):
            with self.subTest(broken=broken[-150:]), self.assertRaises(ValueError):
                check_projection(broken, vector, 0)

    def test_input_identity_and_geometry(self):
        log, vector = self.fixture()
        with self.assertRaises(ValueError):
            vector_identity(vector.replace(f"{1:032x}", f"{0:032x}"))
        with self.assertRaises(ValueError):
            vector_identity(vector.replace("A 0 0 ffff 1234", "A 0 0 ffff 9876", 1))
        with self.assertRaises(ValueError):
            check_projection(log, vector.replace("CMD 0 6 2 2 4", "CMD 0 6 2 2 3"), 0)

    def test_negative_performance_is_reported_not_discarded(self):
        log, vector = self.fixture()
        log = log.replace("cycles=900 payload", "cycles=1100 payload")
        log = log.replace("context_cycles=25200", "context_cycles=30800")
        result = check_projection(log, vector, 0)
        self.assertEqual(result["performance"], "regressed")
        self.assertFalse(result["deployment_approved"])


if __name__ == "__main__":
    unittest.main()
