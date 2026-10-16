import unittest
from reduce_fault import isolate
from trace_fault import instrument, TOOLS


class FaultReductionTests(unittest.TestCase):
    def test_preserves_memory_and_handler(self):
        source = (TOOLS / 'fault_replay_oracle.c').read_text()
        trigger = dict(unmapped=0, store=1, boundary=3, mode=2, split=0)
        reduced = isolate(source, trigger)
        selector = '        if(!(unmapped==0 && store_case==1 && boundary==3 && mode==2 && split==0))continue;\n'
        self.assertEqual(reduced.replace(selector, ''), source)
        self.assertIn('RVV_FAULT_BEGIN', instrument(reduced))
        self.assertLess(reduced.index(selector), reduced.index('long address=call(222'))

    def test_rejects_unmeasured_domain(self):
        source = (TOOLS / 'fault_replay_oracle.c').read_text()
        with self.assertRaises(ValueError):
            isolate(source, dict(unmapped=0, store=0, boundary=2, mode=3, split=0))

    def test_segment_split_preserves_recovery(self):
        source = (TOOLS / 'fault_replay_oracle.c').read_text()
        trigger = dict(unmapped=1, store=0, boundary=5, mode=2, split=1)
        for fields in range(2, 9):
            reduced = isolate(source, trigger, fields)
            selector = '        if(!(unmapped==1 && store_case==0 && boundary==5 && mode==2 && split==1))continue;\n'
            self.assertEqual(reduced.replace(selector, ''), source)
        for fields in (0, 1, 9, True):
            with self.assertRaises(ValueError):isolate(source, trigger, fields)

    def test_stride_selectors_preserve_source(self):
        source = (TOOLS / 'fault_replay_oracle.c').read_text()
        trigger = dict(unmapped=1, store=1, boundary=3, mode=2, split=0, gap=3)
        reduced = isolate(source, trigger, strided=True)
        selector = '        if(!(unmapped==1 && store_case==1 && boundary==3 && mode==2 && split==0 && gap==3))continue;\n'
        self.assertEqual(reduced.replace(selector, ''), source)
        self.assertIn('num(gap)', instrument(reduced, True))
        with self.assertRaises(ValueError):
            isolate(source, dict(trigger, gap=2), strided=True)
        with self.assertRaises(ValueError):
            isolate(source, trigger)
        trigger.pop('gap')
        trigger['boundary'] = 0
        reduced = isolate(source, trigger, strided=True, zero=True)
        self.assertIn('boundary==0', reduced)
        with self.assertRaises(ValueError):
            isolate(source, trigger, zero=True)
        with self.assertRaises(ValueError):
            isolate(source, dict(trigger, gap=1), strided=True, zero=True)


if __name__ == '__main__':
    unittest.main()
