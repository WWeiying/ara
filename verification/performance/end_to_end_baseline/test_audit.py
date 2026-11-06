import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from audit import agrees, verify_collection, verify_pins


class EvidenceTests(unittest.TestCase):
    def test_recorded_subset(self):
        agrees({"cycles": 5}, {"cycles": 5, "extra": True})
        with self.assertRaises(ValueError):
            agrees({"cycles": 6}, {"cycles": 5})

    def test_empty_pins_rejected(self):
        with self.assertRaises(ValueError):
            verify_pins({})

    def test_pin_drift_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "source"
            path.write_bytes(b"source")
            verify_pins({str(path): hashlib.sha256(b"source").hexdigest()})
            with self.assertRaises(ValueError):
                verify_pins({str(path): "0" * 64})

    def test_bad_collections(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "data").write_bytes(b"data")
            sha = hashlib.sha256(b"data").hexdigest()
            metadata = dict(pins=[dict(expected="a", actual="a")],
                            files=[dict(relative="data", sha256=sha)])
            receipt = dict(root=str(root), hashes_checked=True, metadata=metadata)
            (root / "result.json").write_text(json.dumps(dict(worker_source_pins_match=True)))
            (root / "source-pins.json").write_text(json.dumps({str(root / "data"): sha}))
            def run():
                (root / "collection_receipt.json").write_text(json.dumps(receipt))
                return verify_collection(root)
            self.assertEqual(run()[2]["artifacts"], 1)
            for relative in ("../outside", "/tmp/outside"):
                metadata["files"][0]["relative"] = relative
                with self.assertRaises(ValueError):
                    run()
            metadata["files"][0]["relative"] = "data"
            metadata["files"] *= 2
            with self.assertRaises(ValueError):
                run()
            metadata["files"] = [dict(relative="data", sha256="0" * 64)]
            with self.assertRaises(ValueError):
                run()


if __name__ == "__main__":
    unittest.main()
