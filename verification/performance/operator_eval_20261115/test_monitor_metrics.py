from pathlib import Path
import tempfile
import unittest
import sys
sys.path.insert(0,str(Path(__file__).parent))
from monitor_metrics import parse


class MonitorTests(unittest.TestCase):
    def test_four_lane_roi(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            (p/'run.vcs.log').write_text('\n'.join('OPERATOR_UNIT x.gen_lanes['+str(i)+'] cycles=10 '
                'native_requests=1 qk_requests=2 pv_requests=3 qk_elements=4 pv_elements=8'
                for i in range(4)))
            (p/'llm_perf_report_test.log').write_text('[LLM_PERF] case=x phase=total nr_lanes=4 cycles=10 '
                'retired_vector_inst_count=3 retired_inst_count=9 axi_r_bus_bytes=32 axi_r_beat_count=2\n')
            r=parse(p)
            self.assertEqual(r['four_lane_unit_roi'][0]['cycles'],10)
            self.assertEqual(r['four_lane_unit_roi'][0]['qk_elements'],16)
            self.assertEqual(r['four_lane_unit_roi'][0]['fpu_accepted_lane_requests_per_cycle'],2.4)
            (p/'run.vcs.log').write_text('OPERATOR_UNIT x.gen_lanes[0] cycles=10\n')
            with self.assertRaises(ValueError):
                parse(p)

    def test_no_roi_is_not_zero_utilization(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'run.vcs.log').write_text('smoke')
            r=parse(p)
            self.assertEqual(r['total_roi'],[])
            self.assertEqual(r['four_lane_unit_roi'],[])


if __name__ == '__main__':
    unittest.main()
