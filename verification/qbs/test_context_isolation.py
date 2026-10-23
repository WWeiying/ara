import json
from pathlib import Path
import tempfile
import unittest

from run_context_isolation import END, START, first_tile, hashes, projection_pins, successor


def fixture(byte=1, output=0x3f800000):
    lines = ["CMD 0 6 2 2 4 32 28 01"]
    for k in range(28):
        lines.append(f"T {k} 0 4")
        for offset in range(0, 136, 16):
            count = min(16, 136 - offset)
            data = int.from_bytes(bytes([byte]) * count, "little")
            lines.append(f"A 0 {offset} {(1 << count) - 1:04x} {data:032x}")
        lines.extend(["W 0 0 ffff 00000000000000000000000000000001", "ENDT"])
    lines.extend(f"O {i} {output:08x}" for i in range(128))
    lines.extend(["C 224 30464 3808 114688 114688 3584 0 0", "END"])
    block = "\n".join(lines)
    return "QBSCMD1 28\n" + "\n".join(
        block.replace("CMD 0 ", f"CMD {i} ", 1) for i in range(28)) + "\n"


class IsolationTests(unittest.TestCase):
    def test_sealed_vector_change_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            a, b = root / "inputs0.vectors", root / "inputs4.vectors"
            a.write_text(fixture())
            b.write_text(fixture(2, 0x40000000))
            pins = hashes([a, b])
            (root / "status.json").write_text(json.dumps({"sources_and_inputs": pins}))
            self.assertEqual(projection_pins(root), pins)
            b.write_text(fixture(3, 0x40400000))
            with self.assertRaises(RuntimeError):
                projection_pins(root)
            (root / "status.json").write_text(json.dumps({"sources_and_inputs": hashes([a])}))
            with self.assertRaises(ValueError):
                projection_pins(root)

    def test_successor_preserves_outer_suite(self):
        a, b = first_tile(fixture()), first_tile(fixture(2, 0x40000000))
        source = "prefix\n" + START + "original direct\n" + END + "suffix\n"
        derived, changes = successor(source, a, b)
        self.assertEqual(changes, (3808, 128))
        self.assertTrue(derived.startswith("prefix\n"))
        self.assertTrue(derived.endswith(END + "suffix\n"))
        self.assertIn("expected_output[index] = saved_output[index]", derived)
        self.assertIn("expected_flags = saved_flags", derived)
        self.assertIn("memory_epoch++", derived)
        self.assertIn("context_read_bytes != 0", derived)
        self.assertEqual(a["vector"].splitlines()[0], "QBSCMD1 1")

    def test_identical_or_wrong_weights_rejected(self):
        a, b = first_tile(fixture()), first_tile(fixture(2, 0x40000000))
        with self.assertRaises(ValueError):
            successor(START + END, a, a)
        b["weights"] = []
        with self.assertRaises(ValueError):
            successor(START + END, a, b)

    def test_incomplete_or_conflicting_records_rejected(self):
        text = fixture()
        for bad in (text.replace("O 127 3f800000\n", "", 1),
                    text.replace("O 127 3f800000", "O 0 3f800000", 1),
                    text.replace("A 0 128 00ff", "A 0 128 ffff", 1),
                    text.replace("4 32 28 01", "8 16 28 01", 1)):
            with self.subTest(bad=bad[:80]), self.assertRaises(ValueError):
                first_tile(bad)

    def test_anchor_drift_rejected(self):
        a, b = first_tile(fixture()), first_tile(fixture(2, 0x40000000))
        for source in (START, END, START + START + END):
            with self.assertRaises(ValueError):
                successor(source, a, b)


if __name__ == "__main__":
    unittest.main()
