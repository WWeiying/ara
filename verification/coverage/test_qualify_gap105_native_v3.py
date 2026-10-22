"""Acceptance retirement is not seed-load completion; actual parser regressions."""
import csv
import unittest

import qualify_gap105_native_v3 as q
import test_qualify_gap105_native_v2 as previous


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

    def accepted_before_done(self):
        seeds = {0,1,2,3,9,10,11,12}
        for row in self.commit:
            if row['event'] in ('uop_alloc','uop_done'):
                seq = int(row['order']); row['port'] = str(seq%8)
                if row['event']=='uop_done' and seq in seeds:
                    row['cycle'] = str(seq*1000+60)
        for row in self.vector:
            if row['event']=='config': continue
            seq = int(row['arch_seq']); row['vid'] = str(seq%8)
            if seq in seeds:
                if row['event']=='done': row['cycle'] = str(seq*1000+60)
                elif row['event']=='write': row['cycle'] = str(seq*1000+50)

    def change_done(self,seq,cycle):
        for row in self.commit:
            if row['event']=='uop_done' and int(row['order'])==seq: row['cycle'] = str(cycle)
        for row in self.vector:
            if row['event']=='done' and int(row['arch_seq'])==seq: row['cycle'] = str(cycle)

    def test_load_retire_and_response_before_complete_writeback_valid(self):
        self.accepted_before_done()
        result = self.execute()
        self.assertEqual(result['custom_write_bytes'],64)
        self.assertTrue(all(w['retire']<w['done'] for b in result['bindings'] for w in b['seed_windows']))
        self.assertTrue(all(w['done']<b['custom_alloc'] for b in result['bindings'] for w in b['seed_windows']))

    def test_seed_done_crossing_custom_consumer_rejected(self):
        self.accepted_before_done(); self.change_done(3,4013)
        with self.assertRaisesRegex(ValueError,'Seed completion crosses custom consumer'):
            self.execute()

    def test_seed_write_after_done_rejected(self):
        self.accepted_before_done()
        row = next(r for r in self.vector if r['event']=='write' and r['arch_seq']=='0')
        row['cycle'] = '61'
        with self.assertRaisesRegex(ValueError,'outside lifecycle'): self.execute()

    def test_custom_done_after_response_still_rejected(self):
        self.change_done(4,4016)
        with self.assertRaisesRegex(ValueError,'Custom completion after terminal response'): self.execute()

    def test_store_done_after_response_still_rejected(self):
        self.change_done(5,5016)
        with self.assertRaisesRegex(ValueError,'Store completion after terminal response'): self.execute()

    def test_custom_done_after_retire_still_rejected(self):
        self.change_done(4,4017)
        with self.assertRaisesRegex(ValueError,'Custom/store completion after retirement'): self.execute()


def load_tests(loader,tests,pattern):
    suite = unittest.TestSuite()
    for case in (previous.frozen.Native,previous.frozen.Readback,previous.frozen.Writebacks,
                 previous.frozen.Software,CSVIntegration):
        suite.addTests(loader.loadTestsFromTestCase(case))
    return suite


if __name__=='__main__': unittest.main()
