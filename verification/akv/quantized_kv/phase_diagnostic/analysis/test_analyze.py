import copy
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze as a


def fixture_elf():
    code = {
        0x1000: (0xC0002573, 4, "rdcycle", "main"),
        0x1004: (0xC00025F3, 4, "rdcycle", "main"),
        0x1008: (0x0001, 2, "nop", "main"),
        0x1100: (0xF2805057, 4, "vfwmacc.vf", "dot"),
        0x1104: (0x02056407, 4, "vle32.v", "dot"),
        0x1200: (0x10B57553, 4, "fmul.s", "scale"),
        0x1300: (0x06B5045B, 4, ".word", "native"),
        0x1304: (0x02B5045B, 4, ".word", "native"),
    }
    text = bytearray(0x400)
    for pc, (bits, size, _, _) in code.items():
        text[pc-0x1000:pc-0x1000+size] = bits.to_bytes(size, "little")
    names, symbols = bytearray(b"\0"), bytearray(24)
    for name, address, size in (("main", 0x1000, 10), ("dot", 0x1100, 8),
                                 ("scale", 0x1200, 4), ("native", 0x1300, 8)):
        offset = len(names)
        names += name.encode() + b"\0"
        symbols += struct.pack("<IBBHQQ", offset, 0x12, 0, 1, address, size)
    symoff = 64 + len(text)
    stroff = symoff + len(symbols)
    shoff = (stroff + len(names) + 7) & ~7
    ident = b"\x7fELF\x02\x01\x01" + bytes(9)
    data = bytearray(ident + struct.pack("<HHIQQQIHHHHHH", 2, 243, 1, 0x1000,
                                       0, shoff, 0, 64, 0, 0, 64, 4, 0))
    data += text + symbols + names
    data += bytes(shoff - len(data))
    for section in ((0,)*10, (0, 1, 6, 0x1000, 64, len(text), 0, 0, 2, 0),
                    (0, 2, 0, 0, symoff, len(symbols), 3, 1, 8, 24),
                    (0, 3, 0, 0, stroff, len(names), 0, 0, 1, 0)):
        data += struct.pack("<IIQQQQIIQQ", *section)
    disasm = "\n".join(f"{pc:x}: {bits:0{size*2}x} {mnemonic} a0,a1"
                       for pc, (bits, size, mnemonic, _) in code.items())
    return bytes(data), disasm


def fixture_rows(instructions):
    rows, order, cycle = [], 0, 10
    def retire(pc, value=0):
        nonlocal order, cycle
        row = dict.fromkeys(a.COMMIT_HEADER, 0)
        row.update(event="retire", cycle=cycle, order=order, port=0, trans_id=-1,
                   pc=pc, insn=instructions[pc]["bits"], rd_wdata=value,
                   rd=(instructions[pc]["bits"] >> 7 & 31) if pc in (0x1000, 0x1004) else 0)
        rows.append(row)
        order += 1
        cycle += 2
    for i in range(3):
        retire(0x1000, 1000*i)
        retire(0x1008)
        retire(0x1100)
        retire(0x1104)
        retire(0x1200)
        if i == 2:
            for _ in range(4):
                retire(0x1300)
                retire(0x1304)
        retire(0x1004, 1000*i + 100*(i+1))
    return rows


def csv_text(rows):
    def value(k, v):
        return f"{v:x}" if k in a.csv_module.HEX_FIELDS and isinstance(v, int) else str(v)
    return ",".join(a.COMMIT_HEADER) + "\n" + "\n".join(
        ",".join(value(k, row[k]) for k in a.COMMIT_HEADER) for row in rows) + "\n"


