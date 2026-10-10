from pathlib import Path
import tempfile
import unittest

import analyze_qbs_k2_pending782 as analysis

VCD=analysis.life.OUT/'qbs-k2-row-pending-cycle782-agent-20261008-01/pending.vcd'


class CycleTests(unittest.TestCase):
    def test_actual_pending_owner_and_byte(self):
        r=analysis.cycles(VCD)
        p,q=r['producer_to_pending'][:2]
        self.assertEqual(p['slot1_owner']['offset'],28)
        self.assertEqual(p['remaining']>>16,0xff00)
        self.assertEqual(q['pending_strb'],0xff00)
        self.assertEqual(q['slot0_selected_word'],1)
        self.assertEqual(q['hit'],8192)

    def test_wrong_pending_mask_reject(self):
        text=VCD.read_text()
        start=text.index('#20325000\n');end=text.index('#20335000\n',start)
        block=text[start:end];marker='#20325000\n'
        self.assertEqual(block.count(marker),1)
        # strb already held ff00, so the actual VCD omits an unchanged assignment.
        self.assertNotIn(' y/\n',block)
        block=block.replace(marker,marker+'b1111111000000000 y/\n')
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'mutation.vcd';p.write_text(text[:start]+block+text[end:])
            with self.assertRaises(ValueError):analysis.cycles(p)

    def test_missing_native_identity_reject(self):
        text=VCD.read_text();old='activation_pending_q $end'
        self.assertEqual(text.count(old),1)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'mutation.vcd';p.write_text(text.replace(old,'other_pending_q $end'))
            with self.assertRaises(ValueError):analysis.cycles(p)


if __name__=='__main__':unittest.main()
