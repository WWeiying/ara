import unittest
import json
import inventory_csr_707 as m


class InventoryTests(unittest.TestCase):
    def test_rvh_arm(self):
        self.assertEqual(m.classify(dict(line="2551", expression="(curr_priv==PRIV_LVL_S)", raw_index=403), "cond")[0],
                         "RVH0_INACTIVE_PRIVILEGE_ARM")

    def test_mixed_block_not_excluded(self):
        point = dict(line="2551", expression="", statements=[dict(line_num="2579")])
        self.assertEqual(m.classify(point, "line")[0], "FUNCTIONAL_REACHABILITY_REVIEW")

    def test_tied_debug_true_only(self):
        point = dict(line="2649", expression="(1'b1 && debug_req_i)", vector="-1")
        self.assertEqual(m.classify(point, "cond")[0], "TIED_INPUT_BOOLEAN_TRUE_IMPOSSIBLE")
        point["vector"] = "-0"
        self.assertEqual(m.classify(point, "cond")[0], "DEBUG_NORMAL_RUN_INVARIANT_REVIEW")

    def test_debug_privilege_not_auto_unreachable(self):
        point = dict(line="2579", expression="((csr_addr_i[11:4] == 8'h7b) && !debug_mode_q)", vector="11")
        self.assertEqual(m.classify(point, "cond")[0], "DEBUG_NORMAL_RUN_INVARIANT_REVIEW")

    def test_pmp_no_blanket_exclusion(self):
        self.assertEqual(m.classify(dict(line="1964", expression="(pmpcfg_q[index].locked)"), "cond")[0], "PMP0_CONTEXT_HOLD")

    def test_sATP_candidate(self):
        self.assertEqual(m.classify(dict(line="1425", expression="mode permitted", raw_index=155), "cond")[0],
                         "DIRECTED_SATP_UNSUPPORTED_MODE")

    def test_mprv_candidate(self):
        self.assertEqual(m.classify(dict(line="2330", expression="translation permitted", raw_index=334), "cond")[0],
                         "DIRECTED_MPRV_BARE_NONM")

    def test_mixed_hypervisor_not_auto_unreachable(self):
        point = dict(line="389", expression="(mstatus_q.fs==Off)||(1'b0&&v_q)", vector="10")
        self.assertEqual(m.classify(point, "cond")[0], "CONFIG_CONTEXT_HOLD")

    def test_actual707_shape(self):
        bitmap = json.loads((m.BASE / "combined-bits.json").read_bytes())
        design = m.Design(m.BUILD / "sim/simv.vdb")
        line = bitmap["metrics"]["line"][m.SCOPE]
        mapped, missing = m.mapped_points("line", design.definition(m.SCOPE, "line"), line)
        self.assertEqual(len(mapped), 969)
        self.assertEqual(missing, [268, 608, 641, 932, 959])
        with self.assertRaises(ValueError):
            m.mapped_points("line", design.definition(m.SCOPE, "line"), dict(line, width=975))
        branch = bitmap["metrics"]["branch"][m.SCOPE]
        self.assertEqual(len(m.mapped_points("branch", design.definition(m.SCOPE, "branch"), branch)[0]), 626)
        cond = bitmap["metrics"]["cond"][m.SCOPE]
        nodes = [n for n in m.read_xml(design.db / "shape/cond.verilog.shape.xml") if
                 n.get("id") == design.hierarchy[m.SCOPE].get("id") and n.get("chksum") == cond["checksum"]]
        self.assertEqual(len(nodes), 1)
        self.assertEqual(len(m.mapped_points("cond", nodes[0], cond)[0]), 571)


if __name__ == "__main__":
    unittest.main()
