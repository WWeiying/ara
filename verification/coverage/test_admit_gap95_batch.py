import copy
import unittest

import admit_gap95_batch as admission


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.spec = dict(expected_vector_instructions=48, expected_vector_bytes=12288,
                         checks=1616, symbols=dict(g75_result=0x80002288,
                                                  num_failed=0x80002280, tohost=0x80001000))
        self.vector = dict(status="PASS", compared_instructions=48, compared_bytes=12288,
                           skipped_unknown_bytes=0, non_bit_exact_instructions=0,
                           incomplete_requests=[], unretired_requests=[], trapped_requests=[])

    def test_exact_vector_only(self):
        self.assertTrue(admission.vector_exact(self.vector, self.spec))
        for key, value in (("status", "PREFIX"), ("compared_instructions", 47),
                           ("compared_bytes", 12287), ("skipped_unknown_bytes", 1),
                           ("non_bit_exact_instructions", 1), ("incomplete_requests", [1]),
                           ("unretired_requests", [1]), ("trapped_requests", [1])):
            bad = copy.deepcopy(self.vector)
            bad[key] = value
            self.assertFalse(admission.vector_exact(bad, self.spec), key)
        for key in self.vector:
            bad = copy.deepcopy(self.vector)
            del bad[key]
            self.assertFalse(admission.vector_exact(bad, self.spec), key)

    def test_exact_signature_masks_and_values(self):
        writes = {0x80002288: (15, 1616), 0x8000228c: (240, 0),
                  0x80002280: (15, 0), 0x80001000: (255, 1)}
        self.assertTrue(admission.signature_exact(writes, self.spec))
        for address in writes:
            bad = dict(writes)
            del bad[address]
            self.assertFalse(admission.signature_exact(bad, self.spec))
            bad = dict(writes)
            mask, value = bad[address]
            bad[address] = (mask ^ 1, value)
            self.assertFalse(admission.signature_exact(bad, self.spec))
            bad[address] = (mask, value ^ 1)
            self.assertFalse(admission.signature_exact(bad, self.spec))

    def test_conflicting_pin_rejected(self):
        pins = {"a": "x"}
        admission.pin_merge(pins, {"a": "x", "b": "y"})
        with self.assertRaisesRegex(ValueError, "Conflicting pin"):
            admission.pin_merge(pins, {"a": "z"})


if __name__ == "__main__":
    unittest.main()
