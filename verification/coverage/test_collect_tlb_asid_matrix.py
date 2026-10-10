import copy
import unittest
from unittest.mock import patch
import collect_tlb_asid_matrix as c


class Collector(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.q=c.life.read_bound(c.PRE/'preflight.json',c.PRE_SEAL)
        cls.ref=c.pre.build.parse_spike_commits(c.PRE/'spike.trace')
        cls.rows=[]
        for i,item in enumerate(cls.ref):
            addr,read,write,data=0,0,0,0
            if item.memory_accesses:
                addr,value=item.memory_accesses[0];access=c.scalar_memory(item.instruction)
                if access:
                    kind,size=access;mask=((1 << size)-1) << (addr&7)
                    read=mask if kind == 'read' else 0;write=mask if kind == 'write' else 0
                    data=value or 0
            gpr=list(item.gpr_writes.items())
            rd,value=gpr[0] if gpr else (0,0)
            cls.rows.append(dict(event='retire',order=str(i),pc=hex(item.pc),insn=hex(item.instruction),
                trap='0',mem_addr=hex(addr),mem_rmask=hex(read),mem_wmask=hex(write),mem_wdata=hex(data),
                rd=str(rd),rd_wdata=hex(value)))

    def test_actual_spike_to_native_encoding_full_positive(self):
        self.assertEqual(c.pre.validate(c.native_reference(self.rows),self.q['symbols']),self.q['counts'])

    def mutate_reject(self,change):
        rows=copy.deepcopy(self.rows);change(rows)
        with self.assertRaises(ValueError):c.pre.validate(c.native_reference(rows),self.q['symbols'])

    def test_missing_compressed_load_mask(self):
        self.mutate_reject(lambda rows:next(r for r in rows if int(r['pc'],16)==self.q['symbols']['tam_first_load']).update(mem_rmask='0'))

    def test_wrong_load_value(self):
        self.mutate_reject(lambda rows:next(r for r in rows if int(r['pc'],16)==self.q['symbols']['tam_first_load']).update(rd_wdata='0'))

    def test_unknown_load_value(self):
        self.mutate_reject(lambda rows:next(r for r in rows if int(r['pc'],16)==self.q['symbols']['tam_first_load']).update(rd_wdata='xxxxxxxxxxxxxxxx'))

    def test_wrong_vpn_address(self):
        self.mutate_reject(lambda rows:next(r for r in rows if int(r['pc'],16)==self.q['symbols']['tam_first_load']).update(mem_addr='0x80000008'))

    def test_missing_retire(self):
        self.mutate_reject(lambda rows:rows.pop(30))

    def test_unshifted_store(self):
        r=dict(event='retire',order='0',pc='0x80000000',insn='0x2023',trap='0',mem_addr='0x80000004',
               mem_rmask='0',mem_wmask='0xf0',mem_wdata='0x6b',rd='0',rd_wdata='0')
        self.assertEqual(c.native_reference([r])[0].memory_accesses,((0x80000004,0x6b),))

    def test_bad_store_mask(self):
        self.mutate_reject(lambda rows:next(r for r in rows if int(r['mem_wmask'],16)).update(mem_wmask='1'))

    def test_trap_rejected(self):
        self.mutate_reject(lambda rows:rows[0].update(trap='1'))

    def test_console_protocol_error(self):
        text='Core Test *** SUCCESS ***\n[ARA_CONTRACT] requests=0 responses=0 exceptions=0 protocol_errors=1 outstanding=0\n'
        with self.assertRaises(ValueError):c.console_gate(text)

    def test_duplicate_population_rejected(self):
        before=dict(tests=['same']*768)
        with self.assertRaises(ValueError):c.full_union(before,dict(tests=[str(c.RUN/'code.vdb')]))

    def test_admit_unqualified_rejected(self):
        with patch.object(c.life,'read_bound',return_value=dict(status='FAILED')):
            with self.assertRaises(ValueError):c.admit(c.Path('/q'),'seal',c.Path('/nonexistent-asid-769'))


if __name__ == '__main__':unittest.main()
