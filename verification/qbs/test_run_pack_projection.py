import copy
import json
from pathlib import Path
import tempfile
import unittest

from run_half_scale_soc import digest
from run_pack_projection import functional_gate


class PackGateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source.h"
        self.source.write_text("sealed\n")
        (self.root / "manifest.json").write_text(json.dumps({str(self.source): digest(self.source)}))
        self.state = dict(state="PASS", child_pid=None, cases=[])
        for vlen, avl in ((128, 0), (1024, 0), (1024, 7)):
            elf = self.root / f"init-avl{avl}"
            elf.write_bytes(b"pinned ELF")
            log = self.root / f"vlen{vlen}-avl{avl}.log"
            log.write_text(f"PACK_CANDIDATE_PASS cases=33264 rvv=1 avl_limit={avl} invalid=14\n"
                           "PACK_GUEST_EXIT=0\n")
            self.state["cases"].append(dict(vlen=vlen, avl_limit=avl, cases=33264,
                                          elf_sha256=digest(elf), log_sha256=digest(log)))

    def test_complete_gate(self):
        functional_gate(self.root, self.state)

    def test_partial_or_failed_not_dispatched(self):
        for key, value in (("state", "FAIL"), ("child_pid", 1), ("cases", self.state["cases"][:2])):
            altered = copy.deepcopy(self.state)
            altered[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                functional_gate(self.root, altered)

    def test_source_drift(self):
        self.source.write_text("modified\n")
        with self.assertRaises(ValueError):
            functional_gate(self.root, self.state)

    def test_elf_drift(self):
        (self.root / "init-avl0").write_bytes(b"another ELF")
        with self.assertRaises(ValueError):
            functional_gate(self.root, self.state)

    def test_false_pass_marker(self):
        log = self.root / "vlen128-avl0.log"
        log.write_text(log.read_text() + "PACK_CANDIDATE_FAIL\n")
        self.state["cases"][0]["log_sha256"] = digest(log)
        with self.assertRaises(ValueError):
            functional_gate(self.root, self.state)


if __name__ == "__main__":
    unittest.main()
