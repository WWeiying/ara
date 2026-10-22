"""Offline fixtures only; no simulation or real201 replay."""
import copy
import struct
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import current_random_trace_replay as r


def elf_fixture():
    names = b"\0tohost\0__ara_vector_signature_exit_ecall\0"
    shoff, strings = 64, 64 + 5 * 64
    symbols = strings + len(names)
    text = symbols + 72
    blob = bytearray(text + 8)
    blob[:6] = b"\x7fELF\x02\x01"
    struct.pack_into("<HHIQQQIHHHHHH", blob, 16, 2, 243, 1, 0x80000000, 0, shoff,
                     0, 64, 56, 0, 64, 5, 0)
    struct.pack_into("<IIQQQQIIQQ", blob, shoff + 64, 0, 1, 6, 0x80000000, text, 8, 0, 0, 4, 0)
    struct.pack_into("<IIQQQQIIQQ", blob, shoff + 128, 0, 3, 0, 0, strings, len(names), 0, 0, 1, 0)
    struct.pack_into("<IIQQQQIIQQ", blob, shoff + 192, 0, 2, 0, 0, symbols, 72, 2, 0, 8, 24)
    struct.pack_into("<IIQQQQIIQQ", blob, shoff + 256, 0, 8, 3, 0x80002000, 0, 8, 0, 0, 8, 0)
    blob[strings:symbols] = names
    struct.pack_into("<IBBHQQ", blob, symbols + 24, 1, 0x11, 0, 4, 0x80002000, 8)
    struct.pack_into("<IBBHQQ", blob, symbols + 48, 8, 0x10, 0, 1, 0x80000004, 0)
    struct.pack_into("<II", blob, text, 0x13, 0x73)
    return bytes(blob)


def with_symbols(extra, names=b"$d\0"):
    original = elf_fixture()
    shoff = 64
    strings = 384
    old_names = b"\0tohost\0__ara_vector_signature_exit_ecall\0"
    old_symbols = strings+len(old_names)
    old_text = old_symbols+72
    new_symbols = old_symbols+len(names)
    new_text = new_symbols+72+24*len(extra)
    blob = bytearray(new_text+8)
    blob[:strings] = original[:strings]
    blob[strings:new_symbols] = old_names+names
    blob[new_symbols:new_symbols+72] = original[old_symbols:old_text]
    for i, (name, info, index, value, size) in enumerate(extra):
        struct.pack_into("<IBBHQQ", blob, new_symbols+72+24*i, name, info, 0, index, value, size)
    blob[new_text:] = original[old_text:]
    struct.pack_into("<Q", blob, shoff+64+24, new_text)
    struct.pack_into("<Q", blob, shoff+128+32, len(old_names)+len(names))
    struct.pack_into("<Q", blob, shoff+192+24, new_symbols)
    struct.pack_into("<Q", blob, shoff+192+32, 72+24*len(extra))
    return bytes(blob), len(old_names)


