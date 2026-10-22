import copy
import unittest
import admit_gap114_743 as m


class Contracts(unittest.TestCase):
    def test_exact_prefix(self):
        paths = ['/old/%d'%i for i in range(742)]
        m.exact_prefix(paths, [str(m.DESIGN), *paths])
        for other in (paths[:-1], paths[:-1]+[paths[0]], paths[:-1]+[str(m.VDB)]):
            with self.assertRaises(ValueError): m.exact_prefix(other, [str(m.DESIGN), *other])
        with self.assertRaises(ValueError): m.exact_prefix(paths, [str(m.DESIGN), *reversed(paths)])

    def test_positive_gain(self):
        delta = dict(metrics=dict(line=0, cond=0, branch=0, fsm=1), instances=[dict(
            instance='ara_tb.dut.i_ara_soc.i_system.i_ariane.ex_stage_i.lsu_i.i_load_unit', metric='fsm', new_bits=1)])
        m.positive_gain(delta)
        for key, value in [('fsm', 0), ('fsm', 4), ('line', 1)]:
            bad = copy.deepcopy(delta); bad['metrics'][key] = value
            with self.assertRaises(ValueError): m.positive_gain(bad)
        delta['instances'][0]['instance'] = 'outside_product'
        with self.assertRaises(ValueError): m.positive_gain(delta)

    def fixture(self):
        rows = {str(i): dict(width=2, checksum='9', bits='0x1') for i in range(6159)}
        old = dict(design={'design': 'fixed'}, input_hashes={'/synthetic': 'a'*64},
                   tests=['/old/%d'%i for i in range(742)], metrics={
            'line': rows, 'cond': {'c': dict(width=2, checksum='9', bits='0x1')},
            'branch': {'b': dict(width=2, checksum='9', bits='0x1')},
            'fsm': {'f': dict(width=2, checksum='9', bits='0x1')}})
        single = copy.deepcopy(old); single['tests'] = [str(m.VDB)]
        single['metrics']['fsm']['f']['bits'] = '0x2'
        return old, single, m.bitmap.combine(old, single)

    def test_full_OR(self):
        self.assertEqual(m.verify_union(*self.fixture()), 6162)

    def test_OR_prefix_identity_and_universe_mutations(self):
        for mutation in ('or', 'prefix', 'checksum', 'width', 'scope', 'design'):
            old, single, result = self.fixture()
            if mutation == 'or': result['metrics']['fsm']['f']['bits'] = '0x2'
            elif mutation == 'prefix': result['tests'][0] = '/foreign'
            elif mutation in ('checksum', 'width'): result['metrics']['fsm']['f'][mutation] = 42
            elif mutation == 'scope': result['metrics']['fsm']['foreign'] = result['metrics']['fsm'].pop('f')
            else: result['design'] = {'foreign': 'shape'}
            with self.assertRaises(ValueError): m.verify_union(old, single, result)

    def test_pin_conflict(self):
        with self.assertRaises(ValueError): m.life.merge_pins({'/fixed': 'a'*64}, {'/fixed': 'b'*64})

    def test_status_excludes_hold115(self):
        state = m.payload(dict(count=6162, delta={'metrics': dict(line=0, cond=0, branch=0, fsm=1)}))
        self.assertTrue(state['coverage_admitted']); self.assertFalse(state['gap115_included'])
        self.assertFalse(state['official_denominator_verified']); self.assertEqual(state['aggregate_passed'], 743)


if __name__ == '__main__': unittest.main()
