import unittest
from test_model_check import ModelCheck
from run_census import census_check, transform


class CensusCheck(unittest.TestCase):
    def setUp(self):
        fixture = ModelCheck()
        fixture.setUp()
        rows = [f'GRAPH_COMMAND_RECORD mode={m} kind={k} step={t} count={100+k*3+t}'
                for m in range(2) for k in range(2) for t in range(3)]
        rows += [f'GRAPH_COMMAND_COMPARE kind={k} step={t} count={100+k*3+t} exact=1'
                 for k in range(2) for t in range(3)]
        self.text = fixture.text + '\n' + '\n'.join(rows)

    def test_complete(self):
        result = census_check(self.text)
        self.assertEqual(result['native_calls_per_mode'], 615)
        self.assertTrue(result['native_call_shapes_verified'])
        self.assertFalse(result['hardware_command_counts_verified'])
        self.assertFalse(result['performance_measured'])

    def test_reject(self):
        for old, new in [('mode=1 kind=0 step=0 count=100', 'mode=1 kind=0 step=0 count=101'),
                         ('step=0 count=100', 'step=0 count=0'),
                         ('exact=1', 'exact=0'), ('count=105', 'count=1048577'),
                         ('bitwise=1', 'bitwise=0'),
                         ('GRAPH_COMMAND_RECORD mode=0 kind=0 step=0 count=100', '')]:
            with self.subTest(field=old), self.assertRaises(ValueError):
                census_check(self.text.replace(old, new, 1))

    def test_ambiguous_source(self):
        with self.assertRaises(ValueError):
            transform('int main() { return 0; }')


if __name__ == '__main__':
    unittest.main()