def fixture_log():
    lines = [a.CAP]
    work = [(768, 768, 0, 768, 0, 0, 0), (8, 768, 0, 128, 0, 0, 0), (8, 0, 8, 128, 4, 9216, 1)]
    for i, (calls, dots, commands, values, panels, copied, groups) in enumerate(work):
        lines += [f"QUANT_DIAG_HSB_BEGIN trial={i} mode={i}",
                  f"QUANT_DIAG_HSB_RESULT trial={i} mode={i} cycles={100*(i+1)} "
                  f"calls={calls} dots={dots} commands={commands} values={values} panels={panels} "
                  f"copied={copied} quantizations=6 map=0 status=0 selection=0 groups={groups} executor=0 "
                  "fcsr=3 vcsr=5 max_abs=00000000 pair_max_abs=00000000 pair_bits_differ=0 errors=0 hex=" + "00000000"*768]
    return "\n".join(lines + [a.SUITE, "Core Test *** SUCCESS ***", "UVM_ERROR : 0", "UVM_FATAL : 0"]) + "\n"


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.binary, self.text = fixture_elf()
        self.elf = a.LinkedELF(self.binary)
        self.instructions = a.disassembly_map(self.text, self.elf)
        self.calls = a.call_log(fixture_log())
        self.rows = fixture_rows(self.instructions)
        self.phases = dict(schema="quantkv_phase_map_v1", functions={"dot": "qk_leaf", "scale": "scale_leaf"}, ranges=[])

    def run_analysis(self, rows=None, **kwargs):
        return a.analyze(kwargs.get("instructions", self.instructions),
                         io.StringIO(csv_text(self.rows if rows is None else rows)),
                         kwargs.get("calls", self.calls), kwargs.get("pcs", [0x1000, 0x1004]),
                         kwargs.get("phases", self.phases))

    def test_complete_counts_and_nonexecution_gap_semantics(self):
        report = self.run_analysis()
        self.assertEqual(report["csr_reads"], 6)
        self.assertFalse(report["functional_acceptance"])
        self.assertFalse(report["performance_acceptance"])
        self.assertEqual(report["phase_coverage"], "PARTIAL")
        for i, w in enumerate(report["windows"]):
            self.assertEqual(w["cycles"], 100*(i+1))
            self.assertNotEqual(w["monitor_retire_span"], w["cycles"])
            self.assertEqual(w["monitor_minus_csr_delta"], w["monitor_retire_span"]-w["cycles"])
            self.assertEqual(w["retired_instructions"], 12 if i == 2 else 4)
            self.assertEqual(w["mapped_phase_instructions"], 3)
            self.assertEqual(w["unmapped_phase_instructions"], 9 if i == 2 else 1)
            self.assertEqual(sum(w["function_next_pc_gap_cycles"].values()) + w["end_csr_gap_cycles"], w["monitor_retire_span"])
            self.assertEqual(sum(w["phase_next_pc_gap_cycles"].values()) + w["end_csr_gap_cycles"], w["monitor_retire_span"])
        self.assertEqual(report["windows"][2]["qbs_command_words"], [f"{x:08x}" for x in a.CUSTOM_SEQUENCE])

    def test_uops_not_architectural_instructions(self):
        row = dict(self.rows[1], event="uop_alloc", order=900, port=7, trans_id=0)
        rows = self.rows[:1] + [row, dict(row, event="uop_done")] + self.rows[1:]
        self.assertEqual(self.run_analysis(rows), self.run_analysis())

    def test_scalar_csr_alias_is_not_fp_arithmetic(self):
        self.assertEqual(a.instruction_type(dict(bits=0x00302573, bytes=4, mnemonic="frcsr")), "scalar_other")
        self.assertEqual(a.instruction_type(dict(bits=0x00102573, bytes=4, mnemonic="frflags")), "scalar_other")
        self.assertEqual(a.instruction_type(dict(bits=0x0000000F, bytes=4, mnemonic="fence")), "scalar_other")
        self.assertEqual(a.instruction_type(self.instructions[0x1200]), "scalar_fp")

    def test_same_cycle_two_ports_and_zero_gap(self):
        self.rows[2].update(cycle=self.rows[1]["cycle"], port=1)
        r = self.run_analysis()
        self.assertEqual(r["windows"][0]["functions"]["dot"], 2)
        self.rows[2]["port"] = 0
        with self.assertRaisesRegex(ValueError, "port order"):
            self.run_analysis()

    def test_wrapping_cycle_csr(self):
        self.rows[0]["rd_wdata"] = (1 << 64)-50
        self.rows[5]["rd_wdata"] = 50
        self.assertEqual(self.run_analysis()["windows"][0]["csr_cycle_delta"], 100)

    def test_reject_retirement_mutations(self):
        mutations = [(1, "order", 99), (1, "cycle", 0), (1, "trap", 1),
                     (1, "pc", 0x5555), (1, "insn", 0x2), (0, "rd", 0),
                     (0, "rd_wdata", "x"), (5, "rd_wdata", 101),
                     (5, "pc", 0x1000), (0, "rd_wdata", 1 << 64),
                     (0, "port", 2)]
        for index, key, value in mutations:
            with self.subTest(index=index, key=key):
                rows = copy.deepcopy(self.rows)
                rows[index][key] = value
                with self.assertRaises(ValueError): self.run_analysis(rows)
        for rows in (self.rows[:-1], self.rows + [dict(self.rows[-1], order=len(self.rows), cycle=999)], self.rows[1:]):
            with self.assertRaises(ValueError): self.run_analysis(rows)

    def test_reject_missing_or_extra_custom_work(self):
        rows = copy.deepcopy(self.rows)
        target = next(r for r in rows if r["pc"] == 0x1300)
        target.update(pc=0x1008, insn=1)
        with self.assertRaisesRegex(ValueError, "command sequence"):
            self.run_analysis(rows)
        rows = copy.deepcopy(self.rows)
        rows[1].update(pc=0x1300, insn=0x06B5045B)
        with self.assertRaisesRegex(ValueError, "command sequence"):
            self.run_analysis(rows)

    def test_reject_unknown_event_schema_and_unknown_field(self):
        for bad in (csv_text(self.rows).replace("retire", "mystery", 1),
                    csv_text(self.rows).replace("cycle,event", "event,cycle", 1),
                    csv_text(self.rows).replace("rd_wdata", "other", 1)):
            with self.assertRaises(ValueError):
                a.analyze(self.instructions, io.StringIO(bad), self.calls, [0x1000, 0x1004], self.phases)

    def test_pcs_elf_bytes_and_sized_symbols(self):
        with self.assertRaisesRegex(ValueError, "differs from ELF"):
            a.disassembly_map(self.text.replace("c0002573", "c0002673"), self.elf)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            a.disassembly_map(self.text + "\n1008: 0001 nop", self.elf)
        with self.assertRaises(ValueError): a.LinkedELF(self.binary[:50])
        with self.assertRaises(ValueError): a.LinkedELF(self.binary.replace(b"\x7fELF\x02", b"\x7fELF\x01", 1))
        with self.assertRaises(ValueError): self.run_analysis(pcs=[0x1004, 0x1000])
        other = copy.deepcopy(self.instructions)
        other[0x2000] = dict(other[0x1000])
        with self.assertRaisesRegex(ValueError, "Extra cycle"):
            self.run_analysis(instructions=other)

    def test_phase_ranges_require_exact_code_bounds(self):
        mapping = copy.deepcopy(self.phases)
        mapping["ranges"] = [dict(start="0x1008", end="0x100a", function="main", phase="fixture_only", evidence="Synthetic nop; not production phase proof")]
        self.assertEqual(self.run_analysis(phases=mapping)["windows"][0]["unmapped_phase_instructions"], 0)
        for field, value in (("end", "0x1009"), ("end", "0x1108"), ("function", "dot"), ("evidence", "")):
            bad = copy.deepcopy(mapping); bad["ranges"][0][field] = value
            with self.assertRaises(ValueError): self.run_analysis(phases=bad)
        bad = copy.deepcopy(mapping); bad["ranges"] *= 2
        with self.assertRaises(ValueError): self.run_analysis(phases=bad)
        for name in ("main", "akv_quant_strided_execute", "absent"):
            bad = copy.deepcopy(self.phases); bad["functions"][name] = "fake_precise_phase"
            with self.assertRaises(ValueError): self.run_analysis(phases=bad)

    def test_no_silent_phase_success_without_trace(self):
        with self.assertRaises(ValueError): self.run_analysis([])
        with self.assertRaises(ValueError): self.run_analysis(calls=self.calls[:2])
        with self.assertRaises(ValueError): self.run_analysis(calls=[dict(c, cycles=c["cycles"]+1) for c in self.calls])

    def test_log_exact_diagnostic_not_old_abba(self):
        self.assertEqual([c["mode"] for c in self.calls], [0, 1, 2])
        for bad in (fixture_log().replace(a.CAP+"\n", ""),
                    fixture_log().replace(a.PREFIX, "QUANT_THREEWAY_"),
                    "QUANT_PHASE_DIAGNOSTIC trials=3 order=H/S/B\n"+fixture_log(),
                    fixture_log().replace("trials=3", "trials=6"),
                    fixture_log().replace("dots=768", "dots=767", 1),
                    fixture_log().replace("mode=1", "mode=2", 1),
                    fixture_log().replace("fcsr=3", "fcsr=1", 1),
                    fixture_log().replace(a.SUITE, "QUANT_THREEWAY_SUITE_PASS trials=6"),
                    fixture_log()+a.SUITE+"\n",
                    fixture_log().replace("errors=0", "errors=1", 1)):
            with self.assertRaises(ValueError): a.call_log(bad)

    def test_cli_pins_and_terminal_finalization_without_tools(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            payloads = {"elf": self.binary, "log": fixture_log().encode(), "commit": csv_text(self.rows).encode(),
                        "phase_map": json.dumps(self.phases).encode(), "objdump": b"synthetic-tool-only",
                        "monitor": ("cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,mem_addr,\n"
                                    "rvfi_instr_i[port].pc_rdata rvfi_instr_i[port].rd_wdata").encode()}
            files = {}
            for role, data in payloads.items():
                path = root / role; path.write_bytes(data)
                files[role] = dict(path=role, sha256=a.digest(path))
            manifest = root / "inputs.json"
            manifest.write_text(json.dumps(dict(schema="quantkv_phase_inputs_v1", files=files,
                                                start_pc="0x1000", end_pc="0x1004")))
            output = root / "analysis"
            argv = ["analyze.py", "--inputs", str(manifest), "--inputs-sha256", a.digest(manifest), "--output", str(output)]
            result = type("Completed", (), dict(stdout=self.text, stderr=""))()
            with patch.object(sys, "argv", argv), patch.object(a.subprocess, "run", return_value=result) as command, patch("sys.stdout", io.StringIO()):
                a.main()
            command.assert_called_once()
            report = json.loads((output / "result.json").read_text())
            self.assertEqual(report["state"], "DIAGNOSTIC_RETIREMENT_PROVEN")
            self.assertTrue(report["pre_post_pins_match"])
            self.assertEqual(report["disassembly_sha256"], a.digest(output / "disassembly.txt"))
            self.assertEqual(report["pins_sha256"], a.digest(output / "pins.json"))
            argv[-1] = str(root / "bad")
            def mutate(*args, **kwargs):
                (root / "log").write_text(fixture_log()+"unrelated drift\n")
                return result
            with patch.object(sys, "argv", argv), patch.object(a.subprocess, "run", side_effect=mutate):
                with self.assertRaisesRegex(ValueError, "Post-analysis input drift"): a.main()
            self.assertFalse((root / "bad").exists())


if __name__ == "__main__":
    unittest.main()