class ElfTests(unittest.TestCase):
    def test_repeated_mapping_labels_not_evidence(self):
        _, name = with_symbols([])
        blob, _ = with_symbols([(name,0,1,0x80000000,0),(name,0,4,0x80002000,0)])
        meta = r.elf_metadata(blob)
        self.assertNotIn("$d", meta["symbols"])
        self.assertEqual(meta["exit_pc"], 0x80000004)

    def test_mapping_exemption_cannot_hide_global_or_other_local_conflicts(self):
        for label, info in ((b"$d\0",0x10),(b"$x\0",0x10),(b"ordinary_local\0",0),
                            (b"ordinary_global\0",0x10),(b"$dont_ignore\0",0)):
            _, name = with_symbols([],label)
            blob, _ = with_symbols([(name,info,1,0x80000000,0),
                                    (name,info,4,0x80002000,0)],label)
            with self.assertRaisesRegex(ValueError,"Ambiguous ELF symbol"):
                r.elf_metadata(blob)

    def test_important_duplicate_undefined_and_wrong_section_reject(self):
        for extra in ([(1,0x11,4,0x80002004,0)], [(1,0x11,0,0x80002000,8)],
                      [(1,0x11,1,0x80002000,8)], [(8,0x10,1,0x80000000,0)]):
            blob, _ = with_symbols(extra)
            with self.assertRaises(ValueError):
                r.elf_metadata(blob)
        for label in (b"__ara_vector_checkpoint_0_start\0", b"region_0\0", b"__ara_region_0_end\0"):
            _, name = with_symbols([],label)
            blob, _ = with_symbols([(name,0,4,0x80002000,0),(name,0,4,0x80002004,0)],label)
            with self.assertRaisesRegex(ValueError,"Ambiguous ELF symbol"):
                r.elf_metadata(blob)

    def test_exit_and_tohost_derived_from_elf_not_saved_comparison(self):
        meta = r.elf_metadata(elf_fixture())
        self.assertEqual(meta["entry"], 0x80000000)
        self.assertEqual(meta["tohost"], 0x80002000)
        self.assertEqual(meta["exit_pc"], 0x80000004)

    def test_bad_machine_truncation_or_non_ecall_reject(self):
        original = elf_fixture()
        bad_machine = bytearray(original)
        struct.pack_into("<H", bad_machine, 18, 62)
        bad_exit = bytearray(original)
        bad_exit[-4:] = b"\0" * 4
        for blob in (original[:80], bytes(bad_machine), bytes(bad_exit)):
            with self.assertRaises(ValueError):
                r.elf_metadata(blob)


def comparison():
    scalar = dict(status="TERMINAL_MATCH", mismatch=None, matched_instructions=2720,
        ara_committed_instructions=2720, stopped_at_unobservable=None,
        terminal_ecall=dict(instruction="0x00000073", trap=True), aligned_vector_faults=[])
    vector = dict(status="PASS", nr_lanes=4, vlen_bits=1024, selected_index=None,
        stopped_at_spike_index=None, incomplete_requests=[], unretired_requests=[],
        vector_destination_requests=236, prefix_vector_destination_requests=236,
        compared_instructions=236, compared_bytes=11925, skipped_unknown_bytes=14179,
        non_bit_exact_instructions=0, trapped_requests=[], verified_trapped_destination_requests=[],
        verified_zero_write_traps=[], verified_identity_write_traps=[], verified_probed_load_faults=[],
        first_mismatch=None)
    return scalar, vector


