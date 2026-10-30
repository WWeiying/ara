import json
from pathlib import Path
import tempfile
import unittest

from audit_runtime_activation_pack import CONFIGURATIONS, audit
from run_half_scale_soc import digest, hashes


class NativePackingAuditTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        sentinel = self.root / "source.c"
        sentinel.write_text("sealed input")
        self.write("manifest.json", hashes([sentinel]))
        self.state = dict(state="PASS", child_pid=None, cases=[])
        for mode, vlen, avl in CONFIGURATIONS:
            name = f"{mode}-avl{avl}"
            elf = self.root / f"init-{name}"
            elf.write_bytes(name.encode())
            log = self.root / f"vlen{vlen}-{name}.log"
            log.write_text("RUNTIME_PACK_PASS cases=10752 invalid=8 bytes=exact "
                           "guards=exact fcsr_vcsr=exact\nRUNTIME_PACK_GUEST_EXIT=0\n")
            self.state["cases"].append(dict(mode=mode, vlen=vlen, avl_limit=avl,
                cases=10752, invalid_cases=8, log_sha256=digest(log), elf_sha256=digest(elf)))
        self.write("status.json", self.state)

    def write(self, name, value):
        (self.root / name).write_text(json.dumps(value))

    def test_complete(self):
        result = audit(self.root)
        self.assertEqual((result["layout_checks"], result["invalid_checks"]), (43008, 32))

    def test_rejects_running(self):
        self.write("status.json", {**self.state, "child_pid": 123})
        with self.assertRaises(ValueError):
            audit(self.root)

    def test_rejects_missing_mode(self):
        self.state["cases"].pop()
        self.write("status.json", self.state)
        with self.assertRaises(ValueError):
            audit(self.root)

    def test_rejects_changed_source(self):
        (self.root / "source.c").write_text("changed")
        with self.assertRaises(ValueError):
            audit(self.root)

    def test_rejects_changed_log(self):
        (self.root / "vlen128-vector-avl0.log").write_text("incomplete")
        with self.assertRaises(ValueError):
            audit(self.root)


if __name__ == "__main__":
    unittest.main()
