import unittest
import prove_vlsu_address_padding770 as p


class ProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.texts = {r: (p.ROOT / r).read_text() for r in p.SOURCES}

    def test_actual_frozen_closure(self):
        self.assertEqual(p.source_contract(self.texts)['PLEN'], 56)
        self.assertEqual(sum(map(len, p.names().values())), 51)

    def mutation(self, rel, old, new):
        texts = dict(self.texts)
        self.assertIn(old, texts[rel])
        texts[rel] = texts[rel].replace(old, new, 1)
        with self.assertRaises(ValueError): p.source_contract(texts)

    def test_128bit_arithmetic_writer(self):
        self.mutation('hardware/src/vlsu/addrgen.sv', 'vaddr        : axi_addrgen_q.addr', "vaddr        : 128'(axi_addrgen_q.addr) + (128'd1 << 90)")

    def test_signed_extension(self):
        self.mutation('hardware/src/vlsu/addrgen.sv', 'vaddr        : idx_final_vaddr_q', 'vaddr        : $signed(idx_final_vaddr_q)')

    def test_reset_change(self):
        self.mutation('hardware/deps/common_cells/src/fifo_v3.sv', "mem_q <= {FifoDepth{dtype'('0)}};", "mem_q <= '1;")

    def test_extra_producer(self):
        self.mutation('hardware/src/vlsu/vstu.sv', "b_meta_in               = '0;", "b_meta_in = '0; b_meta_in.vaddr = external_addr;")

    def test_hold_change(self):
        self.mutation('hardware/deps/common_cells/src/fifo_v3.sv', 'mem_n           = mem_q;', "mem_n = '1;")

    def test_missing_source(self):
        texts = dict(self.texts); texts.pop(next(iter(texts)))
        with self.assertRaises(ValueError): p.source_contract(texts)

    def test_existing_partial_overlap(self):
        scope = p.PREFIX + 'i_vstu.i_store_b_metadata'
        for sel in ('[127:64]', '[64]', ''):
            with self.assertRaises(ValueError):
                p.duplicates('INSTANCE: '+scope+'\nToggle mem_q[0].vaddr '+sel, p.names())
        p.duplicates('INSTANCE: '+scope+'\nToggle mem_q[0].vaddr [63:0]', p.names())

    def test_module_exclusion_rejected(self):
        with self.assertRaises(ValueError): p.duplicates('MODULE: fifo_v3', p.names())


if __name__ == '__main__': unittest.main()
