"""Static-signature fixtures, not compiled RTL or functional PLIC tests.

Run with the prepared PLIC venv. Missing hjson skips the fixture suite without
breaking unittest discovery; the lazy-dependency failure test still runs.
All files created by tests are disposable and no generator/EDA is invoked.
"""

import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from fpga import check_plic as gate


HJSON_AVAILABLE = importlib.util.find_spec("hjson") is not None
DT_AVAILABLE = all(shutil.which(name) for name in ("dtc", "fdtget"))


def fixture_offsets():
    # Independently spelled out layout, not imported from the checker.
    result = {f"PRIO{i}": i * 4 for i in range(58)}
    result.update(IP_0=0x1000, IP_1=0x1004, IE0_0=0x2000, IE0_1=0x2004,
                  IE1_0=0x2080, IE1_1=0x2084, THRESHOLD0=0x200000, CC0=0x200004,
                  THRESHOLD1=0x201000, CC1=0x201004, MSIP0=0x3FFFFF8, ALERT_TEST=0x3FFFFFC)
    return result


def fixture_hjson():
    def reg(name, bits, sw="rw", hw="hro", **extra):
        return dict(name=name, fields=[{"bits": bits}], swaccess=sw, hwaccess=hw, **extra)
    registers = [reg(f"PRIO{i}", "2:0") for i in range(58)]
    for name, offset, sw, hw in (("IP", 0x1000, "ro", "hwo"), ("IE0", 0x2000, "rw", "hro"),
                                  ("IE1", 0x2080, "rw", "hro")):
        registers.extend([{"skipto": hex(offset)},
                          {"multireg": reg(name, "0", sw, hw, count="NumSrc")}])
    for context, offset in ((0, 0x200000), (1, 0x201000)):
        registers.extend([{"skipto": hex(offset)}, reg(f"THRESHOLD{context}", "2:0"),
                          reg(f"CC{context}", "5:0", hw="hrw", hwext="true", hwqe="true", hwre="true")])
    registers.extend([{"skipto": "0x3fffff8"}, reg("MSIP0", "0"),
                      {"skipto": "0x3fffffc"}, reg("ALERT_TEST", "0", sw="wo")])
    return {"name": "rv_plic", "regwidth": "32", "no_auto_alert_regs": "True",
            "bus_interfaces": [{"protocol": "reg_iface", "direction": "device"}],
            "param_list": [{"name": name, "default": value, "local": "true", "type": "int"}
                           for name, value in (("NumSrc", "58"), ("NumTarget", "2"), ("PrioWidth", "3"))],
            "inter_signal_list": [{"name": name, "width": "2"} for name in ("irq", "msip")],
            "registers": registers}


