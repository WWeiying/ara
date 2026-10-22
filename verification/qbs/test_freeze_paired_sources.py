import json
import tempfile
import unittest
from pathlib import Path

from freeze_paired_sources import check, digest, freeze


class FreezePairedSourcesTest(unittest.TestCase):
    def test_snapshot_preserves_data_and_rebinds_akv_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apps = []
            for kind in ("qbs", "rvv"):
                app = root / kind
                (app / "generated").mkdir(parents=True)
                (app / "case.json").write_text('{"weight_type":"q4_K"}')
                for name in ("source_weight.bin", "activation_f32.bin", "golden_f32.bin"):
                    (app / "generated" / name).write_bytes(name.encode())
                apps.append(app)
            capture = root / "tensor.bin"
            capture.write_bytes(b"captured data")
            assembly = root / "akv.S"
            assembly.write_text(f'.incbin "{capture}"\n')
            elf = root / "akv.elf"
            elf.write_bytes(b"ELF")
            runner = root / "runner.sh"
            runner.write_bytes(b"archived runner")
            manifest = root / "pairs.json"
            manifest.write_text(json.dumps({
                "schema_version": 1,
                "qbs_pairs": [{"qbs_app": str(apps[0]), "rvv_app": str(apps[1])}],
                "akv_pair": {"rvv_asm": str(assembly), "akv_asm": str(assembly),
                             "rvv_elf": str(elf), "akv_elf": str(elf)},
            }))
            output = root / "frozen"
            evidence = freeze(manifest, runner, output)
            frozen = json.loads((output / "paired_manifest.json").read_text())
            self.assertEqual(evidence["status"], "PASS")
            self.assertEqual(digest(output / "captures/tensor.bin"), digest(capture))
            self.assertEqual(digest(Path(frozen["qbs_pairs"][0]["qbs_app"]) /
                                    "generated/source_weight.bin"),
                             digest(apps[0] / "generated/source_weight.bin"))
            self.assertIn(str(output / "captures/tensor.bin"),
                          Path(frozen["akv_pair"]["akv_asm"]).read_text())
            self.assertEqual(check(output), [])
            capture.unlink()
            self.assertTrue((output / "captures/tensor.bin").is_file())
            (output / "captures/tensor.bin").write_bytes(b"altered")
            self.assertTrue(check(output))
            with self.assertRaises(ValueError):
                freeze(manifest, runner, output)


if __name__ == "__main__":
    unittest.main()
