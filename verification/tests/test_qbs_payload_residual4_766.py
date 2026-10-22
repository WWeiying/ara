import struct
import unittest
import build_qbs_payload_residual4_766 as model


def decoded(phase,b,i):
    g=i//16
    if phase==0:
        packet,lane=divmod(i,32)
        q=(b[32+32*(packet//4)+lane]>>(2*(packet%4)))&3
        if not (b[lane]>>packet)&1:q-=4
        region,within=divmod(g,4)
        scale=((b[96+(region%2)*4+within]>>(4*(region//2)))&15)|(((b[104+within]>>(2*region))&3)<<4)
        return q*(scale-32)
    if phase==3:
        half,rem=divmod(i,128);group,lane=divmod(rem,16)
        q=(b[16+32*half+16*(group&1)+lane]>>(2*(group//2)))&3
        return q*(b[g]&15)-(b[g]>>4)
    half,rem=divmod(i,128);quarter,lane=divmod(rem,32)
    lo=(b[64*half+32*(quarter&1)+lane]>>(4*(quarter//2)))&15
    hi=(b[128+32*half+lane]>>(2*quarter))&3
    s=b[192+g];s=s-256 if s>=128 else s
    return ((lo|(hi<<4))-32)*s


class TestResidual(unittest.TestCase):
    def test_all_format_elements_independent_unpack(self):
        for phase in range(4):
            for row in range(8):
                b=model.packed_row(phase,row)
                self.assertEqual(len(b),model.SIZE[phase])
                for i in range(256):self.assertEqual(decoded(phase,b,i),model.logical(phase,row,i))

    def test_all64_numeric_outputs(self):
        for phase in range(4):
            weight,activation,gold=model.fixture(phase)
            for ctx in range(8):
                for row in range(8):
                    start=64+model.WP[phase]+model.SIZE[phase]*row
                    b=weight[start:start+model.SIZE[phase]]
                    a=activation[64+model.AP[phase]:]
                    actual=sum(decoded(phase,b,i)*(a[32+8*i+ctx]-256 if a[32+8*i+ctx]>=128 else a[32+8*i+ctx]) for i in range(256))
                    self.assertLess(abs(actual),2**23)
                    self.assertEqual(gold[8*ctx+row],int.from_bytes(struct.pack('<f',actual),'little'))

    def test_full_vrf_preservation(self):
        for phase in range(4):
            image=model.expected_frame(phase);seed=model.base.seed_bytes()
            target={1024+128*c+i for c in range(8) for i in range(32)}
            self.assertEqual(len(image),4096)
            self.assertTrue(all(image[i]==seed[i] for i in range(4096) if i not in target))

    def test_fresh_plan_and_exact_targets(self):
        plan=model.common.read(model.PLAN)
        self.assertEqual(model.common.sha(model.PLAN),model.PLAN_SHA)
        self.assertEqual(plan['baseline'],766)
        self.assertEqual(sum(c['incremental_mapping_directions'] for c in plan['commands'][:4]),504)
        self.assertEqual([(c['weight_profile_enum'],c['weight_phase'],c['activation_phase']) for c in plan['commands'][:4]],list(zip(model.PROFILE,model.WP,model.AP)))

    def test_source_mutation_changes_gold(self):
        for phase in range(4):
            b=bytearray(model.packed_row(phase,0));b[0]^=1
            self.assertTrue(any(decoded(phase,b,i)!=model.logical(phase,0,i) for i in range(256)))


if __name__=='__main__':unittest.main()