def fixture_rtl():
    package = ["package rv_plic_reg_pkg;"]
    for name, value in (("NumSrc", 58), ("NumTarget", 2), ("PrioWidth", 3), ("BlockAw", 26), ("NumAlerts", 1)):
        package.append(f"parameter int {name} = {value};")
    for name in [f"prio{i}" for i in range(58)] + ["threshold0", "threshold1"]:
        package.extend([f"typedef struct packed {{ logic [2:0] q; }} rv_plic_reg2hw_{name}_reg_t;",
                        f"rv_plic_reg2hw_{name}_reg_t {name};"])
    for context in range(2):
        package.extend([
            f"rv_plic_reg2hw_ie{context}_mreg_t [57:0] ie{context};",
            f"typedef struct packed {{ logic [5:0] q; logic qe; logic re; }} rv_plic_reg2hw_cc{context}_reg_t;",
            f"typedef struct packed {{ logic [5:0] d; }} rv_plic_hw2reg_cc{context}_reg_t;",
            f"rv_plic_reg2hw_cc{context}_reg_t cc{context};",
            f"rv_plic_hw2reg_cc{context}_reg_t cc{context};"])
    package.append("rv_plic_hw2reg_ip_mreg_t [57:0] ip;")
    for name, offset in fixture_offsets().items():
        package.append(f"parameter logic [BlockAw-1:0] RV_PLIC_{name}_OFFSET = 26'h {offset:x};")
    package.append("endpackage")

    top = ["module rv_plic_reg_top #(parameter int AW = 26) ();",
           "assign reg_addr = reg_intf_req.addr[BlockAw-1:0];",
           "assign reg_error = (devmode_i & addrmiss) | wr_err;",
           "assign reg_intf_rsp.error = reg_error;"]
    for index, name in enumerate(fixture_offsets()):
        top.append(f"addr_hit[{index}] = (reg_addr == RV_PLIC_{name}_OFFSET);")
    for name in [f"prio{i}" for i in range(58)] + ["threshold0", "threshold1"]:
        top.append(f"prim_subreg u_{name} (.q(reg2hw.{name}.q));")
    for context in range(2):
        top.extend([f"logic [5:0] cc{context}_qs;", f"logic [5:0] cc{context}_wd;"])
        for source in range(58):
            top.append(f"prim_subreg u_ie{context}_{source} (.q(reg2hw.ie{context}[{source}].q));")
        top.append(f"prim_subreg_ext u_cc{context} (.d(hw2reg.cc{context}.d), .qre(reg2hw.cc{context}.re), "
                   f".qe(reg2hw.cc{context}.qe), .q(reg2hw.cc{context}.q));")
    for source in range(58):
        top.append(f"prim_subreg u_ip{source} (.d(hw2reg.ip[{source}].d));")
    top.append("endmodule")

    core = ["module rv_plic #(localparam int SRCW = $clog2(NumSrc)) (",
            "input [NumSrc-1:0] intr_src_i, output [NumTarget-1:0] irq_o, input clk_i);",
            "localparam int MAX_PRIO = 7;", "assign msip_o = '0;", "assign cc_id = irq_id_o;"]
    for source in range(58):
        core.append(f"assign prio[{source}] = reg2hw.prio{source}.q;")
    for context in range(2):
        core.extend([f"for (genvar s = 0; s < 58; s++) begin : gen_ie{context}",
                     f"assign ie[{context}][s] = reg2hw.ie{context}[s].q; end",
                     f"assign threshold[{context}] = reg2hw.threshold{context}.q;",
                     f"assign claim_re[{context}] = reg2hw.cc{context}.re;",
                     f"assign claim_id[{context}] = irq_id_o[{context}];",
                     f"assign complete_we[{context}] = reg2hw.cc{context}.qe;",
                     f"assign complete_id[{context}] = reg2hw.cc{context}.q;",
                     f"assign hw2reg.cc{context}.d = cc_id[{context}];"])
    core.extend(["for (genvar s = 0; s < 58; s++) begin : gen_ip",
                 "assign hw2reg.ip[s].de = 1'b1; assign hw2reg.ip[s].d = ip[s]; end",
                 "rv_plic_gateway #(.N_SOURCE(NumSrc)) u_gateway (.src_i(intr_src_synced),",
                 ".le_i(LevelEdgeTrig), .claim_i(claim), .complete_i(complete), .ip_o(ip));",
                 "for (genvar i = 0; i < NumTarget; i++) begin : gen_target",
                 "rv_plic_target #(.N_SOURCE(NumSrc), .MAX_PRIO(MAX_PRIO)) u_target (",
                 ".ip_i(ip), .ie_i(ie[i]), .prio_i(prio), .threshold_i(threshold[i]),",
                 ".irq_o(irq_o[i]), .irq_id_o(irq_id_o[i])); end",
                 "rv_plic_reg_top #(.reg_req_t(reg_req_t), .reg_rsp_t(reg_rsp_t)) u_reg (.devmode_i(1'b1));",
                 "`ASSUME(Irq0Tied_A, intr_src_i[0] == 1'b0)", "endmodule"])
    gateway = """module rv_plic_gateway #(parameter int N_SOURCE = 32) (
input [N_SOURCE-1:0] src_i, output logic [N_SOURCE-1:0] ip_o); endmodule"""
    target = """module rv_plic_target #(parameter int N_SOURCE = 32,
parameter int MAX_PRIO = 7, localparam int SrcWidth = $clog2(N_SOURCE),
parameter int Unused = 0) (); prim_max_tree #(.NumSrc(N_SOURCE)) tree (); endmodule"""
    return {"rv_plic_reg_pkg": "\n".join(package), "rv_plic_reg_top": "\n".join(top),
            "rv_plic": "\n".join(core), "rv_plic_gateway": gateway, "rv_plic_target": target}


