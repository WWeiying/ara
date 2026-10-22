import unittest

from lzc_padding_proof import prove


def heap_reference(width):
    levels = (width - 1).bit_length()
    heap = {}
    leaf_base = (1 << (levels - 1)) - 1
    for k in range(1 << (levels - 1)):
        # Mirror the RTL's three leaf generate conditions, independently of span.
        if 2 * k < width - 1:
            bits = [2 * k, 2 * k + 1]
        elif 2 * k == width - 1:
            bits = [2 * k]
        else:
            bits = []
        heap[leaf_base + k] = bits
    expected = {}
    for level in reversed(range(levels - 1)):
        for index in range(1 << level):
            node = (1 << level) - 1 + index
            left, right = heap[2 * node + 1], heap[2 * node + 2]
            expected[(level, index)] = (left, right)
            heap[node] = left + right
    return expected


class LzcPaddingProofTest(unittest.TestCase):
    def test_ranges_against_independent_rtl_heap(self):
        for width in (2, 3, 4, 10, 16, 23, 32, 53):
            expected = heap_reference(width)
            actual = {(n["level"], n["index"]):
                      (n["left_real_bits"], n["right_real_bits"])
                      for n in prove(width)["nodes"]}
            self.assertEqual(actual, expected)
            self.assertEqual(len(prove(width)["nodes"]), len(expected))

    def test_all_width10_inputs(self):
        expected = heap_reference(10)
        for node in prove(10)["nodes"]:
            left_bits, right_bits = expected[(node["level"], node["index"])]
            actual = set()
            for value in range(1 << 10):
                left = int(any(value & (1 << bit) for bit in left_bits))
                right = int(any(value & (1 << bit) for bit in right_bits))
                actual.add(f"{left}{right}")
            self.assertEqual(actual, set(node["reachable_child_vectors"]))

    def test_width23_witnesses(self):
        expected = heap_reference(23)
        for node in prove(23)["nodes"]:
            left_bits, right_bits = expected[(node["level"], node["index"])]
            for vector, encoded in node["witnesses_in_tmp"].items():
                value = int(encoded, 16)
                self.assertLess(value, 1 << 23)
                left = int(any(value & (1 << bit) for bit in left_bits))
                right = int(any(value & (1 << bit) for bit in right_bits))
                self.assertEqual(vector, f"{left}{right}")
            if not node["right_real_bits"]:
                self.assertTrue(all(v[1] == "0" for v in node["reachable_child_vectors"]))

    def test_power_of_two_has_no_padding(self):
        self.assertTrue(all(not n["unreachable_child_vectors"] for n in prove(16)["nodes"]))

    def test_invalid_width(self):
        for width in (0, 1, -1, True, 2.5):
            with self.assertRaises(ValueError):
                prove(width)


if __name__ == "__main__":
    unittest.main()
