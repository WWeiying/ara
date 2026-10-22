"""Finite transaction IDs are reusable after response, never concurrently."""
import copy
import csv
import unittest

import qualify_gap105_native_v4 as q
import test_qualify_gap105_native_v3 as previous


class CSVIntegration(previous.CSVIntegration):
    def execute(self):
        for row in self.vector:
            if row['wdata'].startswith('0x'):
                row['wdata'] = format(int(row['wdata'],16),'016x')
        self.commit.sort(key=lambda r:int(r['cycle']))
        self.vector.sort(key=lambda r:int(r['cycle']))
        for name,rows in [('commit_trace.csv',self.commit),('vector_trace.csv',self.vector)]:
            with (self.run/name).open('w') as stream:
                writer = csv.DictWriter(stream,fieldnames=list(rows[0]))
                writer.writeheader(); writer.writerows(rows)
        return q.runtime(self.run,self.symbols,self.data,self.sites,self.native)

    def reuse_id(self):
        for row in self.commit:
            if row['event'] in ('arch_start','cvx_req','cvx_resp'): row['trans_id'] = '0'

    def test_legal_finite_id_reuse_across_phases_with_early_load_retire(self):
        self.accepted_before_done(); self.reuse_id()
        result = self.execute()
        a,b = [r['custom_binding'] for r in result['bindings']]
        self.assertEqual(a['trans_id'],b['trans_id'])
        self.assertNotEqual(a['arch_seq'],b['arch_seq'])
        self.assertEqual([a['pc'],b['pc']],[0x8000017a,0x80000252])
        self.assertLess(a['retire'],b['arch_start'])
        self.assertEqual(result['custom_write_bytes'],64)

    def test_duplicate_response_same_activity_rejected(self):
        self.reuse_id()
        response = next(r for r in self.commit if r['event']=='cvx_resp' and r['cycle']=='4015')
        self.commit.insert(self.commit.index(response)+1,copy.deepcopy(response))
        with self.assertRaisesRegex(ValueError,'unknown transaction|Orphan'): self.execute()

    def test_concurrent_reuse_same_id_rejected(self):
        self.reuse_id()
        request = next(r for r in self.commit if r['event']=='cvx_req' and r['cycle']=='4011')
        duplicate = dict(request,cycle='4012')
        self.commit.insert(self.commit.index(request)+1,duplicate)
        with self.assertRaisesRegex(ValueError,'duplicate in-flight|Duplicate transaction'): self.execute()


class WindowIdentity(unittest.TestCase):
    def test_two_nonoverlapping_windows_same_id_accepted(self):
        claimed = set()
        a = q.bind_custom(17,0x8000017a,0,17609,18127,[(18125,18125)],claimed)
        b = q.bind_custom(40,0x80000252,0,61031,61549,[(61547,61547)],claimed)
        self.assertEqual(len(claimed),2)
        self.assertEqual(a['trans_id'],b['trans_id'])

    def test_two_responses_in_one_window_rejected(self):
        with self.assertRaisesRegex(ValueError,'one response'):
            q.bind_custom(17,0x8000017a,0,10,30,[(20,21),(22,23)],set())

    def test_same_response_cannot_bind_two_architectural_activities(self):
        claimed = set()
        q.bind_custom(17,0x8000017a,0,10,30,[(20,21)],claimed)
        with self.assertRaisesRegex(ValueError,'already claimed'):
            q.bind_custom(40,0x80000252,0,10,30,[(20,21)],claimed)

    def test_outside_start_retire_window_rejected(self):
        for interval in ([(9,20)],[(20,31)],[(25,24)]):
            with self.assertRaisesRegex(ValueError,'outside architecture'):
                q.bind_custom(17,0x8000017a,0,10,30,interval,set())


def load_tests(loader,tests,pattern):
    suite = unittest.TestSuite()
    fixture = previous.previous.frozen
    for case in (fixture.Native,fixture.Readback,fixture.Writebacks,fixture.Software,
                 CSVIntegration,WindowIdentity):
        suite.addTests(loader.loadTestsFromTestCase(case))
    return suite


if __name__=='__main__': unittest.main()
