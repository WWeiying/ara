import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('power_convert',HERE/'convert.py')
c=importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class ConversionTests(unittest.TestCase):
    def test_delayed_initial_snapshot(self):
        data=c.vcd_window(HERE/'fixtures/window_probe.vcd')
        self.assertEqual(data['first_tick'],100000)
        self.assertEqual(data['last_tick'],200000)
        self.assertEqual(data['duration_fs'],100000000)
        self.assertEqual(data['initial_snapshot_values'],1)

    def test_no_tail_without_state(self):
        text=(HERE/'fixtures/window_probe.vcd').read_text()
        text=text.replace('$dumpvars\n0!\n$end\n','0!\n')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'tail.vcd'
            path.write_text(text)
            with self.assertRaisesRegex(ValueError,'snapshot'):
                c.vcd_window(path)

    def test_clock_duration_and_unknown_gates(self):
        v=dict(duration_fs=100000000,tick_fs=1000)
        s=dict(duration_ticks=100000,tick_fs=1000,
               clock_activity=dict(T0=50000,T1=50000,TX=0,TC=200))
        c.check_activity(v,s,100,1)
        s['clock_activity']['TX']=1
        with self.assertRaisesRegex(ValueError,'Unknown'):
            c.check_activity(v,s,100,1)
        s['clock_activity']['TX']=0
        s['duration_ticks']=99
        with self.assertRaisesRegex(ValueError,'duration'):
            c.check_activity(v,s,100,1)

    def test_actual_tool_probe_when_available(self):
        path=Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/'
                  'power_converter_probe_20261117_ticks_02.saif')
        if not path.exists():
            self.skipTest('Local synthetic converter probe not present')
        summary=c.saif_summary(path,clock='clk')
        self.assertEqual(summary['duration_ticks'],100000)
        self.assertEqual(summary['clock_activity']['TX'],0)
        self.assertEqual(summary['clock_activity']['T0'],50000)
        self.assertEqual(summary['clock_activity']['T1'],50000)

    def test_select_root_clock_not_gated_child(self):
        text='''(SAIFILE
(TIMESCALE 1 ps)
(DURATION 100)
(INSTANCE ara_tb
 (INSTANCE dut
  (INSTANCE i_ara_soc
   (INSTANCE gated
    (NET
     (clk_i
      (T0 100) (T1 0) (TX 0) (TC 0)
     )
    )
   )
   (NET
    (clk_i
     (T0 50) (T1 50) (TX 0) (TC 20)
    )
   )
  )
 )
)
)
'''
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'nested.saif'
            path.write_text(text)
            self.assertEqual(c.saif_summary(path)['clock_activity']['TC'],20)


if __name__=='__main__':
    unittest.main()
