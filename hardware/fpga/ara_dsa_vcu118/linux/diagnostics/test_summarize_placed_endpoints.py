import unittest

from summarize_placed_endpoints import owner, summarize


class EndpointTests(unittest.TestCase):
    def row(self, slack, clock="src"):
        return dict(slack=str(slack), endpoint="i_dram_wrapper/gen_cdc.i_axi_cdc_mig/i_axi_cdc_dst/i_cdc_fifo_gray_src_r/q/D",
                    startpoint="p/Q", start_clock=clock, end_clock="dst")

    def test_owner(self):
        self.assertEqual(owner(self.row(-1)["endpoint"]), "ddr1/cdc/i_cdc_fifo_gray_src_r")
        self.assertEqual(owner("gen_ddr2.i_dram_wrapper_c2/gen_channel_c2.i_dram/foo"),
                         "ddr2/gen_channel_c2.i_dram")

    def test_duplicate_endpoint_keeps_worst(self):
        result = summarize([self.row(-0.2), self.row(-1.2)])
        self.assertEqual(result["endpoint_clock_pairs"], 1)
        self.assertEqual(result["groups"][0]["worst_slack_ns"], -1.2)

    def test_clock_pairs_not_merged(self):
        result = summarize([self.row(-0.2), self.row(-1.2, "other")], limit=2)
        self.assertEqual(result["endpoint_clock_pairs"], 2)
        self.assertTrue(result["export_limit_reached"])

    def test_bad_slack_rejected(self):
        for value in (0, 1, "nan", "inf"):
            with self.assertRaises(ValueError):
                summarize([self.row(value)])


if __name__ == "__main__":
    unittest.main()
