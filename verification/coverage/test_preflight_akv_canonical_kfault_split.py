import unittest
import preflight_akv_canonical_kfault_split as p


class TestSplit(unittest.TestCase):
    def test_parent_seal(self):
        self.assertEqual(p.h.sha(p.PARENT),p.PARENT_SHA)

    def test_unchanged_full_oracle(self):
        import collect_akv_canonical_kfault as c
        for i in range(2):
            info = dict(symbols={'gap71_'+k[len('akvc%d_'%i):]:v for k,v in p.h.read(p.PARENT)['artifacts']['dut']['symbols'].items() if k.startswith('akvc%d_'%i)})
            self.assertEqual(len(c.owner_oracle(i)['final_memory']('gap71_akv_fault',info)),5680)

    def test_missing_trace(self):
        with self.assertRaises(Exception): p.validate('',{},0)

    def test_source_mutation(self):
        with self.assertRaises(Exception): p.p.replace_one('wrong main','int main(void)','changed')

    def test_boot_literal_mutation(self):
        symbols = dict(rvtest_init=0x80000104,akvc0_handler_entry=0x80000128)
        words = [0x00300293,0x00b29293,0x3002a073,0x00000297,0x01828293,0x30529073,0x00008067]
        p.boot_gate(symbols,lambda pc:words[(pc-symbols['rvtest_init'])//4],0)
        words[0] = 0x00100293
        with self.assertRaises(Exception): p.boot_gate(symbols,lambda pc:words[(pc-symbols['rvtest_init'])//4],0)


if __name__ == '__main__': unittest.main()
