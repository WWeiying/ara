import os
from dataclasses import replace
from pathlib import Path
import unittest
import build_scalar_slot_rotation792 as b


class SlotGold(unittest.TestCase):
    def test_complement(self):
        self.assertEqual(b.A^b.B,(1<<64)-1)
        self.assertEqual([x&7 for x in b.ADDRESSES],[3,4,3]*4)

    def test_slots(self):
        self.assertEqual(b.SLOTS,[2]*3+[3]*3+[6]*3+[7]*3)

    def test_trap_mutations(self):
        s={'slot_fault'+str(i):0x80003000+128*i for i in range(12)}
        text='\n'.join('core 0: exception trap_%s_address_misaligned, epc 0x%x\ncore 0: tval 0x%x'%('store' if i%3==1 else 'load',s['slot_fault'+str(i)],b.ADDRESSES[i]) for i in range(12))
        self.assertEqual(len(b.traps(text,s)),12)
        for wrong in [text.replace('0x80003000','0x80003004',1),text.replace('0x2555555003','0x2555555004',1),text.replace('trap_load','trap_store',1),text+'\n'+text]:
            with self.assertRaises(ValueError): b.traps(wrong,s)

    @unittest.skipUnless(os.environ.get('SLOT_PREFLIGHT'),'Actual fixture requested')
    def test_actual_gold(self):
        import json
        p=Path(os.environ['SLOT_PREFLIGHT']); m=json.loads((p/'preflight-manifest.json').read_bytes())
        s=b.elf_shape(p/'input.elf'); cs=b.reference(p/'spike.trace',s); ledger=b.traps((p/'spike.trace').read_text(),s)
        self.assertEqual(b.validate(cs,s,ledger),m['validation'])
        # Corrupt a real architectural store, not a declaration-only fixture.
        import copy
        for symbol in ('slot_records','slot_page','slot_csr','g75_result'):
            bad=copy.deepcopy(cs)
            owners=[i for i,c in enumerate(bad) if any(a==s[symbol] and v is not None for a,v in c.memory_accesses)]
            self.assertTrue(owners)
            i=owners[-1]; c=bad[i]
            bad[i]=replace(c,memory_accesses=tuple(
                (a,v^1 if a==s[symbol] and v is not None else v)
                for a,v in c.memory_accesses))
            with self.assertRaises(ValueError): b.validate(bad,s,ledger)


if __name__=='__main__': unittest.main()
