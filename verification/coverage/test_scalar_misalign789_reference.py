"""Actual sealed software reference negative checks, not DUT qualification."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from elftools.elf.elffile import ELFFile
import build_scalar_misalign789 as m

PRE=m.OUT/'scalar-misalign789-preflight-agent-20261008-02'
SEAL='01352b7d72be5c4605faa231ba78d4555ee26788edfedcebb66c326f480ab94f'

class ActualReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert m.sha(PRE/'preflight-manifest.json')==SEAL
        cls.pre=json.loads((PRE/'preflight-manifest.json').read_bytes());cls.symbols=cls.pre['symbols']
        all_commits=list(m.shared.parse_spike_commits(PRE/'spike.trace'))
        start=next(i for i,c in enumerate(all_commits) if c.pc==0x80000000)
        end=next(i for i,c in enumerate(all_commits) if (cls.symbols['tohost'],1) in c.memory_accesses)
        cls.commits=all_commits[start:end+1];cls.ledger=cls.pre['validation']['trap_ledger']
    def test_actual_reference(self):
        self.assertEqual(m.validate(self.commits,self.symbols,self.ledger),self.pre['validation'])
        self.assertEqual(m.traps((PRE/'spike.trace').read_text(),self.symbols),self.ledger)
    def mutate_store(self,symbol,value):
        out=[];target=self.symbols[symbol]
        for c in self.commits:
            if any(a==target and v is not None for a,v in c.memory_accesses):
                accesses=tuple((a,value if a==target and v is not None else v) for a,v in c.memory_accesses)
                c=SimpleNamespace(**dict(vars(c),memory_accesses=accesses))
            out.append(c)
        return out
    def test_wrong_fault_destination(self):
        with self.assertRaises(ValueError):m.validate(self.mutate_store('mis_dest',0),self.symbols,self.ledger)
    def test_fault_store_side_effect(self):
        with self.assertRaises(ValueError):m.validate(self.mutate_store('mis_page',0),self.symbols,self.ledger)
    def test_wrong_trap_frame(self):
        with self.assertRaises(ValueError):m.validate(self.mutate_store('mis_records',13),self.symbols,self.ledger)
    def test_wrong_signature(self):
        with self.assertRaises(ValueError):m.validate(self.mutate_store('g75_result',55),self.symbols,self.ledger)
    def test_fault_memory_access_rejected(self):
        c=self.commits[0]
        altered=SimpleNamespace(**dict(vars(c),memory_accesses=((m.ADDRESSES[0],1),)))
        with self.assertRaises(ValueError):m.validate([altered,*self.commits[1:]],self.symbols,self.ledger)
    def test_exact_uncompressed_fault_opcodes(self):
        with (PRE/'input.elf').open('rb') as stream:
            elf=ELFFile(stream)
            for name,opcode in (('mis_ld_pc',3),('mis_sd_pc',0x23)):
                pc=self.symbols[name];segments=[s for s in elf.iter_segments() if s['p_type']=='PT_LOAD' and s['p_vaddr']<=pc and pc+4<=s['p_vaddr']+s['p_filesz']]
                self.assertEqual(len(segments),1);s=segments[0];word=int.from_bytes(s.data()[pc-s['p_vaddr']:pc-s['p_vaddr']+4],'little')
                self.assertEqual(word&127,opcode);self.assertEqual(word>>12&7,3)
                self.assertEqual(word&3,3)
    def test_complete_bound_serializer(self):
        target=json.loads((PRE/'target-before.json').read_bytes())
        self.assertEqual(len(target['fields']),5)
        for field in target['fields']:
            for position,bit,pair in field['logical_bit_pairs']:
                self.assertEqual(position,field['serialized_field_offset']+2*(63-bit)+pair)
                self.assertIn(pair,(0,1));self.assertTrue(0<=bit<64)
if __name__=='__main__':unittest.main()
