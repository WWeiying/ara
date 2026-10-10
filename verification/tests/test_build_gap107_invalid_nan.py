import copy
import struct
import unittest

import build_gap107_invalid_nan as b
import audit_gap107_invalid_nan as a


class Numeric(unittest.TestCase):
    def row(self,phase):
        return dict(phase=phase,scope='bounded-native-IEEE-host-only',dot=0 if phase==0 else 256,
            correction=0,bits=0x7fc00000,flags=16,csr_flags=24,
            stage_bits=[0,0,0x7f800000,0,0x7fc00000,0x7fc00000] if phase==0 else
                [0x43800000,0,0x7fc00000,0x7fc00000,0x7fc00000,0x7fc00000],
            stage_flags=[0,0,0,0,16,0] if phase==0 else [0,0,0,16,0,0])

    def test_independent_ieee_contract(self):
        for phase in (0,1):b.oracle_check(self.row(phase),phase)

    def test_quiet_nan_must_not_be_nv_source(self):
        row=self.row(1);row['stage_flags'][2]=16
        with self.assertRaises(ValueError):b.oracle_check(row,1)

    def test_flags_or_not_addition(self):
        for key,value in [('flags',32),('csr_flags',40),('bits',0xffc00000)]:
            row=self.row(0);row[key]=value
            with self.assertRaises(ValueError):b.oracle_check(row,0)

    def test_q5_q8_exact_bytes_and_bsums(self):
        for phase in (0,1):
            w,act=b.fixtures(phase)
            self.assertEqual((len(w),len(act)),(176,292))
            self.assertEqual(struct.unpack('<HH',w[:4]),(0x7c00 if phase==0 else 0x7e01,0))
            self.assertEqual(w[16:48],bytes(32));self.assertEqual(w[48:],bytes([0 if phase==0 else 0x11])*128)
            self.assertEqual(struct.unpack('<I',act[:4])[0],0x3f800000 if phase==0 else 0x7f800000)
            self.assertEqual(act[4:260],bytes([1])*256)
            self.assertEqual(struct.unpack('<16h',act[260:]),(16,)*16)

    def test_unreviewed_phase_rejected(self):
        for phase in (True,2,-1,'1'):
            with self.assertRaises(ValueError):b.fixtures(phase)


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
