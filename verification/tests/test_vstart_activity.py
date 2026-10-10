import unittest

from ara_verify.vstart_activity import collect_vstart


def row(pc, insn, rd="", data=""):
    return {"event": "retire", "trap": "0", "pc": f"{pc:016x}",
            "insn": f"{insn:08x}", "rd": rd, "rd_wdata": data}


class VstartActivityTests(unittest.TestCase):
    def test_links_known_nonzero_write_to_retired_vector_operation(self):
        csrw_x5 = (8 << 20) | (5 << 15) | (1 << 12) | 0x73
        csrrs_read = (8 << 20) | (2 << 12) | 0x73
        csrw_zero = (8 << 20) | (1 << 12) | 0x73
        vector_load = 0x02056087
        vsetvli = 0x00007057
        rows = [row(0, 0x03f00293, "5", "000000000000003f"),
                row(4, csrw_x5), row(8, vector_load),
                row(12, csrrs_read), row(16, csrw_zero),
                row(20, vsetvli), row(24, vector_load)]
        instructions = {8: (vector_load, "vle32.v", "v1,(a0)"),
                        20: (vsetvli, "vsetvli", "zero,zero,e8,m1,ta,ma"),
                        24: (vector_load, "vle32.v", "v1,(a0)")}
        report = collect_vstart(rows, instructions)
        self.assertEqual(report["explicit_vstart_writes"], 2)
        self.assertEqual(report["linked_known_nonzero"], 1)
        self.assertEqual(report["linked_known_zero"], 0)
        self.assertEqual(report["linked"][0]["value"], 63)
        self.assertEqual(report["linked"][0]["mnemonic"], "vle32.v")

    def test_unknown_source_is_not_reported_as_nonzero(self):
        csrw_x5 = (8 << 20) | (5 << 15) | (1 << 12) | 0x73
        vector_load = 0x02056087
        report = collect_vstart([row(0, csrw_x5), row(4, vector_load)],
                                {4: (vector_load, "vle32.v", "v1,(a0)")})
        self.assertEqual(report["linked_known_nonzero"], 0)
        self.assertEqual(report["linked_unknown_value"], 1)

    def test_set_bits_write_does_not_claim_a_known_vstart_value(self):
        csrrs_x5 = (8 << 20) | (5 << 15) | (2 << 12) | 0x73
        vector_load = 0x02056087
        rows = [row(0, 0x03f00293, "5", "000000000000003f"),
                row(4, csrrs_x5), row(8, vector_load)]
        report = collect_vstart(rows, {8: (vector_load, "vle32.v", "v1,(a0)")})
        self.assertEqual(report["explicit_vstart_writes"], 1)
        self.assertEqual(report["linked_known_nonzero"], 0)
        self.assertEqual(report["linked_unknown_value"], 1)

    def test_trap_breaks_write_to_vector_link(self):
        csrw_zero = (8 << 20) | (1 << 12) | 0x73
        vector_load = 0x02056087
        trap = row(4, 0)
        trap["trap"] = "1"
        report = collect_vstart([row(0, csrw_zero), trap, row(8, vector_load)],
                                {8: (vector_load, "vle32.v", "v1,(a0)")})
        self.assertEqual(report["explicit_vstart_writes"], 1)
        self.assertEqual(report["linked_nonconfig_vector_instructions"], 0)


if __name__ == "__main__":
    unittest.main()
