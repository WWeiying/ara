"""URG report integrity checks must reject silent fatal failures."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ara_verify.urg_report import audit_report


class UrgReportTest(unittest.TestCase):
    def test_valid_report_is_diagnostic_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "report"
            report.mkdir()
            compile_vdb = root / "compile.vdb"
            test_vdb = root / "test.vdb"
            (report / "session.xml").write_text(
                '<session><info><attr name="command" value="urg -dir '
                f'{compile_vdb} {test_vdb}"/><attr name="top_instance" '
                'value="ara_tb"/></info><old_coverage><scope type="top">'
                '<metric name="Line" value="5/10"/></scope>'
                '</old_coverage></session>', encoding="utf-8")
            for name in ("dashboard.html", "hierarchy.html", "modlist.html"):
                (report / name).write_text("ok", encoding="utf-8")
            log = root / "urg.log"
            log.write_text("report complete\n", encoding="utf-8")
            result = audit_report(report, log, {"line"}, compile_vdb, test_vdb)
            self.assertEqual(result["status"], "REPORT_VALID")
            self.assertEqual(result["top_instance"], "ara_tb")
            log.write_text("Segmentation fault\n", encoding="utf-8")
            self.assertEqual(audit_report(report, log, {"line"},
                                          compile_vdb, test_vdb)["status"],
                             "INVALID")
            self.assertEqual(audit_report(report, log, {"line", "cond"},
                                          compile_vdb, test_vdb)["status"],
                             "INVALID")


if __name__ == "__main__":
    unittest.main()
