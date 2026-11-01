import gzip
import io
import json
import tempfile
import unittest
from pathlib import Path

from ara_verify.vdb_raw import export_raw


class VdbRawTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.compile_vdb = root / "compile.vdb"
        self.test_vdb = root / "case.vdb"
        self.compile_vdb.mkdir()
        (self.compile_vdb / ".vdb_version").write_text("V-2023.12-SP1\n", encoding="ascii")
        self._xml(
            self.compile_vdb / "snps/coverage/db/design/verilog.design.xml",
            '<design><ucapi_version patch_str="V-2023.12-SP1"/></design>',
            compressed=True,
        )
        self.test_dir = self.test_vdb / "snps/coverage/db/testdata/case"
        self.test_dir.mkdir(parents=True)

    def _xml(self, path, content, compressed=True):
        path.parent.mkdir(parents=True, exist_ok=True)
        if compressed:
            with gzip.open(path, "wb") as stream:
                stream.write(content.encode("utf-8"))
        else:
            path.write_text(content, encoding="utf-8")

    def _metric(self, metric, body, version="V-2023.12-SP1", compressed=True):
        self._xml(
            self.test_dir / f"{metric}.verilog.data.xml",
            f'<covdata><ucapi_version patch_str="{version}"/>{body}</covdata>',
            compressed=compressed,
        )

    def test_exports_bitmap_and_interval_without_claiming_coverage(self):
        self._metric(
            "line",
            '<instance_data name="ara_tb" value="1111"/>'
            '<instance_data name="ara_tb.dut" value="1010" chksum="7"/>'
            '<instance_data name="ara_tb.dut.core" value="01"/>',
        )
        self._metric(
            "tgl",
            '<instance_data name="ara_tb.dut" value="011"/>'
            '<instance_intervaldata name="ara_tb.dut" value=" 0 8 14 -1"/>',
            compressed=False,
        )
        output = io.StringIO()
        summary = export_raw(
            self.compile_vdb, self.test_vdb, ("line", "tgl"),
            "ara_tb.dut", None, output,
        )
        records = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([item["type"] for item in records],
                         ["metadata", "raw_record", "raw_record", "raw_record", "raw_record", "summary"])
        self.assertEqual([item["instance"] for item in records[1:-1]],
                         ["ara_tb.dut", "ara_tb.dut.core", "ara_tb.dut", "ara_tb.dut"])
        self.assertEqual(records[-2]["record_type"], "instance_intervaldata")
        self.assertEqual(records[-2]["value"], " 0 8 14 -1")
        self.assertEqual(summary["metrics"]["line"]["raw_one_characters"], 3)
        self.assertEqual(summary["metrics"]["tgl"]["interval_records"], 1)
        self.assertFalse(summary["coverage_scores_computed"])

    def test_summary_only_omits_raw_values(self):
        self._metric("branch", '<instance_data name="ara_tb.dut" value="101"/>')
        output = io.StringIO()
        export_raw(self.compile_vdb, self.test_vdb, ("branch",), None,
                   None, output, summary_only=True)
        records = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["metrics"]["branch"]["raw_bitmap_characters"], 3)

    def test_rejects_missing_metric(self):
        with self.assertRaisesRegex(ValueError, "missing metric data"):
            export_raw(self.compile_vdb, self.test_vdb, ("line",), None,
                       None, io.StringIO())

    def test_rejects_mismatched_version(self):
        self._metric("line", '<instance_data name="ara_tb" value="1"/>',
                     version="V-2022.06")
        with self.assertRaisesRegex(ValueError, "version differs"):
            export_raw(self.compile_vdb, self.test_vdb, ("line",), None,
                       None, io.StringIO())

    def test_rejects_unknown_records(self):
        self._metric("line", '<other name="ara_tb" value="1"/>')
        with self.assertRaisesRegex(ValueError, "unsupported XML element"):
            export_raw(self.compile_vdb, self.test_vdb, ("line",), None,
                       None, io.StringIO())


if __name__ == "__main__":
    unittest.main()
