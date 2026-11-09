"""Fail-closed receipt parsing checks; no simulator needed."""
import unittest
import run


class ReceiptTests(unittest.TestCase):
    def log(self):
        return '\n'.join(
            f'PV_GROUP_CASE_PASS id={i} error={e} flags={f} writes={w}'
            for i, e, f, w in run.EXPECTED) + (
                '\nPV_GROUP_PASS cases=10 terminals=10 cycles=100 stalled=1 '
                'rejected=1 cancel=1 done_stalls=1\n')

    def test_positive(self):
        self.assertEqual(run.check_positive(self.log())['cases'], 10)

    def test_bad_positive(self):
        for log in (self.log() * 2, self.log().replace('id=1 ', 'id=2 '),
                    self.log().replace('stalled=1', 'stalled=0'),
                    self.log().replace('writes=4', 'writes=0'), self.log() + 'Fatal: error\n'):
            with self.subTest(log=log), self.assertRaises(ValueError):
                run.check_positive(log)

    def test_negative(self):
        log = ('PV_GROUP_EXPECT_POSTCOMMIT_FATAL writes=1\n'
               'Fatal: "/inputs/akv_resident_pv_group.sv", 144: '
               'resident_pv_group_tb.dut.unnamed$$_1: at time 65000 ps\n'
               'Resident PV group post-authorization lane error\n')
        run.check_negative(1, log)
        run.check_negative(0, log)
        for rc, text in ((2, log), (124, log), (137, log), (1, ''), (1, log * 2),
                         (1, log.replace('post-authorization', 'unrelated'))):
            with self.subTest(rc=rc, text=text), self.assertRaises(ValueError):
                run.check_negative(rc, text)


if __name__ == '__main__':
    unittest.main()
