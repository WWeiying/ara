import unittest
from test_model_check import ModelCheck
from run_census import census_check, transform, audit_calls


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

    def test_link_audit(self):
        text = '''00001000 <__wrap_qbs_native_execute_command>:
1000: abc jr 126(t1) # 4000 <qbs_native_execute_command>
1004: abc jalr 32(ra) # 4000 <qbs_native_execute_command>
00002000 <direct>:
2000: abc jr 716(t1) # 1000 <__wrap_qbs_native_execute_command>
00003000 <projection>:
3000: abc jalr 356(ra) # 1000 <__wrap_qbs_native_execute_command>
'''
        self.assertEqual(audit_calls(text), 2)
        with self.assertRaises(ValueError):
            audit_calls(text + '3004: abc jr 10(t1) # 4000 <qbs_native_execute_command>\n')
        with self.assertRaises(ValueError):
            audit_calls(text.replace('jr 716(t1)', 'nop'))


if __name__ == '__main__':
    unittest.main()
