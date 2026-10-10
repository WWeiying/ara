import copy
import struct
import unittest
import build_gap109_k2_sticky as b
import audit_gap109_k2_sticky as a


class Numeric(unittest.TestCase):
    def test_exact_separate_rounding_contract(self):
        for phase in (0,1):
            row=b.oracle_expected(phase);b.oracle_check(row,phase)
            self.assertEqual(row['bits'],(0x43800000,0x43800000)[phase])
            self.assertEqual(row['flags'],(0,1)[phase])
            self.assertEqual(row['csr_flags'],(8,9)[phase])

    def test_lost_continuation_result_rejected(self):
        row=b.oracle_expected(1);row['bits']=0x25800000
        with self.assertRaises(ValueError):b.oracle_check(row,1)

    def test_exact_control_must_not_raise_underflow(self):
        row=b.oracle_expected(0);row['flags']=3;row['csr_flags']=11
        with self.assertRaises(ValueError):b.oracle_check(row,0)

    def test_rounding_flags_must_not_be_lost(self):
        for key,value in [('flags',0),('csr_flags',8),('stage_flags',[0]*12)]:
            row=b.oracle_expected(1);row[key]=value
            with self.assertRaises(ValueError):b.oracle_check(row,1)

    def test_native_two_blocks_and_individual_bsums(self):
        for phase in (0,1):
            w,act=b.fixtures(phase)
            self.assertEqual((len(w),len(act)),(352,584))
            for block in (0,1):
                wb,ab=w[176*block:176*(block+1)],act[292*block:292*(block+1)]
                self.assertEqual(struct.unpack('<HH',wb[:4]),(0x3c00,0))
                self.assertEqual(wb[16:48],bytes(32))
                self.assertEqual(wb[48:],bytes([0x11])*128)
                self.assertEqual(struct.unpack('<I',ab[:4])[0],
                                 (0 if phase==0 else 0x21800000) if block==0 else 0x3f800000)
                self.assertEqual(ab[4:260],bytes([1])*256)
                self.assertEqual(struct.unpack('<16h',ab[260:]),(16,)*16)

    def test_flags_only_second_block_dot_fma(self):
        row=b.oracle_expected(1)
        self.assertEqual(row['stage_flags'],[0]*10+[1,0])
        self.assertEqual(row['stage_bits'][2],0x21800000)
        self.assertEqual(row['stage_bits'][4:6],[0x25800000]*2)
        self.assertEqual(row['stage_bits'][10:12],[0x43800000]*2)

    def test_k1_truncation_and_each_block_bsum_rejected(self):
        import gap109_oracle as oracle
        w,a=b.fixtures(1)
        with self.assertRaises(ValueError):oracle.evaluate(w[:176],a[:292],1)
        for block in (0,1):
            bad=bytearray(a);bad[292*block+260]^=1
            with self.assertRaises(ValueError):oracle.evaluate(w,bytes(bad),1)

    def test_second_block_quant_change_rejected(self):
        import gap109_oracle as oracle
        w,a=b.fixtures(1);bad=bytearray(w);bad[176+48]^=1
        with self.assertRaises(ValueError):oracle.evaluate(bytes(bad),a,1)

    def test_prior_accumulator_or_order_and_flags_cannot_match_stages(self):
        import gap109_oracle as oracle
        w,a=b.fixtures(1)
        bad=oracle.evaluate(w,a[292:]+a[:292],1)
        self.assertEqual(bad['bits'],0x43800000)
        with self.assertRaises(ValueError):b.oracle_check(bad,1)
        row=b.oracle_expected(1);row['stage_flags'][10]=0
        with self.assertRaises(ValueError):b.oracle_check(row,1)
        row=b.oracle_expected(1);row['stage_bits'][4]=0
        with self.assertRaises(ValueError):b.oracle_check(row,1)

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
        self.assertEqual(record['stage_operations'],24)

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


class IntegerOracle(unittest.TestCase):
    def test_exact_binary_value_and_rne(self):
        from fractions import Fraction
        import gap109_oracle as oracle
        self.assertEqual(oracle.finite_value(0x21800000),Fraction(1,1<<60))
        self.assertEqual(oracle.finite_value(0x25800000),Fraction(1,1<<52))
        self.assertEqual(oracle.round_single(Fraction(256)+Fraction(1,1<<52)),(0x43800000,1))
        self.assertEqual(oracle.round_single(Fraction(256)),(0x43800000,0))

    def test_nonfinite_not_silently_modelled(self):
        import gap109_oracle as oracle
        for word in (0x7f800000,0x7fc00000):
            with self.assertRaises(ValueError):oracle.finite_fma(word,0x3f800000,0)

if __name__=='__main__':unittest.main()


