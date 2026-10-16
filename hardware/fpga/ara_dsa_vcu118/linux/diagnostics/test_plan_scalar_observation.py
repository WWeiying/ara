import unittest

from plan_scalar_observation import build, members


class ScalarProfileTests(unittest.TestCase):
    def test_literal_brackets_and_no_prefix_collision(self):
        names = ["port[valid]", "port[valid][0]", "port[valid][1]",
                 "port[valid_extra]", "port[valid][x]", "port[valid][0]_rep"]
        self.assertEqual(members(names, "port[valid]"), names[:3])

    def test_multidimensional_bus(self):
        self.assertEqual(members(["bus[0][1]", "bus[0][0]", "bus_extra"], "bus"),
                         ["bus[0][0]", "bus[0][1]"])

    def test_required_source_cannot_be_silently_dropped(self):
        with self.assertRaisesRegex(ValueError, "lsu/clk_i"):
            build([], [], [], {"selected": []})

    def test_input_inventory_is_not_modified_on_failure(self):
        pins = [dict(kind="lsu", cell="top/lsu", pin="top/lsu/clk_i", net="top/clock")]
        with self.assertRaises(ValueError):
            build(pins, [], [], {"selected": []})
        self.assertNotIn("object", pins[0])


if __name__ == "__main__":
    unittest.main()
