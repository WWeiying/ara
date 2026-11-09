"""Host-only PV source-contract checks and geometry/handshake models, not RTL simulation.

Run: python3 -B verification/performance/resident_rvv/soc_admission/geometry_test.py -v
"""
import itertools
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[4]
SEQUENCER = ROOT / "hardware/src/ara_sequencer.sv"
LANE = ROOT / "hardware/src/lane/lane_sequencer.sv"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def compact(source):
    source = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)
    return re.sub(r"\s+", " ", source).strip()


def between(source, start, end):
    require(source.count(start) == 1, "Missing/ambiguous start: " + start)
    tail = source.split(start, 1)[1]
    require(end in tail, "Missing end: " + end)
    return tail.split(end, 1)[0]


def function(source, name):
    match = re.search(r"function automatic [^;]*\b" + name + r"\s*\(.*?endfunction",
                      source)
    require(match is not None, "Missing function: " + name)
    return match.group()


def contains(source, text):
    require(text in source, "Missing contract: " + text)


def pv_source_contract(sequencer, lane):
    seq, lane = compact(sequencer), compact(lane)
    for name in ("vfu", "target_vfus"):
        routing = function(seq, name)
        arm = between(routing, "[VLE:VLXE],", "[VSE:VSXE]")
        contains(arm, "VAKVPV:")
        contains(arm, "VFU_LoadUnit")
        require("VFU_MFpu" not in arm, "PV reserves a native MFPU queue")
    require("VAKVPV" not in function(seq, "no_src_vrf"), "PV skips lane source acceptance")

    source_count = function(seq, "source_register_count")
    reservation = between(source_count,
                          "if (!first_source && req.op == VAKVPV) begin", "end")
    match = re.fullmatch(r" source_register_count = (\d+); return source_register_count; ",
                         reservation)
    require(match is not None and int(match[1]) == 8, "PV must reserve eight vs2 registers")
    require(seq.count("source_register_count(ara_req_i, ara_req_i.eew_vs2, 1'b0)") == 2,
            "RAW checks and read entries must share source geometry")
    contains(function(seq, "destination_register_count"), "lmul_register_count(req.emul)")
    contains(seq, "emul : ara_req_i.emul,")
    contains(seq, "vl : ara_req_i.vl,")
    contains(lane, "vfu_operation_d.vl = pe_req.vl / NrLanes;")

    entries = between(seq, "begin : group_access_update", "end : group_access_update")
    contains(entries, "ordered_access_wait_complete = ara_req_i.op inside "
                      "{VSLIDEUP, VSLIDEDOWN, VAKVPV};")
    contains(entries, "destination_wait_complete = ordered_access_wait_complete ||")
    contains(entries, "vs2_access_wait_complete = ordered_access_wait_complete ||")
    contains(entries, "wait_complete: destination_wait_complete")
    contains(entries, "wait_complete: vs2_access_wait_complete")
    contains(entries, "read_mask_d[ara_req_i.vs2 + i][vinsn_id_n] = 1'b1;")
    contains(seq, "ara_req_i.op inside {VRGATHER, VRGATHEREI16, VCOMPRESS, VAKVPV}")
    contains(seq, "ara_req_i.op inside {VIOTA, VID, VCOMPRESS, VAKVPV}")

    pv = between(lane, "if (pe_req.op == VAKVPV && pe_req.use_vs2) begin", "end")
    assignment = between(pv, "operand_request[StA] = '{", "};")
    fields = {}
    for field in assignment.split(","):
        key, value = field.strip().split(":", 1)
        require(key not in fields, "Duplicate source-request field")
        fields[key] = value.strip()
    expected = dict(id="pe_req.id", vs="pe_req.vs2", eew="EW16",
                    conv="OpQueueConversionNone", scale_vl="1'b0", vtype="pe_req.vtype",
                    vl="vlen_t'(96)", vstart="'0",
                    hazard="pe_req.hazard_vs2 | pe_req.hazard_vd", target_fu="ALU_SLDU",
                    cvt_resize="CVT_SAME", default="'0")
    require(fields == expected, "Wrong independent PV source request")
    contains(pv, "operand_request_push[StA] = 1'b1;")
    contains(lane, "if (pe_req.op == VAKVPV) vfu_operation_valid_d = 1'b0;")
    contains(lane, "operand_request[q].hazard_wait_complete = pe_req.hazard_wait_complete;")
    contains(lane, "if (pe_req_valid && pe_req_ready && !vinsn_running_d[pe_req.id])")
    contains(lane, "vinsn_running_d[pe_req.id] = (vfu_operation_d.vfu != VFU_None)")

    readiness = between(lane, "VFU_LoadUnit: begin pe_req_ready =", ";")
    contains(readiness, "pe_req.op == VAKVPV")
    contains(readiness, "!operand_request_valid_o[StA] || operand_request_ready_i[StA]")
    contains(seq, "memory_lane_accepted_d = no_src_vrf(pe_req_d) ? '1 : '0;")
    contains(seq, "memory_lane_accepted_d[lane] |= pe_req_broadcast_valid && pe_req_ready_i[lane];")
    contains(seq, "if (is_load(ara_req_i.op) || is_store(ara_req_i.op) ||")
    contains(seq, "state_d = WAIT;")
    contains(seq, "pe_resp_i[NrLanes+OffsetLoad].vinsn_done[pe_req_o.id]) "
                  "memory_load_completed_d = 1'b1;")
    contains(seq, "(pe_req_o.op != VAKVPV || memory_load_completed_d) &&")
    flags = between(seq, "if (pe_req_o.op inside {VQBEXEC, VAKVPV}) begin", "end")
    require(flags.strip() == "ara_resp_o.fflags = qbs_fflags_i; "
                            "ara_resp_o.fflags_valid = qbs_fflags_valid_i;",
            "PV flags must use VLSU command-local terminal status")
    completion = between(seq, "if ((is_load(pe_req_o.op) || is_store(pe_req_o.op)) &&",
                         ") begin pe_req_valid_d = 1'b0;")
    contains(completion, "(&memory_lane_accepted_d) && memory_mask_accepted_d")
    return dict(source_registers=int(match[1]), source_lane_vl=96,
                readiness=readiness, completion="(is_load(pe_req_o.op) || "
                "is_store(pe_req_o.op)) &&" + completion)


