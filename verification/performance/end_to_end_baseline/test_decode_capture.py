import struct
import unittest

from decode_capture import SOURCES, PATTERN, check
from test_projection_capture import fixture as original_fixture


def fixture():
    original = original_fixture()
    lines = [original.splitlines()[0].replace('PROJECTION_CAPTURE','DECODE_CAPTURE')]
    lines += ['GGML_RISCV_QUANT_PREFILL status=0 runtime_called=1']*28
    lines.append('DECODE_CAPTURE_BEGIN prompt=40 token=22406 position=40 kv=q8_0 qbs=1')
    seq = 0
    def capture(name):
        k = SOURCES[name]; lines.append(f'DECODE_CAPTURE_SHAPE source={name} k={k} rows=1 type=f32')
        for offset in range(0,k,16):
            bits = ''.join(f'{struct.unpack("<I",struct.pack("<f",offset+i+1.0))[0]:08x}' for i in range(16))
            lines.append(f'DECODE_CAPTURE_DATA source={name} offset={offset} bits={bits}')
    def call(index):
        nonlocal seq
        k,n = PATTERN[index%7]; profile = 2 if index%7 in (1,6) else 1
        lines.append(f'GGML_RISCV_QBS_CALL type={"q6_K" if profile == 2 else "q4_K"} mode=gemv '
                     f'k={k} input_rows=1 output_rows={n} split_k=0')
        for j in range(n//32):
            seq += 1; access = 0 if k>4096 else 1 if j==0 else 3 if j==n//32-1 else 2
            lines.append(f'GGML_RISCV_QBS_COMMAND seq={seq} m=1 n=32 k_blocks={k//256} weight_profile={profile} '
                         f'activation_profile=1 emulated=0 segmented=0 access={access}')
        if index%7 == 2:
            lines.append('GGML_RISCV_QUANT_KV status=0 runtime_called=1')
            lines.append('GGML_RISCV_QUANT_KV_OUTPUT_TILE enabled=1 status=0')
    capture('attn_norm-0')
    for i in range(196):
        call(i)
        if i == 3: capture('ffn_norm-0')
        elif i == 5: capture('ffn_swiglu-0')
    capture('result_norm')
    lines += ['DECODE_CAPTURE_DONE sources=4 bytes=49152 stop=before_decode_vocabulary performance=not_measured',
              'GUEST_TEST_EXIT=0']
    return '\n'.join(lines),original


class DecodeCaptureTests(unittest.TestCase):
    def test_actual_phase_and_full_layer_work(self):
        text, original = fixture(); payload, metadata = check(text,original)
        self.assertEqual([len(p) for p in payload.values()],[8192,8192,24576,8192])
        self.assertEqual(metadata['native_projection_commands'],17920)
        self.assertFalse(metadata['complete_decode_executed'])
        self.assertTrue(metadata['complete_prefill_executed'])

    def test_missing_work_wrong_phase_and_context_rejected(self):
        text, original = fixture()
        for old,new in (('token=22406','token=22407'),('m=1 n=32','m=4 n=32'),('seq=1 ','seq=2 '),
                        ('access=0','access=2'),('sources=4 bytes=49152','sources=3 bytes=40960'),
                        ('position=40','position=0')):
            with self.assertRaises(ValueError): check(text.replace(old,new,1),original)

    def test_prefill_row_cannot_be_presented_as_decode(self):
        text, original = fixture()
        old = [s for s in original.splitlines() if s.startswith('PROJECTION_CAPTURE_DATA row=0 ')]
        mapping = {s.split('offset=',1)[1].split()[0]:s.split('bits=',1)[1] for s in old}
        lines = text.splitlines()
        for i,line in enumerate(lines):
            if line.startswith('DECODE_CAPTURE_DATA source=attn_norm-0 '):
                offset = line.split('offset=',1)[1].split()[0]
                lines[i] = line.split('bits=',1)[0]+'bits='+mapping[offset]
        with self.assertRaises(ValueError): check('\n'.join(lines),original)


if __name__ == '__main__': unittest.main()
