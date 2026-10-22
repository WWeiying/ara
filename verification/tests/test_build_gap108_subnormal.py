import copy
import struct
import unittest
import build_gap108_subnormal as b
import audit_gap108_subnormal as a


class Numeric(unittest.TestCase):
    def test_exact_separate_rounding_contract(self):
        for phase in (0,1):
            row=b.oracle_expected(phase);b.oracle_check(row,phase)
            self.assertEqual(row['bits'],(0x100,0x200)[phase])
            self.assertEqual(row['flags'],(0,3)[phase])
            self.assertEqual(row['csr_flags'],(8,11)[phase])

    def test_whole_expression_fusion_gold_rejected(self):
        row=b.oracle_expected(1);row['bits']=0x180
        with self.assertRaises(ValueError):b.oracle_check(row,1)

    def test_exact_tiny_must_not_raise_underflow(self):
        row=b.oracle_expected(0);row['flags']=3;row['csr_flags']=11
        with self.assertRaises(ValueError):b.oracle_check(row,0)

    def test_rounding_flags_must_not_be_lost(self):
        for key,value in [('flags',0),('csr_flags',8),('stage_flags',[0]*6)]:
            row=b.oracle_expected(1);row[key]=value
            with self.assertRaises(ValueError):b.oracle_check(row,1)

    def test_native_sizes_bytes_and_individual_bsums(self):
        for phase in (0,1):
            w,act=b.fixtures(phase)
            self.assertEqual((len(w),len(act)),(176,292))
            self.assertEqual(struct.unpack('<HH',w[:4]),((0x3c00,0x3800)[phase],0))
            self.assertEqual(w[16:48],bytes(32));self.assertEqual(w[48:],bytes([0x11])*128)
            self.assertEqual(struct.unpack('<I',act[:4])[0],(1,3)[phase])
            self.assertEqual(act[4:260],bytes([1])*256)
            self.assertEqual(struct.unpack('<16h',act[260:]),(16,)*16)

    def test_unreviewed_phase_rejected(self):
        for phase in (True,2,-1,'1'):
            with self.assertRaises(ValueError):b.fixtures(phase)

    def trace(self):
        syms=dict(probe_ledger=0x80001000,tohost=0x80002000)
        values=[]
        for phase in (0,1):
            row=b.oracle_expected(phase)
            for bits,flags in zip(row['stage_bits'],row['stage_flags']):values.extend((bits,flags))
            values.extend((row['csr_flags'],2))
        text='\n'.join('mem 0x%x 0x%x'%(syms['probe_ledger']+8*i,v) for i,v in enumerate(values))
        return text+'\nmem 0x80002000 0x1\n',syms

    def test_standard_spike_scope_not_custom(self):
        record=b.spike_check(*self.trace())
        self.assertFalse(record['custom_isa_pass'])
        self.assertFalse(record['qbs_app_spike_executed'])
        self.assertEqual(record['stage_operations'],12)

    def test_spike_missing_changed_duplicate_or_trapped_rejected(self):
        trace,symbols=self.trace()
        for broken in (trace.replace('mem 0x80001000 0x43800000','mem 0x80001000 0x1'),
                       trace.replace('mem 0x80001000 0x43800000',''),
                       trace+'mem 0x80001000 0x43800000\n',
                       trace+'exception trap_illegal_instruction\n'):
            with self.assertRaises(ValueError):b.spike_check(broken,symbols)


class Instructions(unittest.TestCase):
    def fixture(self):
        csrs=(0xc20,0xc21,0x008,0x002,0x001,0x00f)
        def read(csr):return csr<<20|2<<12|5<<7|0x73
        def sd(off):return (off>>5)<<25|5<<20|14<<15|3<<12|(off&31)<<7|0x23
        words=[0x10000293,0x0132f057]
        words += [0x02006007|(reg<<7)|(12<<15) for reg in (0,8,16,24)]
        words += [0x4285,0x0102f057]
        words += [(csr<<20)|(imm<<15)|(5<<12)|0x73 for csr,imm in ((8,0),(2,2),(1,8),(15,5))]
        words += [v for i,csr in enumerate(csrs) for v in (read(csr),sd(8*i))]
        words += [0x0330000f,0x00b5045b]
        words += [v for i,csr in enumerate(csrs) for v in (read(csr),sd(48+8*i))]
        words += [0x10000293,0x0132f057]
        words += [0x02006027|(reg<<7)|(13<<15) for reg in (0,8,16,24)]
        offsets=[];pc=0x80000000
        for word in words:offsets.append(pc);pc+=4 if word&3==3 else 2
        return words,offsets,offsets[words.index(0x00b5045b)]

    def test_complete_csr_seed_snapshot_execution(self):
        a.audit_execution(*self.fixture())

    def test_wrong_opcode_rejected(self):
        words,offsets,pc=self.fixture();words[offsets.index(pc)]^=0x100
        with self.assertRaises(ValueError):a.audit_execution(words,offsets,pc)

    def test_flags_read_after_snapshot_rejected(self):
        words,offsets,pc=self.fixture();index=offsets.index(pc)+9
        words[index]=0x0132f057
        with self.assertRaises(ValueError):a.audit_execution(words,offsets,pc)

    def test_wrong_seed_or_snapshot_register_rejected(self):
        for opcode in (0x07,0x27):
            words,offsets,pc=self.fixture()
            index=next(i for i,w in enumerate(words) if w&0x7f==opcode and (w>>12)&7==6)
            words[index]|=1<<7
            with self.assertRaises(ValueError):a.audit_execution(words,offsets,pc)

    def test_masked_load_rejected(self):
        words,offsets,pc=self.fixture()
        index=next(i for i,w in enumerate(words) if w&0x7f==7 and (w>>12)&7==6)
        words[index]&=~(1<<25)
        with self.assertRaises(ValueError):a.audit_execution(words,offsets,pc)

    def test_wrong_fflags_seed_rejected(self):
        words,offsets,pc=self.fixture();words[words.index(0x00145073)]^=1<<15
        with self.assertRaises(ValueError):a.audit_execution(words,offsets,pc)


if __name__=='__main__':unittest.main()

