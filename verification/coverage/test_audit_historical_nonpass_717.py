import unittest

from audit_historical_nonpass_717 import category


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.original = {"elf_sha256": "elf-a", "image_signature": "image-a"}
        self.passed = dict(self.original, member717=True)

    def test_exact_admitted_pass(self):
        self.assertEqual(category(self.original, [self.passed]),
                         "SAME_IMAGE_SAME_ELF_PASS_ADMITTED")

    def test_same_name_other_elf_does_not_close(self):
        self.passed["elf_sha256"] = "elf-b"
        self.assertEqual(category(self.original, [self.passed]),
                         "OTHER_ELF_OR_UNPROVEN_IDENTITY_PASS_ONLY")

    def test_other_image_does_not_close(self):
        self.passed["image_signature"] = "image-b"
        self.assertEqual(category(self.original, [self.passed]),
                         "DIFFERENT_IMAGE_SAME_ELF_PASS_ONLY")

    def test_functional_pass_is_not_admission(self):
        self.passed["member717"] = False
        self.assertEqual(category(self.original, [self.passed]),
                         "SAME_IMAGE_SAME_ELF_PASS_NOT_ADMITTED")

    def test_missing_identity_is_not_equal(self):
        self.original["image_signature"] = None
        self.passed["image_signature"] = None
        self.assertEqual(category(self.original, [self.passed]),
                         "OTHER_ELF_OR_UNPROVEN_IDENTITY_PASS_ONLY")

    def test_no_pass_preserves_original(self):
        self.assertEqual(category(self.original, []), "NO_MATCHING_PASS")


if __name__ == "__main__":
    unittest.main()
