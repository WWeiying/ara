import copy
import unittest

import query_smoke as q


class QueryTests(unittest.TestCase):
    def fixture(self):
        text = 'RESIDENT_QUERY '+ ' '.join(f'info{i}={v:016x}' for i, v in enumerate(q.EXPECTED[:5]))
        text += ' status=0 valid=1 pv=1 qk=1 lanes=4 vlen=1024 errors=0\nCore Test *** SUCCESS ***\n'
        rows = [dict(trap='0', insn='000545db', event='retire', rd_wdata=f'{v:016x}') for v in q.EXPECTED]
        return text, rows

    def test_pass(self):
        self.assertEqual(q.check_native(*self.fixture())['retired_queries'], 7)

    def test_old_zero_contract_or_bad_trace_rejected(self):
        text, rows = self.fixture()
        for bad in (text.replace('0000040000040301', '0000000000000000'), text+text,
                    text.replace('errors=0', 'errors=1'), text.replace('Core Test *** SUCCESS ***', 'FAIL')):
            with self.assertRaises(ValueError): q.check_native(bad, rows)
        for index in range(7):
            bad = copy.deepcopy(rows); bad[index]['rd_wdata'] = '1'
            with self.assertRaises(ValueError): q.check_native(text, bad)
        with self.assertRaises(ValueError): q.check_native(text, rows[:-1])
        bad = copy.deepcopy(rows); bad[0]['trap'] = '1'
        with self.assertRaises(ValueError): q.check_native(text, bad)


if __name__ == '__main__':
    unittest.main()
