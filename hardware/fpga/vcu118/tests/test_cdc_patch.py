#!/usr/bin/env python3
"""Frozen FIFO patch replay and evidence checks, without updating main RTL."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cdc_fpga import OLD_READ, OLD_WRITE, NEW_READ, NEW_WRITE, patch_fifo_selectors
from prepare import ROOT


class CdcPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pkg = ROOT / "hardware/fpga/ara_dsa_vcu118"
        cls.rel = "rtl/common_cells/src/cdc_fifo_gray.sv"
        cls.raw = subprocess.check_output([
            "git", "show", "4d5a4b02:hardware/fpga/ara_dsa_vcu118/" + cls.rel], cwd=ROOT, text=True)

    def test_exact_export_replay(self):
        self.assertEqual(patch_fifo_selectors(self.raw), (self.pkg / self.rel).read_text())

    def test_only_local_data_selectors_change(self):
        patched = patch_fifo_selectors(self.raw)
        self.assertEqual(patched.replace(NEW_READ, OLD_READ).replace(NEW_WRITE, OLD_WRITE), self.raw)
        self.assertEqual(patched.count('DONT_TOUCH = "TRUE"'), 2)
        self.assertEqual(patched.count("LOG_DEPTH == 5 && $bits(T) >= 128"), 2)

    def test_unreviewed_protocol_is_rejected(self):
        for text in ("", self.raw.replace("PtrFull", "Changed"), patch_fifo_selectors(self.raw)):
            with self.assertRaises(RuntimeError): patch_fifo_selectors(text)

    def test_whole_vector_storage_owners(self):
        self.assertNotIn("data_q[word_idx]", NEW_WRITE)
        self.assertIn("logic [Bits-1:0] word_q;", NEW_WRITE)
        self.assertIn("word_q <= '0;", NEW_WRITE)
        self.assertIn("word_q <= src_bits[s*Slice +: Bits];", NEW_WRITE)
        self.assertIn("assign data_bits[word_idx*Width+s*Slice +: Bits] = word_q;", NEW_WRITE)
        self.assertIn("assign data_q = data_bits;", NEW_WRITE)
        self.assertNotIn("async_data_i[word_idx]", NEW_READ)
        self.assertIn("assign dst_data = selected_bits;", NEW_READ)

    def test_provenance_replays(self):
        blocks = re.split(r"(?=^--- a/)", (self.pkg / "provenance/integration.patch").read_text(), flags=re.M)
        patch = "".join(b for b in blocks if b.startswith("--- a/" + self.rel + "\n"))
        self.assertTrue(patch)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / self.rel
            target.parent.mkdir(parents=True)
            target.write_text(self.raw)
            subprocess.run(["git", "apply", "--whitespace=nowarn", "-"], input=patch,
                           text=True, cwd=directory, check=True, capture_output=True)
            self.assertEqual(target.read_text(), (self.pkg / self.rel).read_text())

    def test_measured_evidence_matches(self):
        directory = ROOT / "hardware/fpga/vcu118/results/20260916_cdc_storage"
        record = json.loads((directory / "result.json").read_text())
        for name, digest in record["inputs"].items():
            self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), digest, name)
        log = (directory / "run.txt").read_bytes()
        self.assertEqual(hashlib.sha256(log).hexdigest(), record["run_sha256"])
        self.assertEqual(log.count(b"PASS FIFO "), 9)
        self.assertIn(b"PASS: all FIFO comparisons", log)


if __name__ == "__main__":
    unittest.main()
