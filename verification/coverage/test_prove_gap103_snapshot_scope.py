import unittest
import prove_gap103_snapshot_scope as m


class SnapshotTests(unittest.TestCase):
    def sources(self):
        return ((m.OUT/"old-image-source-evidence-20261006-01/ara_dispatcher.sv").read_text(),
                (m.ROOT/"hardware/src/ara_sequencer.sv").read_text(),
                (m.ROOT/"hardware/src/vlsu/vstu.sv").read_text())

    def test_frozen_single_store_nonmutating_contract(self):
        self.assertFalse(m.source_contract(*self.sources())["source_reshuffle_gate"])

    def test_uniform_emul_gate_mutation_rejected(self):
        d,s,v=self.sources()
        d=d.replace("same_eew_by_lmul[LMUL_1] = 1'b1;","same_eew_by_lmul[LMUL_1] = 1'b0;")
        with self.assertRaises(ValueError): m.source_contract(d,s,v)

    def test_notebook_usevd_gate_removal_rejected(self):
        d,s,v=self.sources()
        d=d.replace("if (ara_req_valid_d && ara_req_d.use_vd && ara_req_ready_i &&",
                    "if (ara_req_valid_d && ara_req_ready_i &&")
        with self.assertRaises(ValueError): m.source_contract(d,s,v)

    def test_old_eew_store_extraction_mutation_rejected(self):
        d,s,v=self.sources()
        v=v.replace("shuffle_index(vrf_seq_byte, NrLanes, vinsn_issue_q.old_eew_vs1)",
                    "shuffle_index(vrf_seq_byte, NrLanes, vinsn_issue_q.eew_vs1)")
        with self.assertRaises(ValueError): m.source_contract(d,s,v)


if __name__ == "__main__": unittest.main()
