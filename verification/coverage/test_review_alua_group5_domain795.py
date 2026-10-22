"""Actual795 source/shape replay and legal-path protection negatives."""
import copy
import json
from pathlib import Path
import unittest

import review_alua_group5_domain795 as review
from inventory_operand_debug import Design


class AluaDomain795(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads((review.OUT /
            'alua-group5-domain795-source-review-agent-20261008-03.json').read_text())
        config = json.loads((review.OUT /
            'current-population794-soc61-parent-20261008-01/config.json').read_text())
        design = Design(Path(config['input_ledger'][0]))
        definition = design.definition(cls.receipt['candidates'][0]['scope'], 'branch')
        cls.group = next(n for n in definition.iter('branch_spec') if n.get('id') == '5')
        width = sum(len(list(n.iter('branch_vector'))) for n in definition.iter('branch_spec'))
        cls.points = {p['vector']: p for p in review.points('branch', definition, width)
                      if p['native_id'] == '5'}

    def test_complete795_actual_receipt(self):
        self.assertEqual(review.collect(), self.receipt)
        self.assertEqual(self.receipt['candidate_count'], 137)
        self.assertEqual(self.receipt['additional_to_frozen24'], 113)
        self.assertEqual(len(self.receipt['protected_group5_vectors']), 47)
        self.assertTrue(all(not x['current795_hit'] for x in self.receipt['candidates']))
        self.assertTrue(self.receipt['protected_other_branch_groups'])
        self.assertEqual(self.receipt['finite_dynamic_case']['current795_missing_coordinates'], 0)
        self.assertEqual(self.receipt['finite_dynamic_case']['recommendation'],
                         'DO_NOT_RUN_ALREADY_HIT_IN795')

    def test_legal_sext2_zext2_leaves_protected(self):
        for vector in ('0', '1', '2', '12', '13', '14'):
            self.assertIsNone(review.classify(self.group, self.points[vector], 0))

    def test_only_active_support_false_is_candidate(self):
        for vector in ('4', '16'):
            self.assertEqual(review.classify(self.group, self.points[vector], 0),
                             'CONFIG_SUPPORT_INT_EXT2_TRUE')

    def test_reduction_lane_predicates_not_general_domain_waiver(self):
        for vector in ('24', '25', '26', '27'):
            self.assertIsNone(review.classify(self.group, self.points[vector], 0))
            self.assertEqual(review.classify(self.group, self.points[vector], 1),
                             'FIXED_LANE_ID_REDUCTION_BRANCH')
        self.assertEqual(review.classify(self.group, self.points['28'], 0),
                         'FIXED_LANE_ID_REDUCTION_BRANCH')
        self.assertIsNone(review.classify(self.group, self.points['28'], 1))

    def test_default_dynamic_short_packet_protected(self):
        for lane in range(4):
            self.assertIsNone(review.classify(self.group, self.points['44'], lane))
            self.assertIsNone(review.classify(self.group, self.points['45'], lane))

    def test_widefp2_false_pattern_requires_route_proof(self):
        for vector in ('30', '31', '32', '33', '34'):
            self.assertEqual(review.classify(self.group, self.points[vector], 0),
                             'WIDEFP2_PRODUCERS_ROUTE_ONLY_TO_MFPU')
        source = (review.OUT / 'old-image-source-evidence-20261006-01/ara_dispatcher.sv').read_text()
        self.assertEqual(len(review.wide_routes(source)), 9)
        location = source.index('ara_req.conversion_vs1 = OpQueueConversionWideFP2;')
        start = source.rfind('ara_pkg::VFADD;', 0, location)
        bad = source[:start] + source[start:].replace('ara_pkg::VFADD;', 'ara_pkg::VADD;', 1)
        self.assertNotEqual(source, bad)
        with self.assertRaises(ValueError):
            review.wide_routes(bad)

    def test_missing_outer_case_rejected(self):
        point = copy.deepcopy(self.points['34'])
        vector = list(point['native_vector']['vector'])
        vector[-46] = '0'
        point['native_vector']['vector'] = ''.join(vector)
        with self.assertRaises(ValueError):
            review.classify(self.group, point, 0)


if __name__ == '__main__':
    unittest.main()
