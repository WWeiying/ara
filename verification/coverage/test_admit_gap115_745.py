import copy
import unittest
import admit_gap115_745 as m


class Contracts(unittest.TestCase):
    def test_prefix(self):
        paths = ['/old/%d'%i for i in range(744)]
        m.exact_prefix(paths, [str(m.DESIGN), *paths])
        for bad in (paths[:-1], paths[:-1]+[paths[0]], paths[:-1]+[str(m.VDB)]):
            with self.assertRaises(ValueError): m.exact_prefix(bad, [str(m.DESIGN), *bad])
        with self.assertRaises(ValueError): m.exact_prefix(paths, [str(m.DESIGN), *reversed(paths)])

    def test_qualification_no_fake_uvm_pass(self):
        q = m.life.read_bound(m.QUAL/'qualification.json', m.QUAL_SHA)
        m.qualification_exact(q)
        for name, value in [('uvm_check_report_pass', True), ('axi_burst_conservation_verified', False),
                            ('original_failures_preserved', False), ('software_checks', 678)]:
            bad = dict(q); bad[name] = value
            with self.assertRaises(ValueError): m.qualification_exact(bad)

    def fixture(self):
        old = dict(design={'design': 'fixed'}, tests=['/old/%d'%i for i in range(744)],
                   input_hashes={'/synthetic': 'a'*64}, metrics={
            'line': {str(i): dict(width=2, checksum='9', bits='0x1') for i in range(6159)},
            **{k: {'scope': dict(width=2, checksum='9', bits='0x1')} for k in ('cond', 'branch', 'fsm')}})
        new = copy.deepcopy(old); new['tests'] = [str(m.VDB)]
        new['metrics']['fsm']['scope']['bits'] = '0x2'
        return old, new, m.bitmap.combine(old, new)

    def test_OR(self):
        self.assertEqual(m.verify_union(*self.fixture()), 6162)
        for mutation in ('or', 'prefix', 'width', 'checksum', 'design', 'universe'):
            old, new, combined = self.fixture()
            if mutation == 'or': combined['metrics']['fsm']['scope']['bits'] = '0x2'
            elif mutation == 'prefix': combined['tests'][0] = '/foreign'
            elif mutation in ('width', 'checksum'): combined['metrics']['fsm']['scope'][mutation] = 4
            elif mutation == 'design': new['design'] = {'foreign': 'design'}
            else: del combined['metrics']['fsm']['scope']
            with self.assertRaises(ValueError): m.verify_union(old, new, combined)

    def test_gain_and_status(self):
        delta = dict(metrics=dict(line=0, cond=0, branch=0, fsm=4), instances=[dict(
            instance=m.audit.ROOT+'.gen_lanes[%d].i_lane.i_vfus.i_vmfpu.i_simd_div'%i,
            metric='fsm', new_bits=1) for i in range(4)])
        m.positive_gain(delta)
        for bad in (dict(delta, metrics=dict(line=0, cond=0, branch=0, fsm=0)),
                    dict(delta, instances=delta['instances'][:-1])):
            with self.assertRaises(ValueError): m.positive_gain(bad)
        s = m.payload(dict(count=6162, delta=delta))
        self.assertEqual(s['aggregate_passed'], 745)
        self.assertFalse(s['uvm_check_report_pass'])
        self.assertTrue(s['original_missing_uvm_summary_failure_preserved'])

    def test_pin_conflict(self):
        with self.assertRaises(ValueError): m.life.merge_pins({'/fixed': 'a'*64}, {'/fixed': 'b'*64})


if __name__ == '__main__': unittest.main()
