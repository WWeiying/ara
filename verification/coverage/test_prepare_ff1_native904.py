import unittest
from prepare_ff1_native904 import decision, exact_forward


class FF1SelectionTests(unittest.TestCase):
    def setUp(self):
        self.mapping = {-2: 0, -1: 1, **{bit: bit + 2 for bit in range(52)}}

    def test_exact904_and824(self):
        targets = sum(decision(case, raw, False, inner, self.mapping)
                      for _ in range(4) for inner in range(4) for _ in range(2)
                      for case, raw in self.mapping.items())
        self.assertEqual(targets, 904)
        self.assertEqual(32 * 54 - targets, 824)

    def test_default_zero_and_width64_always_protected(self):
        for inner in range(4):
            for case in (-2, -1):
                self.assertFalse(decision(case, self.mapping[case], True, inner, self.mapping))
        for case, raw in self.mapping.items():
            self.assertFalse(decision(case, raw, True, 0, self.mapping))

    def test_hit_target_rejected(self):
        with self.assertRaises(ValueError):
            decision(0, 2, True, 1, self.mapping)

    def test_bad_calibration_and_parent_rejected(self):
        for args in ((0, 3, False, 1), (0, 2, False, 4), (99, 0, False, 1)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                decision(*args, self.mapping)

    def test_forward_is_bound_to_exact_instance(self):
        good = 'child #(.Other($bits(foo)), .FPUSupport(FPUSupport)) i_child ();'
        self.assertEqual(exact_forward(good, 'child', 'i_child')['value'], 'FPUSupport')
        for bad in (good.replace('(FPUSupport)', '(Other)'), good.replace('i_child', 'i_wrong'),
                    '// ' + good, good + good, good + '\ndefparam i_child.FPUSupport = 0;'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                exact_forward(bad, 'child', 'i_child')

    def test_known_soc_conditional_suffix_only(self):
        text = 'ara_system #(.FPUSupport(FPUSupport))\n`else\nara_system\n`endif\ni_system ();'
        self.assertEqual(exact_forward(text, 'ara_system', 'i_system')['value'], 'FPUSupport')
        with self.assertRaises(ValueError):
            exact_forward(text.replace('`else\nara_system', '`else\nother'), 'ara_system', 'i_system')


if __name__ == "__main__":
    unittest.main()
