import struct
import unittest

from check_output_gqa6 import SCOPE, check


def fixture():
    golden = struct.pack('<1536f', *([1.0]*1536))
    rows = [SCOPE, 'OUTPUT_GQA6_FORMAT q4=0']
    for trial, candidate in enumerate((0,1,1,0)):
        rows.append(f'OUTPUT_GQA6_BEGIN trial={trial} candidate={candidate}')
        for i in range(8):
            m = 4 if i%2 == 0 else 2
            rows.append(f'[QBS_PERF] seq={trial*8+i+1} m={m} n=32 vlen=1024 lanes=4 success=1 fault=0 '
                        f'validation_fault=0 read_fault=0 weight_bytes=4352 useful_pairs={m*4096} '
                        'activation_access=0 busy_cycles=1000')
        rows.append(f'OUTPUT_GQA6_RESULT trial={trial} candidate={candidate} cycles={10000 if candidate else 12000} '
                    'commands=8 groups=1 values=128 panels=4 key_bytes=17408 fcsr=9 vcsr=5 errors=0 hex='+
                    '3f800000'*768)
    return '\n'.join(rows+['OUTPUT_GQA6_SUITE_PASS'])+'\n', golden


class OutputGqa6Tests(unittest.TestCase):
    def test_complete_call_and_bitwise_pair(self):
        text, golden = fixture(); result = check(text, golden)
        self.assertEqual(result['speedup'], 1.2)
        self.assertEqual(result['outputs_per_trial'], 768)
        self.assertEqual(result['trials'][0]['useful_pairs'], 98304)

    def test_reject_missing_command_wrong_flags_bits_or_capture(self):
        text, golden = fixture()
        for broken in (text.replace('seq=2 ', 'seq=1 ', 1),
                       text.replace('values=128', 'values=127', 1),
                       text.replace('3f800000', '3f800001', 1),
                       text.replace('fcsr=9', 'fcsr=8', 1),
                       text.replace('errors=0', 'errors=1', 1), text+text,
                       text+'Fatal: injected\n'):
            with self.assertRaises(ValueError): check(broken, golden)
        with self.assertRaises(ValueError): check(text, bytes(len(golden)))


if __name__ == '__main__': unittest.main()