def boolean_expression(expression, substitutions, values):
    """Evaluate only the extracted SV boolean subset used by the two gates."""
    for source, target in sorted(substitutions.items(), key=lambda item: -len(item[0])):
        expression = expression.replace(source, target)
    expression = expression.replace("&&", " and ").replace("||", " or ")
    expression = re.sub(r"!(?!=)", " not ", expression).strip()
    require(re.fullmatch(r"[\w\s()!=]+", expression) is not None,
            "Unsupported boolean expression")
    return bool(eval(expression, {"__builtins__": {}}, values))


def lane_ready(expression, op, qbs_enabled, use_vs1, mask_valid, mask_ready,
               sta_valid, sta_ready, index_valid, index_ready):
    substitutions = {"qbs_pkg::QbsVrfContinuationEnable": "qbs_enabled",
                     "pe_req.op": "op", "pe_req.use_vs1": "use_vs1"}
    for queue, prefix in (("MaskM", "mask"), ("StA", "sta"), ("SlideAddrGenA", "index")):
        substitutions[f"operand_request_valid_o[{queue}]"] = prefix + "_valid"
        substitutions[f"operand_request_ready_i[{queue}]"] = prefix + "_ready"
    values = dict(locals(), VAKVPV=1, VQBEXEC=2, VLXE=3)
    return boolean_expression(expression, substitutions, values)


def wait_ready(expression, op, accepted, ack, done, fault=False, mask=True,
               prior_ack=False):
    substitutions = {"is_load(pe_req_o.op)": "load", "is_store(pe_req_o.op)": "store",
                     "pe_req_o.op": "op", "(&memory_lane_accepted_d)": "all_lanes",
                     "addrgen_exception_d.valid": "fault"}
    values = dict(op=op, VAKVPV=1, load=True, store=False, all_lanes=all(accepted),
                  addrgen_acked_q=prior_ack, addrgen_ack_i=ack,
                  memory_mask_accepted_d=mask, fault=fault, memory_load_completed_d=done,
                  refill_wait=False, refill_older_drained=False, WaitForStoreB=True,
                  memory_store_completed_d=False)
    return boolean_expression(expression, substitutions, values)


