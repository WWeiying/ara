import struct
import unittest
from check_planned_native import check_log


class PlannedCheckTest(unittest.TestCase):
    def test_accept_and_reject(self):
        lines=['PREFILL_PLAN_SCOPE baseline=fixed_groups candidate=bounded_boundaries planning_in_roi=1',
               'PREFILL_CAP q4=1 rows=10 d=128 first_query=0 tokens=5 trials=4']
        for trial,shared in enumerate((0,1,1,0)):
            lines.extend([f'PREFILL_BEGIN trial={trial} shared={shared}',
                f'PREFILL_RESULT trial={trial} shared={shared} cycles=100 commands=5 values={6 if shared else 9} '
                'fcsr=1 vcsr=5 errors=0 hex='+'3f800000'*1280])
        lines.append('PREFILL_SUITE_PASS');text='\n'.join(lines)
        golden=struct.pack('<40960f',*([1.]*40960))
        self.assertEqual(check_log(text,golden,1)['outputs_per_trial'],1280)
        for old,new in [('commands=5','commands=4'),('values=6','values=9'),
                        ('planning_in_roi=1','planning_in_roi=0'),('3f800000','7fc00000'),
                        ('errors=0','errors=1'),('vcsr=5','vcsr=0')]:
            with self.subTest(old=old),self.assertRaises(ValueError):
                check_log(text.replace(old,new,1),golden,1)


if __name__=='__main__':unittest.main()
