"""Sealed actual architecture and exact ordered union rejection tests."""
import unittest

import admit_qbs_pending_m4_786 as case


class Admission(unittest.TestCase):
    def setUp(self):
        self.q = case.life.read_bound(case.QUAL/'qualification.json',case.Q_SHA)
        def read(name):
            path = case.QUAL/name
            return case.life.read_bound(path,self.q['output_pins'][str(path)])
        self.audit, self.cycle = read('runtime-audit.json'),read('cycle-proof.json')

    def check(self): case.architecture(self.q,self.audit,self.cycle)

    def test_real_architecture(self): self.check()

    def test_wrong_qualification(self):
        self.q['status'] = 'SUCCESS'
        with self.assertRaises(ValueError): self.check()

    def test_no_custom_spike_claim(self):
        self.q['custom_spike_pass'] = True
        with self.assertRaises(ValueError): self.check()

    def test_missing_checkpoint(self):
        self.audit['bindings'].pop()
        with self.assertRaises(ValueError): self.check()

    def test_missing_source_guards(self):
        self.audit['source_guard_bytes'] -= 1
        with self.assertRaises(ValueError): self.check()

    def test_protocol_failure(self):
        self.audit['contract']['protocol_errors'] = 1
        with self.assertRaises(ValueError): self.check()

    def test_wrong_native_vl(self):
        self.audit['bindings'][1]['backend_vl'] = 8
        with self.assertRaises(ValueError): self.check()

    def test_no_falling_witness(self):
        self.cycle['transitions'] = [e for e in self.cycle['transitions'] if e['from_value'] != 1]
        with self.assertRaises(ValueError): self.check()

    def test_wrong_baseline_seal(self):
        with self.assertRaises(ValueError): case.evaluate(case.BASE,'0'*64)

    def union_fixture(self):
        before = dict(tests=['test%d'%i for i in range(785)],design={},input_hashes={'/fixture/old.xml':'a'*64},metrics={})
        single = dict(tests=[str(case.RUN/'code.vdb')],design={},input_hashes={'/fixture/new.xml':'b'*64},metrics={})
        for metric,count in case.COUNTS.items():
            before['metrics'][metric] = {'scope%d'%i:dict(width=2,checksum='1',bits='1') for i in range(count)}
            single['metrics'][metric] = {'scope%d'%i:dict(width=2,checksum='1',bits='2') for i in range(count)}
        return before,single

    def test_complete6162_union(self):
        b,s = self.union_fixture();a = case.full_union(b,s)
        self.assertEqual(len(a['tests']),786)
        self.assertEqual(sum(map(len,a['metrics'].values())),6162)
        self.assertTrue(all(r['bits']=='0x3' or int(r['bits'],16)==3 for rows in a['metrics'].values() for r in rows.values()))

    def test_duplicate_vdb(self):
        b,s = self.union_fixture();b['tests'][-1] = s['tests'][0]
        with self.assertRaises(ValueError): case.full_union(b,s)

    def test_missing_scope(self):
        b,s = self.union_fixture();s['metrics']['line'].pop('scope0')
        with self.assertRaises(ValueError): case.full_union(b,s)

    def test_shape_drift(self):
        b,s = self.union_fixture();s['metrics']['cond']['scope0']['checksum']='2'
        with self.assertRaises(ValueError): case.full_union(b,s)


if __name__ == '__main__': unittest.main()