class ResidentPvGeometry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seq = SEQUENCER.read_text()
        cls.lane = LANE.read_text()
        cls.contract = pv_source_contract(cls.seq, cls.lane)

    def test_rtl_source_contract(self):
        self.assertEqual(self.contract["source_registers"], 8)
        self.assertEqual(self.contract["source_lane_vl"], 96)

    def test_reservation_and_import_are_distinct_for_every_aligned_base(self):
        for base in range(0, 32, 8):
            reserved = set(range(base, base + self.contract["source_registers"]))
            consumed = set(range(base, base + 6))
            for offset in range(8):
                with self.subTest(base=base, offset=offset):
                    self.assertIn(base + offset, reserved)
                    self.assertEqual(base + offset in consumed, offset < 6)
            self.assertEqual(len(reserved - consumed), 2)

    def test_balanced_fixed_import_and_fixed_head_stride(self):
        for dimension, heads, tokens in itertools.product((64, 96, 128), (1, 2), (1, 8, 9, 63, 64)):
            with self.subTest(dimension=dimension, heads=heads, tokens=tokens):
                self.assertEqual(self.contract["source_lane_vl"] * 4, 384)
                words = self.contract["source_lane_vl"] * 16 // 64
                self.assertEqual(words, 24)
                self.assertEqual(words * 4 * 8, 6 * 128)
                active_seed_words = [8 * head + word for head in range(heads)
                                     for word in range(dimension // 16)]
                self.assertEqual(len(active_seed_words), heads * dimension // 16)
                self.assertTrue(all(word < 16 for word in active_seed_words))
                self.assertEqual(words - 16, 8)
                self.assertLessEqual(2 * tokens, 128)
                self.assertEqual(256 // 4, 64)  # Destination lane VL is not source lane VL.
                self.assertEqual(256 * 16 // 1024, 4)

    def test_pv_stalls_on_occupied_sta_but_native_readiness_is_unchanged(self):
        for op, bits in itertools.product(range(1, 5), itertools.product((False, True), repeat=8)):
            qbs, vs1, mv, mr, sv, sr, iv, ir = bits
            expected = ((not mv or mr) and
                        (not (op == 1 or (op == 2 and qbs and vs1)) or not sv or sr) and
                        (op != 3 or not iv or ir))
            self.assertEqual(lane_ready(self.contract["readiness"], op, *bits), expected)

    def test_pv_wait_requires_every_lane_ack_and_loadunit_done(self):
        for accepted, ack, done, fault, mask in itertools.product(
                itertools.product((False, True), repeat=4), (False, True), (False, True),
                (False, True), (False, True)):
            self.assertEqual(wait_ready(self.contract["completion"], 1, accepted, ack, done,
                                        fault, mask), all(accepted) and ack and done and mask)

    def test_native_load_ack_and_fault_policy_is_unchanged(self):
        for accepted, ack, done, fault in itertools.product(
                itertools.product((False, True), repeat=4), (False, True), (False, True),
                (False, True)):
            self.assertEqual(wait_ready(self.contract["completion"], 4, accepted, ack, done,
                                        fault), all(accepted) and ack and (not fault or done))

    def test_unequal_lane_acceptance_and_early_ack_do_not_release_pv(self):
        accepted = [False] * 4
        for lane in (2, 0, 3, 1):
            accepted[lane] = True
            self.assertFalse(wait_ready(self.contract["completion"], 1, accepted,
                                        ack=True, done=False))
        self.assertTrue(wait_ready(self.contract["completion"], 1, accepted,
                                   ack=False, done=True, prior_ack=True))
        self.assertFalse(wait_ready(self.contract["completion"], 1, [True, True, False, True],
                                    ack=False, done=True, prior_ack=True))

    def test_contract_mutations_are_rejected(self):
        changes = (("seq", "source_register_count = 8;", "source_register_count = 6;"),
                   ("seq", "{VSLIDEUP, VSLIDEDOWN, VAKVPV}", "{VSLIDEUP, VSLIDEDOWN}"),
                   ("seq", "{VQBEXEC, VAKVPV}", "{VQBEXEC}"),
                   ("seq", "(pe_req_o.op != VAKVPV || memory_load_completed_d) &&", ""),
                   ("lane", "vl: vlen_t'(96)", "vl: vfu_operation_d.vl"),
                   ("lane", "vl: vlen_t'(96)", "vl: vlen_t'(128)"),
                   ("lane", "vs: pe_req.vs2", "vs: pe_req.vd"),
                   ("lane", "eew: EW16", "eew: EW32"),
                   ("lane", "conv: OpQueueConversionNone", "conv: pe_req.conversion_vs2"),
                   ("lane", "scale_vl: 1'b0", "scale_vl: 1'b1"),
                   ("lane", "hazard: pe_req.hazard_vs2 | pe_req.hazard_vd",
                    "hazard: pe_req.hazard_vs2"),
                   ("lane", "hazard: pe_req.hazard_vs2 | pe_req.hazard_vd,\n"
                    "              target_fu: ALU_SLDU",
                    "hazard: pe_req.hazard_vs2 | pe_req.hazard_vd,\n"
                    "              target_fu: MFPU_ADDRGEN"),
                   ("lane", "if (pe_req.op == VAKVPV) vfu_operation_valid_d = 1'b0;", ""))
        for owner, old, new in changes:
            source = self.seq if owner == "seq" else self.lane
            self.assertIn(old, source)
            with self.subTest(owner=owner, mutation=new), self.assertRaises(ValueError):
                pv_source_contract(self.seq.replace(old, new, 1) if owner == "seq" else self.seq,
                                   self.lane.replace(old, new, 1) if owner == "lane" else self.lane)


if __name__ == "__main__":
    unittest.main()
