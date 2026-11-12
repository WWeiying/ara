import copy
import unittest

import retire_audit as audit


class RetirementTests(unittest.TestCase):
    def test_mixed_events_and_fail_closed_mutations(self):
        old, new = audit.modules()
        text = 'RESIDENT_QUERY '+ ' '.join(f'info{i}={v:016x}' for i, v in enumerate(old.EXPECTED[:5]))
        text += ' status=0 valid=1 pv=1 qk=1 lanes=4 vlen=1024 errors=0\nCore Test *** SUCCESS ***\n'
        retired = [dict(trap='0', insn='000545db', event='retire', rd_wdata=f'{v:016x}') for v in old.EXPECTED]
        starts = [dict(row, event=event, rd_wdata='0') for row in retired for event in ('arch_start', 'cvx_req')]
        mixed = starts+retired
        with self.assertRaisesRegex(ValueError, 'Malformed AKVINFO retirement'):
            old.check_native(text, mixed)
        self.assertEqual(new.check_native(text, mixed)['retired_queries'], 7)
        for bad in (mixed[:-1], mixed+retired[:1], starts):
            with self.assertRaises(ValueError): new.check_native(text, bad)
        for index in range(7):
            bad = copy.deepcopy(retired); bad[index]['rd_wdata'] = '1'
            with self.assertRaises(ValueError): new.check_native(text, starts+bad)
        bad = copy.deepcopy(starts); bad[0]['trap'] = '1'
        with self.assertRaises(ValueError): new.check_native(text, bad+retired)
        with self.assertRaises(ValueError):
            new.check_native(text.replace('0000040000040301', '0000000000000000'), mixed)


if __name__ == '__main__':
    unittest.main()
