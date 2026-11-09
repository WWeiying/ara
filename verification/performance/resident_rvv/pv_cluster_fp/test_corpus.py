import unittest
from corpus import records, selections


class CorpusTest(unittest.TestCase):
    def setUp(self):
        self.meta = [dict(id=0, elements=1, heads=1, tokens=1, rm=0,
                          mode=0, fma_flags=0, prepared_flags=0, name='one')]
        self.text = '50565531 1\n0 1 1 1 0 0 0 -1 0 0 0 0 0 0\n'

    def test_identity(self):
        self.assertEqual(records(self.text, self.meta)['one']['body'], [])

    def test_drift(self):
        with self.assertRaises(ValueError):
            records(self.text.replace('0 1 1 1', '0 2 1 1'), self.meta)
        with self.assertRaises(ValueError):
            records(self.text+'0\n', self.meta)

    def test_selection(self):
        selected = selections()
        self.assertEqual(len(selected), 68)
        self.assertEqual(selected[2], [f'qwen3_tile2_lane{l}' for l in range(4)])
        self.assertTrue(all(len(group)==4 for group in selected))
