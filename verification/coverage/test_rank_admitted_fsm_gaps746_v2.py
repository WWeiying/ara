import unittest
import rank_admitted_fsm_gaps746_v2 as rank


class RankV2Tests(unittest.TestCase):
    def test_typed_record_normalization(self):
        record = ['fsm', 'scope', 'module', 'metric', 'machine', 'sha',
                  'Transition', 'A->B', '0->1']
        self.assertEqual(list(rank.exclusions({'x': [record]})), [
            ('module', 'metric', 'scope', 'machine', 'sha', '', 'Transition', 'A->B', '0->1')])

    def test_original_record_preserved(self):
        record = ['1', '2', 'scope', 'machine', 'sha', 'why', 'Transition', 'A->B', '0->1']
        self.assertEqual(list(rank.exclusions([record])), [tuple(record)])

    def test_dwc_all_qualified_points_marked(self):
        result = rank.collect()
        scopes = [r for r in result['instances'] if '.i_ariane_axi_dwc.' in r['scope'] and
                  r['scope'].endswith('.i_atop_filter')]
        self.assertEqual(len(scopes), 1)
        self.assertEqual((scopes[0]['remaining_transitions'], scopes[0]['remaining_states']), (0, 0))
        self.assertEqual(sum(x['already_native_qualified_exclusion']
                             for x in scopes[0]['missing']), 31)


if __name__ == '__main__':
    unittest.main()
