from decimal import Decimal as D
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[2]/'vcu118/ethernet'))
import check_repaired_synthesis as g


class RepairedReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        (self.root/'completed.txt').write_text('903503b5ace4\n')
        (self.root/'timing.rpt').write_text('current')
        (self.root/'pins.tsv').write_text('port\tpin\tbank\n'
            'sys_clk_p\tE12\t71\nsys_clk_n\tD12\t71\n'
            'c2_sys_clk_p\tAW26\t41\nc2_sys_clk_n\tAW27\t41\n')
        clocks='clock\tsource\tperiod\nsys_clk\tsys_clk_p\t4\nc2_sys_clk\tc2_sys_clk_p\t4\n'
        for suffix,prefix in (('',g.C2),('_1',g.C1)):
            for clock,period in (('mmcm_clkout0','3.333'),('mmcm_clkout6','13.333')):
                clocks+=f'{clock}{suffix}\t{prefix}mmcm/{clock}\t{period}\n'
        (self.root/'clocks.tsv').write_text(clocks)
        rows='from\tto\tslack\tsource\tdestination\n'
        self.current={}
        for pair,prefix,count,slack in (
            (('c2_sys_clk','c2_sys_clk'),g.C2,16,'-.062'),
            (('sys_clk','sys_clk'),g.C1,16,'-.062'),
            (('mmcm_clkout0','mmcm_clkout6'),g.C2,1,'-.173'),
            (('mmcm_clkout0_1','mmcm_clkout6_1'),g.C1,1,'-.154')):
            cross=pair[0]!=pair[1]
            kind='cross' if cross else 'ref'
            for i in range(count):
                rows+=f'{pair[0]}\t{pair[1]}\t{slack}\t{prefix}{kind}_source/C\t{prefix}{kind}_dest{i}/D\n'
            key=('Inter Clock Table',pair,'WHS(ns)') if cross else ('Intra Clock Table',(pair[0],),'WHS(ns)')
            self.current[key]=(D(slack),D(count))
        (self.root/'paths.tsv').write_text(rows)
        self.baseline={('Intra Clock Table',('sys_clk',),'WHS(ns)'):(D('-.062'),D(16)),
                       ('Inter Clock Table',('mmcm_clkout0','mmcm_clkout6'),'WHS(ns)'):(D('-.154'),D(1))}
        self.values=list(map(D,['1','0','0','100','-.173','-1','34','100','1','0','0','100']))
        self.summary=patch.object(g,'summary',return_value=self.values); self.summary.start()
        self.clocks=patch.object(g,'clock_violations',side_effect=lambda text: self.baseline if text=='baseline' else self.current)
        self.clocks.start()

    def tearDown(self):
        self.clocks.stop(); self.summary.stop(); self.tmp.cleanup()

    def check(self): return g.check('current','baseline',self.root)

    def test_positive_is_not_clean_timing(self):
        result=self.check()
        self.assertTrue(result['eligible_for_implementation'])
        self.assertFalse(result['synthesis_timing_clean'])
        self.assertFalse(result['routed_checks_relaxed'])

    def test_missing_completion(self):
        (self.root/'completed.txt').unlink()
        with self.assertRaises(OSError): self.check()

    def test_rejects_physical_pin_regression(self):
        p=self.root/'pins.tsv'; p.write_text(p.read_text().replace('AW26\t41','E12\t71'))
        with self.assertRaisesRegex(ValueError,'pin mapping'): self.check()

    def test_rejects_wrong_clock_owner(self):
        p=self.root/'clocks.tsv'; p.write_text(p.read_text().replace(g.C2,'wrong/'))
        with self.assertRaisesRegex(ValueError,'ownership'): self.check()

    def test_rejects_unreviewed_endpoint(self):
        p=self.root/'paths.tsv'; p.write_text(p.read_text().replace(g.C2+'ref_dest0','cpu/ref_dest0'))
        with self.assertRaisesRegex(ValueError,'leaves'): self.check()

    def test_rejects_correspondence_change(self):
        p=self.root/'paths.tsv'; p.write_text(p.read_text().replace(g.C2+'cross_dest0',g.C2+'other_dest'))
        with self.assertRaisesRegex(ValueError,'correspond'): self.check()

    def test_rejects_worse_hold(self):
        p=self.root/'paths.tsv'; p.write_text(p.read_text().replace('-.173','-.180'))
        with self.assertRaisesRegex(ValueError,'envelope'): self.check()

    def test_rejects_duplicate_endpoint(self):
        p=self.root/'paths.tsv'; p.write_text(p.read_text()+p.read_text().splitlines()[1]+'\n')
        with self.assertRaisesRegex(ValueError,'Duplicate'): self.check()

    def test_rejects_setup_failure(self):
        self.values[0]=D(-1)
        with self.assertRaisesRegex(ValueError,'setup'): self.check()

    def test_rejects_other_new_group(self):
        self.current[('Intra Clock Table',('unsafe',),'WHS(ns)')]=(D('-.1'),D(1))
        with self.assertRaisesRegex(ValueError,'Unreviewed'): self.check()


if __name__=='__main__': unittest.main()
