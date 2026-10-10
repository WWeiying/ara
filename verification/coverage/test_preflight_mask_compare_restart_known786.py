import unittest
import preflight_mask_compare_restart_known786 as p


class KnownOldTests(unittest.TestCase):
    def test_gold_prestart_active(self):
        for start in p.STARTS:
            value=int.from_bytes(p.mask_gold(start),'little')
            old=int.from_bytes(p.old_bytes(0),'little')
            a,b=p.source_bytes(0),p.source_bytes(1)
            for i in range(64):
                self.assertEqual(value>>i&1,old>>i&1 if i<start else int(a[i]<b[i]))

    def test_wrong_old_word_discriminates(self):
        seed=p.old_bytes(0)
        for start in p.STARTS:
            mask=(1<<start)-1
            first=int.from_bytes(seed[:8],'little')&mask
            self.assertNotEqual(first,0)
            for offset in (8,16,32):
                self.assertNotEqual(first,int.from_bytes(seed[offset:offset+8],'little')&mask)
            self.assertNotEqual(first,int.from_bytes(p.old_bytes(1)[:8],'little')&mask)

    def test_full_seed_distinct(self):
        self.assertEqual(len(p.old_bytes(0)),128)
        self.assertNotEqual(p.old_bytes(0),p.old_bytes(1))
        self.assertEqual(len(set(p.old_bytes(0)[i:i+8] for i in range(0,128,8))),16)

    def test_invalid_case(self):
        for start in (0,1,65):
            with self.assertRaises(Exception): p.mask_gold(start)
        with self.assertRaises(Exception): p.old_bytes(2)

    def test_no_mask_tail_consumed(self):
        self.assertTrue(all(len(p.mask_gold(s))==8 for s in p.STARTS))
        self.assertIn('vsm.v v1',p.APP.read_text())
        self.assertIn('vs1r.v v2',p.APP.read_text())

    def test_linked_inventory(self):
        wanted=['vsetvli']*3+['vle8.v']*4+['vmv.v.i','vmsltu.vv','vsm.v','vxor.vv']+['vs1r.v']*4
        dis='\n'.join('80002000: 00000000 '+m for m in wanted)
        self.assertEqual(len(p.linked(dis)),15)
        with self.assertRaises(Exception): p.linked(dis+'\n80003000: 00000000 vmv.v.i')

    def test_original_app_preserved(self):
        self.assertEqual(p.life.digest(p.old.APP),'e96b5afb27b90114334f52a4de0c77acd4b258f3a87ed47e04324dcc7299d4ec')


if __name__=='__main__': unittest.main()
