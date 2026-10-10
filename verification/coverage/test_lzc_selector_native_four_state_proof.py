from itertools import product
import json
import unittest

import lzc_selector_native_four_state_proof as subject


class FourStateTests(unittest.TestCase):
    def test_or_and_equality_preserve_unknown(self):
        self.assertEqual({subject.sv_or(a, b) for a, b in product('X0', repeat=2)}, {'X', '0'})
        self.assertEqual(subject.sv_or('1', 'X'), '1')
        self.assertEqual(subject.sv_or('Z', '0'), 'X')
        self.assertEqual(subject.sv_eq_one('X'), 'X')
        self.assertNotEqual(subject.sv_eq_one('X'), '0')

    def test_exact_source_driver_contract_and_mutation(self):
        text = subject.SOURCE.read_text()
        subject.source_contract(text)
        with self.assertRaises(ValueError):
            subject.source_contract(text.replace("assign sel_nodes[2 ** level - 1 + k] = 1'b0;",
                                                 "assign sel_nodes[2 ** level - 1 + k] = 1'b1;"))

    def test_no_real_leaf_can_be_proven_padding(self):
        with self.assertRaisesRegex(ValueError, 'Real input'):
            subject.padded_cone(10, 3, 0)
        with self.assertRaises(ValueError):
            subject.padded_cone(16, 3, 7)

    def test_all60_exact_cones_and_unknown_initialization(self):
        result = json.loads((subject.DEFAULT_BATCH / 'batch-result.json').read_bytes())
        self.assertEqual(len(result['results']), 60)
        for record in result['results']:
            proof = subject.prove_candidate(record['candidate'])
            self.assertEqual(proof['predicate_possible_values'], ['X', '0'])
            self.assertTrue(proof['known_true_unreachable_before_and_after_settling'])
            self.assertTrue(proof['transient_X_is_not_false'])
            self.assertEqual(proof['left_selector_cone']['real_input_dependencies'], [])

    def test_branch_op16_and_false_vector_rejected(self):
        result = json.loads((subject.DEFAULT_BATCH / 'batch-result.json').read_bytes())
        candidate = result['results'][0]['candidate']
        for field, value in (('metric', 'branch'),):
            with self.assertRaises(ValueError):
                subject.prove_candidate(dict(candidate, **{field: value}))
        candidate['xml_provenance']['vector'] = '0'
        with self.assertRaises(ValueError):
            subject.prove_candidate(candidate)


if __name__ == '__main__':
    unittest.main()
