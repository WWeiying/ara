"""Exact terminal trace RVC regression; no VCS, bitmap collection, or admission."""
import csv
import hashlib
import unittest

import qualify_gap105_native_v5 as q
import test_qualify_gap105_native_v4 as previous
import test_qualify_gap105_native as legacy


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


class Readback(unittest.TestCase):
    def setUp(self):
        legacy.Readback.setUp(self)
        for row in self.rows: row['pc'] = '80000300'

    def check(self): return q.readback(self.rows,0,20,self.symbols,self.expected)

    def test_all_regions_complete_with_new_decoder(self):
        self.assertEqual(sum(self.check().values()),24096//2)

    def test_fldsp_read_checked_in_every_protected_region(self):
        for name,blob in self.expected.items():
            row = next(r for r in self.rows if int(r['mem_addr'],16)==self.symbols[name][0])
            original = dict(row)
            row.update(insn='3406',rd='8')
            self.check()
            row['rd_wdata'] = hex(int(row['rd_wdata'],16)^1)
            with self.assertRaisesRegex(ValueError,'Readback differs'): self.check()
            row.update(original)

    def test_fp_zero_register_observed_not_skipped(self):
        self.rows[0].update(insn='2002',rd='0')
        self.check()
        self.rows[0]['rd_wdata'] = hex(int(self.rows[0]['rd_wdata'],16)^1)
        with self.assertRaisesRegex(ValueError,'Readback differs'): self.check()

    def test_fp_read_mask_and_destination_rejected(self):
        self.rows[0].update(insn='3406',rd='8',mem_rmask='f')
        with self.assertRaisesRegex(ValueError,'address/mask'): self.check()
        self.rows[0].update(mem_rmask='ff',rd='9')
        with self.assertRaisesRegex(ValueError,'unobservable'): self.check()

    def test_unknown_outside_region_read_still_rejected(self):
        self.rows.append(dict(self.rows[0],mem_addr='bffffd90',insn='0001'))
        with self.assertRaisesRegex(ValueError,'Unknown scalar read encoding'): self.check()

    def test_missing_fp_byte_observation_still_rejected(self):
        self.rows = self.rows[1:]
        with self.assertRaisesRegex(ValueError,'Incomplete'): self.check()


class ActualTrace(unittest.TestCase):
    def test_frozen_terminal_csv_all_memory_reads_decode_no_skips(self):
        path = q.life.OUT/'gap105-m8-phase8-old-image-parent-20261006-01/commit_trace.csv'
        raw = path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         '49d62d541d962d41e4c204e6bd2ad1055247470887f2e1446414f539f0a84bdc')
        unknown_before = []
        for row in csv.DictReader(raw.decode().splitlines()):
            if row['event']!='retire' or int(row['cycle'])<18127 or not int(row['mem_rmask'],16): continue
            word = int(row['insn'],16)
            access = q.scalar_access(word)
            self.assertIsNotNone(access)
            kind,size = access
            self.assertEqual(kind,'read')
            address = int(row['mem_addr'],16)
            self.assertEqual(address%size,0)
            self.assertEqual(int(row['mem_rmask'],16),((1<<size)-1)<<(address&7))
            if legacy.q.scalar_access(word) is None: unknown_before.append(row)
        self.assertEqual(len(unknown_before),8)
        self.assertEqual({(int(r['pc'],16),int(r['insn'],16),int(r['mem_addr'],16)) for r in unknown_before},
                         {(0x80000e10,0x3406,0xbffffd90),(0x80000e12,0x24e6,0xbffffd88)})
        for row in unknown_before:
            floating,rd = q.load_destination(int(row['insn'],16))
            self.assertTrue(floating); self.assertEqual(rd,int(row['rd']))


def load_tests(loader,tests,pattern):
    suite = unittest.TestSuite()
    for case in (legacy.Native,legacy.Readback,legacy.Writebacks,legacy.Software,CSVIntegration,
                 previous.WindowIdentity,Readback,ActualTrace):
        suite.addTests(loader.loadTestsFromTestCase(case))
    return suite


if __name__=='__main__': unittest.main()