class VerdictTests(unittest.TestCase):
    def test_isa_unknown_allowed_and_scalar_and_full_accounting_required(self):
        scalar, vector = comparison()
        r.strict_verdict(scalar, vector)
        variants = [(dict(scalar, status="PREFIX"), vector),
                    (dict(scalar, matched_instructions=2719), vector),
                    (scalar, dict(vector, selected_index=1)),
                    (scalar, dict(vector, incomplete_requests=[1])),
                    (scalar, dict(vector, compared_instructions=235)),
                    (scalar, dict(vector, non_bit_exact_instructions=1)),
                    (scalar, dict(vector, first_mismatch={"reason": "active byte"}))]
        for s, v in variants:
            with self.assertRaises(ValueError):
                r.strict_verdict(s, v)

    def test_unknown_active_byte_rejects_but_agnostic_bitmask_allows(self):
        self.assertEqual(r.require_known_active(None, 0, True), "ISA_UNKNOWN")
        with self.assertRaisesRegex(ValueError, "active unknown"):
            r.require_known_active(None, 255, True)
        with self.assertRaisesRegex(ValueError, "reference"):
            r.require_known_active(1, 255, False)


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.artifact = Path("/fixtures/results/case/tests/seed1417")
        self.meta = r.elf_metadata(elf_fixture())
        self.case = dict(source_name="seed1417", seed=1417, watchdog_cycles=100000,
            spike="/fixtures/spike", contract=dict(isa="rv64gcv_zvfh_zvl1024b"), fault_vstart_probe=False)
        a = self.artifact
        self.rtl = dict(cwd=str(a), command=["/fixtures/coverage_simv", "-l", "run.vcs.log",
            "+ntb_random_seed=1417", "+PRELOAD="+str(a/"input.elf"), "+TESTCASE=seed1417", "+NO_FSDB",
            "+COMMIT_TRACE="+str(a/"ara_commit_trace.csv"), "+VECTOR_TRACE="+str(a/"ara_vector_trace.csv"),
            "+COMMIT_WATCHDOG=100000", "+COMMIT_TOHOST=0000000080002000", "+COMMIT_EXIT_PC=0000000080000004"])
        self.spike = dict(cwd=str(a), command=["/fixtures/spike", "--isa=rv64gcv_zvfh_zvl1024b",
            "--log-commits", "--log="+str(a/"spike_commit.log"), str(a/"input.elf")])

    def test_exact_replay_command_and_symbol_binding(self):
        r.validate_commands(self.artifact, self.case, self.meta, self.rtl, self.spike, "/fixtures/coverage_simv")

    def test_duplicate_wrong_exit_foreign_trace_and_weakened_spike_reject(self):
        for arg in ("+COMMIT_EXIT_PC=0000000080000008", "+COMMIT_TRACE=/foreign/trace", "+TESTCASE=other"):
            changed = copy.deepcopy(self.rtl)
            key = arg.split("=", 1)[0] + "="
            changed["command"] = [arg if x.startswith(key) else x for x in changed["command"]]
            with self.assertRaises(ValueError):
                r.validate_commands(self.artifact, self.case, self.meta, changed, self.spike, "/fixtures/coverage_simv")
        changed = copy.deepcopy(self.rtl)
        changed["command"].append(changed["command"][-1])
        with self.assertRaises(ValueError):
            r.validate_commands(self.artifact, self.case, self.meta, changed, self.spike, "/fixtures/coverage_simv")
        changed = copy.deepcopy(self.spike)
        changed["command"].remove("--log-commits")
        with self.assertRaises(ValueError):
            r.validate_commands(self.artifact, self.case, self.meta, self.rtl, changed, "/fixtures/coverage_simv")


