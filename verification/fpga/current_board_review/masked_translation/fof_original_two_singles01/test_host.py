"""Independent byte-oracle boundary tests, including allowed FOF outputs."""
import unittest
from pathlib import Path
import json
import observer as o

class Host(unittest.TestCase):
    def test_both_actual_elf_models(self):
        for sew in (8,64):
            s=json.loads((Path(__file__).parent/'software01'/f'e{sew}'/'spike.symbols.json').read_text())
            for phase in (0,1):
                m=o.expected(s,sew,phase)
                if phase:
                    for i,b in enumerate((0x800).to_bytes(8,'little')):m[s['fx_records']+24+i]=b
                o.compare(m,s,sew,phase)
            if sew==8:
                # No initial-value restriction is smuggled into the shortened region.
                for values in ((0,0,0,0),(255,17,99,213)):
                    for i,v in zip(range(5,9),values):m[s['fx_out']+i]=v
                    o.compare(m,s,sew,1)
            mutations={'result0':s['fx_out']+sew//8,'guard0':s['fx_out'],
                       'guard9':s['fx_out']+9*(sew//8),'allocation_end':s['fx_out']+129*(sew//8),
                       'mask_physical_tail':s['fx_mask']+15,'source_word':s['fx_pages']+4096-4*(sew//8),
                       'other_memory':s['fx_pages']+8191,'protected_leaf':s['fx_pages']+16384+8,
                       'returned_VL_pack':s['fx_return'],'returned_vstart_pack':s['fx_return']+4,
                       'post_vstart':s['fx_post']+16,'trap_cause':s['fx_records'],
                       'trap_vtype':s['fx_records']+48,'outer_page_guard':s['fx_guard_hi']}
            if sew==64:mutations['wrong_repeated_byte_5b']=s['fx_out']+8+1
            for name,address in mutations.items():
                bad=dict(m);bad[address]^=1
                with self.subTest(sew=sew,name=name),self.assertRaises(ValueError):o.compare(bad,s,sew,1)
            bad=dict(m);del bad[s['fx_out']+129*(sew//8)]
            with self.subTest(sew=sew,name='missing_byte'),self.assertRaises(ValueError):o.compare(bad,s,sew,1)

if __name__=='__main__':unittest.main(verbosity=2)
