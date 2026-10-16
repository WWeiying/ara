import unittest

from plan_stall_observation import resolve


class ObservationPlanTests(unittest.TestCase):
    def test_connected_pin(self):
        rows = [dict(kind="unit", cell="top/u", object="top/u/valid", net="top/v")]
        result = resolve(rows, [], {"unit": ["valid"]}, {})
        self.assertTrue(result["candidate_sources_resolved"])
        self.assertFalse(result["insertion_ready"])
        self.assertFalse(result["hardware_capture"])

    def test_missing_is_not_zero(self):
        result = resolve([], [], {"unit": ["valid"]}, {})
        self.assertFalse(result["candidate_sources_resolved"])
        self.assertEqual(result["selected"], [])

    def test_optimized_port_is_not_zero(self):
        rows = [dict(kind="unit", cell="top/u", object="top/u/valid", net="")]
        result = resolve(rows, [], {"unit": ["valid"]}, {})
        self.assertEqual(result["missing"][0]["reason"], "unconnected")

    def test_duplicate_instances_rejected(self):
        rows = [dict(kind="unit", cell=f"top/u{i}", object=f"top/u{i}/valid",
                     net=f"top/v{i}") for i in range(2)]
        result = resolve(rows, [], {"unit": ["valid"]}, {})
        self.assertFalse(result["candidate_sources_resolved"])

    def test_bus_order_is_explicit(self):
        rows = [dict(kind="unit", cell="top/u", net=f"top/u/count[{i}]")
                for i in (2, 0, 1)]
        result = resolve([], rows, {}, {"unit": [f"count[{i}]" for i in range(3)]})
        self.assertEqual([r["name"] for r in result["selected"]],
                         ["count[0]", "count[1]", "count[2]"])

    def test_scope_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            resolve([], [dict(kind="unit", cell="top/u", net="other/valid")], {}, {})

    def test_aliases_keep_logical_bit_mapping(self):
        rows = [dict(kind="unit", cell="top/u", object=f"top/u/pc[{i}]", net="top/sign")
                for i in range(2)]
        result = resolve(rows, [], {"unit": ["pc[0]", "pc[1]"]}, {})
        self.assertEqual(result["physical_nets"], ["top/sign"])
        self.assertEqual([r["probe_bit"] for r in result["selected"]], [0, 0])

    def test_register_q_not_name_guess(self):
        row = dict(kind="unit", cell="top/u", register="top/u/state_reg[0]",
                   ref="FDCE", net="top/u/p_42_out", clock="", init="1'b0")
        result = resolve([], [], {}, {}, [row], {"unit": ["state_reg[0]"]})
        self.assertEqual(result["selected"][0]["net"], "top/u/p_42_out")
        self.assertFalse(result["insertion_ready"])

    def test_clock_is_not_probe_data(self):
        row = dict(kind="unit", cell="top/u", object="top/u/clk_i", net="top/clk")
        result = resolve([row], [], {"unit": ["clk_i"]}, {})
        self.assertEqual(result["clock_nets"], ["top/clk"])
        self.assertEqual(result["physical_nets"], [])


if __name__ == "__main__":
    unittest.main()
