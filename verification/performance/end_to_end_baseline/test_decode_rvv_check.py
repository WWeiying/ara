from copy import deepcopy
import struct
import unittest

import check_decode_rvv as c


def fixture():
    golden = [struct.pack('<128f', *[float(p+i)/100 for i in range(128)]) for p in range(7)]
    packed = [bytes(s) for s in (2336, 2336, 7008, 2336)]
    lines = [c.SCOPE]
    def emit(tag, row): lines.append(tag+' '+' '.join(k+'='+str(v) for k,v in row.items()))
    for stage in range(4):
        emit('RVV_DECODE_PREP', dict(stage=stage, k=6144 if stage == 2 else 2048, cycles=100,
            before_fcsr=8 if stage == 0 else 9, fcsr=9, before_vcsr=5 if stage == 0 else 3,
            vcsr=3, before_vstart=0, vstart=0, checksum=c.checksum(packed[stage]),
            payload_errors=0, guard_errors=0, state_errors=0))
    for part in range(7):
        words = struct.unpack('<128I', golden[part]); diff = c.differences(words, words)
        emit('RVV_DECODE_PART', dict(part=part, profile=c.PROFILE[part], k=c.K[part], stage=c.STAGE[part],
            dispatch=10, execution=1000, calls=1 if c.PROFILE[part] == 1 else 128,
            before_fcsr=9, fcsr=9, before_vcsr=3, vcsr=3, before_vstart=0, vstart=0,
            checksum=c.checksum(golden[part]), **diff, guard_errors=0, state_errors=0, errors=0))
        for idx, word in enumerate(words): emit('RVV_DECODE_OUTPUT', dict(part=part, idx=idx, bits=word))
    emit('RVV_DECODE_RESULT', dict(preparation=400, dispatch=70, execution=7000, region=7600,
                                  parts=7, outputs=896, q4_calls=4, q6_calls=384, errors=0))
    emit('SPIKE_SOC_EXIT', dict(status=0, uart_bytes=50000))
    return '\n'.join(lines)+'\n', golden, packed


class RVVDecodeChecks(unittest.TestCase):
    def test_complete_words_and_state_not_instruction_model_cycles(self):
        args = fixture(); isa = c.check(*args, isa_model=True); rtl = c.check(*args)
        self.assertFalse(isa['performance_measured'])
        self.assertEqual(c.compare_isa(rtl, isa)['bitwise_outputs'], 896)
        shifted = args[0].replace('execution=1000', 'execution=2000').replace('execution=7000', 'execution=14000').replace('region=7600', 'region=15000')
        self.assertEqual(c.compare_isa(c.check(shifted, *args[1:]), isa)['state_records'], 11)

    def test_missing_duplicate_reordered_output_rejected(self):
        text, *oracle = fixture()
        line = next(row for row in text.splitlines() if row.startswith('RVV_DECODE_OUTPUT '))
        for broken in (text.replace(line+'\n', '', 1), text+line+'\n', text.replace('part=0 idx=0', 'part=0 idx=1', 1)):
            with self.assertRaises(ValueError): c.check(broken, *oracle, isa_model=True)

    def test_state_payload_shape_diagnostics_and_terminal_mutations(self):
        text, *oracle = fixture()
        for old,new in (('before_vcsr=5', 'before_vcsr=3'), ('fcsr=9', 'fcsr=8'),
                        ('checksum=', 'checksum=1'), ('errors=0', 'errors=1'), ('mismatches=0', 'mismatches=1'),
                        ('max_ulp=0', 'max_ulp=1'), ('q6_calls=384', 'q6_calls=383'),
                        ('status=0', 'status=1'), ('bits=0', 'bits=2143289344')):
            with self.subTest(old=old), self.assertRaises((ValueError, OverflowError)):
                c.check(text.replace(old,new,1), *oracle, isa_model=True)
        with self.assertRaises(ValueError): c.check(text+'RVV_DECODE_FAIL reason=trap\n', *oracle, isa_model=True)

    def test_float_metrics_rounding_and_strict_isa_equality(self):
        words = [c.bits(1.0)]*128; changed = words.copy(); changed[-1] += 1
        self.assertEqual(c.differences(changed, words)['max_ulp'], 1)
        self.assertEqual(c.differences(changed, words)['bit_differences'], 1)
        zero = [0]*128; signed = [0x80000000]*128
        self.assertEqual(c.differences(zero, signed)['max_ulp'], 0)
        for bad in (0x7f800000, 0x7fc12345, 1 << 32):
            invalid = words.copy(); invalid[0] = bad
            with self.assertRaises(ValueError): c.differences(invalid, words)
        result = c.check(*fixture(), isa_model=True); other = deepcopy(result); other['outputs_hex'][0] = '00'*512
        with self.assertRaises(ValueError): c.compare_isa(other, result)

    def test_duplicate_numeric_fields_are_never_accepted(self):
        with self.assertRaises(ValueError): c.fields('RECORD q4_calls=4 q4_calls=4', 'RECORD')


if __name__ == '__main__': unittest.main()
