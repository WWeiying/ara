import unittest
from compose_standalone import ROOT, compose, adapt_tb, COUNTERS


class StandaloneCompositionTests(unittest.TestCase):
    def test_complete_headers_preserved(self):
        for kind in ('qbs','akv'):
            source=(ROOT/f'hardware/src/vlsu/{kind}/{kind}_engine.sv').read_text()
            wrapper=compose(source,kind)
            header=source[:source.index('\n  );')+len('\n  );')]
            self.assertTrue(wrapper.startswith(header.replace('module '+kind+'_engine',
                                                              'module '+kind+'_engine_composed',1)))
            self.assertEqual(wrapper.count(') i_engine ('),1)
            self.assertEqual(wrapper.count(') i_shared_reader ('),1)
            self.assertIn('.reader_rsp_i(client_rsp[0])',wrapper)
            for counter,field in COUNTERS.items():
                self.assertIn(f'.{counter}(observed_{counter})',wrapper)
                self.assertIn(f'assign {counter} = owner_q ? observed_{counter} : i_shared_reader.reader_rsp.{field}',wrapper)

    def test_tb_only_hierarchy_changes(self):
        for kind in ('qbs','akv'):
            source=(ROOT/f'verification/{kind}/{kind}_engine_tb.sv').read_text()
            actual=adapt_tb(source,kind)
            self.assertEqual(actual.count('$fatal'),source.count('$fatal'))
            self.assertEqual(actual.count('dut.i_engine.'),source.count('dut.'))
            self.assertIn(kind+'_engine_composed #(',actual)
            self.assertNotIn('dut.i_engine.i_engine.',actual)

    def test_changed_interfaces_rejected(self):
        source=(ROOT/'hardware/src/vlsu/qbs/qbs_engine.sv').read_text()
        with self.assertRaises(ValueError):
            compose(source.replace('ActivationLookahead','DifferentParameter'), 'qbs')
        with self.assertRaises(ValueError):
            adapt_tb('module unrelated; endmodule','akv')


if __name__=='__main__':
    unittest.main()
