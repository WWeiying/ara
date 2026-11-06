import copy
import unittest

from test_decode_native import fixture
from check_decode_native import check
from diagnose_decode_native import explain


class DecodeServiceTests(unittest.TestCase):
    def test_service_bound_and_byte_conservation(self):
        measured=check(*fixture());r=explain(measured)
        self.assertEqual(r['context_counts']['context_reuse_count'],21)
        self.assertEqual(r['context_counts']['activation_axi_bytes_saved'],49056)
        self.assertEqual(r['activation_axi_payload_bytes'],35040)
        self.assertEqual(r['physical_reader_totals']['weight_bytes'],1665024)
        self.assertEqual(r['physical_reader_totals']['payload_bytes'],1700512)
        self.assertTrue(r['no_observed_fp_input_or_result_backpressure'])
        self.assertTrue(all(x['qbs_busy']>=x['unchanged_service_cycle_floor'] for x in r['parts']))

    def test_invalid_domains_and_changed_payload_rejected(self):
        measured=check(*fixture())
        changed=copy.deepcopy(measured);changed['activity'][0]['counters']['r_beats']=10**9
        with self.assertRaises(ValueError):explain(changed)
        changed=copy.deepcopy(measured);changed['activity'][0]['activation_axi_payload_bytes']+=16
        with self.assertRaises(ValueError):explain(changed)


if __name__=='__main__':unittest.main()
