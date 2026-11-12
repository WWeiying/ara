"""Offline configuration/command and SV-preprocessor tests. No EDA build runs.

Run: python3 -B verification/performance/optimization_enablement/config_test.py
Candidate: make -C hardware config-check optimization_profile=candidate_all
All four knobs accept explicit 0/1 overrides. This profile is not signoff and
does not authorize runtime memory or advertise resident capability index 4.
"""
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
HW = ROOT / "hardware"
KNOBS = ("shared_simd_mul", "shared_fma", "akv_resident", "qbs_lane_mul")
MACROS = ("ARA_SHARED_SIMD_MUL", "ARA_SHARED_FMA",
          "ARA_AKV_RESIDENT_PV_ENABLE", "ARA_AKV_RESIDENT_QK_ENABLE",
          "ARA_QBS_LANE_MUL_ENABLE")


def make(*args, extra=None, file=None):
    env = dict(os.environ)
    for key in (*KNOBS, "optimization_profile", "qbs", "akv", "akv_v2",
                "MAKEFLAGS", "MAKEOVERRIDES", "MFLAGS", "ARA_CONFIGURATION"):
        env.pop(key, None)
    cmd = ["make", "--no-print-directory", "-C", str(HW),
           "-f", str(file or HW / "Makefile"), "config=default",
           "ARA_DIR=" + str(ROOT), "ROOT_DIR=" + str(HW)]
    if extra is not None:
        cmd += ["-f", "-"]
    return subprocess.run([*cmd, *args], input=extra, text=True, env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)


