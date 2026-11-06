import unittest

from projection_resources import check, service_bound
from run_projection_resources import bench_source


VECTOR = 'QBSCMD1 1\nCMD 0 1 2 2 4 4 1 00\nC 1 576 1168 4096 4096 128 96 16\nEND\n'
LOG = '''QBS command case 0 PASS profile=1 M=4 N=4 Kb=1 layouts=2/2
QBS_RESOURCE case=0 dot=128 pairs=4096 groups=128 corrections=128 requests=16 main=64 cast=32 half=0 scale=16 min_scale=16 accum_dot=16 accum_min=16 cast_dot=16 cast_aux=16 main_blocked=0 cast_blocked=0 request_blocked=0 fp_occupied=104 busy=220
QBS command fault discard PASS
QBS pipeline fault stage 0 PASS drain_cycles=3
QBS pipeline fault stage 1 PASS drain_cycles=3
QBS pipeline fault stage 2 PASS drain_cycles=3
QBS pipeline fault stage 3 PASS drain_cycles=3
QBS command engine PASS: 1 functional cases
'''


class ResourceCheck(unittest.TestCase):
    def test_balanced_q4k(self):
        row = check(LOG,VECTOR)[0]
        self.assertEqual(row['current_service_bound']['lower_bound_cycles'],128)
        self.assertEqual(row['hypothetical_2x_dot_only']['lower_bound_cycles'],64)
        self.assertIn('fp_arithmetic',row['hypothetical_2x_dot_only']['limiting_resources'])

    def test_short_block_port_bound(self):
        row = dict(dot=16,corrections=16,main=16,cast=16,half=16,requests=16)
        self.assertEqual(service_bound(row,2,4)['lower_bound_cycles'],16)

    def test_subgroup16_correction_bound(self):
        row = dict(dot=128,corrections=256,main=32,cast=16,half=0,requests=16)
        self.assertEqual(service_bound(row,2,2)['lower_bound_cycles'],128)
        self.assertEqual(service_bound(row,2,4)['lower_bound_cycles'],64)

    def test_reject_corrupt_or_incomplete(self):
        for old,new in (('main=64','main=63'),('corrections=128','corrections=127'),
                        ('M=4','M=3'),('functional cases','cases'),
                        ('stage 3 PASS','stage 2 PASS'),('cast_dot=16','cast_dot=15')):
            with self.subTest(old=old),self.assertRaises(ValueError): check(LOG.replace(old,new),VECTOR)
        with self.assertRaises(ValueError): check(LOG+LOG,VECTOR)
        with self.assertRaises(ValueError): check(LOG+'Error: failure\n',VECTOR)

    def test_anchors(self):
        text='module qbs_compute_engine_tb;\n  qbs_compute_engine dut (\n      total_errors += case_errors;\nendmodule : qbs_compute_engine_tb'
        result=bench_source(text)
        self.assertIn('snapshot_resources(case_id)',result)
        with self.assertRaises(ValueError): bench_source(text.replace('dut (','dut (\n  qbs_compute_engine dut ('))


if __name__ == '__main__':
    unittest.main()
