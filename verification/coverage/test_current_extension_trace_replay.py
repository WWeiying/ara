"""Focused offline negative fixtures; no VCS/DVE invocation."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import current_extension_trace_replay as r


class ExtensionTests(unittest.TestCase):
    def test_exact_population_ancestor_failure_and_foreign_image_rejected(self):
        state = dict(status="COMPLETE",coverage_status="COMPLETE",phase="complete",image="old",
            live_rtl_reverted=False,baseline_passed=654,aggregate_passed=655,new_passed=1,
            cases={"pass":dict(status="PASS"),"vgap76_red16":dict(status="FAIL")})
        args = (76,("pass","vgap76_red16"),655,654,Path("/parent"),"old")
        self.assertEqual(r.check_state(state,*args),["pass"])
        changes = [dict(image="new"),dict(aggregate_passed=656),dict(baseline_passed=True),
                   dict(baseline_directory="/other"),dict(status="RUNNING"),dict(new_passed=2)]
        for change in changes:
            with self.assertRaises(ValueError):
                r.check_state(dict(state,**change),*args)
        changed = copy.deepcopy(state)
        changed["cases"]["vgap76_red16"]["status"] = "PASS"
        with self.assertRaises(ValueError):
            r.check_state(changed,*args)

    def test_red32_is_not_a_strict_pass(self):
        profiles = [dict(name="case%d"%i) for i in range(32)]+[dict(name=r.RED32)]
        self.assertEqual(len(r.select_cases(profiles,[])),32)
        for names in ([r.RED32],["missing"],["case0","case0"]):
            with self.assertRaises(ValueError):
                r.select_cases(profiles,names)
        proof = r.red32_integer_math()
        self.assertEqual(proof["reduction_instances"],14)
        self.assertFalse(proof["admitted"])
        self.assertFalse(proof["bit_exact_writeback_proven"])
        self.assertIsNone(proof["rounding_tolerance"])
        self.assertTrue(all(x["partial_sum_abs_bound"]<=130 for x in proof["cases"]))

    def test_non_bit_exact_and_unknown_remain_strictly_rejected(self):
        scalar = dict(status="TERMINAL_TOHOST_MATCH",mismatch=None)
        vector = dict(status="PASS",nr_lanes=4,vlen_bits=1024,compared_bytes=1,selected_index=None,
            first_mismatch=None,stopped_at_spike_index=None,skipped_unknown_bytes=0,
            non_bit_exact_instructions=0,incomplete_requests=[],unretired_requests=[],trapped_requests=[])
        r.admission.validate_comparisons(scalar,vector)
        for change in (dict(non_bit_exact_instructions=14),dict(skipped_unknown_bytes=112),
                       dict(selected_index=1),dict(unretired_requests=[1])):
            with self.assertRaises(ValueError):
                r.admission.validate_comparisons(scalar,dict(vector,**change))
        with self.assertRaises(ValueError):
            r.admission.validate_comparisons(dict(scalar,status="PREFIX"),vector)

    def test_conflicting_shared_pins_rejected(self):
        pins = {"/old":"a"}
        with self.assertRaises(ValueError):
            r.merge_pins(pins,{"/old":"b"})

    def test_historical_revision_hold_does_not_relax_runtime_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/"historical.py"
            source.write_text("current bytes")
            runtime = Path(directory)/"input.elf"
            runtime.write_text("actual runtime bytes")
            old = "0"*64
            pins = {str(source):old,str(runtime):old}
            with patch.object(r,"HISTORICAL_MUTABLE_SOURCES",{str(source)}):
                verified, held = r.partition_source_pins(pins)
            self.assertEqual(held[str(source)]["historical_sha256"],old)
            self.assertFalse(held[str(source)]["historical_bytes_verified"])
            self.assertEqual(verified,{str(runtime):old})
            self.assertEqual(pins[str(source)],old)
            with self.assertRaises(ValueError):
                r.admission.FileSeal().hashes(verified)

    def test_actual_fixed_population_and_signature_binding_only(self):
        count = 0
        for gap,names,_ in r.admission.EXTENSIONS:
            path = r.OUT/("gap%d-old-image-20261006-01"%gap)
            state = r.admission.old.prior.jread(path/"status.json")
            for name in names:
                if name == "vgap76_red16":
                    continue
                self.assertEqual(state["cases"][name]["status"],"PASS")
                symbols = r.admission.elf_symbols((path/"results"/name/"input.elf").read_bytes())
                self.assertGreaterEqual(abs(symbols["tohost"]-symbols["g75_result"]),8)
                count += 1
        self.assertEqual(count,33)

    def test_worker_partial_error_and_private_drift_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            file = p/"log"
            file.write_text("original")
            profile = dict(name="fixture",directory=str(p),tree_root=str(p),state_row={},source_pins={},
                input_sha256={str(file):r.admission.sha_bytes(file.read_bytes())})
            with patch.object(r.admission,"audit_case",side_effect=ValueError("PREFIX")):
                self.assertEqual(r.replay(profile,{},5)["status"],"FAILED_DIAGNOSTIC_ONLY")
            file.write_text("changed")
            result = r.replay(profile,{},5)
            self.assertEqual(result["status"],"FAILED_DIAGNOSTIC_ONLY")
            self.assertIn("SHA differs",result["reason"])
            self.assertFalse(result["admitted687"])

    def test_extra_private_file_and_no_tools_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            file = p/"log"
            file.write_text("bound")
            profile = dict(name="fixture",directory=str(p),tree_root=str(p),state_row={},source_pins={},
                input_sha256={str(file):r.admission.sha_bytes(file.read_bytes())})
            (p/"extra").write_text("unbound")
            self.assertIn("inventory changed",r.replay(profile,{},5)["reason"])
        import subprocess
        with r.admission.old.no_tools(), self.assertRaises(RuntimeError):
            subprocess.Popen(["simv"])

    def test_deadlines_and_workers_bounded(self):
        with self.assertRaises(TimeoutError):
            r.timeout(0,None)
        for workers,seconds in ((9,300),(0,300),(True,300),(8,601),(8,0)):
            with self.assertRaises(ValueError):
                r.check("/nonexistent","0"*64,workers,seconds)


if __name__ == "__main__":
    unittest.main()
