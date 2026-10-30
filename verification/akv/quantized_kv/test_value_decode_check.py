#!/usr/bin/env python3
"""Independent Q8_0 format oracle and native transcript mutation tests."""
import struct
import unittest

from check_value_decode import CAP, BOUNDARY, SUITE, TERMINAL, ORDER, expected_hash, update_hash, check_log


class ValueDecodeTest(unittest.TestCase):
    def test_known_values_and_hidden_rows(self):
        data = (b'\x00\x3c'+bytes(range(32)))*4*512
        actual = b''.join(struct.pack('<f', float(x)) for _ in range(256*4) for x in range(32))
        self.assertEqual(expected_hash(data), f'{update_hash(14695981039346656037, actual):016x}')
        hidden = bytearray(data)
        for head in range(2):
            for token in range(128, 256):
                for block in range(4):
                    start = (head*256+token)*136+block*34
                    hidden[start:start+2] = b'\x01\x7c'
        self.assertEqual(expected_hash(hidden), expected_hash(data))
        hidden[:2] = b'\x00\x7c'
        with self.assertRaises(ValueError):
            expected_hash(hidden)

    def transcript(self):
        data = bytes(69632)
        checksum = expected_hash(data)
        lines = [CAP, BOUNDARY]
        for kind in range(2):
            for trial, optimized in enumerate(ORDER):
                lines.append(f'QUANT_VALUE_BEGIN kind={kind} trial={trial} optimized={optimized}')
                lines.append(f'QUANT_VALUE_RESULT kind={kind} trial={trial} optimized={optimized} '
                    f'cycles=1000 outputs=32768 fcsr=0 vcsr=5 hash={checksum} errors=0')
        return '\n'.join(lines+[SUITE, TERMINAL, 'UVM_ERROR : 0', 'UVM_FATAL : 0']), data

    def test_complete_and_mutated_transcripts(self):
        text, data = self.transcript()
        result = check_log(text, [data, data])
        self.assertEqual(len(result['trials']), 8)
        self.assertFalse(result['model_speedup_claimed'])
        variants = [text.replace(CAP, CAP+'\n'+CAP, 1), text.replace(BOUNDARY, '', 1),
            text.replace('optimized=0', 'optimized=1', 1),
            text.replace('fcsr=0', 'fcsr=1', 1), text.replace('vcsr=5', 'vcsr=0', 1),
            text.replace('outputs=32768', 'outputs=32767', 1),
            text.replace('hash=', 'hash=0', 1), text.replace('errors=0', 'errors=1', 1),
            text.replace('cycles=1000', 'cycles=0', 1), text.replace(TERMINAL, ''),
            text.replace('UVM_FATAL : 0', 'UVM_FATAL : 1'), text+'\n'+BOUNDARY,
            text+'\n[QBS_PERF] success=1', text.replace(SUITE, SUITE+'\n'+SUITE, 1)]
        for i, changed in enumerate(variants):
            with self.subTest(mutation=i), self.assertRaises(ValueError):
                check_log(changed, [data, data])


if __name__ == '__main__':
    unittest.main()
