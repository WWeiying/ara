import copy
import csv
import json
import unittest
import check_operand_index_snapshot_offline_v2 as m


class ActualTrace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = m.life.read_bound(m.RUN/'manifest.json',m.RUN_SEAL)
        cls.symbols = cls.manifest['preflight']['symbols']
        with (m.RUN/'commit_trace.csv').open() as stream:
            cls.rows = list(csv.DictReader(stream))
        cls.commits = m.old.software.s.parse_spike_commits(m.old.PRE/'spike.trace')

    def check_changed(self,opcode,field,value):
        changed = copy.deepcopy(self.rows)
        row = next(r for r in changed if r['event'] == 'retire' and int(r['insn'],16) == opcode)
        row[field] = value(row) if callable(value) else value
        with self.assertRaises(ValueError):
            m.compressed_memory(changed,self.commits,self.symbols)

    def test_real_complete_compressed_memory_and_signature(self):
        result,normalized = m.compressed_memory(self.rows,self.commits,self.symbols)
        self.assertEqual((result['compressed_loads'],result['compressed_stores']),(324,321))
        self.assertEqual(result['matched_retirements'],7395)
        self.assertEqual(result['skipped_memory_events'],0)
        self.assertEqual(m.old.signature(normalized,self.symbols)['checks'],457)
        first = result['records'][0]
        self.assertEqual((first['pc'],first['instruction'],first['decode']['mnemonic']),
                         ('0x80002002','0xe422','C.SDSP'))
        self.assertEqual(self.rows[0]['insn'],normalized[0]['insn'])
        original = next(r for r in self.rows if r['event'] == 'retire' and r['insn'] == '0000e422')
        self.assertEqual(original['insn'],'0000e422')

    def test_store_address_mask_data_rejected(self):
        for field,value in (('mem_addr',lambda r:hex(int(r['mem_addr'],16)+4)),
                            ('mem_wmask','ff'),('mem_rmask','01'),
                            ('mem_wdata',lambda r:hex(int(r['mem_wdata'],16)^1))):
            self.check_changed(0xc190,field,value)
        self.check_changed(0xe422,'mem_wdata','1')

    def test_load_address_mask_rd_sign_data_rejected(self):
        for field,value in (('mem_addr',lambda r:hex(int(r['mem_addr'],16)+4)),
                            ('mem_rmask','ff'),('mem_wmask','01'),('rd','14'),
                            ('rd_wdata',lambda r:hex(int(r['rd_wdata'],16)^0xffffffff00000000))):
            self.check_changed(0x419c,field,value)

    def test_pc_opcode_trap_and_partial_alignment_rejected(self):
        for field,value in (('pc','80002000'),('insn','c191'),('trap','1')):
            self.check_changed(0xc190,field,value)
        with self.assertRaises(ValueError):
            m.compressed_memory(self.rows[1:],self.commits,self.symbols)

    def test_unknown_compressed_memory_is_not_skipped(self):
        changed = copy.deepcopy(self.rows)
        index = next(i for i,c in enumerate(self.commits) if c.pc == 0x80002002)
        commits = list(self.commits)
        from dataclasses import replace
        commits[index] = replace(commits[index],instruction=0x2000)
        row = next(r for r in changed if r['event'] == 'retire' and r['pc'] == '0000000080002002')
        row['insn'] = '2000'
        with self.assertRaisesRegex(ValueError,'Unsupported compressed memory'):
            m.compressed_memory(changed,commits,self.symbols)


if __name__ == '__main__':
    unittest.main()
