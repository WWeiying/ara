import unittest
from test_census_check import CensusCheck
from schedule_check import check


class ScheduleCheck(unittest.TestCase):
    def setUp(self):
        fixture = CensusCheck(); fixture.setUp()
        self.text = fixture.text
        for mode in range(2):
            rows = []
            for i in range(6):
                stats = [2*(i+1), i+1, i+1, i+1, 0, 0, 0, 0, 64*(i+1), 32*(i+1), i+1, 0, 0, 0]
                rows += [f'GRAPH_SCHEDULE epoch={i+1} nodes=3 groups=1',
                         f'GRAPH_SCHEDULE_GROUP epoch={i+1} first=0 last=2 op=29',
                         f'GRAPH_CACHE epoch={i+1} ' + ' '.join(f's{j}={v}' for j,v in enumerate(stats))]
            anchor = f'GRAPH_CYCLES_MODEL_END enabled={mode}'
            self.text = self.text.replace(anchor, '\n'.join(rows)+'\n'+anchor)

    def test_valid(self):
        result = check(self.text)
        self.assertEqual(result['schedule_groups_per_mode'], 6)
        self.assertTrue(result['reuse_counts_verified'])

    def test_invalid(self):
        for old,new in [('first=0 last=2 op=29', 'first=0 last=1 op=29'),
                        ('s1=1', 's1=0'), ('nodes=3 groups=1', 'nodes=3 groups=2'),
                        ('GRAPH_CACHE epoch=1', 'GRAPH_CACHE epoch=2'),
                        ('s10=1', 's10=9')]:
            with self.subTest(field=old), self.assertRaises(ValueError):
                check(self.text.replace(old,new,1))


if __name__ == '__main__': unittest.main()