DTS = """/dts-v1/;
/ {
  #address-cells = <2>; #size-cells = <2>;
  cpus {
    #address-cells = <1>; #size-cells = <0>;
    cpu@0 { device_type = "cpu"; reg = <0>;
      CPU0: interrupt-controller { compatible = "riscv,cpu-intc";
        #address-cells = <0>; #interrupt-cells = <1>; interrupt-controller;
      };
    };
  };
  soc { #address-cells = <2>; #size-cells = <2>; ranges;
    plic: interrupt-controller@4000000 { compatible = "riscv,plic0";
      #address-cells = <0>; #interrupt-cells = <1>; interrupt-controller;
      interrupts-extended = <&CPU0 11 &CPU0 9>;
      riscv,ndev = <57>; riscv,max-priority = <7>;
      reg = <0 0x04000000 0 0x04000000>;
    };
  };
};
"""


class DependencyTests(unittest.TestCase):
    def test_missing_hjson_is_reported_not_import_time_failure(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(gate.importlib, "import_module", side_effect=ModuleNotFoundError("hjson")):
            report = gate.check_plic(Path(tmp))
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("configuration error: missing hjson", json.dumps(report["errors"]))


@unittest.skipUnless(HJSON_AVAILABLE, "run with verification/tools/plic-venv/bin/python")
class PlicTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix=".plic-test-", dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.plic = self.root / "plic"
        self.config = {"instance_name": "rv_plic", "param_values":
                       {"src": 58, "target": 2, "prio": 7, "nonstd_regs": 0}}
        self.write("data/rv_plic.ipconfig.hjson", json.dumps(self.config))
        self.write("data/rv_plic.hjson", "// HJSON fixture, not a generated IP\n" + json.dumps(fixture_hjson()))
        for name, text in fixture_rtl().items():
            self.write(f"rtl/{name}.sv", text)
        self.dts = self.root / "input.dts"
        self.dts.write_text(DTS)

    def write(self, name, text):
        path = self.plic / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def audit(self, dts=False):
        return gate.check_plic(self.plic, self.dts if dts else None)

    def fail_report(self, text=None, dts=False):
        report = self.audit(dts)
        self.assertEqual(report["status"], "FAIL", report)
        self.assertFalse(report["accepted"])
        if text:
            self.assertIn(text, json.dumps(report["errors"]))
        return report

    def test_plic_only_pass_is_explicitly_not_functional_or_soc_validation(self):
        report = self.audit()
        self.assertEqual(report["status"], "STATIC_PASS", report["errors"])
        self.assertEqual(report["dts"]["status"], "NOT_CHECKED")
        self.assertEqual(report["contract"]["src"], 58)
        self.assertEqual(report["contract"]["ndev"], 57)
        self.assertEqual(report["functional_status"], "NOT_VALIDATED")
        self.assertEqual(report["soc_wiring"], "NOT_VALIDATED")
        self.assertEqual(report["os_custom_context"], "NOT_VALIDATED")
        self.assertEqual(len(report["files"]), 7)
        for name, record in report["files"].items():
            self.assertEqual(record["sha256"], hashlib.sha256(Path(name).read_bytes()).hexdigest())

    def test_each_required_file_missing_fails(self):
        for path in list(self.plic.rglob("*")):
            if path.is_file():
                with self.subTest(path=path):
                    text = path.read_text()
                    path.unlink()
                    self.fail_report(path.name)
                    path.write_text(text)

    def test_ipconfig_explicit_values_and_types(self):
        path = "data/rv_plic.ipconfig.hjson"
        for key, value in (("src", 51), ("src", 52), ("src", 57), ("src", 59), ("src", True),
                           ("target", 1), ("prio", 8), ("nonstd_regs", 1)):
            with self.subTest(key=key, value=value):
                config = {"instance_name": "rv_plic", "param_values": dict(self.config["param_values"], **{key: value})}
                self.write(path, json.dumps(config))
                self.fail_report("ipconfig")
        self.write(path, '{instance_name: "rv_plic", param_values: {}}')
        self.fail_report("explicit src/target")

    def test_unquoted_hjson_and_optional_cfg(self):
        self.write("data/rv_plic.ipconfig.hjson", """{
instance_name: rv_plic
param_values: {
src: 58
target: 2
prio: 7
nonstd_regs: 0
}
}""")
        self.write("rv_plic.cfg.hjson", json.dumps(self.config))
        self.assertTrue(self.audit()["accepted"])
        self.write("rv_plic.cfg.hjson", json.dumps({**self.config, "param_values": {}}))
        self.fail_report("rv_plic.cfg.hjson")

    def test_malformed_and_duplicate_hjson_rejected(self):
        for text in ("{broken", "[]", '{"instance_name":"rv_plic", "instance_name":"rv_plic"}'):
            with self.subTest(text=text):
                self.write("data/rv_plic.ipconfig.hjson", text)
                self.fail_report("ipconfig")

    def test_hjson_register_map_mutants(self):
        for mutation in ("count", "stride", "cc_width", "duplicate", "access", "missing_cc", "parameter"):
            with self.subTest(mutation=mutation):
                desc = fixture_hjson()
                regs = desc["registers"]
                if mutation == "count":
                    regs[59]["multireg"]["count"] = "57"
                elif mutation == "stride":
                    next(r for r in regs if r.get("skipto") == "0x2080")["skipto"] = "0x2100"
                elif mutation == "cc_width":
                    next(r for r in regs if r.get("name") == "CC1")["fields"][0]["bits"] = "4:0"
                elif mutation == "duplicate":
                    regs.append(regs[0])
                elif mutation == "access":
                    regs[0]["swaccess"] = "ro"
                elif mutation == "missing_cc":
                    regs[:] = [r for r in regs if r.get("name") != "CC1"]
                else:
                    desc["param_list"][0]["default"] = "32"
                self.write("data/rv_plic.hjson", json.dumps(desc))
                self.fail_report("data/rv_plic.hjson")

    def test_old_32_1_package_rejected_even_with_correct_metadata(self):
        path = self.plic / "rtl/rv_plic_reg_pkg.sv"
        path.write_text(path.read_text().replace("NumSrc = 58", "NumSrc = 32")
                        .replace("NumTarget = 2", "NumTarget = 1").replace("BlockAw = 26", "BlockAw = 27"))
        self.fail_report("NumSrc")

    def test_pkg_and_core_mutants(self):
        mutants = [
            ("rv_plic_reg_pkg", "BlockAw = 26", "BlockAw = 27"),
            ("rv_plic_reg_pkg", "PrioWidth = 3", "PrioWidth = 4"),
            ("rv_plic_reg_pkg", "26'h 2080", "26'h 2100"),
            ("rv_plic_reg_pkg", "[57:0] ie1", "[31:0] ie1"),
            ("rv_plic", "reg2hw.ie1[s].q", "reg2hw.ie0[s].q"),
            ("rv_plic", "s < 58", "s < 57"),
            ("rv_plic", "assign prio[57] = reg2hw.prio57.q;", ""),
            ("rv_plic", ".N_SOURCE(NumSrc)", ".N_SOURCE(32)"),
            ("rv_plic", ".devmode_i(1'b1)", ".devmode_i(1'b0)"),
            ("rv_plic", "assign msip_o = '0;", "assign msip_o = reg2hw.msip0.q;"),
            ("rv_plic", "`ASSUME(Irq0Tied_A, intr_src_i[0] == 1'b0)", ""),
            ("rv_plic", ".irq_o(irq_o[i])", ".irq_o(irq_o[0])"),
            ("rv_plic_target", ".NumSrc(N_SOURCE)", ".NumSrc(32)"),
        ]
        for name, old, new in mutants:
            with self.subTest(name=name, old=old):
                original = fixture_rtl()[name]
                self.assertIn(old, original)
                self.write(f"rtl/{name}.sv", original.replace(old, new))
                self.fail_report(f"rtl/{name}.sv")
                self.write(f"rtl/{name}.sv", original)

    def test_reg_top_connection_decode_and_width_mutants(self):
        path = "rtl/rv_plic_reg_top.sv"
        original = fixture_rtl()["rv_plic_reg_top"]
        for old, new in (("reg2hw.ie1[57].q", "reg2hw.ie1[56].q"),
                         ("reg2hw.cc1.re", "reg2hw.cc0.re"),
                         ("RV_PLIC_IE1_0_OFFSET", "RV_PLIC_IE0_0_OFFSET"),
                         ("reg2hw.threshold1.q", "reg2hw.threshold0.q"),
                         ("[5:0] cc1_wd", "[4:0] cc1_wd"),
                         ("reg_intf_req.addr[BlockAw-1:0]", "reg_intf_req.addr[26:0]")):
            with self.subTest(old=old):
                self.write(path, original.replace(old, new))
                self.fail_report("rtl/rv_plic_reg_top.sv")

    def test_comments_strings_and_conditionals_do_not_supply_required_signatures(self):
        path = "rtl/rv_plic_reg_pkg.sv"
        original = fixture_rtl()["rv_plic_reg_pkg"]
        required = "parameter int BlockAw = 26;"
        for replacement in ("// " + required, "/* " + required + " */", '"' + required + '"',
                            "`ifdef NEVER\n" + required + "\n`endif"):
            with self.subTest(replacement=replacement):
                self.write(path, original.replace(required, replacement))
                self.fail_report("rtl/rv_plic_reg_pkg.sv")

    def test_duplicate_constant_rejected(self):
        path = "rtl/rv_plic_reg_pkg.sv"
        self.write(path, fixture_rtl()["rv_plic_reg_pkg"] + "\nparameter int NumSrc = 58;\n")
        self.fail_report("NumSrc")

    @unittest.skipUnless(DT_AVAILABLE, "dtc/fdtget required")
    def test_real_dtc_queries_correct_dts(self):
        report = self.audit(dts=True)
        self.assertEqual(report["status"], "STATIC_PASS", report["errors"])
        self.assertEqual(report["dts"]["contexts"], ["hart0:M", "hart0:S"])
        self.assertEqual(report["dts"]["boot_dtb"], "NOT_VALIDATED")

    @unittest.skipUnless(DT_AVAILABLE, "dtc/fdtget required")
    def test_dts_contract_mutants(self):
        for old, new in (("ndev = <57>", "ndev = <51>"), ("ndev = <57>", "ndev = <58>"),
                         ("&CPU0 11 &CPU0 9", "&CPU0 9 &CPU0 11"),
                         ("&CPU0 11 &CPU0 9", "&CPU0 11"),
                         ("0 0x04000000 0 0x04000000", "0 0x0c000000 0 0x04000000"),
                         ("0 0x04000000 0 0x04000000", "0 0x04000000 0 0x08000000"),
                         ("riscv,max-priority = <7>;", ""),
                         ('compatible = "riscv,plic0";', 'compatible = "riscv,plic0"; status = "disabled";'),
                         ('device_type = "cpu"; reg = <0>;', 'device_type = "cpu"; reg = <1>;')):
            with self.subTest(old=old, new=new):
                self.dts.write_text(DTS.replace(old, new))
                self.fail_report(dts=True)

    @unittest.skipUnless(DT_AVAILABLE, "dtc/fdtget required")
    def test_known_initrd_placeholders_do_not_claim_final_dtb_validation(self):
        chosen = "chosen { linux,initrd-start = <0 __INITRD_START__>; linux,initrd-end = <0 __INITRD_END__>; };"
        self.dts.write_text(DTS.replace("  cpus {", "  " + chosen + "\n  cpus {", 1))
        report = self.audit(dts=True)
        self.assertTrue(report["accepted"], report["errors"])
        self.assertEqual(report["dts"]["input_kind"], "DTS_TEMPLATE")
        self.assertEqual(len(report["dts"]["template_substitutions"]), 2)
        self.assertEqual(report["dts"]["boot_dtb"], "NOT_VALIDATED")

    def test_unknown_or_misplaced_template_tokens_fail(self):
        for value in ("__NDEV__", "__INITRD_START__"):
            self.dts.write_text(DTS.replace("ndev = <57>", f"ndev = <{value}>"))
            self.fail_report(dts=True)

    def test_dt_tools_missing_or_timeout_are_failures(self):
        with patch.object(gate.shutil, "which", return_value=None):
            self.fail_report("dtc and fdtget", dts=True)
            self.assertTrue(self.audit()["accepted"])
        with patch.object(gate.shutil, "which", side_effect=lambda x: x), \
                patch.object(gate.subprocess, "run", side_effect=subprocess.TimeoutExpired("dtc", 5)):
            self.fail_report("timed out", dts=True)

    def test_dts_includes_rejected_without_external_reads(self):
        self.dts.write_text('/dts-v1/; /include/ "external.dtsi"')
        self.fail_report("self-contained", dts=True)

    @unittest.skipUnless(DT_AVAILABLE, "dtc/fdtget required")
    def test_dts_bus_translation_or_missing_identity_mapping_fails(self):
        for replacement in ("", "ranges = <0 0x04000000 0 0x0c000000 0 0x04000000>;"):
            with self.subTest(replacement=replacement):
                self.dts.write_text(DTS.replace("ranges;", replacement))
                self.fail_report("ranges", dts=True)

    @unittest.skipUnless(DT_AVAILABLE, "dtc/fdtget required")
    def test_two_distinct_context_phandles_are_not_two_privilege_contexts(self):
        extra = """cpu@1 { device_type = "cpu"; reg = <1>;
          CPU1: interrupt-controller { compatible = "riscv,cpu-intc";
            #interrupt-cells = <1>; interrupt-controller; };
        };"""
        self.dts.write_text(DTS.replace("    cpu@0", extra + "\n    cpu@0", 1)
                            .replace("&CPU0 11 &CPU0 9", "&CPU0 11 &CPU1 9"))
        self.fail_report("same-hart", dts=True)

    def test_oversized_or_nonregular_input_is_rejected(self):
        path = self.plic / "data/rv_plic.hjson"
        path.write_text(" " * (gate.MAX_INPUT_BYTES + 1))
        self.fail_report("bounded regular")
        path.unlink()
        path.mkdir()
        self.fail_report("bounded regular")

    def test_cli_refuses_output_symlink(self):
        link = self.root / "result-link"
        target = self.root / "not-created.json"
        link.symlink_to(target)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(gate.main(["--plic-dir", str(self.plic), "--output", str(link)]), 2)
        self.assertFalse(target.exists())

    def test_output_is_exclusive_and_never_changes_inputs(self):
        before = {p: p.read_bytes() for p in self.plic.rglob("*") if p.is_file()}
        report = self.root / "report.json"
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(gate.main(["--plic-dir", str(self.plic), "--output", str(report)]), 0)
        self.assertEqual(json.loads(stdout.getvalue()), json.loads(report.read_text()))
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(gate.main(["--plic-dir", str(self.plic), "--output", str(report)]), 2)
            self.assertEqual(gate.main(["--plic-dir", str(self.plic), "--output", str(self.plic / "new.json")]), 2)
            self.assertEqual(gate.main(["--plic-dir", str(self.plic), "--output", str(self.dts)]), 2)
        self.assertEqual(before, {p: p.read_bytes() for p in self.plic.rglob("*") if p.is_file()})

    def test_cli_fail_exit_and_optional_cfg_broken_symlink(self):
        (self.plic / "rv_plic.cfg.hjson").symlink_to(self.root / "absent")
        self.fail_report("rv_plic.cfg.hjson")
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(gate.main(["--plic-dir", str(self.plic)]), 1)
        self.assertEqual(json.loads(stdout.getvalue())["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
