import unittest

from compile_context_attribution import OBSERVER, SOURCE, instrument


class AttributionTest(unittest.TestCase):
    def test_observation_does_not_change_existing_decisions(self):
        original = SOURCE.read_text()
        candidate = instrument(original)
        self.assertEqual(candidate.count(OBSERVER), 1)
        restored = candidate.replace(OBSERVER, '', 1)
        for expression in (
            'observe(nullptr, -1, "missing_graph", false)',
            'observe(next_node, node_index, "may_modify_activation", false)',
            'observe(next_node, node_index, "expert_context_consumer", false)',
            'observe(next_node, node_index, "ineligible_matrix", false)',
            'observe(nullptr, node_count, "end_of_graph", false)',
        ):
            self.assertEqual(restored.count(expression), 1)
            restored = restored.replace(expression, 'false', 1)
        expression = 'observe(next_node, node_index, "identity_match", same_cross_op_identity(current, next))'
        self.assertEqual(restored.count(expression), 1)
        restored = restored.replace(expression, 'same_cross_op_identity(current, next)', 1)
        self.assertEqual(restored, original)

    def test_reject_instrumenting_twice(self):
        with self.assertRaises(ValueError):
            instrument(instrument(SOURCE.read_text()))


if __name__ == '__main__':
    unittest.main()