class Configuration(unittest.TestCase):
    def checked(self, *args):
        result = make("config-check", *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return dict(line.split("=", 1) for line in result.stdout.splitlines())

    def test_generic_off(self):
        config = self.checked()
        self.assertEqual(config["optimization_profile"], "generic")
        for knob in KNOBS:
            self.assertEqual(config[knob], "0")
        for macro in MACROS:
            self.assertNotIn(macro, config["bender_defs"])

    def test_candidate(self):
        config = self.checked("optimization_profile=candidate_all")
        for knob in KNOBS:
            self.assertEqual(config[knob], "1")
        for macro in (*MACROS, "ARA_QBS_ENABLE", "ARA_AKV_V2_ENABLE"):
            self.assertIn("--define " + macro + "=1", config["bender_defs"])

    def test_individual_selection(self):
        dependencies = {"akv_resident": ["akv_v2=1"], "qbs_lane_mul": ["qbs=1"]}
        for knob in KNOBS:
            with self.subTest(knob=knob):
                config = self.checked(knob + "=1", *dependencies.get(knob, []))
                self.assertEqual([config[k] for k in KNOBS], [str(int(k == knob)) for k in KNOBS])

    def test_explicit_override(self):
        config = self.checked("optimization_profile=candidate_all", *[k + "=0" for k in KNOBS])
        for macro in MACROS:
            self.assertNotIn(macro, config["bender_defs"])

    def test_invalid_values(self):
        for knob in KNOBS:
            for value in ("", "2", "yes", "0 1", "1 garbage"):
                with self.subTest(knob=knob, value=value):
                    result = make("config-check", knob + "=" + value)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(knob + " must be 0 or 1", result.stderr)

    def test_unknown_profile(self):
        for value in ("", "all", "generic candidate_all", "candidate_all garbage"):
            self.assertNotEqual(make("config-check", "optimization_profile=" + value).returncode, 0)

    def test_dependencies(self):
        for args, message in [(["akv_resident=1"], "requires akv_v2=1"),
                              (["qbs_lane_mul=1"], "requires qbs=1"),
                              (["optimization_profile=candidate_all", "qbs=0"], "requires qbs=1"),
                              (["optimization_profile=candidate_all", "akv_v2=0"], "requires akv_v2=1")]:
            result = make("config-check", *args)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(message, result.stderr)

    def test_geometry(self):
        for knob in ("akv_resident", "qbs_lane_mul"):
            for geometry in (["nr_lanes=2"], ["vlen=2048"], ["nr_lanes=8", "vlen=2048"]):
                result = make("config-check", knob + "=1", "qbs=1", "akv_v2=1", *geometry)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("require nr_lanes=4 vlen=1024", result.stderr)
        self.checked("nr_lanes=2", "vlen=2048")  # Generic behavior unchanged.
        for knob in ("shared_simd_mul", "shared_fma"):
            self.checked(knob + "=1", "nr_lanes=2", "vlen=2048")
        result = make("config-check", "optimization_profile=candidate_all", "nr_lanes=2",
                      *[k + "=0" for k in KNOBS])
        self.assertNotEqual(result.returncode, 0)

    def test_vcs_dc_command_propagation(self):
        for target in ("compile", "dc_flist_locked"):
            result = make("-n", target, "optimization_profile=candidate_all")
            self.assertEqual(result.returncode, 0, result.stderr)
            commands = [line for line in result.stdout.splitlines() if " script " in line and "--define" in line]
            self.assertEqual(len(commands), 1, result.stdout)
            for macro in MACROS:
                self.assertIn("--define " + macro + "=1", commands[0])
            self.assertIn("vcs " if target == "compile" else "defines.temp", result.stdout)

    def test_generic_defines_match_head(self):
        old = subprocess.check_output(["git", "show", "HEAD:hardware/Makefile"], cwd=ROOT, text=True)
        probe = '.PHONY: config-probe\nconfig-probe:\n\t@echo "$(strip $(bender_defs))"\n'
        with tempfile.TemporaryDirectory(prefix="ara-config-") as work:
            path = Path(work) / "Makefile"
            path.write_text(old)
            for settings in ([], ["qbs=1", "akv_v2=1"], ["nr_lanes=2", "vlen=2048"]):
                before = make("config-probe", *settings, file=path, extra=probe)
                after = make("config-probe", *settings, extra=probe)
                self.assertEqual(before.returncode, 0, before.stderr)
                self.assertEqual(after.returncode, 0, after.stderr)
                self.assertEqual(before.stdout.split(), after.stdout.split())

    @unittest.skipUnless(shutil.which("iverilog"), "iverilog preprocessor unavailable")
    def test_real_sv_preprocessing(self):
        # Preprocessing only: no elaboration, compilation or simulation.
        for enabled in (False, True):
            cmd = ["iverilog", "-g2012", "-E", "-o", "-",
                   "-I" + str(HW / "include"), "-I" + str(HW / "deps/common_cells/include")]
            config = self.checked(*(["optimization_profile=candidate_all"] if enabled else []))
            definitions = shlex.split(config["bender_defs"])
            self.assertTrue(all(token == "--define" for token in definitions[::2]))
            cmd += ["-D" + value for value in definitions[1::2]]
            result = subprocess.run([*cmd, *[str(HW / path) for path in (
                "include/ara_pkg.sv", "include/akv_pkg.sv", "include/qbs_pkg.sv", "src/ara.sv")]],
                                    text=True, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(re.findall(r"localparam bit EnableSharedFma = 1'b([01]);", result.stdout),
                             [str(int(enabled))])
            for name in ("AkvEnable", "AkvV2Enable", "AkvResidentPvEnable", "QbsEnable"):
                self.assertIn("localparam bit " + name + " = 1'b" + str(int(enabled)) + ";", result.stdout)
            self.assertEqual(re.findall(r"parameter\s+bit\s+EnableQbsLaneMul = 1'b([01]),", result.stdout),
                             [str(int(enabled))])
            self.assertIn("localparam bit AkvResidentQkEnable = " +
                          ("AkvResidentPvEnable;" if enabled else "1'b0;"), result.stdout)
            for name in ("AkvResidentPvSupported", "AkvResidentQkSupported"):
                self.assertIn("localparam bit " + name + " = 1'b0;", result.stdout)
            for name in ("akv_resident_pv_capability_word", "akv_resident_qk_capability_word"):
                body = result.stdout.split("function automatic logic [63:0] " + name, 1)[1].split("endfunction", 1)[0]
                self.assertIn("return '0;", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
