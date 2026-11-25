"""Protocol tests use synthetic receipts, never execute the target binary."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import analyze as checker


class AnalyzeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="resident-direct-checker-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.write("status", "COMPLETE\n")
        self.save("platform.json", dict(schema=1, operator_accepted=True, board_id="unit-not-board",
                                       bitstream_sha256="a" * 64, kernel_sha256="b" * 64,
                                       machine="riscv64", online_cpus="0"))
        self.names = ("resident-direct-pair", "run_board.sh", "analyze.py", "README.md", "goldens.json", "source-pins.json")
        pins = {}
        for name in self.names[:-1]:
            self.write(name, "synthetic checker artifact: " + name)
            pins["/frozen/inputs/" + name] = self.digest(name)
        for suffix in ("/direct_cost/low_overhead_prepared/bench.cpp", "/direct_cost/build_prepared.py", "/direct/direct_client.c",
                       "/direct/direct_client.h", "/direct/direct_uapi.h", "/software/akv/src/akv_v2_native_riscv.c",
                       "/software/akv/src/akv_v2_attention_rvv.S", "/resident_attention/qk.S", "/resident_attention/pv.S"):
            pins["/frozen" + suffix] = "c" * 64
        self.save("source-pins.json", pins)
        self.checksums()
        for label, tokens in (("probe", 0), ("t65", 65), ("t128", 128), ("t137", 137)):
            self.write(label + ".rc", "0\n")
            setup = dict(scope=checker.SCOPE, sdk_commit=checker.SDK_COMMIT, tokens=tokens, probe=tokens == 0,
                         abi=1, features=7, online_cpus=1, gate_signature="0x414b5601", hart=0, acquires=1,
                         lease_generation=9, owner_tid=100, vlenb=128, finite_prechecks=1, mlockall=True,
                         stack_prefault_bytes=262144, vector_first_use=True, fp_initialized=True,
                         fixture_preflights=2, errors=0)
            lines = ["DIRECT_SETUP " + json.dumps(setup)]
            trials = [0, 0]
            if tokens:
                tiles = (tokens + 63) // 64
                for sequence, arm in enumerate(checker.ORDER):
                    trial = trials[arm]
                    trials[arm] += 1
                    sample = dict(sequence=sequence, mode=checker.MODES[arm], tokens=tokens, trial=trial, cold=trial == 0,
                                  ns=2000 if arm else 3000, status=0, completed_groups=1, sdk_calls=1, info_calls=0,
                                  native_qk=0 if arm else tiles, native_pv=0 if arm else tiles,
                                  resident_qk=tiles if arm else 0, resident_pv=tiles if arm else 0,
                                  incoming_fflags=8, fflags=11, vcsr=0, vstart=0, hot_client_calls=0,
                                  output_fnv64=checker.GOLDENS[tokens][1], errors=0)
                    lines.append("DIRECT_SAMPLE " + json.dumps(sample))
            lines.append("DIRECT_DONE " + json.dumps(dict(tokens=tokens, acquires=1, releases=1, hot_client_calls=0, errors=0)))
            lines.append("AKV_DIRECT_PAIR_PASS" if tokens else "AKV_DIRECT_PROBE_PASS")
            self.write(label + ".log", "\n".join(lines) + "\n")

    def write(self, name, text):
        (self.root / name).write_text(text)

    def save(self, name, value):
        self.write(name, json.dumps(value))

    def digest(self, name):
        return hashlib.sha256((self.root / name).read_bytes()).hexdigest()

    def checksums(self):
        self.write("SHA256SUMS", "".join(self.digest(name) + "  " + name + "\n" for name in self.names))

    def edit_record(self, label, index, **changes):
        path = self.root / (label + ".log")
        lines = path.read_text().splitlines()
        tag, payload = lines[index].split(" ", 1)
        value = json.loads(payload)
        value.update(changes)
        lines[index] = tag + " " + json.dumps(value)
        path.write_text("\n".join(lines) + "\n")

    def rejects(self):
        with self.assertRaises((ValueError, OSError)):
            checker.analyze(self.root)

    def test_valid_synthetic_protocol(self):
        result = checker.analyze(self.root)
        self.assertEqual(result["sample_count"], 42)
        self.assertEqual(result["warm_sample_count"], 36)
        self.assertFalse(result["complete_ggml_graph"])
        self.assertFalse(result["performance_acceptance"])
        for row in result["rows"]:
            self.assertEqual(row["native_akv_over_resident"], 1.5)
            self.assertEqual(row["abba_ratios"], [1.5] * 3)
            self.assertEqual(row["resident"]["warm_samples"], 6)

    def test_incomplete_collection(self):
        self.write("status", "RUNNING\n")
        self.rejects()

    def test_missing_point(self):
        (self.root / "t137.log").unlink()
        self.rejects()

    def test_failed_process(self):
        self.write("t65.rc", "132\n")
        self.rejects()

    def test_probe_failed_process(self):
        self.write("probe.rc", "1\n")
        self.rejects()

    def test_extra_diagnostics(self):
        path = self.root / "t65.log"
        path.write_text(path.read_text() + "unexpected diagnostic\n")
        self.rejects()

    def test_truncated_samples(self):
        path = self.root / "t128.log"
        lines = path.read_text().splitlines()
        self.write("t128.log", "\n".join(lines[:7] + lines[8:]) + "\n")
        self.rejects()

    def test_duplicated_sample(self):
        path = self.root / "t65.log"
        lines = path.read_text().splitlines()
        lines[4] = lines[3]
        self.write("t65.log", "\n".join(lines) + "\n")
        self.rejects()

    def test_wrong_order(self):
        path = self.root / "t65.log"
        lines = path.read_text().splitlines()
        lines[3], lines[4] = lines[4], lines[3]
        self.write("t65.log", "\n".join(lines) + "\n")
        self.rejects()

    def test_cold_mislabel(self):
        self.edit_record("t65", 3, cold=True)
        self.rejects()

    def test_ok_native_fallback_is_not_resident(self):
        self.edit_record("t65", 2, resident_qk=0, resident_pv=0, native_qk=2, native_pv=2)
        self.rejects()

    def test_unwitnessed_resident(self):
        self.edit_record("t137", 2, resident_pv=0)
        self.rejects()

    def test_bad_sample_fields(self):
        original = (self.root / "t137.log").read_text()
        for key, value in dict(status=1, completed_groups=0, sdk_calls=2, info_calls=4, native_qk=1,
                               incoming_fflags=0, fflags=3, vcsr=1, vstart=8, hot_client_calls=1,
                               output_fnv64="0" * 16, errors=1, trial=6, tokens=65).items():
            with self.subTest(key=key):
                self.write("t137.log", original)
                self.edit_record("t137", 2, **{key: value})
                self.rejects()

    def test_bad_durations_and_types(self):
        original = (self.root / "t65.log").read_text()
        for value in (0, -1, True, 1.5, "3000", None, 2**63, float("nan"), float("inf")):
            with self.subTest(value=value):
                self.write("t65.log", original)
                self.edit_record("t65", 1, ns=value)
                self.rejects()

    def test_boolean_is_not_integer_status(self):
        self.edit_record("t65", 1, status=False)
        self.rejects()

    def test_setup_capability_and_preparation(self):
        original = (self.root / "t65.log").read_text()
        bad = dict(scope="ggml-graph", sdk_commit="0" * 40, abi=0, features=3, online_cpus=2,
                   gate_signature="0x414b5600", hart=1, acquires=2, vlenb=64, finite_prechecks=0,
                   lease_generation=0, owner_tid=0, mlockall=False, stack_prefault_bytes=4096,
                   vector_first_use=False, fp_initialized=False, fixture_preflights=0, errors=1, probe=True)
        for key, value in bad.items():
            with self.subTest(key=key):
                self.write("t65.log", original)
                self.edit_record("t65", 0, **{key: value})
                self.rejects()

    def test_probe_capability(self):
        self.edit_record("probe", 0, features=1)
        self.rejects()

    def test_release_balance(self):
        self.edit_record("t128", -2, releases=0)
        self.rejects()

    def test_hot_teardown_client_call(self):
        self.edit_record("t128", -2, hot_client_calls=1)
        self.rejects()

    def test_wrong_terminal_marker(self):
        path = self.root / "probe.log"
        self.write("probe.log", path.read_text().replace("AKV_DIRECT_PROBE_PASS", "AKV_DIRECT_PAIR_PASS"))
        self.rejects()

    def test_duplicate_json_key(self):
        path = self.root / "t65.log"
        self.write("t65.log", path.read_text().replace('"errors": 0', '"errors": 0, "errors": 1', 1))
        self.rejects()

    def test_missing_field(self):
        path = self.root / "t65.log"
        self.write("t65.log", path.read_text().replace(', "info_calls": 0', '', 1))
        self.rejects()

    def test_missing_image_attestation(self):
        value = json.loads((self.root / "platform.json").read_text())
        value.pop("bitstream_sha256")
        self.save("platform.json", value)
        self.rejects()

    def test_wrong_platform(self):
        value = json.loads((self.root / "platform.json").read_text())
        value["operator_accepted"] = False
        self.save("platform.json", value)
        self.rejects()

    def test_non_object_platform(self):
        self.save("platform.json", [])
        self.rejects()

    def test_elf_drift(self):
        self.write("resident-direct-pair", "changed")
        self.rejects()

    def test_pin_file_drift(self):
        self.write("source-pins.json", "{}")
        self.rejects()

    def test_pin_package_disagreement(self):
        pins = json.loads((self.root / "source-pins.json").read_text())
        pins["/frozen/inputs/analyze.py"] = "d" * 64
        self.save("source-pins.json", pins)
        self.checksums()
        self.rejects()

    def test_missing_arithmetic_pin(self):
        pins = json.loads((self.root / "source-pins.json").read_text())
        del pins["/frozen/resident_attention/qk.S"]
        self.save("source-pins.json", pins)
        self.checksums()
        self.rejects()

    def test_duplicate_checksum(self):
        path = self.root / "SHA256SUMS"
        self.write("SHA256SUMS", path.read_text() + path.read_text().splitlines()[0] + "\n")
        self.rejects()

    def test_unsafe_checksum_path(self):
        self.write("SHA256SUMS", "a" * 64 + "  ../outside\n")
        self.rejects()

    def test_omitted_package_artifact(self):
        path = self.root / "SHA256SUMS"
        self.write("SHA256SUMS", "\n".join(line for line in path.read_text().splitlines()
                                             if not line.endswith("  goldens.json")) + "\n")
        self.rejects()


if __name__ == "__main__":
    unittest.main()


