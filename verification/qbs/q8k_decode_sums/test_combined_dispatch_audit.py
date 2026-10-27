import unittest
from audit_combined_dispatch import normalize_parent


class ParentTest(unittest.TestCase):
    def test_only_zero_parent_after_complete_suite_is_removed(self):
        child='Q8K_COMBINED_DISPATCH mode=0 original=796 installed=0\nQ8K_COMBINED_DISPATCH mode=1 original=0 installed=458\n'
        suite='Q8K_MODEL_SUITE_PASS comparisons=6 performance=not_measured\n'
        parent='Q8K_COMBINED_DISPATCH mode=invalid original=0 installed=0\n'
        exit='GUEST_TEST_EXIT=0\n'
        text=child+suite+parent+exit
        self.assertEqual(normalize_parent(text),'\n'.join((child+suite+exit).splitlines()))
        for bad in (child+parent+suite+exit,text.replace('mode=invalid original=0','mode=invalid original=1'),
                    text+parent,child+suite+exit,text.replace('GUEST_TEST_EXIT=0','GUEST_TEST_EXIT=1')):
            with self.subTest(bad=bad),self.assertRaises(ValueError):normalize_parent(bad)


if __name__=='__main__':unittest.main()
