import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import old_image_source_snapshot as snapshot_module
from old_image_source_snapshot import validate


class SourceSnapshotTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[2]
        source = self.root / "verification/out/old-image-source-evidence-20261006-01"
        if not source.exists():
            self.skipTest("recovered evidence unavailable")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.snapshot = Path(self.tmp.name) / "snapshot"
        shutil.copytree(source, self.snapshot)

    def alter_manifest(self, change):
        p = self.snapshot / "manifest.json"
        data = json.loads(p.read_text())
        change(data)
        p.write_text(json.dumps(data))

    def test_real_three_source_bytes(self):
        result = validate(self.root, self.snapshot)
        self.assertEqual(len(result["source_aliases"]), 3)
        self.assertFalse(result["admission_approved"])

    def test_extra_source_rejected(self):
        self.alter_manifest(lambda d: d["files"].append(d["files"][0]))
        with self.assertRaises(ValueError):
            validate(self.root, self.snapshot)

    def test_path_escape_rejected(self):
        self.alter_manifest(lambda d: d["files"][0].update(snapshot_file="../ara_dispatcher.sv"))
        with self.assertRaises(ValueError):
            validate(self.root, self.snapshot)

    def test_changed_source_rejected(self):
        p = self.snapshot / "ara_dispatcher.sv"
        p.write_bytes(p.read_bytes() + b"\n")
        with self.assertRaises(ValueError):
            validate(self.root, self.snapshot)

    def test_symlink_rejected(self):
        p = self.snapshot / "ara_dispatcher.sv"
        renamed = p.with_suffix(".saved")
        p.rename(renamed)
        p.symlink_to(renamed)
        with self.assertRaises(ValueError):
            validate(self.root, self.snapshot)

    def test_same_bytes_replaced_entity_rejected(self):
        original_digest = snapshot_module.digest
        replaced = False

        def digest_and_replace(path):
            nonlocal replaced
            value = original_digest(path)
            if path.name == "sldu.sv" and not replaced:
                replacement = path.with_suffix(".replacement")
                replacement.write_bytes(path.read_bytes())
                replacement.replace(path)
                replaced = True
            return value

        with patch.object(snapshot_module, "digest", side_effect=digest_and_replace):
            with self.assertRaisesRegex(ValueError, "file replaced"):
                validate(self.root, self.snapshot)
        self.assertTrue(replaced)


if __name__ == "__main__":
    unittest.main()
