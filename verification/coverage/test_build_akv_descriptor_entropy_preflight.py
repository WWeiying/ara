import unittest
from pathlib import Path
import tempfile
import build_akv_descriptor_entropy_preflight as p


class TestEntropy(unittest.TestCase):
    def test_high_stride_only_zero_index(self):
        self.assertEqual(p.ranges([0x80004000,0x80005000,0x80006000],128),
                         p.ranges([0x80004000,0x80005000,0x80006000],0xfffffffe))

    def test_v2_high_stride_rejected(self):
        with self.assertRaises(ValueError): p.ranges([128,256,384],0xfffffffe,v2=True)

    def test_later_index_rejected(self):
        for changes in ({'rows':2},{'tokens':2},{'tile':1},{'head':128}):
            with self.assertRaises(ValueError): p.ranges([128,256,384],0xfffffffe,**changes)

    def test_bad_stride(self):
        for stride in (127,129,0x100000000,True):
            with self.assertRaises(ValueError): p.ranges([128,256,384],stride)

    def test_bad_base(self):
        for base in (129,-2,0xfffffffffffffffe):
            with self.assertRaises(ValueError): p.ranges([base,256,384],128)

    def test_exact_descriptor(self):
        d=p.descriptor([128,256,384],0xfffffffe)
        self.assertEqual(len(d),64); self.assertEqual(d[:8],bytes([1,1,1,0,64,0,1,0]))
        self.assertEqual(d[8:20],bytes.fromhex('feffffff')*3)
        self.assertEqual(d[48:],bytes(16))

    def test_all_frames_and_inactive_registers(self):
        for phase in range(6):
            self.assertEqual(len(p.frame(phase)),4224)
            self.assertEqual(p.frame(phase)[64:64+8*128],p.frame(0)[64:64+8*128])
        self.assertNotEqual(p.frame(4)[64+8*128:64+9*128],p.frame(0)[64+8*128:64+9*128])

    def test_no_v2_full(self):
        self.assertEqual([w>>12&7 for w in p.WORDS],[5,2,2,2,3,5])
        self.assertEqual(p.WORDS[1:4],[0x00b5205b]*3)

    def test_target_el_overlap_rejected(self):
        blob=('CHECKSUM: "1 2"\nINSTANCE: '+p.SCOPE+'\nToggle descriptor_q "reg descriptor_q[511:0]"\n').encode()
        with self.assertRaises(ValueError): p.assert_unexcluded(blob)

    def test_observer_ancestor_rejected(self):
        blob=b'CHECKSUM: "1"\nINSTANCE: ara_tb.dut.i_ara_soc.i_system\n'
        with self.assertRaises(ValueError): p.assert_unexcluded(blob)

    def test_other_target_retained(self):
        blob=('CHECKSUM: "1 2"\nINSTANCE: '+p.SCOPE+'\nToggle unrelated "reg unrelated[7:0]"\n').encode()
        p.assert_unexcluded(blob)

    def native_toggle(self, name):
        return ('CHECKSUM: "1 2"\nINSTANCE: '+p.SCOPE+'\nToggle '+name+' "logic '+name+'"\n').encode()

    def test_actual_descriptor_parent_rejected(self):
        p.assert_unexcluded(self.native_toggle('descriptor.flags'))
        with self.assertRaises(ValueError):
            p.assert_unexcluded(self.native_toggle('descriptor'))

    def test_sibling_member_not_name_prefix(self):
        for name in ('descriptor.reserved10', 'descriptor_q_extra', 'descriptor_extra.reserved0'):
            p.assert_unexcluded(self.native_toggle(name))
        with self.assertRaises(ValueError):
            p.assert_unexcluded(self.native_toggle('descriptor.reserved0[7:0]'))

    def test_array_element_ownership_not_generic_prefix(self):
        targets = {'entries[0].reserved0'}
        for name in ('entries[1]', 'entries[0].flags', 'entries_extra[0]'):
            p.assert_unexcluded(self.native_toggle(name), targets)
        for name in ('entries', 'entries[0]', 'entries[0].reserved0', 'entries[0].reserved0[0]'):
            with self.assertRaises(ValueError):
                p.assert_unexcluded(self.native_toggle(name), targets)

    def test_all_actual_parser_owners_pinned(self):
        owners = {x.name for x in p.parser_dependencies()}
        self.assertTrue({'build_akv_column_boundary_preflight.py', 'rank_cva6_scalar_data767.py',
                         'branch720_next_report_contract.py', 'targeted_toggle_evidence.py',
                         'spike_trace.py', 'build_gap95_preflight.py'} <= owners)

    def test_dependency_drift_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'parser.py'
            path.write_text('original')
            pins = {str(path): p.sha(path)}
            p.shared.check(pins)
            path.write_text('changed')
            with self.assertRaises(ValueError):
                p.shared.check(pins)

    def test_native_unknown_opcode_rejected(self):
        with self.assertRaises((ValueError, p.struct.error)):
            p.native_sites(bytes(64),{})


if __name__ == '__main__': unittest.main()
