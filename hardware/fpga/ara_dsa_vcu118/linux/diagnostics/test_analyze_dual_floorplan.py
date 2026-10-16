import unittest

from analyze_dual_floorplan import analyze, owner


class FloorplanTests(unittest.TestCase):
    def test_owners(self):
        self.assertEqual(owner("i_dram_wrapper/gen_ethernet.i_eth_loader/i_loader/loader_bd_i/ddr_fabric/inst/m00_exit_pipeline/a"),
                         "c1/loader/fabric/m00_exit_pipeline")
        self.assertEqual(owner("gen_ddr2.i_dram_wrapper_c2/gen_cdc.i_axi_cdc_mig/i_axi_cdc_dst/i_cdc_fifo_gray_dst_r/a"),
                         "c2/cdc/i_axi_cdc_dst/i_cdc_fifo_gray_dst_r")

    def test_crossings_and_literal_indexes(self):
        cells = [dict(name=f"block/r[{i}]", ref="FDCE", loc=f"SLICE_X0Y{i}", region=r, slr=s)
                 for i, (r, s) in enumerate((("X0Y0", "SLR0"), ("X0Y0", "SLR0"),
                                            ("X1Y0", "SLR0"), ("X1Y5", "SLR1")))]
        paths = [dict(STARTPOINT_PIN="block/r[0]/C", ENDPOINT_PIN=f"block/r[{i}]/CE",
                      STARTPOINT_CLOCK="ui", ENDPOINT_CLOCK="ui", SLACK=str(-i / 10))
                 for i in range(1, 5)]
        result = analyze(cells, {"setup": paths})
        self.assertEqual(dict(result["timing"]["setup"]["crossings"]),
                         dict(same_region=1, cross_region=1, cross_slr=1, unknown=1))
        group = result["timing"]["setup"]["groups"][0]
        self.assertEqual(group["worst_slack_ns"], -.4)
        self.assertAlmostEqual(group["exported_slack_sum_ns"], -1)

    def test_duplicate_cells_rejected(self):
        row = dict(name="a", ref="FDCE", loc="", region="", slr="")
        with self.assertRaises(ValueError):
            analyze([row, row], {})


if __name__ == "__main__":
    unittest.main()
