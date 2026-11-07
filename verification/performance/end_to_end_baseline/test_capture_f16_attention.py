import json
from pathlib import Path
import struct
import tempfile
import unittest

from capture_f16_attention import TENSORS, validate


def fixture(root):
    for phase,queries in (('prefill',64),('decode',1)):
        folder=root/phase/'block';folder.mkdir(parents=True)
        for name,kind,shape in zip(TENSORS,('f32','f16','f16','f16','f32'),
            ([128,queries,16,1],[128,96,8,1],[128,96,8,1],[96,queries,1,1],[2048,queries,1,1])):
            size=4 if kind=='f32' else 2;strides=[size]
            for n in shape[:-1]:strides.append(strides[-1]*n)
            count=shape[0]*shape[1]*shape[2]*shape[3]
            raw=bytearray(count*size)
            if name==TENSORS[3]:
                for row in range(queries):
                    visible=row+1 if phase=='prefill' else 65
                    for col in range(visible,96):struct.pack_into('<H',raw,(row*96+col)*2,0xfc00)
            meta=dict(type=kind,shape=shape,strides=strides,nbytes=len(raw))
            (folder/(name+'.bin')).write_bytes(raw)
            (folder/(name+'.json')).write_text(json.dumps(meta))
        (folder/'attention_params-0.json').write_text(json.dumps(dict(
            op='FLASH_ATTN_EXT',scale=0.0883883,max_bias=0,logit_softcap=0)))


class F16CaptureTests(unittest.TestCase):
    def test_both_real_execution_phases_and_native_sized_prefill(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);fixture(root);result=validate(root)
            self.assertEqual(result['prefill']['query_shape'],[128,64,16,1])
            self.assertEqual(result['decode']['visible_prefixes'],[65])

    def test_quantized_relabel_geometry_and_stride_corruption_rejected(self):
        for key,value in (('type','q8_0'),('shape',[128,96,4,1]),('strides',[2,1,24576,196608])):
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);fixture(root);p=root/'decode/block/attn_k_input-0.json'
                meta=json.loads(p.read_text());meta[key]=value;p.write_text(json.dumps(meta))
                with self.subTest(key=key),self.assertRaises(ValueError):validate(root)

    def test_mask_holes_and_wrong_decode_prefix_rejected(self):
        for offset,bits in ((2,0),(65*2,0)):
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);fixture(root);p=root/'decode/block/attn_mask_input-0.bin'
                data=bytearray(p.read_bytes())
                if offset==2:bits=0xfc00
                struct.pack_into('<H',data,offset,bits);p.write_bytes(data)
                with self.assertRaises(ValueError):validate(root)

    def test_masked_nan_padding_ignored_but_active_nan_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);fixture(root);p=root/'decode/block/attn_k_input-0.bin'
            raw=bytearray(p.read_bytes());struct.pack_into('<H',raw,95*128*2,0x7e00);p.write_bytes(raw)
            validate(root)
            struct.pack_into('<H',raw,0,0x7e00);p.write_bytes(raw)
            with self.assertRaisesRegex(ValueError,'Nonfinite'):validate(root)

    def test_bad_params_and_truncation_rejected(self):
        for bad_params in (False,True):
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);fixture(root)
                if bad_params:
                    p=root/'decode/block/attention_params-0.json';data=json.loads(p.read_text())
                    data['logit_softcap']=1;p.write_text(json.dumps(data))
                else:
                    p=root/'decode/block/attn_v_input-0.bin';p.write_bytes(p.read_bytes()[:-2])
                with self.assertRaises(ValueError):validate(root)


if __name__=='__main__':unittest.main()
