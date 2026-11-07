import math
from pathlib import Path
import struct
import tempfile
import unittest

from prepare_f16_native_data import SCALE, independent_attention, independent_decode, rows, subset
from test_capture_f16_attention import fixture


class F16DataTests(unittest.TestCase):
    def test_rows_respect_captured_strides(self):
        meta=dict(type='f32',shape=[2,3,3,1],strides=[4,16,64,192])
        raw=bytes(range(168))
        self.assertEqual(rows(meta,raw,2,2),raw[:8]+raw[16:24]+raw[64:72]+raw[80:88])
        with self.assertRaises(ValueError):rows(meta,raw,4,2)

    def test_real_shape_subsets_and_decode_conversion(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);fixture(root)
            for phase,nq in (('prefill',64),('decode',1)):
                data,record=subset(root,phase)
                self.assertEqual(record['outputs'],2*nq*128)
                self.assertEqual(len(data['query']),2*nq*128*4)
                self.assertEqual(len(data['mask']),96*nq*2)
                self.assertEqual(record['max_abs_mapping_error'],0)
                if phase=='decode':self.assertEqual(len(data['query_f16']),512)

    def test_nontrivial_reference_two_heads_and_causal_rows(self):
        q=[0.0]*(2*2*128);q[0]=q[128]=1;q[256]=q[384]=-1
        key=[0.0]*256;key[128]=2
        val=[1.0]*128+[3.0]*128
        expected=independent_attention(struct.pack('<512f',*q),struct.pack('<256e',*key),
                                       struct.pack('<256e',*val),[1,2])
        self.assertEqual(expected[:256],[1.0]*256)
        weight=math.exp(2*SCALE)
        self.assertAlmostEqual(expected[256],(1+3*weight)/(1+weight))
        self.assertAlmostEqual(expected[384],(weight+3)/(weight+1))

    def test_wrong_golden_row_mapping_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);fixture(root)
            p=root/'prefill/block/kqv_out-0.bin'
            data=bytearray(p.read_bytes());struct.pack_into('<f',data,2048*4,1);p.write_bytes(data)
            with self.assertRaisesRegex(ValueError,'golden differs'):subset(root,'prefill')

    def test_decode_reference_retains_intermediate_half_rounding(self):
        query=bytes(256*4);key=bytes(256*2)
        value=struct.pack('<256e',*([.3]*128+[.4]*128))
        exact=independent_attention(query,key,value,[2])
        rounded=independent_decode(query,key,value,[2])
        self.assertGreater(abs(exact[0]-rounded[0]),1e-5)
        self.assertEqual(rounded[0],struct.unpack('<e',struct.pack('<e',
            sum(struct.unpack('<2e',struct.pack('<2e',.3,.4)))))[0]/2)


if __name__=='__main__':unittest.main()
