"""Actual frozen-source/compiled-leaf replay and producer-domain negatives."""
import copy
import json
from pathlib import Path
import unittest

import review_alua_ext24_producers794 as review
from inventory_operand_debug import Design


class ProducerReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads((review.OUT /
            'alua-ext24-producers794-source-review-agent-20261008-02.json').read_text())
        cls.dispatch = (review.OUT /
            'old-image-source-evidence-20261006-01/ara_dispatcher.sv').read_text()
        config = json.loads((review.OUT /
            'current-population794-soc61-parent-20261008-01/config.json').read_text())
        design = Design(Path(config['input_ledger'][0]))
        scope = cls.receipt['targets'][0]['scope']
        definition = design.definition(scope, 'branch')
        group = next(n for n in definition.iter('branch_spec') if n.get('id') == '5')
        cls.items = list(group.iter('branch_citem'))

    def test_actual_full_review_receipt(self):
        self.assertEqual(review.collect(), self.receipt)
        self.assertEqual(len(self.receipt['targets']), 24)
        self.assertTrue(all(len(c['protected_vectors']) == 40
                            for c in self.receipt['group5_protected_complement']))

    def test_every_frozen_dispatcher_assignment(self):
        writes = review.domain_gate(self.dispatch)
        self.assertEqual(len(writes), 63)
        self.assertFalse(review.DOMAIN & review.FORBIDDEN)

    def test_new_live_vs1_producer_rejected(self):
        for conversion in sorted(review.FORBIDDEN):
            with self.subTest(conversion=conversion), self.assertRaises(ValueError):
                review.domain_gate(self.dispatch +
                    '\nara_req.conversion_vs1 = ' + conversion + ';\n')

    def test_nonliteral_vs1_producer_rejected(self):
        with self.assertRaises(ValueError):
            review.domain_gate(self.dispatch +
                              '\nara_req.conversion_vs1 = ara_req.conversion_vs2;\n')

    def test_comments_comparisons_and_vs2_not_producers(self):
        suffix = ('\n// ara_req.conversion_vs1 = OpQueueConversionSExt8;\n'
                  'if (ara_req.conversion_vs1 == OpQueueConversionSExt2) ;\n'
                  'ara_req.conversion_vs2 = OpQueueConversionSExt8;\n')
        self.assertEqual(review.domain_gate(self.dispatch + suffix),
                         review.domain_gate(self.dispatch))

    def test_all_actual_target_leaf_conjunctions(self):
        for target in self.receipt['targets']:
            review.target_gate(target, self.items)

    def test_other_branch_or_position_rejected(self):
        target = self.receipt['targets'][0]
        for name, value in [('native_id', '4'), ('vector', '20'), ('raw_index', 0)]:
            changed = copy.deepcopy(target)
            changed[name] = value
            with self.subTest(name=name), self.assertRaises(ValueError):
                review.target_gate(changed, self.items)

    def test_wrong_compiled_conjunct_rejected(self):
        target = copy.deepcopy(self.receipt['targets'][0])
        vector = list(target['native_vector']['vector'])
        conversion = review.LEAVES[target['vector']][0]
        item = next(n for n in self.items if n.get('name').strip() == conversion)
        vector[-int(item.get('index'))] = '0'
        target['native_vector']['vector'] = ''.join(vector)
        with self.assertRaises(ValueError):
            review.target_gate(target, self.items)


if __name__ == '__main__':
    unittest.main()
