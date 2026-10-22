import copy
import json
import subprocess
import unittest
import apply_qbs_rooted_701 as report


class RebindTests(unittest.TestCase):
    def config(self):
        c = json.loads((report.PRIOR / "config.json").read_bytes())
        c.update(inputs=(report.BASE701 / "combined-inputs.txt").read_text().splitlines(),
                 selected_tests=(report.RAW701 / "selected_tests.txt").read_text().splitlines(), latest_precheck_tests=701,
                 latest701=dict(baseline=str(report.BASE701), raw_reference=str(report.RAW701),
                                prior_config_sha256=report.PRIOR_SEAL, prior_result_sha256=report.PRIOR_RESULT_SEAL))
        return c

    def test_actual701_membership(self):
        report.population_gate(self.config())

    def test_reject699_or_reorder(self):
        for change in (lambda c: c.update(latest_precheck_tests=699),
                       lambda c: c["inputs"].reverse(), lambda c: c["selected_tests"].pop()):
            c = self.config()
            change(c)
            with self.assertRaises(ValueError):
                report.population_gate(c)

    def test_protected_inventory_and_zero(self):
        c = self.config()
        bitmap = json.loads((report.BASE701 / "combined-bits.json").read_bytes())
        old = json.loads((report.base.BASE / "combined-bits.json").read_bytes())
        report.zero_targets(c["plan"]["scopes"], bitmap, old)
        scope = next(iter(c["plan"]["scopes"]))
        row = next(r for r in c["plan"]["scopes"][scope]["branch"] if r["target"])
        bad = copy.deepcopy(bitmap)
        record = bad["metrics"]["branch"][scope]
        record["bits"] = format(int(record["bits"], 16) | 1 << (record["width"] - row["point"]["raw_index"] - 1), "x")
        with self.assertRaises(ValueError):
            report.zero_targets(c["plan"]["scopes"], bad, old)
        with self.assertRaises(ValueError):
            report.zero_targets({scope: c["plan"]["scopes"][scope]}, bitmap, old)

    def test_shape_changed(self):
        c = self.config()
        bitmap = json.loads((report.BASE701 / "combined-bits.json").read_bytes())
        old = json.loads((report.base.BASE / "combined-bits.json").read_bytes())
        bitmap["metrics"]["branch"][next(iter(c["plan"]["scopes"]))]["checksum"] = "0"
        with self.assertRaises(ValueError):
            report.zero_targets(c["plan"]["scopes"], bitmap, old)

    def test_product_only_exact_vendor_absence(self):
        reference = report.reference_rows(report.RAW701 / "summary.csv")
        product = {s: r for s, r in reference.items() if s != report.vendor.ROOT}
        report.product_match(product, reference)
        product.pop(next(s for s in product if s != "ara_tb"))
        with self.assertRaises(ValueError):
            report.product_match(product, reference)

    def test_product_metrics_must_match(self):
        reference = report.reference_rows(report.RAW701 / "summary.csv")
        product = copy.deepcopy({s: r for s, r in reference.items() if s != report.vendor.ROOT})
        product["ara_tb"]["Branch"] = "0.00%"
        with self.assertRaises(ValueError):
            report.product_match(product, reference)

    def test_root_alias_rejected(self):
        c = self.config()
        c["root_refresh_scopes"][-1] = "i_payload_buffer"
        with self.assertRaises(ValueError):
            report.population_gate(c)

    def test_exact_tcl_population_change(self):
        original = (report.base.HERE / "apply_qbs_historical.tcl").read_text()
        body = original[original.index("proc qbsapp_session"):original.index("if {![info exists qbsapp_library_only]}")]
        hook = report.TCL.read_text()
        transform = hook[hook.index("set needle"):hook.index("set failed")]
        result = subprocess.run(["tclsh"], text=True, input=body + transform + '\nputs [info body qbsapp_session]\n',
                                capture_output=True, check=True)
        self.assertEqual(result.stderr, "")
        self.assertIn("$qbsapp_count != 701", result.stdout)
        self.assertNotIn("$qbsapp_count != 699", result.stdout)
        self.assertNotIn("-update", hook)


if __name__ == "__main__":
    unittest.main()
