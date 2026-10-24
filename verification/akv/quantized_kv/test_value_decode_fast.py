"""Independent format arithmetic, full transcript and rejection checks."""
import struct
import unittest

from check_value_decode_fast import CAP, BOUNDARY, SUITE, TERMINAL, ORDER, expected_hash, check_log


class FastDecodeTest(unittest.TestCase):
    def transcript(self):
        data = bytes(69632)
        checksum = expected_hash(data)
        lines = [CAP, BOUNDARY]
        for kind in range(2):
            for trial, optimized in enumerate(ORDER):
                lines += [f'QUANT_VALUE_FAST_BEGIN kind={kind} trial={trial} optimized={optimized}',
                    f'QUANT_VALUE_FAST_RESULT kind={kind} trial={trial} optimized={optimized} '
                    'cycles=1000 outputs=32768 fcsr=0 vcsr=5 compared=32768 errors=0']
            lines += [f'QUANT_VALUE_FAST_HASH kind={kind} outputs=32768 hash={checksum}']
        return '\n'.join(lines+[SUITE, TERMINAL, 'UVM_ERROR : 0', 'UVM_FATAL : 0']), data

    def test_complete(self):
        text, data = self.transcript()
        result = check_log(text, [data, data])
        self.assertEqual(len(result['trials']), 8)
        self.assertEqual(result['performance'][0]['speedup'], 1)
        self.assertEqual(result['hash_algorithm'], 'word_fnv64')

    def test_reject_mutations(self):
        text, data = self.transcript()
        variants = [text.replace(CAP, CAP+'\n'+CAP, 1), text.replace(BOUNDARY, '', 1),
            text.replace('optimized=0', 'optimized=1', 1),
            text.replace('fcsr=0', 'fcsr=1', 1), text.replace('vcsr=5', 'vcsr=0', 1),
            text.replace('compared=32768', 'compared=32767', 1),
            text.replace('cycles=1000', 'cycles=0', 1), text.replace('hash=', 'hash=0'),
            text.replace('errors=0', 'errors=1', 1), text.replace(TERMINAL, ''),
            text.replace('UVM_FATAL : 0', 'UVM_FATAL : 1'), text+'\n'+BOUNDARY,
            text+'\n[QBS_PERF] success=1', text.replace(SUITE, SUITE+'\n'+SUITE, 1)]
        records = text.splitlines()
        for index, line in enumerate(records):
            if 'FAST_HASH' in line:
                variants.append('\n'.join(records[:index]+records[index+1:]))
                variants.append('\n'.join(records[:index]+[line]+records[index:]))
        for index, variant in enumerate(variants):
            with self.subTest(index=index), self.assertRaises(ValueError):
                check_log(variant, [data, data])

    def test_words_signed_zero_and_hidden_rows(self):
        # Expected values independently constructed, not using the format decoder.
        for scale in (1.0, -0.0, 0.5, 65504.0):
            integers = list(range(-16, 16))
            data = (struct.pack('<e', scale)+struct.pack('32b', *integers))*2048
            value = 14695981039346656037
            for _ in range(1024):
                for integer in integers:
                    word = int.from_bytes(struct.pack('<f', scale*integer), 'little')
                    value = ((value ^ word)*1099511628211) % (2**64)
            self.assertEqual(expected_hash(data), f'{value:016x}')
        hidden = bytearray(data)
        for head in range(2):
            for token in range(128, 256):
                hidden[(head*256+token)*136:(head*256+token)*136+2] = b'\x00\x7c'
        self.assertEqual(expected_hash(hidden), expected_hash(data))
        hidden[:2] = b'\x01\x7c'
        with self.assertRaises(ValueError):
            expected_hash(hidden)


if __name__ == '__main__':
    unittest.main()
