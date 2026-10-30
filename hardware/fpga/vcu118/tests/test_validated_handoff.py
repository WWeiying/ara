"""Keep the pinned handoff's integrated dispatcher adaptations unchanged."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from dispatcher_fpga import patch_dispatcher_layout
from dispatcher_control_fpga import patch_dispatcher_control
from export import patch_akv_byte_counts, patch_dispatcher_vlen_casts, patch_qbs_fault_decode
from prepare import FPGA_TARGETS


class ValidatedHandoffTests(unittest.TestCase):
    def test_export_retains_implicit_bender_target_defines(self):
        manifest = json.loads((HERE.parent / "ara_dsa_vcu118/manifest.json").read_text())
        for target in FPGA_TARGETS:
            self.assertIn("TARGET_" + target.upper(), manifest["defines"])
        self.assertEqual(manifest["defines"]["VLEN"], 1024)
        self.assertEqual(manifest["defines"]["NR_LANES"], 4)
        self.assertTrue({"TARGET_SRAM_MC", "FOR_VERIFY", "IDEAL_DISPATCHER"}.isdisjoint(
            manifest["defines"]))

    def test_full_ara_export_matches_pinned_source_and_adaptations(self):
        package = HERE.parent / "ara_dsa_vcu118"
        manifest = json.loads((package / "manifest.json").read_text())
        transforms = {
            "hardware/src/vlsu/qbs/qbs_engine.sv": patch_qbs_fault_decode,
            "hardware/src/vlsu/akv/akv_engine.sv": patch_akv_byte_counts,
        }
        checked = set()
        for record in manifest["source_hashes_before_integration"]:
            relative = record["file"]
            if not relative.startswith("rtl/ara/hardware/"):
                continue
            source = relative.removeprefix("rtl/ara/")
            raw = (ROOT / source).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), record["source_sha256"], source)
            expected = transforms.get(source, lambda text: text)(raw.decode()).encode()
            self.assertEqual((package / relative).read_bytes(), expected, source)
            checked.add(relative)
        self.assertEqual(len(checked), 68)
        for name in ("qbs_akv_shared_reader", "akv/akv_refill_order_guard",
                     "akv/akv_legacy_repacker", "akv/akv_q_store",
                     "akv/akv_unified_context", "qbs/qbs_half_scale",
                     "qbs/qbs_seed_stream_router", "qbs/qbs_vrf_seed_mapper"):
            relative = "rtl/ara/hardware/src/vlsu/" + name + ".sv"
            self.assertIn(relative, checked)
            self.assertIn(relative, manifest["files"])

    def test_integration_provenance_replays_on_delivery_tag(self):
        package = HERE.parent / "ara_dsa_vcu118"
        patch = (package / "provenance/integration.patch").read_text()
        blocks = re.split(r"(?=^--- a/)", patch, flags=re.M)
        patched = set()
        with tempfile.TemporaryDirectory() as directory:
            for block in blocks:
                match = re.match(r"--- a/(rtl/ara/[^\n]+)\n", block)
                if not match:
                    continue
                relative = match[1]
                target = Path(directory) / relative
                if relative not in patched:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    raw = subprocess.check_output([
                        "git", "show", "qbs-akv-validated-20261029:" +
                        relative.removeprefix("rtl/ara/")], cwd=ROOT)
                    target.write_bytes(raw)
                subprocess.run(["git", "apply", "--whitespace=error", "-"],
                               input=block, text=True, cwd=directory,
                               check=True, capture_output=True)
                patched.add(relative)
            self.assertEqual(patched, {
                "rtl/ara/hardware/src/vlsu/qbs/qbs_engine.sv",
                "rtl/ara/hardware/src/vlsu/akv/akv_engine.sv",
            })
            for relative in patched:
                self.assertEqual((Path(directory) / relative).read_bytes(),
                                 (package / relative).read_bytes())

    def test_integrated_helpers_match_reviewed_predecessor(self):
        path = "hardware/src/ara_dispatcher.sv"
        current = (ROOT / path).read_text()
        prior = subprocess.check_output(
            ["git", "show", "5ee02215:" + path], cwd=ROOT, text=True)
        for name in ("slide_bound", "slidedown_source_start", "slidedown_source_end",
                     "active_register_mask", "active_register_count",
                     "active_group_needs_reshuffle", "active_group_has_mixed_eew"):
            pattern = r"  function automatic [^\n]*\b" + name + r"\(.*?  endfunction : " + name
            before = re.findall(pattern, prior, re.S)
            after = re.findall(pattern, current, re.S)
            self.assertEqual(len(before), 1, name)
            self.assertEqual(after, before, name)

    def test_exact_handoff_passes_without_rewriting(self):
        source = (ROOT / "hardware/src/ara_dispatcher.sv").read_text()
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),
                         "7bd7b46c87e2821e349d7c8938870ac79b2a77bf31eb3525fa07b904fc4eadf8")
        for transform in (patch_dispatcher_vlen_casts, patch_dispatcher_layout,
                          patch_dispatcher_control):
            self.assertEqual(transform(source), source)

    def test_unreviewed_revisions_still_fail_closed(self):
        source = (ROOT / "hardware/src/ara_dispatcher.sv").read_text()
        for transform in (patch_dispatcher_layout, patch_dispatcher_control):
            for changed in (source + "\n", source.replace("if (arch_decode)", "if (1'b1)")):
                self.assertNotEqual(changed, source)
                with self.assertRaises(RuntimeError):
                    transform(changed)


if __name__ == "__main__":
    unittest.main()
