import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from audit_m4_prepare_soc import audit
from run_half_scale_soc import digest
from run_m4_prepare_soc import check_result


class AuditM4PreparationTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "soc/work").mkdir(parents=True)
        text = "".join(
            f"M4_SOC trial={i} path={p} cycles={c} flags=1 used={u}\n"
            for i, p, c, u in ((0, "generic", 100, 0), (1, "vector", 60, 1),
                               (2, "vector", 60, 1), (3, "generic", 100, 0)))
        text += "M4_SOC_RESULT errors=0 bytes=3808 inputs=3584 k=896 calls=4 golden=linux_ggml\n"
        log = self.root / "soc/work/run.vcs.log"
        log.write_text(text)
        self.write("manifest.json", {})
        self.write("status.json", {"state": "PASS"})
        self.write("result.json", dict(state="PASS", trials=check_result(text),
                   generic_sum_cycles=200, vector_sum_cycles=120, log_sha256=digest(log)))
        self.write("soc/uvm_result.json", dict(status="PASS", issues=[],
                   log_sha256=digest(log), elf_sha256="elf", simv_sha256="image"))

    def write(self, name, value):
        (self.root / name).write_text(json.dumps(value))

    def test_recomputed_ratio(self):
        self.assertEqual(audit(self.root)["preparation_speedup"], 200 / 120)

    def test_rejects_failed_protocol_and_stale_report(self):
        for key, value in (("status", "FAIL"), ("issues", ["bad response"]),
                           ("log_sha256", "unrelated")):
            file = self.root / "soc/uvm_result.json"
            old = json.loads(file.read_text())
            self.write("soc/uvm_result.json", {**old, key: value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                audit(self.root)
            self.write("soc/uvm_result.json", old)

    def test_rejects_cycle_corruption(self):
        old = json.loads((self.root / "result.json").read_text())
        self.write("result.json", {**old, "vector_sum_cycles": 1})
        with self.assertRaises(ValueError):
            audit(self.root)

    def test_rejects_input_drift(self):
        with patch("audit_m4_prepare_soc.hashes", return_value={"source": "changed"}):
            with self.assertRaises(ValueError):
                audit(self.root)


if __name__ == "__main__":
    unittest.main()
