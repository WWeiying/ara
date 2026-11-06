import unittest

from ffn_capture import SOURCES, check, environment
from test_projection_capture import fixture as original_fixture


def fixture():
    original = original_fixture()
    text = 'FFN_CAPTURE_SCOPE model=qwen3_1p7b layer=0 qbs=1 kv=q8_0 trace=1\n'
    text += original.splitlines()[0].replace('PROJECTION_', 'FFN_')+'\n'
    seq = 0
    for source, k in SOURCES.items():
        calls = {'attn_norm-0': [],
                 'ffn_norm-0': [('q4_K',2048),('q6_K',1024),('q4_K',1024),('q4_K',2048)],
                 'ffn_swiglu-0': [('q4_K',6144),('q4_K',6144)]}[source]
        for ty,n in calls:
            text += f'GGML_RISCV_QBS_CALL type={ty} mode=gemm k=2048 input_rows=40 output_rows={n} split_k=0\n'
            profile = '1' if ty == 'q4_K' else '2'
            for i in range(n//32*10):
                seq += 1
                text += f'GGML_RISCV_QBS_COMMAND seq={seq} m=4 n=32 k_blocks=8 emulated=0 segmented=0 weight_profile={profile} activation_profile=1 access=0\n'
        text += f'FFN_CAPTURE_SHAPE source={source} k={k} rows=4 tokens=40 type=f32\n'
        old = [s for s in original.splitlines() if s.startswith('PROJECTION_CAPTURE_DATA ')]
        # Extend this test fixture only; real captures never repeat/extend rows.
        for row in range(4):
            for offset in range(0,k,16):
                line = old[row*128+(offset//16)%128]
                line = line.replace('PROJECTION_CAPTURE_DATA ', 'FFN_CAPTURE_DATA source='+source+' ')
                line = line.replace('offset='+str(offset%2048)+' ', 'offset='+str(offset)+' ')
                text += line+'\n'
    text += 'GGML_RISCV_QUANT_PREFILL status=0 runtime_called=1 commands=352 groups=80\n'
    text += 'FFN_CAPTURE_DONE sources=3 bytes=163840 stop=before_first_down performance=not_measured\nGUEST_TEST_EXIT=0\n'
    return text, original


class FFNCaptureTests(unittest.TestCase):
    def test_payloads_and_native_path(self):
        text, original = fixture(); payload, metadata = check(text, original)
        self.assertEqual([len(v) for v in payload.values()], [32768,32768,98304])
        self.assertEqual(metadata['native_projection_commands'], 5760)
        self.assertFalse(metadata['performance_measured'])

    def test_source_payload_path_and_terminal_fail_closed(self):
        text, original = fixture()
        for before, after in (('k=6144 rows=4','k=2048 rows=4'), ('GUEST_TEST_EXIT=0','GUEST_TEST_EXIT=1'),
                              ('emulated=0','emulated=1'), ('source=ffn_norm-0 row=0 offset=0','source=ffn_norm-0 row=1 offset=0'),
                              ('sources=3 bytes=163840','sources=2 bytes=65536')):
            with self.assertRaises(ValueError): check(text.replace(before,after,1), original)

    def test_environment_comes_from_accepted_fixture(self):
        source = '    env("GGML_RISCV_QBS", "1");\n    env("GGML_RISCV_QBS_TRACE", "0");\n'
        source += '    env("GGML_RISCV_QBS_TRACE_LIFETIME", "0");\n'
        source += '    std::printf("OUTPUT_MODEL_BEGIN enabled=%u\\n", mode);'
        header = environment(source)
        self.assertIn('constexpr unsigned mode = 1;', header)
        self.assertIn('env("GGML_RISCV_QBS_TRACE", "1")', header)
        self.assertIn('env("GGML_RISCV_QBS_TRACE_LIFETIME", "1")', header)
        with self.assertRaises(ValueError): environment(source.replace('TRACE", "0', 'TRACE", "1'))


if __name__ == '__main__': unittest.main()
