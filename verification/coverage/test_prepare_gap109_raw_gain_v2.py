"""Real compiled variant and narrow missing-checksum negative regressions."""
import copy
import unittest

import prepare_gap109_raw_gain_v2 as m


class MappingTests(unittest.TestCase):
    def setUp(self):
        db = m.DESIGN/'snps/coverage/db'
        self.shape = m.inventory.read_xml(db/'shape/cond.verilog.shape.xml')
        tgl = m.inventory.read_xml(db/'shape/tgl.verilog.shape.xml')
        self.tgl = next(n for n in tgl if n.get('id') == '-30' and n.get('chksum') == '1427877459')
        design = m.inventory.read_xml(db/'design/verilog.design.xml')
        self.module = next(n for n in design if n.get('id') == '-30')
        self.row = dict(width=217,checksum=None)

    def call(self, **kw):
        args = dict(shape=self.shape,module=self.module,scope=m.LZC_SCOPE,
                    row=self.row,info_checksum=None,tgl_definition=self.tgl,metric='cond')
        args.update(kw)
        return m.native_definition(**args)

    def test_real_exact_variant(self):
        db=m.DESIGN/'snps/coverage/db'
        info=m.inventory.read_xml(db/'shape/tgl.verilog.info.xml')
        self.assertEqual([n.get('chksum') for n in info.iter('instance_data')
                          if n.get('name') == m.LZC_SCOPE],['1427877459'])
        cond=m.inventory.read_xml(db/'shape/cond.verilog.info.xml')
        self.assertEqual([n for n in cond.iter('instance_data')
                          if n.get('name') == m.LZC_SCOPE],[])
        node, binding = self.call()
        self.assertEqual(node.get('chksum'),'4070328312')
        self.assertIn('full_parameters',binding)
        self.assertEqual(len(m.inventory.points('cond',node,217)),217)

    def test_module_drift(self):
        for key,value in [('id','-31'),('name','fpnew_fma'),('chksum','0')]:
            n=copy.deepcopy(self.module);n.set(key,value)
            with self.assertRaises(ValueError): self.call(module=n)

    def test_parameters_and_tgl_checksum(self):
        for key,value in [('name',m.LZC_NAME.replace('MODE=1','MODE=0')+' '),('chksum','0'),('id','-31')]:
            n=copy.deepcopy(self.tgl);n.set(key,value)
            with self.assertRaises(ValueError): self.call(tgl_definition=n)

    def test_ambiguity(self):
        shape=copy.deepcopy(self.shape)
        shape.append(copy.deepcopy(next(n for n in shape if n.get('chksum')=='4070328312')))
        with self.assertRaises(ValueError): self.call(shape=shape)

    def test_cond_checksum_drift(self):
        shape=copy.deepcopy(self.shape)
        next(n for n in shape if n.get('chksum')=='4070328312').set('chksum','0')
        with self.assertRaises(ValueError): self.call(shape=shape)

    def test_width_metric_checksum(self):
        for args in [dict(row=dict(width=218,checksum=None)),dict(metric='branch'),
                     dict(info_checksum='4070328312'),dict(tgl_definition=None)]:
            with self.assertRaises(ValueError): self.call(**args)

    def test_foreign_scope_rejected(self):
        with self.assertRaises(ValueError): self.call(scope=m.LZC_SCOPE+'.foreign')

    def test_exact_historical_source(self):
        source=m.life.ROOT/'hardware/deps/common_cells/src/lzc.sv'
        build=m.life.read_bound(m.qualifier.BUILD,m.qualifier.BUILD_SHA)
        expected='f31989be4369ea7c4809c0c3d61df28581e9ac7666005fde6e476a975d1acd07'
        self.assertEqual(m.historical_source_pin(source,build),{str(source):expected})
        m.life.check({str(source):expected})
        with self.assertRaises(ValueError): m.historical_source_pin(source.with_name('foreign.sv'),build)
        with self.assertRaises(ValueError): m.life.check({str(source):'0'*64})

    def test_saved_singleton_identity(self):
        self.assertEqual(m.life.digest(m.SAVED_SINGLE),m.SAVED_SHA)


if __name__ == '__main__':
    unittest.main()
