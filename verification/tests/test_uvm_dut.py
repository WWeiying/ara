import tempfile
import unittest
from pathlib import Path

from ara_verify.uvm_dut import check_real_uvm_log


CONTRACT = (
    "[ARA_CONTRACT] requests=6 responses=6 exceptions=0 "
    "mmu_request_cycles=0 protocol_errors=0 outstanding=0 "
    "req_stalled=0 resp_stalled=0\n"
)
UVM = (
    "UVM_INFO @ 100: uvm_test_top.env.scoreboard [CVXIF/COUNT] "
    "observed requests=6 responses=6 aborted=0 reused=1 immediate=1\n"
    "UVM_INFO @ 100: reporter [TEST_DONE] run complete\n"
    "UVM_ERROR :    0\nUVM_FATAL :    0\n"
)
EVENTS = (
    "[ARA_CONTRACT_TRACE] sample=pre_edge cycle=10 req=1/1 fire=1 id=3 "
    "insn=00000057 resp=1/1 fire=1 id=3 exc=0 pending=0 stalled=00 errors=0\n"
    "[ARA_CONTRACT_TRACE] sample=pre_edge cycle=12 req=1/1 fire=1 id=4 "
    "insn=00001057 resp=1/1 fire=1 id=4 exc=0 pending=0 stalled=00 errors=0\n"
    "UVM_INFO @ 100: uvm_test_top.env.agent.monitor [CVXIF/EVENT] "
    "cycle=11 req_fire=1 req_id=3 insn=00000057 resp_fire=1 resp_id=3 exc=0\n"
    "UVM_INFO @ 100: uvm_test_top.env.agent.monitor [CVXIF/EVENT] "
    "cycle=13 req_fire=1 req_id=4 insn=00001057 resp_fire=1 resp_id=4 exc=0\n"
)
BACKEND = (
    "UVM_INFO @ 100: uvm_test_top.env.scoreboard [VID/COUNT] "
    "allocations=2 completions=2 aborted=0 max_live=1\n"
    "UVM_INFO @ 100: uvm_test_top.env.agent.monitor [VID/EVENT] "
    "cycle=20 alloc=1 alloc_id=1 done=00\n"
    "UVM_INFO @ 100: uvm_test_top.env.agent.monitor [VID/EVENT] "
    "cycle=21 alloc=1 alloc_id=1 done=02\n"
    "UVM_INFO @ 100: uvm_test_top.env.agent.monitor [VID/EVENT] "
    "cycle=22 alloc=0 alloc_id=0 done=02\n"
)
AXI_READ = (
    "UVM_INFO @ 100: uvm_test_top.env.scoreboard [AXI/READ_COUNT] "
    "ar=4 r_beats=6 completed=4 aborted=0 pending=0 max_pending=2\n"
)
AXI_WRITE = (
    "UVM_INFO @ 100: uvm_test_top.env.scoreboard [AXI/WRITE_COUNT] "
    "aw=4 w_beats=7 w_bursts=4 matched=4 b=4 aborted=0 pending=0 max_pending=2\n"
)
AXI_STALL = (
    "UVM_INFO @ 100: uvm_test_top.env.agent.monitor [AXI/STALL_COUNT] "
    "ar=1 r=2 aw=3 w=4 b=5 hold_checks=15\n"
)
VECTOR = (
    "cycle,event,arch_seq,vid,lane,source,insn,use_vd,vd,eew,vl,vstart,addr,be,wdata,nr_lanes,vlen_bits\n"
    "100,alloc,0,1,0,0,00000057,0,0,0,0,0,0,00,0,4,1024\n"
    "101,done,0,1,0,0,00000057,0,0,0,0,0,0,00,0,4,1024\n"
    "101,alloc,1,1,0,0,00000057,0,0,0,0,0,0,00,0,4,1024\n"
    "102,done,1,1,0,0,00000057,0,0,0,0,0,0,00,0,4,1024\n"
)


