import csv
import tempfile
import unittest
from pathlib import Path
import experiment as e


class RotationTests(unittest.TestCase):
    def test_trace_contains_actual_alternation_and_tail(self):
        seq = e.expected_signatures()
        self.assertEqual(len(seq), 932)
        self.assertEqual(seq.count(0x0205355B), 136)
        self.assertEqual(seq[233+32:233+36], [0x0205345B, 0x0205355B]*2)

    def test_same_register_candidate_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "vector.csv"
            def write(seq):
                with path.open("w") as stream:
                    w = csv.writer(stream)
                    w.writerow(("cycle", "event", "insn", "nr_lanes", "vlen_bits"))
                    w.writerow((0, "config", "00000000", 4, 1024))
                    for i, insn in enumerate(seq, 1):
                        w.writerow((i, "alloc", f"{insn:08x}", 4, 1024))
            write(e.expected_signatures())
            self.assertEqual(e.vector_work(path)["rotated_v10_commands"], 136)
            write([0x0205345B if x == 0x0205355B else x for x in e.expected_signatures()])
            with self.assertRaises(ValueError):
                e.vector_work(path)

    def test_recipe_reuses_only_pinned_objects(self):
        output = Path("/tmp/rotation-recipe-test")
        recipes = e.recipes(output)
        self.assertEqual(len(recipes), 5)
        link = next(x["argv"] for x in recipes if x["label"] == "link")
        self.assertNotIn(str(e.BASE / "00_main.o"), link)
        self.assertIn(str(output / "main.o"), link)
        self.assertIn(str(output / "rotation.o"), link)
        self.assertIn("-Wl,--wrap="+e.SYMBOL, link)
        self.assertIn("-Wl,--undefined=akv_attention_execute_v2_native", link)
        self.assertEqual(sum(x.endswith(".o") and str(e.BASE) in x for x in link), 15)


if __name__ == "__main__":
    unittest.main()
