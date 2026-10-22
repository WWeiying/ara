"""Validate the static packet, not a DUT model or execution qualification."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
PACKET=ROOT/'verification/out/mask-compare-restart785-source-risk-agent-20261008-01.json'


class SourcePacketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packet=json.loads(PACKET.read_bytes())
        cls.text={Path(p['compiled_source']).name:(ROOT/p['evidence']).read_text()
            for p in cls.packet['source_pins']}

    def test_all_frozen_source_pins(self):
        p=self.packet;book=ROOT/p['build_source_book']
        self.assertEqual(hashlib.sha256(book.read_bytes()).hexdigest(),p['build_source_book_sha256'])
        contents=json.loads(book.read_bytes())
        for row in p['source_pins']:
            self.assertEqual(hashlib.sha256((ROOT/row['evidence']).read_bytes()).hexdigest(),row['sha256'])
            self.assertEqual(contents[str(ROOT/row['compiled_source'])],row['sha256'])
        self.assertEqual(len(p['source_pins']),9)
        self.assertEqual(hashlib.sha256((ROOT/p['admission_manifest']).read_bytes()).hexdigest(),p['admission_sha256'])

    def test_compare_is_not_zero_start_operation(self):
        d=self.text['ara_dispatcher.sv']
        guard=d.split('function automatic logic requires_zero_vstart',1)[1].split('endfunction',1)[0]
        self.assertNotIn('VMSLTU',guard)
        self.assertIn('ara_req.use_vd_op',d.split('ara_pkg::VMSLTU;',1)[1].split('end',1)[0])
        self.assertIn('vstart       : csr_vstart_q',d)

    def test_maskB_zero_override_excludes_compare(self):
        s=self.text['lane_sequencer.sv']
        normal=s.split("// Vd register to provide correct mask undisturbed policy",1)[1].split('VFU_None: begin',1)[0]
        self.assertIn("if (pe_req.op inside {[VMANDNOT:VMXNOR], [VMADC:VMSBC]})\n              operand_request[MaskB].vstart = '0;",normal)
        self.assertNotIn('VMSLTU',normal)
        self.assertRegex(normal,r'vstart\s*:\s*vfu_operation_d\.vstart')
        self.assertIn('operand_request[MaskB].eew = EW64;',normal)

    def test_compiled_enum_order_excludes_compare_from_reset_ranges(self):
        s=self.text['ara_pkg.sv']
        compare='VMSEQ, VMSNE, VMSLTU, VMSLT, VMSLEU, VMSLE, VMSGTU, VMSGT,'
        carry='VMADC, VMSBC,'
        logical='VMANDNOT, VMAND, VMOR, VMXOR, VMORNOT, VMNAND, VMNOR, VMXNOR,'
        self.assertIn(compare,s)
        self.assertIn(carry,s)
        self.assertIn(logical,s)
        self.assertLess(s.index(compare),s.index(carry))
        self.assertLess(s.index(carry),s.index(logical))
        self.assertNotIn('VMSLTU',carry+logical)

    def test_late_override_is_conditional_not_normalization(self):
        s=self.text['lane_sequencer.sv']
        tail=s.split('// Predication masks are packed bits',1)[1]
        before_ad_hoc=tail.split('// VRGATHER and VCOMPRESS access',1)[0]
        self.assertNotIn('operand_request[MaskB]',before_ad_hoc)
        self.assertIn('operand_request[MaskM].vstart = pe_req.vstart / (NrLanes * ELEN);',before_ad_hoc)
        self.assertIn('if (vrgat_state_q == REQUESTING && masku_vrgat_req_valid_q)',tail)
        self.assertIn('vstart     : masku_vrgat_req_q.idx',tail)
        self.assertIn('operand_request_d[queue]       = operand_request[queue];',s)

    def test_address_and_queue_arithmetic(self):
        r=self.text['operand_requester.sv'];p=self.packet['context']
        self.assertIn("? scaled_vector_len_elements\n                                   : operand_request_i[requester_index].vl",r)
        self.assertIn('operand_request_i[requester_index].vstart >>',r)
        stride=p['VLEN']//8//p['NrLanes']//8
        self.assertEqual(stride,4)
        for row in self.packet['conditional_expected_requests']:
            local=row['architectural_vstart']//4
            self.assertEqual(local,row['lane_vstart'])
            self.assertEqual(16*stride+(local>>3),row['AluA_word_address'])
            self.assertEqual(8*stride+(local>>3),row['AluB_word_address'])
            self.assertEqual(stride+local,row['MaskB_normal_branch_word_address'])
            self.assertEqual(stride,row['MaskB_reference_correct_word_address'])
            self.assertNotEqual(row['MaskB_normal_branch_word_address'],row['MaskB_reference_correct_word_address'])
            self.assertEqual(row['AluA_B_elem_count_each']//8,row['AluA_B_words_each'])
            self.assertEqual(row['MaskB_elem_count'],1)

    def test_reference_prestart_detects_wrong_word(self):
        old=0x69;different_word=0x96;compare=0xa35e1b970f42c681
        for start in (4,8,16):
            prefix=(1<<start)-1;active=((1<<64)-1)^prefix
            expected=(old&prefix)|(compare&active)
            wrong=(different_word&prefix)|(compare&active)
            self.assertEqual(expected&prefix,old&prefix)
            self.assertNotEqual(wrong&prefix,expected&prefix)

    def test_nonqualification_contract(self):
        self.assertFalse(self.packet['DUT_bug_confirmed'])
        self.assertFalse(self.packet['EDA_started'])
        self.assertFalse(self.packet['RTL_changed'])
        self.assertFalse(self.packet['coverage_admitted'])
        self.assertFalse(self.packet['context']['addresses_are_observed'])


if __name__=='__main__':unittest.main()
