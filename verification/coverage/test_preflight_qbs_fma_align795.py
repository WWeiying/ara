import json
import unittest
import preflight_qbs_fma_align795 as p


def host_lines():
    lines = []
    gold = p.block_gold()
    for phase in range(2):
        for r in sorted(gold, key=lambda r:(r['phase'],r['block'],r['row'])):
            if r['phase'] == phase:
                lines.append('B {phase} {row} {block} {dot} 0 {before:08x} {after:08x}'.format(**r))
        lines.append('F %d 3 2' % phase)
        lines += ['Q %d %d %08x' % (phase,i,(0x410e3000,0xc10e3000)[i] if i < 2 else 0) for i in range(32)]
    return '\n'.join(lines)+'\n'


class FixtureTests(unittest.TestCase):
    def test_packed_two_block_shapes_and_reverse_order(self):
        for phase in range(2):
            w,a = p.blocks(phase)
            self.assertEqual([len(b) for b in w], [144]*4)
            self.assertEqual([len(b) for b in a], [292]*2)
            self.assertEqual(len(p.payload(phase)),1280)
            self.assertEqual(p.payload(phase)[16:160],w[0])
            self.assertEqual(p.payload(phase)[592:884],a[0])
        self.assertEqual(p.blocks(0)[0][0],p.blocks(1)[0][1])
        self.assertEqual(p.blocks(0)[1][0],p.blocks(1)[1][1])
        for phase in (-1,2,True):
            with self.assertRaises(ValueError):p.blocks(phase)

    def test_independent_group_quantized_dot(self):
        for phase in range(2):
            w,a = p.blocks(phase)
            for row in range(2):
                for k in range(2):
                    q = w[2*row+k][16:]
                    values = [(q[(i//64)*32+i%32]>>(4 if i%64>=32 else 0))&15 for i in range(256)]
                    acts = [b if b<128 else b-256 for b in a[k][4:260]]
                    self.assertEqual(sum(x*y for x,y in zip(values,acts)),8 if row==0 else -8)
                    self.assertEqual(a[k][260:],bytes(32))

    def test_host_complete_gold_and_negative_flags_tail_missing(self):
        good = host_lines();p.host_gate(good)
        for bad in (good.replace('F 0 3 2','F 0 1 2'),
                    good.replace('Q 1 31 00000000','Q 1 31 00000001'),
                    '\n'.join(good.splitlines()[:-1]),good+good.splitlines()[0]+'\n'):
            with self.assertRaises(ValueError):p.host_gate(bad)

    def test_compiled_scalar_isa_is_explicit(self):
        source = p.APP.read_text()
        self.assertIn('.option arch,+v', source)
        self.assertEqual(source.count('qf_native_site: .word 0x00b5045b'),1)
        self.assertIn('qf_result[0] != QF_CHECKS',source)

    def test_actual796_genealogy_and_missing_intersection(self):
        witness = json.loads(p.WITNESS.read_text())
        self.assertEqual(p.proof.gold.digest(p.WITNESS),p.WITNESS_SHA)
        binding = p.binding796(witness)
        self.assertEqual(binding['population'],796)
        self.assertLessEqual(binding['remaining_host_one_witness_positions'],10)
        self.assertFalse(binding['direction_order_inferred'])


if __name__ == '__main__':unittest.main()
