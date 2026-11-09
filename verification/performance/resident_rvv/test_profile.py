import unittest
from run_profile import same_measurement


class MeasurementTests(unittest.TestCase):
    def test_only_log_identity_may_change(self):
        reference = dict(log="old", log_sha256="oldhash", cycles=[1, 2], work={"bytes": 512})
        actual = dict(reference, log="new", log_sha256="newhash")
        self.assertTrue(same_measurement(actual, reference))
        self.assertFalse(same_measurement(dict(actual, cycles=[1, 3]), reference))
        self.assertFalse(same_measurement(dict(actual, work={"bytes": 256}), reference))
        self.assertFalse(same_measurement(dict(actual, extra=0), reference))


if __name__ == "__main__":
    unittest.main()
