import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("view_analyze", Path(__file__).with_name("analyze.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CheckReport(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "status").write_text("COMPLETE\n")
        for kv in (1, 4):
            for token in ("65", "128", "137", "stream"):
                for i, mode in enumerate(("native", "session", "views", "views", "session", "native")):
                    stem = self.root / f"k{kv}_t{token}_{i}_{mode}"
                    rows = []
                    for trial in range(7):
                        calls = 0 if mode == "native" else 1 if mode == "views" else kv
                        rows.append("VIEW_PAIR " + json.dumps(dict(mode=mode, stream=token == "stream",
                            tokens=(65, 128, 137)[trial % 3] if token == "stream" else int(token),
                            kv_heads=kv, trial=trial, warmup=not trial, ns=10000, calls=calls,
                            completed=calls, groups=0 if mode == "native" else kv,
                            registrations=int(mode == "views" and not trial), fflags=3, diagnostic=False, errors=0)))
                    stem.with_suffix(".log").write_text("\n".join(rows) + "\nRESIDENT_VIEW_PAIR_PASS\n")
                    stem.with_suffix(".rc").write_text("0\n")

    def test_good(self):
        r = module.analyze(self.root)
        self.assertEqual(r["checked_calls"], 336)
        self.assertEqual(len(r["rows"]), 8)

    def test_missing(self):
        (self.root / "k4_t137_3_views.log").unlink()
        with self.assertRaises(FileNotFoundError): module.analyze(self.root)

    def test_mutations(self):
        path = self.root / "k4_t137_3_views.log"
        old = path.read_text()
        for old_text, new_text in (( '"errors": 0', '"errors": 1'),
                ('"diagnostic": false', '"diagnostic": true'), ('"completed": 1', '"completed": 0'),
                ('"registrations": 0', '"registrations": 1'), ('"groups": 4', '"groups": 1'),
                ('"mode": "views"', '"mode": "native"')):
            path.write_text(old.replace(old_text, new_text))
            with self.assertRaises(AssertionError): module.analyze(self.root)
        path.write_text(old)


if __name__ == "__main__": unittest.main()
