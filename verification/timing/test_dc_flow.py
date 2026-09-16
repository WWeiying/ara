"""Exercise DC orchestration without a license or a synthesis run."""
import os
import contextlib
import importlib.util
import io
import json
import signal
import sys
import time
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
FLOW = ROOT / "backend/syn/ara_soc/v1-dc"


class FlowTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / "run"
        self.run.mkdir()
        shutil.copy2(FLOW / "run/run.cmd", self.run / "run.cmd")
        scripts = self.root / "global_scripts"
        scripts.mkdir()
        shutil.copy2(FLOW / "global_scripts/dc_lock.sh", scripts / "dc_lock.sh")
        fake = self.root / "dc_shell-t"
        fake.write_text('#!/bin/sh\nprintf "%s\\n" "$FAKE_OUTPUT"\nprintf "%s\\n" "$FAKE_STDERR" >&2\nexit "$FAKE_RC"\n')
        fake.chmod(0o755)

    def run_fake(self, output, rc=0, elaborate=False, stderr=""):
        env = dict(os.environ, PATH=f"{self.root}:{os.environ['PATH']}",
                   FAKE_OUTPUT=output, FAKE_STDERR=stderr, FAKE_RC=str(rc),
                   DC_ELAB_ONLY=str(int(elaborate)))
        return subprocess.run(["bash", str(self.run / "run.cmd")], env=env,
                              capture_output=True, text=True)

    def test_success_requires_marker(self):
        self.assertEqual(self.run_fake("DC_FLOW_COMPLETE").returncode, 0)
        self.assertNotEqual(self.run_fake("stopped during mapping").returncode, 0)

    def test_tool_error_with_zero_exit_is_not_success(self):
        self.assertNotEqual(self.run_fake("Error: failed\nDC_FLOW_COMPLETE").returncode, 0)
        self.assertNotEqual(self.run_fake("DC_FLOW_COMPLETE", stderr="Error: failed").returncode, 0)
        self.assertIn("Error: failed", (self.run / "dc.log").read_text())

    def test_redirected_tool_errors_are_not_success(self):
        self.assertNotEqual(self.run_fake(
            "DC_FLOW_ERROR_COUNT=2\nDC_FLOW_COMPLETE").returncode, 0)
        self.assertEqual(self.run_fake(
            "DC_STARTUP_MANUAL_ERRORS=1\nDiagnostics summary: 1 error\n"
            "DC_FLOW_ERROR_COUNT=0\nDC_FLOW_COMPLETE").returncode, 0)

    def test_physical_summary_uses_pin_collections_and_scalar_metrics(self):
        text = (FLOW / "global_scripts/dc.tcl").read_text()
        start = text.index("# A design object has no area attribute")
        end = text.index("\nset physical_summary", start)
        (self.root / "reports").mkdir()
        (self.root / "reports/area.rpt").write_text(
            "Macro/Black Box area: 2075692.398438\nTotal cell area: 4186807.921888\n")
        mocks = r'''
proc sizeof_collection {collection} {llength $collection}
proc all_registers {args} {
    if {[lsearch -exact $args -edge_triggered] < 0} {error "expected FF scope"}
    if {[lsearch -exact $args -output_pins] >= 0} {return {a/Q b/Q}}
    if {[lsearch -exact $args -data_pins] >= 0} {return {a/D b/D}}
    error "cell collections are not timing points"
}
proc get_timing_paths {args} {
    if {[lsearch -exact $args -from] >= 0} {
        if {[lindex $args [expr {[lsearch -exact $args -from]+1}]] ne {a/Q b/Q}} {error "wrong start pins"}
        if {[lindex $args [expr {[lsearch -exact $args -to]+1}]] ne {a/D b/D}} {error "wrong end pins"}
        return {regpath}
    }
    return {inputpath clkpath outputpath}
}
proc get_attribute {collection attr} {
    if {$attr ne "slack"} {error "unsupported attribute $attr"}
    if {$collection eq {regpath}} {return -0.41}
    return {-0.184779 -0.675988 0.000398636}
}
set reports 0
proc report_timing {args} {
    incr ::reports
    if {[lindex $args [expr {[lsearch -exact $args -group]+1}]] ne "clk_i"} {error "wrong group"}
    return 1
}
set report_timing_opt {-transition_time -nets -sort_by slack}
'''
        checks = r'''
if {$design_total_area != 4186807.921888} {exit 2}
if {$worst_setup_slack != -0.675988} {exit 3}
if {$worst_reg_slack != -0.41 || $reports != 1} {exit 4}
if {[dc_min_path_slack {}] ne "NA"} {exit 5}
puts PHYSICAL_SUMMARY_PASS
'''
        result = subprocess.run(["tclsh"], cwd=self.run,
                                input=mocks + text[start:end] + checks,
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(result.stderr, result.stderr)
        self.assertIn("PHYSICAL_SUMMARY_PASS", result.stdout)

    def test_nonzero_tool_exit_is_propagated(self):
        self.assertEqual(self.run_fake("DC_FLOW_COMPLETE", rc=9).returncode, 9)

    def test_elaboration_is_distinct(self):
        self.assertEqual(self.run_fake("DC_ELAB_COMPLETE", elaborate=True).returncode, 0)
        self.assertNotEqual(self.run_fake("DC_ELAB_COMPLETE").returncode, 0)

    def test_directory_lock(self):
        import fcntl
        with (self.run / ".dc.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.run_fake("DC_FLOW_COMPLETE")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Another DC run", result.stderr)

    def test_old_log_is_retained(self):
        (self.run / "dc.log").write_text("previous synthesis\n")
        self.assertEqual(self.run_fake("DC_FLOW_COMPLETE").returncode, 0)
        archives = list((self.run / "log_archive").glob("*_dc.log"))
        self.assertEqual(len(archives), 1)
        self.assertEqual(archives[0].read_text(), "previous synthesis\n")
        self.assertIn("runner_exit_code=0", (self.run / "dc.status").read_text())

    def test_tcl_is_complete_and_mapped_save_precedes_reports(self):
        for path in [FLOW / "global_scripts/dc.tcl", FLOW / "global_scripts/dc_flow_state.tcl"]:
            script = "set f [open {" + str(path) + "} r]\nset t [read $f]\nclose $f\nexit [expr {![info complete $t]}]\n"
            result = subprocess.run(["tclsh"], input=script, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        text = (FLOW / "global_scripts/dc.tcl").read_text()
        self.assertLess(text.index("dc_flow_checkpoint mapped"), text.index("foreach_in_collection each_path_group"))

    def test_main_real_constraints_and_compile_options(self):
        script = r'''
proc pwd {} {return /test/syn/ara_soc/v1-dc/run}
set calls {}
foreach command {
    create_clock set_clock_uncertainty set_clock_transition set_ideal_network
    set_max_fanout set_max_transition remove_ideal_network set_driving_cell
    set_load group_path set_input_delay set_output_delay set_false_path
} {
    proc $command {args} [format {lappend ::calls [linsert $args 0 %%s]} $command]
}
proc get_ports {args} {return [lindex $args end]}
proc get_clocks {args} {return [lindex $args end]}
proc current_design {} {return ara_soc}
proc all_inputs {} {return {clk_i rst_ni data_i}}
proc all_outputs {} {return {data_o}}
proc all_registers {} {return {reg_q}}
proc get_pins {args} {return {}}
proc sizeof_collection {objects} {return [llength $objects]}
proc remove_from_collection {objects removed} {
    set result {}
    foreach object $objects {
        if {$object ni $removed} {lappend result $object}
    }
    return $result
}
source {%s}
source {%s}
foreach {name expected} {
    GUI_MAX_CPU_NUM 8 GUI_UNGROUP 0 GUI_SYN_CYCLE 1 GUI_DFT 0
    GUI_DCG_MODE 0 GUI_POWER_OPT 1 GUI_CLOCK_GATE 1
    GUI_GATER_CLOCK_MIN_BITWIDTH 8 GUI_GATER_SETUP 0.05
    GUI_GATER_MAX_FANOUT 32 GUI_GATER_NUM_STAGES 1 GUI_PVT tc
} {
    if {[set $name] ne $expected} {error "unexpected $name=[set $name]"}
}
foreach expected {
    {create_clock -name clk_i -period 1.0 clk_i}
    {set_clock_uncertainty -setup 0.15 clk_i}
    {set_clock_uncertainty -hold 0.075 clk_i}
    {set_clock_transition 0.08 clk_i}
    {set_max_transition 0.3 ara_soc}
    {group_path -name clk_i -critical 0.20 -weight 10}
    {set_input_delay -clock clk_i -min 0 {rst_ni data_i}}
    {set_output_delay -clock clk_i -min 0 data_o}
} {
    if {[lsearch -exact $calls $expected] < 0} {error "missing $expected"}
}
if {[lsearch -exact $calls {set_false_path -to {}}] >= 0} {
    error "missing RVFI pins must not create an empty timing exception"
}
puts MAIN_REAL_SETTINGS_PASS
''' % (FLOW / "global_scripts/synopsys_dc.setup.gui",
       FLOW / "local_scripts/ara_soc.sdc")
        result = subprocess.run(["tclsh"], input=script, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(result.stderr, result.stderr)
        self.assertIn("MAIN_REAL_SETTINGS_PASS", result.stdout)
        text = (FLOW / "global_scripts/dc.tcl").read_text()
        self.assertIn("set compile_register_replication false\n", text)
        self.assertIn('set compile_ultra_cmd "compile_ultra -no_seq_output_inversion $compile_ultra_hier_opt"', text)
        self.assertIn('set compile_ultra_hier_opt      " -no_autoungroup"', text)
        self.assertIn('append compile_ultra_hier_opt " -gate_clock "', text)

    def test_phase_and_checkpoint_helpers(self):
        script = """
set GUI_DESIGN_NAME test_soc
set calls {}
set errors 1
proc get_message_info {args} {
    if {$args eq {-occurrences CMD-025}} {return 1}
    return $::errors
}
proc write {args} {lappend ::calls [linsert $args 0 write]; return 1}
proc write_sdc {args} {lappend ::calls [linsert $args 0 write_sdc]; return 1}
source {%s}
dc_flow_stage COMPILE
dc_flow_checkpoint mapped
set f [open dc.status r]
set status [read $f]
close $f
if {![string match *stage=COMPILE* $status]} {exit 2}
if {[llength $calls] != 2} {exit 3}
if {![string match *test_soc_mapped.ddc* [lindex $calls 0]]} {exit 4}
if {![string match *test_soc_mapped.sdc* [lindex $calls 1]]} {exit 5}
unset -nocomplain env(DC_ELAB_ONLY)
if {[dc_flow_elaborate_only]} {exit 6}
set env(DC_ELAB_ONLY) 1
if {![dc_flow_elaborate_only]} {exit 7}
if {![dc_flow_check_errors]} {exit 8}
incr errors
if {[dc_flow_check_errors]} {exit 9}
puts HELPERS_PASS
""" % (FLOW / "global_scripts/dc_flow_state.tcl")
        result = subprocess.run(["tclsh"], cwd=self.run, input=script, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("HELPERS_PASS", result.stdout)

    def test_local_adapter_run_snapshots_its_inputs(self):
        path = ROOT / "verification/timing/run_payload_dc.py"
        spec = importlib.util.spec_from_file_location("local_dc_runner", path)
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        out = self.root / "adapter_snapshot"
        argv = [str(path), "--output", str(out), "--top", "qbs_block_adapter",
                "--elaborate-only", "--compact-read"]
        with mock.patch.object(runner.sys, "argv", argv), \
             mock.patch.object(runner.subprocess, "check_output",
                               side_effect=["unit-test-commit", b""]), \
             mock.patch.object(runner.subprocess, "Popen") as launch, \
             contextlib.redirect_stdout(io.StringIO()):
            runner.main()
        launch.assert_called_once()
        manifest = json.loads((out / "manifest.json").read_text())
        self.assertEqual(manifest["top"], "qbs_block_adapter")
        self.assertTrue(manifest["elaborate_only"])
        self.assertTrue(manifest["compact_read"])
        self.assertEqual(len(manifest["sources"]), 4)
        for source in manifest["sources"]:
            original = ROOT / source["path"]
            self.assertEqual((out / "src" / original.name).read_bytes(), original.read_bytes())
        self.assertEqual((out / "runner.py").read_bytes(), path.read_bytes())
        self.assertEqual(launch.call_args.args[0][1], str(out / "runner.py"))
        script = (out / "payload_dc.tcl").read_text()
        self.assertIn('elaborate $top -parameters "NativeView=0"', script)
        self.assertNotIn("current_design $top", script)

    def test_runtime_reporting_with_and_without_tool_command(self):
        paths = [FLOW / "global_scripts/dc.tcl",
                 ROOT / "verification/timing/payload_dc.tcl"]
        for path in paths:
            text = path.read_text()
            start = text.index("if {[llength [info commands report_runtime]]}")
            end = text.index("\n}\n", start) + 2
            for supported in (False, True):
                with self.subTest(path=path, supported=supported):
                    script = "set calls 0\nset starttime 10\nset endtime 20\nset local_starttime [clock seconds]\n"
                    if supported:
                        script += "proc report_runtime {} {incr ::calls}\n"
                    script += text[start:end] + "\n"
                    script += f"if {{$calls != {int(supported)}}} {{exit 1}}\n"
                    result = subprocess.run(["tclsh"], input=script, text=True,
                                            capture_output=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertFalse(result.stderr, result.stderr)
                    if not supported:
                        self.assertIn("ELAPSED_SECONDS=", result.stdout)

    def test_unique_commit_adapter_snapshot(self):
        path = ROOT / "verification/timing/run_payload_dc.py"
        spec = importlib.util.spec_from_file_location("area_dc_runner", path)
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        out = self.root / "unique_adapter_snapshot"
        argv = [str(path), "--output", str(out), "--top", "qbs_adapter_pipeline_timing",
                "--unique-input-bytes", "--quick-reports"]
        with mock.patch.object(runner.sys, "argv", argv), \
             mock.patch.object(runner.subprocess, "check_output", side_effect=["unit-test-commit", b""]), \
             mock.patch.object(runner.subprocess, "Popen"), \
             contextlib.redirect_stdout(io.StringIO()):
            runner.main()
        manifest = json.loads((out / "manifest.json").read_text())
        self.assertTrue(manifest["unique_input_bytes"])
        self.assertTrue(manifest["quick_reports"])
        self.assertEqual(len(manifest["sources"]), 5)
        wrapper = (out / "src/qbs_adapter_pipeline_timing.sv").read_text()
        self.assertIn("`ifdef QBS_UNIQUE_INPUT_BYTES", wrapper)
        self.assertIn(".UniqueInputBytes(1'b1)", wrapper)
        script = (out / "payload_dc.tcl").read_text()
        start = script.index("set defines {SYNTHESIS TARGET_SRAM_MC}")
        end = script.index('\nif {$top in {simd_mul_timing', start)
        for enabled in (0, 1):
            result = subprocess.run(["tclsh"], input=f"set env(DC_UNIQUE_INPUT_BYTES) {enabled}\n" +
                                    script[start:end] + "\nputs $defines\n",
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(result.stderr)
            self.assertEqual("QBS_UNIQUE_INPUT_BYTES" in result.stdout, bool(enabled))


class IntegratedLockTest(unittest.TestCase):
    """Run the real Makefile DC recipes in a disposable tree with fake tools."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.hw = self.root / "hardware"
        self.flow = self.root / "backend/syn/ara_soc/v1-dc"
        self.run = self.flow / "run"
        self.bin = self.root / "bin"
        for directory in (self.hw / "scripts/akv", self.run,
                          self.flow / "global_scripts", self.bin):
            directory.mkdir(parents=True, exist_ok=True)
        for relative in ("run/run.cmd", "global_scripts/dc_lock.sh"):
            shutil.copy2(FLOW / relative, self.flow / relative)
        text = (ROOT / "hardware/Makefile").read_text()
        recipes = text[text.index("DC_LOCK_SCRIPT :="):text.index("\nsram:")]
        prefix = """SHELL := /bin/bash
ROOT_DIR := $(CURDIR)
BENDER := $(CURDIR)/../bin/bender
mc ?= 1
qbs ?= 1
akv_v2 ?= 1
nr_lanes ?= 4
vlen ?= 1024
bender_defs_veril = --define QBS=$(qbs) --define VLEN=$(vlen)
"""
        (self.hw / "Makefile").write_text(prefix + recipes)
        fake = f"#!{sys.executable}\n" + """import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
stage = {'bender':'flist', 'dc_shell-t':'dc',
         'check-synthesis-preflight.py':'preflight',
         'collect-synthesis-results.py':'collect'}[name]
with open(os.environ['TEST_EVENTS'], 'a') as f:
    f.write(json.dumps({'stage':stage, 'argv':sys.argv[1:]}) + '\\n')
if os.environ.get('TEST_HOLD') == stage:
    Path(os.environ['TEST_REACHED']).touch()
    with open(os.environ['TEST_RELEASE']) as f:
        f.readline()
if os.environ.get('TEST_FAIL') == stage:
    sys.exit(13)
if stage == 'flist':
    print('+incdir+/fake\\n+define+FAKE=1\\n/fake/test_pkg.sv\\n/fake/test.sv')
if stage == 'dc':
    print('DC_ELAB_COMPLETE' if os.environ.get('DC_ELAB_ONLY') == '1' else 'DC_FLOW_COMPLETE')
"""
        for path in (self.bin / "bender", self.bin / "dc_shell-t",
                     self.hw / "scripts/akv/check-synthesis-preflight.py",
                     self.hw / "scripts/akv/collect-synthesis-results.py"):
            path.write_text(fake)
            path.chmod(0o755)
        self.events = self.root / "events.jsonl"
        self.reached = self.root / "reached"
        self.release = self.root / "release"
        os.mkfifo(self.release)
        self.env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}",
                        TEST_EVENTS=str(self.events), TEST_REACHED=str(self.reached),
                        TEST_RELEASE=str(self.release))
        for key in ("MAKEFLAGS", "MFLAGS", "MAKEOVERRIDES", "ARA_DC_LOCK_FILE", "DC_ELAB_ONLY"):
            self.env.pop(key, None)

    def make(self, target="dc", *, flags=(), overrides=(), env=None):
        return subprocess.run(["make", "--no-print-directory", "-C", str(self.hw),
                               *flags, target, *overrides], env=env or self.env,
                              text=True, capture_output=True, timeout=10)

    def stages(self):
        if not self.events.exists():
            return []
        return [json.loads(line)['stage'] for line in self.events.read_text().splitlines()]

    def test_full_flow_and_recursive_make_configuration(self):
        result = self.make(overrides=("vlen=2048",))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.stages(), ['flist', 'preflight', 'dc', 'collect'])
        calls = [json.loads(line) for line in self.events.read_text().splitlines()]
        self.assertIn('VLEN=2048', calls[0]['argv'])
        self.assertEqual(calls[1]['argv'][-1], '2048')

    def test_public_partial_targets(self):
        for target, stages in [('dc_flist', ['flist']),
                               ('dc_preflight', ['flist', 'preflight'])]:
            with self.subTest(target=target):
                self.events.unlink(missing_ok=True)
                result = self.make(target)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(self.stages(), stages)

    def test_elaboration_only_does_not_collect(self):
        result = self.make(env=dict(self.env, DC_ELAB_ONLY='1'))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.stages(), ['flist', 'preflight', 'dc'])

    def test_dry_run_does_not_execute_tools(self):
        result = self.make(flags=('-n',))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.stages(), [])
        self.assertFalse((self.root / 'backend/flist/ara_soc_dc.f').exists())
        self.assertFalse((self.run / 'dc.log').exists())

    def test_internal_targets_reject_missing_lock_even_with_forged_environment(self):
        for target in ('dc_locked', 'dc_preflight_locked', 'dc_flist_locked'):
            with self.subTest(target=target):
                result = self.make(target, env=dict(self.env, ARA_DC_LOCK_FILE=str(self.run / '.dc.lock')))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('requires the outer flow lock', result.stderr)
                self.assertEqual(self.stages(), [])

    def test_failure_stops_later_stages_and_releases_lock(self):
        stages = ['flist', 'preflight', 'dc', 'collect']
        for index, stage in enumerate(stages):
            with self.subTest(stage=stage):
                self.events.unlink(missing_ok=True)
                result = self.make(env=dict(self.env, TEST_FAIL=stage))
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.stages(), stages[:index+1])
                self.assertEqual(self.make('dc_flist').returncode, 0)

    @staticmethod
    def stop(proc):
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate(timeout=5)

    def test_lock_covers_file_generation_through_collection(self):
        for stage in ('flist', 'preflight', 'dc', 'collect'):
            with self.subTest(stage=stage):
                self.events.unlink(missing_ok=True)
                self.reached.unlink(missing_ok=True)
                proc = subprocess.Popen(
                    ['make', '--no-print-directory', '-C', str(self.hw), '-j2', 'dc'],
                    env=dict(self.env, TEST_HOLD=stage), stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True, start_new_session=True)
                try:
                    deadline = time.monotonic() + 10
                    while not self.reached.exists() and proc.poll() is None and time.monotonic() < deadline:
                        time.sleep(0.01)
                    self.assertTrue(self.reached.exists(), f'flow did not reach {stage}')
                    before = self.events.read_bytes()
                    filelist = self.root / 'backend/flist/ara_soc_dc.f'
                    contents = filelist.read_bytes() if filelist.exists() else None
                    for target in ('dc', 'dc_preflight', 'dc_flist'):
                        result = self.make(target)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn('Another DC run', result.stderr)
                    direct = subprocess.run(['bash', str(self.run / 'run.cmd')],
                                            env=self.env, text=True, capture_output=True, timeout=5)
                    self.assertNotEqual(direct.returncode, 0)
                    self.assertIn('Another DC run', direct.stderr)
                    self.assertEqual(self.events.read_bytes(), before)
                    self.assertEqual(filelist.read_bytes() if filelist.exists() else None, contents)
                    with self.release.open('w') as fifo:
                        fifo.write('continue\n')
                    stdout, stderr = proc.communicate(timeout=10)
                    self.assertEqual(proc.returncode, 0, stdout + stderr)
                    self.assertEqual(self.stages(), ['flist', 'preflight', 'dc', 'collect'])
                finally:
                    self.stop(proc)


if __name__ == "__main__":
    unittest.main()
