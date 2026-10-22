import unittest
import review_rvh0_exception_fields771 as p


class SourceTests(unittest.TestCase):
    def test_actual_frozen_sources(self):
        r = p.collect()
        self.assertEqual(r['fields'], 60)
        self.assertEqual(sum(r['actual_missing_positions'].values()), 3058)
        self.assertFalse(r['coverage_admitted'])

    def test_unguarded_nonzero(self):
        with self.assertRaises(ValueError):
            p.member_writes('ex.gva = v_i;', ['ex'])

    def test_else_is_not_disabled(self):
        with self.assertRaises(ValueError):
            p.member_writes("if (CVA6Cfg.RVH) begin ex.gva = '0; end else begin ex.gva = v_i; end", ['ex'])

    def test_negated_rvh_not_guard(self):
        with self.assertRaises(ValueError):
            p.member_writes('if (!CVA6Cfg.RVH) begin ex.tinst = instruction; end', ['ex'])

    def test_partial_member_rejected(self):
        with self.assertRaises(ValueError):
            p.member_writes("ex.tval2[0] = '0;", ['ex'])

    def test_nested_guard_and_literal(self):
        r = p.member_writes("ex.gva = 1'b0; if (CVA6Cfg.RVH) begin if (valid) begin ex.tinst = instruction; end end", ['ex'])
        self.assertEqual(len(r), 2)
        self.assertTrue(r[1]['disabled_by_RVH0'])

    def test_rvh_not_necessary_disjunction(self):
        with self.assertRaises(ValueError):
            p.member_writes('if (CVA6Cfg.RVH || valid) begin ex.gva = v_i; end', ['ex'])
        self.assertTrue(p.rvh_required('CVA6Cfg.RVH && (a || b)'))

    def test_unknown_whole_producer(self):
        texts = {path: (p.ROOT / path).read_text() for path in p.EXTRA}
        texts['hardware/src/vlsu/vstu.sv'] += '\nstore_b_exception_o = arbitrary_exception;'
        with self.assertRaises(ValueError):
            p.extra_contract(texts)

    def test_invalid_cycle_member_override(self):
        texts = {path: (p.ROOT / path).read_text() for path in p.EXTRA}
        texts['hardware/src/vlsu/vstu.sv'] += '\nif (!valid) store_b_exception_d.gva = input_bit;'
        with self.assertRaises(ValueError):
            p.extra_contract(texts)


if __name__ == '__main__':
    unittest.main()
