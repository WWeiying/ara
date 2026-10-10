import unittest

from review_srt_whole_trusted797 import MODULE, SYSTEM, validate_roots


class RootBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.roots = [f'{SYSTEM}.lane{i}.wrapper.srt.x_{MODULE}' for i in range(17)]

    def test_exact_core_roots(self):
        validate_roots(self.roots, [SYSTEM + '.other_ip'])

    def test_duplicate(self):
        with self.assertRaises(ValueError):
            validate_roots(self.roots[:-1] + self.roots[:1], [])

    def test_parent_not_allowed(self):
        with self.assertRaises(ValueError):
            validate_roots(self.roots[:-1] + [SYSTEM + '.wrapper'], [])

    def test_outside_system(self):
        with self.assertRaises(ValueError):
            validate_roots([s.replace(SYSTEM, 'ara_tb.other', 1) for s in self.roots], [])

    def test_inherited_ancestor_overlap(self):
        with self.assertRaises(ValueError):
            validate_roots(self.roots, [self.roots[0].rsplit('.', 1)[0]])

    def test_inherited_descendant_overlap(self):
        with self.assertRaises(ValueError):
            validate_roots(self.roots, [self.roots[0] + '.child'])


if __name__ == '__main__':
    unittest.main()