class RealDutUvmAuditTests(unittest.TestCase):
    def check(self, text, *, require_events=False, reset_kind=None):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "run.log"
            path.write_text(text, encoding="utf-8")
            return check_real_uvm_log(path, require_events=require_events,
                                      reset_kind=reset_kind)

    def test_dedicated_read_reset_requires_real_abort_and_final_epoch_match(self):
        contract = CONTRACT.replace("requests=6 responses=6", "requests=1 responses=1")
        uvm = UVM.replace(
            "requests=6 responses=6 aborted=0", "requests=2 responses=1 aborted=1"
        )
        read = AXI_READ.replace(
            "ar=4 r_beats=6 completed=4 aborted=0",
            "ar=2 r_beats=1 completed=1 aborted=1",
        )
        events = (
            "[ARA_CONTRACT_TRACE] sample=pre_edge cycle=10 req=1/1 fire=1 id=3 "
            "insn=00000057 resp=0/1 fire=0 id=0 exc=0 pending=0 stalled=00 errors=0\n"
            "[ARA_CONTRACT_TRACE] sample=pre_edge cycle=30 req=1/1 fire=1 id=3 "
            "insn=00000057 resp=1/1 fire=1 id=3 exc=0 pending=0 stalled=00 errors=0\n"
            "UVM_INFO @ 100: monitor [CVXIF/EVENT] cycle=10 req_fire=1 req_id=3 "
            "insn=00000057 resp_fire=0 resp_id=0 exc=0\n"
            "UVM_INFO @ 100: monitor [CVXIF/EVENT] cycle=30 req_fire=1 req_id=3 "
            "insn=00000057 resp_fire=1 resp_id=3 exc=0\n"
        )
        markers = (
            "UVM_INFO @ 100: monitor [CVXIF/RESET] cycle=1 epoch=1\n"
            "[ARA_UVM_RESET_TEST] kind=read accepted=1\n"
            "UVM_INFO @ 100: monitor [CVXIF/RESET] cycle=20 epoch=2\n"
            "[ARA_UVM_RESET_TEST] kind=read released=1\n"
        )
        log = contract + uvm + read + events + markers + "Core Test *** SUCCESS *** (tohost = 0)\n"
        result = self.check(log, reset_kind="read")
        self.assertEqual(result["status"], "PASS", result["issues"])
        self.assertEqual(result["reset_kind"], "read")
        self.assertEqual(self.check(log)["status"], "FAIL")
        self.assertEqual(self.check(log.replace("aborted=1", "aborted=0", 2),
                                    reset_kind="read")["status"], "FAIL")
        self.assertEqual(self.check(log.replace("cycle=30 req_fire", "cycle=19 req_fire"),
                                    reset_kind="read")["status"], "FAIL")
        self.assertEqual(self.check(log.replace("kind=read released=1", "kind=write released=1"),
                                    reset_kind="read")["status"], "FAIL")

    def test_startup_reset_does_not_count_as_inflight_reset(self):
        startup = "UVM_INFO @ 100: monitor [CVXIF/RESET] cycle=1 epoch=1\n"
        ordinary = CONTRACT + UVM + startup + "Core Test *** SUCCESS *** (tohost = 0)\n"
        self.assertEqual(self.check(ordinary)["status"], "PASS")
        self.assertEqual(self.check(ordinary, reset_kind="read")["status"], "FAIL")

    def test_state_reset_requires_observed_target_and_one_midrun_reset(self):
        contract = CONTRACT.replace("requests=6 responses=6", "requests=1 responses=1")
        uvm = UVM.replace(
            "requests=6 responses=6 aborted=0", "requests=2 responses=1 aborted=1"
        )
        events = (
            "[ARA_CONTRACT_TRACE] sample=pre_edge cycle=10 req=1/1 fire=1 id=3 "
            "insn=00000057 resp=0/1 fire=0 id=0 exc=0 pending=0 stalled=00 errors=0\n"
            "[ARA_CONTRACT_TRACE] sample=pre_edge cycle=30 req=1/1 fire=1 id=3 "
            "insn=00000057 resp=1/1 fire=1 id=3 exc=0 pending=0 stalled=00 errors=0\n"
            "UVM_INFO @ 100: monitor [CVXIF/EVENT] cycle=10 req_fire=1 req_id=3 "
            "insn=00000057 resp_fire=0 resp_id=0 exc=0\n"
            "UVM_INFO @ 100: monitor [CVXIF/EVENT] cycle=30 req_fire=1 req_id=3 "
            "insn=00000057 resp_fire=1 resp_id=3 exc=0\n"
        )
        markers = (
            "UVM_INFO @ 100: monitor [CVXIF/RESET] cycle=1 epoch=1\n"
            "[ARA_UVM_RESET_TEST] kind=state observed=1 target=qbs_commit "
            "actual=QBS_ENGINE_COMMIT\n"
            "UVM_INFO @ 100: monitor [CVXIF/RESET] cycle=20 epoch=2\n"
            "[ARA_UVM_RESET_TEST] kind=state released=1\n"
        )
        log = contract + uvm + events + markers + "Core Test *** SUCCESS *** (tohost = 0)\n"
        self.assertEqual(self.check(log, reset_kind="state")["status"], "PASS")
        self.assertEqual(self.check(log)["status"], "FAIL")
        self.assertEqual(self.check(log.replace("kind=state observed=1", "kind=state accepted=1"),
                                    reset_kind="state")["status"], "FAIL")
        self.assertEqual(self.check(log.replace("cycle=20 epoch=2", "cycle=1 epoch=1"),
                                    reset_kind="state")["status"], "FAIL")

    def test_dedicated_write_reset_requires_aborted_aw(self):
        contract = CONTRACT.replace("requests=6 responses=6", "requests=1 responses=1")
        uvm = UVM.replace("requests=6 responses=6", "requests=2 responses=2")
        writes = AXI_WRITE.replace(
            "aw=4 w_beats=7 w_bursts=4 matched=4 b=4 aborted=0",
            "aw=4 w_beats=3 w_bursts=3 matched=3 b=3 aborted=1",
        )
        markers = (
            "UVM_INFO @ 100: monitor [CVXIF/RESET] cycle=1 epoch=1\n"
            "[ARA_UVM_RESET_TEST] kind=write accepted=1\n"
            "UVM_INFO @ 100: monitor [CVXIF/RESET] cycle=12 epoch=2\n"
            "[ARA_UVM_RESET_TEST] kind=write released=1\n"
        )
        log = contract + uvm + writes + EVENTS + markers + \
              "Core Test *** SUCCESS *** (tohost = 0)\n"
        self.assertEqual(self.check(log, reset_kind="write")["status"], "PASS")
        self.assertEqual(self.check(log.replace("aborted=1", "aborted=0"),
                                    reset_kind="write")["status"], "FAIL")

    def test_agrees_with_independent_monitor(self):
        result = self.check(CONTRACT + UVM + "Core Test *** SUCCESS *** (tohost = 0)\n")
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["uvm_counts"]["requests"], 6)

    def test_rejects_count_mismatch(self):
        result = self.check(
            CONTRACT + UVM.replace("observed requests=6", "observed requests=5")
            + "Core Test *** SUCCESS *** (tohost = 0)\n"
        )
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("disagree" in issue for issue in result["issues"]))

    def test_rejects_missing_uvm_report_phase(self):
        result = self.check(
            CONTRACT + UVM.replace("[TEST_DONE]", "[NOT_DONE]")
            + "Core Test *** SUCCESS *** (tohost = 0)\n"
        )
        self.assertEqual(result["status"], "FAIL")

    def test_rejects_nonzero_uvm_errors(self):
        result = self.check(
            CONTRACT + UVM.replace("UVM_ERROR :    0", "UVM_ERROR :    1")
            + "Core Test *** SUCCESS *** (tohost = 0)\n"
        )
        self.assertEqual(result["status"], "FAIL")

    def test_matching_transaction_events(self):
        contract = CONTRACT.replace("requests=6 responses=6", "requests=2 responses=2")
        uvm = UVM.replace("requests=6 responses=6", "requests=2 responses=2")
        result = self.check(
            contract + uvm + EVENTS + "[CVXIF/EVENT]     2\n"
            + "Core Test *** SUCCESS *** (tohost = 0)\n",
            require_events=True,
        )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["uvm_event_count"], 2)
        self.assertEqual(result["uvm_event_sha256"], result["contract_event_sha256"])

    def test_rejects_idle_contract_trace_records(self):
        contract = CONTRACT.replace("requests=6 responses=6", "requests=2 responses=2")
        uvm = UVM.replace("requests=6 responses=6", "requests=2 responses=2")
        idle = (
            "[ARA_CONTRACT_TRACE] sample=pre_edge cycle=11 req=0/1 fire=0 id=0 "
            "insn=00000000 resp=0/1 fire=0 id=0 exc=0 pending=0 stalled=00 errors=0\n"
        )
        result = self.check(
            contract + uvm + EVENTS + idle + "Core Test *** SUCCESS *** (tohost = 0)\n",
            require_events=True,
        )
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("idle record" in issue for issue in result["issues"]))

    def test_rejects_same_count_wrong_transaction_id(self):
        contract = CONTRACT.replace("requests=6 responses=6", "requests=2 responses=2")
        uvm = UVM.replace("requests=6 responses=6", "requests=2 responses=2")
        corrupted = EVENTS.replace("req_id=4", "req_id=5")
        result = self.check(
            contract + uvm + corrupted + "Core Test *** SUCCESS *** (tohost = 0)\n",
            require_events=True,
        )
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("events disagree" in issue for issue in result["issues"]))

    def test_rejects_truncated_event_trace(self):
        contract = CONTRACT.replace("requests=6 responses=6", "requests=2 responses=2")
        uvm = UVM.replace("requests=6 responses=6", "requests=2 responses=2")
        truncated = EVENTS.replace(
            "UVM_INFO @ 100: uvm_test_top.env.agent.monitor [CVXIF/EVENT] "
            "cycle=13 req_fire=1 req_id=4 insn=00001057 resp_fire=1 resp_id=4 exc=0\n",
            "",
        )
        result = self.check(
            contract + uvm + truncated + "Core Test *** SUCCESS *** (tohost = 0)\n",
            require_events=True,
        )
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("incomplete" in issue for issue in result["issues"]))

    def test_backend_vid_events_match_independent_trace(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            log = path / "run.log"
            trace = path / "vector.csv"
            log.write_text(CONTRACT + UVM + BACKEND + "[VID/EVENT]     3\n" +
                           "Core Test *** SUCCESS *** (tohost = 0)\n")
            trace.write_text(VECTOR)
            result = check_real_uvm_log(log, require_backend=True, vector_trace=trace)
            self.assertEqual(result["status"], "PASS", result["issues"])
            self.assertEqual(result["backend_counts"]["allocations"], 2)
            self.assertEqual(result["uvm_backend_event_sha256"],
                             result["vector_backend_event_sha256"])
            trace.write_text(VECTOR.replace("102,done,1,1", "102,done,1,2"))
            result = check_real_uvm_log(log, require_backend=True, vector_trace=trace)
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("backend VID events disagree" in issue
                                for issue in result["issues"]))

    def test_backend_vid_reset_epochs_match_with_independent_marker(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            log = path / "run.log"
            trace = path / "vector.csv"
            reset_log = (
                CONTRACT.replace("requests=6 responses=6", "requests=1 responses=1")
                + UVM.replace("requests=6 responses=6 aborted=0",
                              "requests=2 responses=1 aborted=1")
                + BACKEND.replace("allocations=2 completions=2 aborted=0",
                                  "allocations=2 completions=1 aborted=1")
                .replace("cycle=20 alloc=1 alloc_id=1 done=00",
                         "cycle=20 alloc=1 alloc_id=1 done=00")
                .replace("cycle=21 alloc=1 alloc_id=1 done=02",
                         "cycle=40 alloc=1 alloc_id=1 done=00")
                .replace("cycle=22 alloc=0 alloc_id=0 done=02",
                         "cycle=41 alloc=0 alloc_id=0 done=02")
                + AXI_READ.replace("ar=4 r_beats=6 completed=4 aborted=0",
                                   "ar=2 r_beats=1 completed=1 aborted=1")
                + "[ARA_CONTRACT_TRACE] sample=pre_edge cycle=20 req=1/1 fire=1 id=3 "
                  "insn=00000057 resp=0/1 fire=0 id=0 exc=0 pending=0 stalled=00 errors=0\n"
                + "[ARA_CONTRACT_TRACE] sample=pre_edge cycle=40 req=1/1 fire=1 id=3 "
                  "insn=00000057 resp=1/1 fire=1 id=3 exc=0 pending=0 stalled=00 errors=0\n"
                + "UVM_INFO @ 100: monitor [CVXIF/EVENT] cycle=20 req_fire=1 req_id=3 "
                  "insn=00000057 resp_fire=0 resp_id=0 exc=0\n"
                + "UVM_INFO @ 100: monitor [CVXIF/EVENT] cycle=40 req_fire=1 req_id=3 "
                  "insn=00000057 resp_fire=1 resp_id=3 exc=0\n"
                + "UVM_INFO @ 100: monitor [CVXIF/RESET] cycle=1 epoch=1\n"
                + "[ARA_UVM_RESET_TEST] kind=read accepted=1\n"
                + "UVM_INFO @ 100: monitor [CVXIF/RESET] cycle=30 epoch=2\n"
                + "[ARA_UVM_RESET_TEST] kind=read released=1\n"
                + "Core Test *** SUCCESS *** (tohost = 0)\n"
            )
            log.write_text(reset_log, encoding="utf-8")
            rows = VECTOR.splitlines()
            trace_text = "\n".join((rows[0], rows[1],
                "21,reset,0,0,0,0,00000000,0,0,0,0,0,0,00,0,4,1024",
                "10,alloc,1,1,0,0,00000057,0,0,0,0,0,0,00,0,4,1024",
                "11,done,1,1,0,0,00000057,0,0,0,0,0,0,00,0,4,1024",
            )) + "\n"
            trace.write_text(trace_text, encoding="utf-8")
            result = check_real_uvm_log(log, require_backend=True, vector_trace=trace,
                                        reset_kind="read")
            self.assertEqual(result["status"], "PASS", result["issues"])
            self.assertEqual(result["uvm_backend_event_sha256"],
                             result["vector_backend_event_sha256"])
            trace.write_text(trace_text.replace("21,reset", "21,write"), encoding="utf-8")
            result = check_real_uvm_log(log, require_backend=True, vector_trace=trace,
                                        reset_kind="read")
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("reset marker" in issue for issue in result["issues"]))
            for corrupted in (
                trace_text.replace("11,done", "12,done"),
                trace_text.replace("10,alloc,1,1", "10,alloc,1,2"),
                trace_text.replace("21,reset", "21,reset\n21,reset"),
            ):
                trace.write_text(corrupted, encoding="utf-8")
                result = check_real_uvm_log(log, require_backend=True,
                                            vector_trace=trace, reset_kind="read")
                self.assertEqual(result["status"], "FAIL", corrupted)

    def test_backend_requires_nonzero_complete_trace(self):
        result = self.check(CONTRACT + UVM + BACKEND +
                            "Core Test *** SUCCESS *** (tohost = 0)\n")
        self.assertEqual(result["status"], "PASS")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "run.log"
            path.write_text(CONTRACT + UVM + BACKEND.replace(
                "cycle=22 alloc=0 alloc_id=0 done=02\n", "") +
                "Core Test *** SUCCESS *** (tohost = 0)\n")
            result = check_real_uvm_log(path, require_backend=True)
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("incomplete" in issue for issue in result["issues"]))

    def test_axi_read_summary_requires_real_completed_traffic(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "run.log"
            path.write_text(CONTRACT + UVM + AXI_READ +
                            "Core Test *** SUCCESS *** (tohost = 0)\n")
            result = check_real_uvm_log(path, require_axi=True)
            self.assertEqual(result["status"], "PASS", result["issues"])
            self.assertEqual(result["axi_read_counts"]["completed"], 4)
            path.write_text(CONTRACT + UVM +
                            "Core Test *** SUCCESS *** (tohost = 0)\n")
            result = check_real_uvm_log(path, require_axi=True)
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("AXI read summary" in issue for issue in result["issues"]))
            path.write_text(CONTRACT + UVM + AXI_READ.replace("completed=4", "completed=3") +
                            "Core Test *** SUCCESS *** (tohost = 0)\n")
            result = check_real_uvm_log(path, require_axi=True)
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("burst accounting" in issue for issue in result["issues"]))

    def test_axi_write_summary_requires_real_completed_traffic(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "run.log"
            success = "Core Test *** SUCCESS *** (tohost = 0)\n"
            path.write_text(CONTRACT + UVM + AXI_WRITE + success)
            result = check_real_uvm_log(path, require_axi_write=True)
            self.assertEqual(result["status"], "PASS", result["issues"])
            self.assertEqual(result["axi_write_counts"]["b"], 4)
            path.write_text(CONTRACT + UVM + success)
            result = check_real_uvm_log(path, require_axi_write=True)
            self.assertEqual(result["status"], "FAIL")
            path.write_text(CONTRACT + UVM + AXI_WRITE.replace("b=4", "b=3") + success)
            result = check_real_uvm_log(path, require_axi_write=True)
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("write burst accounting" in issue
                                for issue in result["issues"]))

    def test_axi_stall_counts_are_observational_and_bounded(self):
        success = "Core Test *** SUCCESS *** (tohost = 0)\n"
        result = self.check(CONTRACT + UVM + AXI_STALL + success)
        self.assertEqual(result["status"], "PASS", result["issues"])
        self.assertEqual(result["axi_stall_counts"]["hold_checks"], 15)
        result = self.check(CONTRACT + UVM + AXI_STALL.replace(
            "hold_checks=15", "hold_checks=16") + success)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("hold checks exceed" in issue for issue in result["issues"]))

    def test_coverage_observations_do_not_invent_missing_channels(self):
        success = "Core Test *** SUCCESS *** (tohost = 0)\n"
        result = self.check(CONTRACT + UVM + BACKEND + AXI_READ + AXI_WRITE +
                            AXI_STALL + success)
        self.assertEqual(result["status"], "PASS", result["issues"])
        observed = result["coverage_observations"]
        self.assertEqual(observed["axi_read_r_beats"], 6)
        self.assertEqual(observed["axi_write_w_beats"], 7)
        self.assertEqual(observed["axi_write_matched_bursts"], 4)
        self.assertEqual(observed["axi_aw_stall_cycles"], 3)
        self.assertEqual(observed["backend_vid_max_live"], 1)
        result = self.check(CONTRACT + UVM + success)
        self.assertIsNone(result["coverage_observations"]["axi_aw_stall_cycles"])
        self.assertIsNone(result["coverage_observations"]["backend_vid_max_live"])

    def test_rejects_duplicate_transaction_summaries(self):
        success = "Core Test *** SUCCESS *** (tohost = 0)\n"
        for summary, name in ((BACKEND, "backend VID"), (AXI_READ, "AXI read"),
                              (AXI_WRITE, "AXI write"), (AXI_STALL, "AXI stall")):
            result = self.check(CONTRACT + UVM + summary + summary + success)
            self.assertEqual(result["status"], "FAIL", name)
            self.assertTrue(any("multiple" in issue for issue in result["issues"]), name)


if __name__ == "__main__":
    unittest.main()