class InventoryTests(unittest.TestCase):
    def test_collection_pins_ledger_and_tampering_rejects(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            ledger = base/"all-passed-outcomes.json"
            ledger.write_text('[{"status":"PASS"}]')
            collection = base/"collection.json"
            collection.write_text(r.json.dumps(dict(reports={str(ledger):r.admission.sha_bytes(ledger.read_bytes())})))
            identity = {"collection.json":r.admission.sha_bytes(collection.read_bytes())}
            with patch.object(r.admission.old, "CURRENT", base), patch.object(r, "LEDGER", ledger), \
                 patch.object(r.admission.old, "IDENTITY", identity):
                self.assertEqual(r.bound_ledger(r.admission.FileSeal()), [{"status":"PASS"}])
                ledger.write_text('[]')
                with self.assertRaises(Exception):
                    r.bound_ledger(r.admission.FileSeal())
                collection.write_text('{}')
                with self.assertRaises(Exception):
                    r.bound_ledger(r.admission.FileSeal())

    def test_bounded_representative_selection(self):
        rows = [dict(name="r0", vdb="/a/seed1417/code.vdb"), dict(name="r1", vdb="/a/seed2/code.vdb")]
        self.assertEqual(r.choose_rows(rows), rows[:1])
        self.assertEqual(r.choose_rows(rows, ["seed1417"]), rows[:1])
        for names, limit in ((["missing"], 1), (["r0", "seed1417"], 2),
                             (["r0", "r1"], 1), ([], 0), ([], True)):
            with self.assertRaises(ValueError):
                r.choose_rows(rows, names, limit)

    def test_exact201_membership_and_duplicate_missing_fail_reject(self):
        rows = [dict(name="r%d" % i, vdb="/vdb/%d" % i, kind="random" if i < 186 else "replay",
                     status="PASS", passed_only=True, reused=False, vdb_valid=True, returncode=0)
                for i in range(201)]
        inputs = ["/design", *[r["vdb"] for r in rows], *["/other/%d" % i for i in range(486)]]
        self.assertEqual(r.select201(inputs, rows), rows)
        for changed in (inputs[:-1], inputs[:-1]+[inputs[1]]):
            with self.assertRaises(ValueError):
                r.select201(changed, rows)
        changed = copy.deepcopy(rows)
        changed[0]["status"] = "FAIL"
        with self.assertRaises(ValueError):
            r.select201(inputs, changed)

    def test_real_inventory_only_no_replay(self):
        inputs = (r.BASELINE/"combined-inputs.txt").read_text().splitlines()
        rows = r.json_read(r.LEDGER)
        selected = r.select201(inputs, rows)
        self.assertEqual(len(selected), 201)
        self.assertEqual(sum(x["kind"] == "replay" for x in selected), 15)


class ObligationsTests(unittest.TestCase):
    def test_complete_read_addresses_and_checkpoint_execution_required(self):
        profile = dict(artifact="/fixtures", exception_log=None,
            read_regions=[dict(pc=16, start=64, size=16, width=8, label="signature"),
                          dict(pc=20, start=128, size=2, width=1, label="store")],
            checkpoint_locations=[dict(checkpoint_pc="0x18", read_loop_pc="0x10")])
        retires = [SimpleNamespace(trap=False, pc=pc, mem_addr=address, instruction=width)
                   for pc, address, width in ((16,64,8),(16,72,8),(20,128,1),(20,129,1),(24,0,0))]
        scalar, _ = comparison()
        with patch.object(r.scalar_api, "_scalar_memory_access", side_effect=lambda width:("read",width)), \
             patch.object(r.random, "_checkpoint_traps", return_value=[]), \
             patch.object(r, "check_checkpoint_report", return_value=dict(status="PASS")):
            with patch.object(r.scalar_api, "parse_ara_retire", return_value=retires):
                report = r.read_coverage_obligations(profile, scalar)
                self.assertEqual(report["signature_and_store_reads"][1]["checked_bytes"], 2)
            for partial in (retires[1:], retires[:-1], retires[:3]+retires[4:]):
                with patch.object(r.scalar_api, "parse_ara_retire", return_value=partial), self.assertRaises(ValueError):
                    r.read_coverage_obligations(profile, scalar)

    def test_checkpoint_failure_and_signature_absence_reject(self):
        with self.assertRaisesRegex(ValueError, "signature"):
            r.signature_regions(dict(symbols={}, sections=[]))
        scalar, _ = comparison()
        with patch.object(r.random, "_vector_checkpoint_report", return_value=dict(status="FAIL")), \
             self.assertRaisesRegex(ValueError, "Checkpoint"):
            r.check_checkpoint_report(scalar, [dict(index=0)], [])

    def test_deadline_and_no_tools_fail_closed(self):
        with self.assertRaises(TimeoutError):
            r.deadline_expired(0, None)
        import subprocess
        with r.admission.old.no_tools(), self.assertRaises(RuntimeError):
            subprocess.Popen(["simv"])


class ReplayTests(unittest.TestCase):
    def test_both_comparators_are_full_and_saved_parameters_unused(self):
        with tempfile.TemporaryDirectory() as directory:
            a = Path(directory)
            for name in ("rtl_console.log", "run.vcs.log"):
                (a/name).write_text("Core Test *** SUCCESS ***\n")
            (a/"commit_comparison.json").write_text('{"status":"PASS","terminal_ecall_pc":123}')
            profile = dict(name="fixture", vdb="/fixture/code.vdb", artifact=str(a),
                case=dict(fault_vstart_probe=False), elf_metadata=dict(entry=1, exit_pc=2, tohost=3),
                exception_log=None, historical_checker_pins={"old":"historical"},
                input_sha256={str(p):r.admission.sha_bytes(p.read_bytes()) for p in a.iterdir()})
            scalar, vector = comparison()
            with patch.object(r.vector_api, "unobservable_vector_scalar_write_indices", return_value={4}), \
                 patch.object(r.scalar_api, "compare_commit_prefix", return_value=scalar) as compare_scalar, \
                 patch.object(r.vector_api, "compare_vector_commits", return_value=vector) as compare_vector, \
                 patch.object(r, "_load_fault_evidence_errors", return_value=[]), \
                 patch.object(r, "check_contract_log", return_value=[]) as contract, \
                 patch.object(r, "validate_trace", return_value={}), \
                 patch.object(r, "unknown_audit", return_value=dict(status="PASS")), \
                 patch.object(r, "read_coverage_obligations", return_value=dict(status="PASS")):
                code = {str(a/"commit_comparison.json"):profile["input_sha256"][str(a/"commit_comparison.json")]}
                result = r.replay(profile, code, 5)
                self.assertEqual(result["status"], "PASS_DIAGNOSTIC_ONLY", result)
                self.assertFalse(result["admitted687"])
                kwargs = compare_scalar.call_args.kwargs
                self.assertEqual(kwargs["terminal_ecall_pc"], 2)
                self.assertEqual(kwargs["terminal_tohost_address"], 3)
                self.assertNotIn("selected_index", compare_vector.call_args.kwargs)
                self.assertNotIn("stop_spike_index", compare_vector.call_args.kwargs)
                contract.return_value = ["violation"]
                self.assertEqual(r.replay(profile, code, 5)["status"], "FAILED_DIAGNOSTIC_ONLY")
                contract.return_value = []
                scalar["status"] = "PREFIX"
                self.assertEqual(r.replay(profile, code, 5)["status"], "FAILED_DIAGNOSTIC_ONLY")


class UnknownAuditTests(unittest.TestCase):
    def test_isa_masked_unknown_vs_active_unknown_and_missing_policy(self):
        item = SimpleNamespace(vector_writes={1:0}, vector_tail_agnostic=True,
            vector_mask_agnostic=False, vector_vl=1, vector_vstart=0)
        activity = SimpleNamespace(instruction=0, writes=[])
        compared = dict(instructions=[dict(arch_seq=1)])
        with patch.object(r.vector_api, "_parse_vector_trace", return_value=(4,1024,{1:activity})), \
             patch.object(r.vector_api, "_parse_architecture_mapping", return_value=([],[],set())), \
             patch.object(r.vector_api, "_map_architecture_retires", return_value={}), \
             patch.object(r.vector_api, "_spike_from_entry", return_value=[item]), \
             patch.object(r.vector_api, "_map_spike_commits", return_value={1:0}), \
             patch.object(r.vector_api, "_advance_unknown_state"), \
             patch.object(r.vector_api, "_uses_mask_predicate", return_value=False), \
             patch.object(r.vector_api, "_architectural_bytes", return_value={(1,0):(None,None)}), \
             patch.object(r.vector_api, "_architectural_compare_mask", return_value=0) as mask:
            self.assertEqual(r.unknown_audit(None,None,None,0,compared)["isa_unconstrained_bytes"], 1)
            mask.return_value = 255
            with self.assertRaisesRegex(ValueError, "active unknown"):
                r.unknown_audit(None,None,None,0,compared)
            mask.return_value = 0
            item.vector_tail_agnostic = None
            with self.assertRaisesRegex(ValueError, "policy"):
                r.unknown_audit(None,None,None,0,compared)


if __name__ == "__main__":
    unittest.main()
