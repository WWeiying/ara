import unittest
from unittest.mock import patch

from run_decode_rvv_rtl import timing, inputs, reference, ISA, ISA_SHA


class RVVRTLTests(unittest.TestCase):
    def test_complete_rtl_times_never_mean_an_sdk_ratio(self):
        text = '\n'.join([f'RVV_DECODE_PREP stage={i} cycles=2' for i in range(4)]+[
            f'RVV_DECODE_PART part={i} execution=3' for i in range(7)]+[
            'RVV_DECODE_RESULT region=40'])
        value = timing(text)
        self.assertEqual(value['total'], dict(region=40))
        self.assertFalse(value['complete_call_ratio_accepted'])
        self.assertEqual(len(value['parts']), 7)
        with self.assertRaises(ValueError): timing(text+'\nRVV_DECODE_RESULT region=40')
        with self.assertRaises(ValueError): timing(text.replace('RVV_DECODE_PART part=6 execution=3',''))

    def test_unknown_width_fails_before_input_collection(self):
        with self.assertRaises(ValueError): inputs(64)

    def test_reference_identity_is_fixed_before_accepting_output(self):
        def fake_bind(pins, path, sha=None):
            self.assertEqual(path, ISA / 'result.json')
            self.assertEqual(sha, ISA_SHA)
            raise ValueError('changed reference')
        with patch('run_decode_rvv_rtl.bind', fake_bind):
            with self.assertRaisesRegex(ValueError, 'changed reference'): reference({})


if __name__ == '__main__': unittest.main()
