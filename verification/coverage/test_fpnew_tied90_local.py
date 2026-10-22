import copy
import json
import unittest
import xml.etree.ElementTree as ET
import fpnew_tied90_local as p


class Local(unittest.TestCase):
    def fixture(self):
        return dict(instances=[dict(scope='a.gen[0].round',design_module_checksum='1',toggle_checksum='2',
            signals=[dict(name='id_i',left=33,right=0)])])

    def test_whole_roundtrip(self):
        c=self.fixture(); self.assertEqual(p.el_gate(p.candidate(c['instances']),c),[('a.gen[0].round','id_i')])

    def test_paired_direction_roundtrip(self):
        c=self.fixture(); text=p.candidate(c['instances']); line=text.splitlines()[-1]
        text=text.replace(line,line.replace('Toggle ','Toggle 0to1 ')+'\n'+line.replace('Toggle ','Toggle 1to0 '))
        p.el_gate(text,c)

    def test_missing_direction(self):
        c=self.fixture()
        with self.assertRaises(ValueError): p.el_gate(p.candidate(c['instances']).replace('Toggle ','Toggle 0to1 '),c)

    def test_foreign_field_and_partial(self):
        c=self.fixture(); text=p.candidate(c['instances'])
        for altered in (text.replace('id_i','rnd_mode_i'),text.replace('[33:0]','[32:0]'),text.replace('1 2','1 3')):
            with self.assertRaises(ValueError): p.el_gate(altered,c)

    def test_foreign_annotation(self):
        c=self.fixture()
        with self.assertRaises(ValueError): p.el_gate(p.candidate(c['instances']).replace(p.ANNOTATION,'foreign'),c)

    def test_actual_recursive_tcl_closure(self):
        pins=p.tcl_pins(p.TCL)
        for name in ('mfpu272_five_phase.tcl','mfpu_constants272_native_bind.tcl',
                     'cva6_fixed_fields_native768.tcl','apply_points740_v4.tcl'):
            self.assertIn(str(p.HERE/name),pins)

    def test_actual_RSR_disabled(self):
        for family in ('fpnew_fma','fpnew_cast_multi'):
            text=(p.life.ROOT/('hardware/deps/fpnew/src/'+family+'.sv')).read_text()
            self.assertIsNotNone(p.re.search(r'\.EnableRSR\s*\(\s*0\s*\)',text))
            self.assertIsNone(p.re.search(r'\.EnableRSR\s*\(\s*0\s*\)',
                                         text.replace('.EnableRSR ( 0 )','.EnableRSR ( 1 )')))

    def test_missing_protected_and_role(self):
        i=self.fixture()['instances'][0]
        i['typed_objects']=[dict(name='id_i',kind='vectornode',left='33',right='0',portnode='2'),
                            dict(name='clk_i',kind='node',portnode='2')]
        header='handle\tpath\tmeta\tname\ttype\tcoverage\tdisplay\n'
        rows='0\tItem0\tItem0\tid_i[33:0]\tport\t0%\t0%\n1\tItem1\tItem1\tclk_i\tport\t0%\t0%\n'
        p.bind(i,header+rows)
        for bad in (rows.splitlines(True)[0],rows.replace('\tport\t','\tsignal\t',1)):
            with self.assertRaises(ValueError): p.bind(i,header+bad)

    def test_generated_full_session_hook(self):
        c=self.fixture(); c['instances'][0]['typed_objects']=[dict(name='id_i',kind='vectornode',left='33',right='0',portnode='2')]
        selection='set mq_design design\nset mq_vdb sample\nset mq_test test\nset mq_instances [list [list {a.gen[0].round} [list {id_i[33:0]}]]]\n'
        evidence=p.host_hook(c,selection,p.candidate(c['instances']))
        self.assertFalse(evidence['EDA_started'])


if __name__=='__main__': unittest.main()
