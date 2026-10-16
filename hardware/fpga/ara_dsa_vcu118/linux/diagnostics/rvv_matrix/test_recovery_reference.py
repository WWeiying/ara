import unittest
from recovery_prepare import reference_coverage


class ReferenceCoverageTests(unittest.TestCase):
    def test_ordinary_release_still_requires_both(self):
        self.assertEqual(reference_coverage(dict(reference_passed=True, reference_vlens=[512,1024])), {512,1024})
        for vlens in ([], [512], [1024]):
            with self.assertRaises(ValueError):
                reference_coverage(dict(reference_passed=True, reference_vlens=vlens))

    def test_explicit_target_is_not_dual_vlen_proof(self):
        self.assertEqual(reference_coverage(dict(reference_passed=True,
            reference_vlens=[1024], required_vlen_bits=1024)), {1024})
        self.assertEqual(reference_coverage(dict(reference_passed=True,
            reference_vlens=[512,1024], required_vlen_bits=1024)), {1024})

    def test_wrong_target_and_failed_reference_are_rejected(self):
        for update in (dict(reference_passed=False), dict(reference_vlens=[512]),
                       dict(required_vlen_bits=512), dict(required_vlen_bits='1024')):
            manifest=dict(reference_passed=True,reference_vlens=[1024],required_vlen_bits=1024)
            manifest.update(update)
            with self.assertRaises(ValueError):
                reference_coverage(manifest)


if __name__=='__main__':
    unittest.main()
