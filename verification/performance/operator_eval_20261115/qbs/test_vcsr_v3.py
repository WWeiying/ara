import unittest
import check_vcsr_v2 as predecessor
import check_vcsr_v3 as exact
from test_vcsr_v2 import commit_fixture, check_commit


class ExactSaturation(unittest.TestCase):
    def test_independent_spike_match_mask(self):
        self.assertEqual(len(exact.verify_encoding()['exact_matches']),18)

    def test_saturating_forms_and_all_operand_fields(self):
        operands = (0, 31<<7, 31<<15, 31<<20, 1<<25,
                    (31<<7)|(31<<15)|(31<<20)|(1<<25))
        for name, match in exact.SATURATING.items():
            for fields in operands:
                with self.subTest(name=name, fields=fields):
                    self.assertTrue(exact.is_saturating(match|fields))

    def test_whole_register_moves_and_other_ops(self):
        for word in (0x9e003057,0x9e00b057,0x9e01b057,0x9e03b057,0x9e7032d7,
                     0x02000057,0xa0000057,0x90000057,0x57,0):
            with self.subTest(word=hex(word)):
                self.assertFalse(exact.is_saturating(word))
        self.assertTrue(predecessor.is_saturating(0x9e7032d7))

    def test_move_retirement_allowed_but_true_saturation_still_rejected(self):
        rows, build, result, proof = commit_fixture()
        original = predecessor.is_saturating
        predecessor.is_saturating = exact.is_saturating
        try:
            for word in (0x9e7032d7,0xbc003057):
                changed = [dict(r) for r in rows]
                changed.insert(13,dict(changed[12],pc='0000000000000300',
                                       insn=f'{word:08x}',rd=0,rd_wdata='0000000000000000'))
                for i,row in enumerate(changed):
                    row.update(cycle=i*3,order=i)
                evidence = (proof[0],dict(proof[1]),*proof[2:])
                evidence[1][0x300]=word
                if exact.is_saturating(word):
                    with self.assertRaisesRegex(ValueError,'saturating operation'):
                        check_commit(changed,build,result,evidence)
                else:
                    check_commit(changed,build,result,evidence)
        finally:
            predecessor.is_saturating = original


if __name__=='__main__':
    unittest.main()
