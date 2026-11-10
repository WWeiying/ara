"""Bounded preparation contract checks; no inference, toolchain build or QEMU."""
import copy
import json
from pathlib import Path
import unittest

import prepare as p


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.plan = p.strict_json((Path(__file__).with_name('plan.json')).read_text())

    def test_reviewed_matrix(self):
        p.validate(self.plan)
        self.assertEqual(len(self.plan['cases']), 5)
        self.assertEqual(sum(c['resident_decode'] for c in self.plan['cases']), 2)

    def test_execution_stays_held(self):
        self.plan['execution_authorized'] = True
        with self.assertRaises(ValueError): p.validate(self.plan)

    def test_no_resource_expansion_or_retry(self):
        for key, value in [('guest_memory', '8G'), ('guest_cpus', 2), ('parallel_models', 2),
                           ('memory_max', '8G'), ('cpu_quota', '200%'), ('automatic_retries', 1)]:
            plan = copy.deepcopy(self.plan); plan['worker'][key] = value
            with self.assertRaises(ValueError): p.validate(plan)

    def test_no_matrix_expansion(self):
        self.plan['cases'].append(copy.deepcopy(self.plan['cases'][0]))
        with self.assertRaises(ValueError): p.validate(self.plan)

    def test_no_weak_baseline(self):
        plan = copy.deepcopy(self.plan); plan['llama_commit'] = plan['llama_native_auto_reference']
        with self.assertRaises(ValueError): p.validate(plan)
        for key in ('GGML_RISCV_QBS', 'GGML_RISCV_QBS_M4_PARALLEL_SUMS', 'AKV_PAIR_HEADS'):
            plan = copy.deepcopy(self.plan); plan['common_environment'][key] = '0'
            with self.assertRaises(ValueError): p.validate(plan)

    def test_quantized_and_d256_stay_fallback(self):
        for index in (2, 3, 4):
            plan = copy.deepcopy(self.plan); plan['cases'][index]['resident_decode'] = True
            with self.assertRaises(ValueError): p.validate(plan)

    def test_exact_prefix_and_continuations(self):
        self.assertEqual(p.token_prefix(list(range(100)), 63, 100), list(range(65)))
        with self.assertRaises(ValueError): p.token_prefix(list(range(64)), 63, 100)

    def test_reject_invalid_token_ids(self):
        for tokens in ([0, True, 2], [0, 1.0, 2], [0, -1, 2], [0, 3, 2], {'0': 0}):
            with self.assertRaises(ValueError): p.token_prefix(tokens, 1, 3)

    def test_json_duplicates_nonfinite_and_corruption(self):
        for text in ('{"x":0,"x":1}', '{"x":NaN}', '{"x":Infinity}', '{"x":'):
            with self.assertRaises(ValueError): p.strict_json(text)

    def test_commands_explicitly_unresolved(self):
        out = Path('/independent/output')
        recipe = p.held_commands(out, self.plan)
        self.assertEqual(recipe['state'], 'HELD_NOT_EXECUTABLE')
        self.assertIn('parent_execution_authorization', recipe['unresolved'])
        self.assertEqual(len(recipe['cases']), 5)
        for case in recipe['cases']:
            argv = case['argv_template']
            self.assertEqual(argv[0], '@ACCEPTED_RESIDENT_QEMU@')
            self.assertEqual(argv[argv.index('-m') + 1], '4G')
            self.assertEqual(argv[argv.index('-smp') + 1], '1')
            self.assertEqual(case['requested'], [0, 1])
            self.assertEqual(case['environment'], self.plan['common_environment'])
            self.assertIn('readonly=on', argv[argv.index('-drive') + 1])
            self.assertEqual(case['systemd_properties']['MemoryMax'], '4G')

    def test_header_uses_full_vocabulary_not_a_logit_slice(self):
        case = self.plan['cases'][0]
        source = 'A source with "quotes".\n'
        text = p.header(case, dict(vocabulary=200, layers=30), list(range(100)), source,
                        self.plan['common_environment'])
        self.assertIn('expected_vocab = 200;', text)
        self.assertIn('prompt_tokens = 63;', text)
        self.assertIn('context_capacity = 128;', text)
        self.assertIn('effective_context_capacity = 256;', text)
        self.assertIn(json.dumps(source), text)
        self.assertNotIn('#define STAGE5_REVIEWED_RESIDENT_ENV', text)


if __name__ == '__main__':
    unittest.main()
