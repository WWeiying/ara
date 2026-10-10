"""License-free regression of input guards, Tcl export and report acceptance."""

import csv
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().with_name("run_dve_coverage.sh")


class CoverageExportTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dve-export-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.design = self.root / "compile.vdb"
        (self.design / "snps/coverage/db/design").mkdir(parents=True)
        (self.design / "snps/coverage/db/design/verilog.design.xml").write_text("fixture")
        self.testdb = self.root / "run.vdb"
        self.testroot = self.testdb / "snps/coverage/db/testdata"
        self.testroot.mkdir(parents=True)
        self.add_test("case1")
        mock = self.root / "bin"
        mock.mkdir()
        driver = self.root / "driver.tcl"
        driver.write_text(r'''
proc gui_open_cov {args} {
    if {[info exists ::env(DVE_TEST_WARNING)]} {
        puts "Warning: \[CMR-VCINF\] Database mismatch; data will not be merged"
    }
}
proc gui_get_window_ids {} { return {CoverageTable.1} }
proc gui_list_get_property {args} {
    set col [lindex $args end]
    if {$col == 5} { return Score }
    if {$col == 6} { return Line }
    return ""
}
proc gui_list_get {args} {
    switch -- [lindex $args 2] {
        -firstChild { return 1 }
        -childCount { return 0 }
        -nextSibling {
            if {[info exists ::env(DVE_TEST_TOO_MANY_ROWS)]} {
                set next [expr {[lindex $args end] + 1}]
                if {$next <= 100001} { return $next }
            }
            return 0
        }
        -text {
            if {[lindex $args 3] == 0} { return {top,"quoted"} }
            return 50.00%
        }
    }
    error "Unexpected API call: $args"
}
proc gui_exit {args} {}
set script [lindex $argv [expr {[lsearch -exact $argv -script] + 1}]]
source $script
''')
        self.executable(mock / "dve", '''#!/usr/bin/env bash
if [[ ${DVE_TEST_HANG:-0} == 1 ]]; then exec sleep 120; fi
mkdir -p DVEfiles
exec tclsh "$DVE_TEST_DRIVER" "$@" > DVEfiles/dve_gui.log 2>&1
''')
        self.executable(mock / "xvfb-run", '''#!/usr/bin/env bash
while (( $# )); do
    case "$1" in
        -a) shift;;
        -e|-s) shift 2;;
        *) exec "$@";;
    esac
done
exit 2
''')
        for tool in ("Xvfb", "xauth"):
            self.executable(mock / tool, "#!/usr/bin/env bash\nexit 0\n")
        self.env = dict(os.environ, PATH=f"{mock}:/usr/bin:/bin",
                        DVE_TEST_DRIVER=str(driver), DVE_COVERAGE_TIMEOUT="5")
        self.out = self.root / "report"

    @staticmethod
    def executable(path, source):
        path.write_text(source)
        path.chmod(0o755)

    def add_test(self, name, contents="data"):
        path = self.testroot / name
        path.mkdir()
        (path / "line.verilog.data.xml").write_text(contents)

    def run_export(self, *inputs):
        return subprocess.run(["bash", str(SCRIPT), str(self.out),
                               *map(str, inputs or (self.design, self.testdb))],
                              env=self.env, capture_output=True, text=True, timeout=20)

    def test_two_tests_and_csv_escaping(self):
        self.add_test("case2")
        result = self.run_export()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len((self.out / "selected_tests.txt").read_text().splitlines()), 2)
        with (self.out / "summary.csv").open(newline="") as stream:
            rows = list(csv.reader(stream))
        self.assertEqual(rows[1], ['top,"quoted"', "0", "50.00%", "50.00%"])
        self.assertFalse((self.out / "summary.csv.partial").exists())

    def test_warning_rejects_final_report(self):
        self.env["DVE_TEST_WARNING"] = "1"
        self.assertNotEqual(self.run_export().returncode, 0)
        self.assertFalse((self.out / "summary.csv").exists())
        self.assertTrue((self.out / "summary.csv.partial").exists())
        self.assertIn("Database mismatch", (self.out / "diagnostics.txt").read_text())

    def test_mixed_incomplete_tests_rejected(self):
        (self.testroot / "interrupted").mkdir()
        self.assertNotEqual(self.run_export().returncode, 0)
        self.assertIn("interrupted", (self.out / "rejected_tests.txt").read_text())
        self.assertFalse((self.out / "summary.csv").exists())

    def test_empty_metric_rejected(self):
        self.add_test("empty", contents="")
        self.assertNotEqual(self.run_export().returncode, 0)
        self.assertIn("empty", (self.out / "rejected_tests.txt").read_text())

    def test_duplicate_database_rejected(self):
        self.assertNotEqual(self.run_export(self.design, self.testdb, self.testdb).returncode, 0)
        self.assertFalse(self.out.exists())

    def test_existing_output_preserved(self):
        self.out.mkdir()
        sentinel = self.out / "sentinel"
        sentinel.write_text("preserve")
        self.assertNotEqual(self.run_export().returncode, 0)
        self.assertEqual(sentinel.read_text(), "preserve")
        self.assertFalse((self.out / "inputs.txt").exists())

    def test_concurrent_output_claim(self):
        command = ["bash", str(SCRIPT), str(self.out), str(self.design), str(self.testdb)]
        processes = [subprocess.Popen(command, env=self.env, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, text=True) for _ in range(2)]
        for process in processes:
            process.communicate(timeout=20)
        self.assertEqual(sorted(p.returncode for p in processes), [0, 2])
        self.assertTrue((self.out / "summary.csv").exists())

    def test_row_limit(self):
        self.env.update(DVE_TEST_TOO_MANY_ROWS="1", DVE_COVERAGE_TIMEOUT="15")
        self.assertNotEqual(self.run_export().returncode, 0)
        self.assertIn("exceeds exporter limits", (self.out / "diagnostics.txt").read_text())
        self.assertFalse((self.out / "summary.csv").exists())

    def test_input_database_not_output(self):
        self.out = self.testdb / "report"
        self.assertNotEqual(self.run_export().returncode, 0)
        self.assertFalse(self.out.exists())

    def test_crlf_input_list(self):
        inputs = self.root / "inputs.txt"
        inputs.write_bytes(f"# comment\r\n{self.design}\r\n{self.testdb}\r\n".encode())
        self.assertEqual(self.run_export("--inputs-file", inputs).returncode, 0)

    def test_invalid_timeout(self):
        self.env["DVE_COVERAGE_TIMEOUT"] = "0"
        self.assertNotEqual(self.run_export().returncode, 0)
        self.assertFalse(self.out.exists())

    def test_timeout_not_success(self):
        self.env.update(DVE_COVERAGE_TIMEOUT="1", DVE_TEST_HANG="1")
        self.assertNotEqual(self.run_export().returncode, 0)
        self.assertFalse((self.out / "summary.csv").exists())


if __name__ == "__main__":
    unittest.main()

