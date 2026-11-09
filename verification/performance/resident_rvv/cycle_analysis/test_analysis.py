import unittest
import tempfile
from pathlib import Path
from analyze import advance, akv_observations, fma_contracts, is_fma, lane_observations, phase_at, validate_fma_work


def lane_row(**extra):
    row = dict(issue_valid=1, processing_valid=1, issue_remaining=32, issue_id=3,
               operand_required=6, operand_valid=6, operands_valid=1,
               latency_stall=0, fp_valid=1, fp_ready=1, fp_out_valid=0,
               fp_out_ready=1, result_full=0, result_req=0, result_gnt=0,
               vm=1, state=0, sew=1, issue_be=255)
    row.update(extra)
    return row


def akv_row(**extra):
    row = dict(state=7, replay_req=15, replay_gnt=15, replay_final=0,
               accepted=0, final_seen=0, busy=1, command_fire=0, terminal=0,
               front_valid=1, front_ready=0, column_bank=0, bank_conflict=0,
               ar_valid=0, ar_ready=0, r_valid=0, r_ready=0)
    row.update(extra)
    return row


class CycleTests(unittest.TestCase):
    def test_fma_decode(self):
        self.assertTrue(is_fma(0xB2805057))
        self.assertTrue(is_fma(0xF2B0D157))
        self.assertFalse(is_fma(0x0205345B))

    def test_lifetime_reuse(self):
        active = {}
        events = [(2, "alloc", 3, 10, 0xB2805057, 0),
                  (9, "done", 3, 10, 0xB2805057, 0),
                  (9, "alloc", 3, 11, 0xF2805057, 0)]
        i = advance(active, events, 0, 8)
        self.assertEqual(active[3]["seq"], 10)
        advance(active, events, i, 9)
        self.assertEqual(active[3]["seq"], 11)

    def test_no_duplicate_live_vid(self):
        with self.assertRaises(ValueError):
            advance({}, [(1, "alloc", 1, 1, 0, 0), (2, "alloc", 1, 2, 0, 0)], 0, 3)

    def test_real_acceptance_not_queued_valid(self):
        active = {3: dict(insn=0xB2805057, vstart=0)}
        self.assertEqual(lane_observations(lane_row(fp_ready=0), active)["fma_input_handshakes"], 0)
        counts = lane_observations(lane_row(), active)
        self.assertEqual(counts["fma_input_handshakes"], 1)
        self.assertEqual(counts["fma_destination_byte_enable_elements"], 4)

    def test_disallow_mask_assumption(self):
        with self.assertRaises(ValueError):
            lane_observations(lane_row(vm=0), {3: dict(insn=0xB2805057, vstart=0)})

    def test_arithmetic_count_matches_each_instruction(self):
        contracts = {1: dict(vl=9, kind="qk"), 2: dict(vl=128, kind="pv")}
        result = validate_fma_work(contracts, {1: 9, 2: 128})
        self.assertEqual(result["qk"]["useful_fmas"], 9)
        with self.assertRaises(ValueError):
            validate_fma_work(contracts, {1: 8, 2: 129})
        with self.assertRaises(ValueError):
            validate_fma_work(contracts, {1: 9})

    def test_reduction_merge_after_source_exhausted(self):
        # Accepted trace cycle 140851: VFREDMAX is merging partials, not idle.
        counts = lane_observations(lane_row(issue_remaining=0, state=5),
                                   {3: dict(insn=0x1E011557, vstart=0)})
        self.assertEqual(counts["fp_input_handshakes"], 1)
        self.assertEqual(counts["fma_input_handshakes"], 0)
        self.assertEqual(counts["no_instruction_to_issue_cycles"], 0)
        self.assertEqual(counts["reduction_state_cycles"], 1)

    def test_softmax_fma_is_not_pv(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "vector.csv"
            path.write_text("cycle,event,insn,arch_seq,vl,vstart\n"
                            "5,alloc,b2805057,1,64,0\n"
                            "15,alloc,b2805057,2,128,0\n")
            contracts = fma_contracts(path, 0, 30, [
                dict(begin=10, end=20, helper="akv_experimental_pv_f16_pair")])
            self.assertEqual(contracts[1]["kind"], "other_call_work")
            self.assertEqual(contracts[2]["kind"], "pv")

    def test_final_ack_not_bank_conflict(self):
        counts = akv_observations(akv_row())
        self.assertEqual(counts["replay_request_denied_cycles"], 0)
        self.assertEqual(counts["context_conflict_cycles"], 0)
        self.assertEqual(counts["replay_final_confirmation_wait_cycles"], 1)
        self.assertEqual(counts["replay_backpressure_counter_condition_cycles"], 1)
        counts = akv_observations(akv_row(accepted=15, replay_req=0, replay_gnt=0))
        self.assertEqual(counts["replay_final_confirmation_wait_cycles"], 1)
        self.assertEqual(counts["replay_backpressure_counter_condition_cycles"], 0)

    def test_word_completion(self):
        counts = akv_observations(akv_row(replay_final=15))
        self.assertEqual(counts["replay_word_completions"], 1)
        self.assertEqual(counts["replay_final_confirmation_wait_cycles"], 0)

    def test_half_open_span(self):
        spans = [dict(begin=10, end=20, helper="akv_experimental_pv_f16_pair")]
        self.assertEqual(phase_at(10, spans, 5, 30), "pv")
        self.assertEqual(phase_at(20, spans, 5, 30), "other_call_work")
        self.assertEqual(phase_at(30, spans, 5, 30), "outside_call")


if __name__ == "__main__":
    unittest.main()
