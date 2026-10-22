import csv
import json
import unittest

import qualify_akv_skew_group_readback as helper


class ActualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        proof = json.loads((helper.RUN/'oracle-result.json').read_text())
        cls.symbols = proof['elf_layout']['symbols']
        cls.cycles = [c['request_cycle'] for c in proof['protocol']['custom']]
        cls.ranges = [(cls.symbols[n]['value'],cls.symbols[n]['value']+len(blob))
                      for n,blob in helper.expected_regions(0,cls.symbols).items()]
        with (helper.RUN/'commit_trace.csv').open() as stream:
            cls.rows = [r for r in csv.DictReader(stream) if r['event']=='retire' and
                int(r['mem_rmask'],16) and any(lo <= int(r['mem_addr'],16) < hi for lo,hi in cls.ranges)]

    def changed(self, name, offset, value=None, **kwargs):
        rows = list(self.rows)
        address = self.symbols[name]['value']+offset
        i = next(i for i,r in enumerate(rows) if int(r['cycle']) >= self.cycles[1] and
                 int(r['mem_addr'],16) == address)
        rows[i] = dict(rows[i],**kwargs)
        if value is not None: rows[i]['rd_wdata'] = '%016x'%value
        return rows

    def test_actual12_complete_frames(self):
        p = helper.audit_readbacks(self.rows,self.symbols,self.cycles)
        self.assertEqual(p['destination_frame_bytes'],7680)
        self.assertEqual(p['total_independent_unique_phase_bytes'],36864)
        self.assertEqual(p['skipped_region_reads'],0)

    def test_active_corruption(self):
        with self.assertRaisesRegex(ValueError,'Independent bytes mismatch'):
            helper.audit_readbacks(self.changed('got',64,0),self.symbols,self.cycles)

    def test_tail_corruption(self):
        with self.assertRaisesRegex(ValueError,'Independent bytes mismatch'):
            helper.audit_readbacks(self.changed('got',64+128,0),self.symbols,self.cycles)

    def test_destination_guard_corruption(self):
        with self.assertRaisesRegex(ValueError,'Independent bytes mismatch'):
            helper.audit_readbacks(self.changed('got',0,0),self.symbols,self.cycles)

    def test_seed_guard_corruption(self):
        with self.assertRaisesRegex(ValueError,'Independent bytes mismatch'):
            helper.audit_readbacks(self.changed('initial',576,0),self.symbols,self.cycles)

    def test_external_guard_corruption(self):
        with self.assertRaisesRegex(ValueError,'Independent bytes mismatch'):
            helper.audit_readbacks(self.changed('source',0,0),self.symbols,self.cycles)

    def test_descriptor_corruption(self):
        with self.assertRaisesRegex(ValueError,'Independent bytes mismatch'):
            helper.audit_readbacks(self.changed('descriptor',0,0),self.symbols,self.cycles)

    def test_missing_guard_readback(self):
        a = self.symbols['got']['value']
        rows = [r for r in self.rows if not (int(r['cycle']) >= self.cycles[11] and int(r['mem_addr'],16) == a)]
        with self.assertRaisesRegex(ValueError,'Incomplete explicit readback'):
            helper.audit_readbacks(rows,self.symbols,self.cycles)

    def test_unobservable_load_rejected(self):
        with self.assertRaisesRegex(ValueError,'Unobservable/malformed'):
            helper.audit_readbacks(self.changed('got',64,rd='0'),self.symbols,self.cycles)

    def test_snapshot_not_live_poison(self):
        p = helper.expected_regions(1,self.symbols)
        self.assertEqual(int.from_bytes(p['got'][64:66],'little'),0x1100)
        self.assertEqual(int.from_bytes(p['source'][66:68],'little'),0x1100^0x5a5a)

    def test_epoch1_not_stale_epoch0(self):
        p = helper.expected_regions(8,self.symbols)
        self.assertEqual(int.from_bytes(p['got'][64:66],'little'),0x2100)

    def test_illegal_seed_preserved(self):
        for phase in (4,5,6):
            p = helper.expected_regions(phase,self.symbols)
            self.assertEqual(p['got'],p['initial'])


if __name__ == '__main__': unittest.main()
