import copy
import json
import unittest
import collect_operand_index_snapshot_raw_724 as m


class RawTests(unittest.TestCase):
    def fixture(self):
        evidence = json.loads(m.qualified.old.TARGETS.read_bytes())
        metrics = {metric:{} for metric in m.bitmap.METRICS}
        for t in evidence['targets']:
            metrics[t['metric']][t['scope']] = dict(width=t['width'],checksum=t['checksum'],bits='0x0')
        for metric in ('line','fsm'):
            metrics[metric]['ara_tb.dut.i_ara_soc.i_system'] = dict(width=1,checksum=None,bits='0x0')
        before = dict(tests=['/old/%d/code.vdb'%i for i in range(724)],design={'design/x':'a'*64},
                      input_hashes={'/old/data.xml':'a'*64},metrics=metrics)
        single = copy.deepcopy(before)
        single['tests'] = [str(m.RUN/'code.vdb')]
        single['input_hashes'] = {'/new/data.xml':'b'*64}
        for t in evidence['targets']:
            row = single['metrics'][t['metric']][t['scope']]
            row['bits'] = hex(int(row['bits'],16)|(1 << (row['width']-1-t['point']['raw_index'])))
        return before,single,evidence

    def test_exact16_raw_union_and_gain(self):
        before,single,evidence = self.fixture()
        proposed,delta = m.population(before,single)
        targets = m.reconcile(before,single,proposed,evidence)
        self.assertEqual(len(targets),16)
        self.assertTrue(all(t['new_vs724'] for t in targets))
        self.assertEqual(delta['metrics'],dict(line=0,cond=12,branch=4,fsm=0))
        self.assertEqual(proposed['tests'][:-1],before['tests'])

    def test_target_unhit_reported_not_fabricated(self):
        before,single,evidence = self.fixture()
        t = evidence['targets'][0]
        row = single['metrics'][t['metric']][t['scope']]
        row['bits'] = hex(int(row['bits'],16)&~(1 << (row['width']-1-t['point']['raw_index'])))
        proposed,_ = m.population(before,single)
        result = m.reconcile(before,single,proposed,evidence)
        self.assertEqual(sum(t['sample_hit'] for t in result),15)

    def test_duplicate_population_and_foreign_design(self):
        for mutation in ('duplicate','population','design'):
            before,single,_ = self.fixture()
            if mutation == 'duplicate':
                before['tests'][-1] = single['tests'][0]
            elif mutation == 'population':
                before['tests'].pop()
            else:
                single['design'] = {'foreign':'f'*64}
            with self.assertRaises(ValueError):
                m.population(before,single)

    def test_conflicting_pins_and_shape_rejected(self):
        before,single,_ = self.fixture()
        single['input_hashes'] = {'/old/data.xml':'b'*64}
        with self.assertRaises(ValueError):
            m.population(before,single)
        before,single,evidence = self.fixture()
        t = evidence['targets'][0]
        single['metrics'][t['metric']][t['scope']]['checksum'] = None
        with self.assertRaises(ValueError):
            m.population(before,single)

    def test_previous_target_hit_rejected(self):
        before,single,evidence = self.fixture()
        t = evidence['targets'][0]
        row = before['metrics'][t['metric']][t['scope']]
        row['bits'] = hex(1 << (row['width']-1-t['point']['raw_index']))
        proposed,_ = m.population(before,single)
        with self.assertRaises(ValueError):
            m.reconcile(before,single,proposed,evidence)

    def test_bool_width_overflow_and_missing_metric_rejected(self):
        before,_,_ = self.fixture()
        for value in (dict(width=True,checksum=None,bits='0x0'),
                      dict(width=1,checksum=None,bits='0x2')):
            altered = copy.deepcopy(before)
            altered['metrics']['line']['ara_tb.dut.i_ara_soc.i_system'] = value
            with self.assertRaises(ValueError):
                m.validate_bitmap(altered)
        del before['metrics']['fsm']
        with self.assertRaises(ValueError):
            m.validate_bitmap(before)


if __name__ == '__main__':
    unittest.main()
