// Native DVE point exclusions; use only through the caller's image/scope guard.
// Audited images:
//   repair-closure-coverage-20260927-01/sim/simv.vdb (current 21)
//   vcs-dve-coverage-20260927-01/sim/simv.vdb (archived 427)
// operand_queue definition checksum: 1532764271
// Line shape checksum: 3998926456; Branch shape checksum: 1417162425
// Toggle shape checksum: ALU/MFPU 2109767059; mask_b 885747700.
// Exact point signatures:
//   Branch 2 (0): source line 127, checksum 949433246, signature "flush_i 1".
//   Branch 7 (0): source line 542, checksum 949433246, signature "flush_i 1".
//   Block 7: line 127, checksum 1270893570, signature "ibuf_usage_d = '0;".
//   Block 172: lines 543+544, checksum 362722431, signature "select_d = '0;".
//   Block 172 has XML index 176; the exclusion selects block ID, not index.
// Source proof: hardware/src/lane/operand_queues_stage.sv ties flush_i to 1'b0
// at lines 82,112,144,172,200,292 for the six explicitly named queues below.
// Branch info lists only ALU A/B instances; do not invent absent MFPU/mask points.
// No Condition exclusion, whole Branch exclusion, false vector, queue/module
// exclusion, descendant FIFO exclusion, or dynamic LSU flush instance is present.
// Native full syntax: VCS V-2023.12-SP1 cov_ref/unified_coverage_api/
// computing_checksum_for_coverage_metrics.html; each metric has its own
// definition/metric CHECKSUM and INSTANCE header. Point checksums/signatures
// below come from the matching VDB shape XML; scalar input signature is net.
// The external guard must still verify exact scope, shape and point mappings.
// Native DVE acceptance requires zero mismatches, need-review and unmappable.

CHECKSUM: "1532764271 1417162425"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_queues.i_operand_queue_alu_a
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:82; exclude true path only, operand_queue.sv:127"
Branch 2 "949433246" "flush_i" (0) "flush_i 1"
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:82; exclude true path only, operand_queue.sv:542"
Branch 7 "949433246" "flush_i" (0) "flush_i 1"

CHECKSUM: "1532764271 3998926456"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_queues.i_operand_queue_alu_a
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:82; unreachable assignment operand_queue.sv:127"
Block 7 "1270893570" "ibuf_usage_d = '0;"
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:82; unreachable assignments operand_queue.sv:543-544"
Block 172 "362722431" "select_d = '0;"

CHECKSUM: "1532764271 2109767059"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_queues.i_operand_queue_alu_a
ANNOTATION: "flush_i input tied to 1'b0 at operand_queues_stage.sv:82; no 0to1 or 1to0 transitions"
Toggle flush_i "net flush_i"

CHECKSUM: "1532764271 1417162425"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_queues.i_operand_queue_alu_b
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:112; exclude true path only, operand_queue.sv:127"
Branch 2 "949433246" "flush_i" (0) "flush_i 1"
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:112; exclude true path only, operand_queue.sv:542"
Branch 7 "949433246" "flush_i" (0) "flush_i 1"

CHECKSUM: "1532764271 3998926456"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_queues.i_operand_queue_alu_b
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:112; unreachable assignment operand_queue.sv:127"
Block 7 "1270893570" "ibuf_usage_d = '0;"
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:112; unreachable assignments operand_queue.sv:543-544"
Block 172 "362722431" "select_d = '0;"

CHECKSUM: "1532764271 2109767059"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_queues.i_operand_queue_alu_b
ANNOTATION: "flush_i input tied to 1'b0 at operand_queues_stage.sv:112; no 0to1 or 1to0 transitions"
Toggle flush_i "net flush_i"

CHECKSUM: "1532764271 3998926456"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_queues.i_operand_queue_mfpu_a
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:144; unreachable assignment operand_queue.sv:127"
Block 7 "1270893570" "ibuf_usage_d = '0;"
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:144; unreachable assignments operand_queue.sv:543-544"
Block 172 "362722431" "select_d = '0;"

CHECKSUM: "1532764271 2109767059"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_queues.i_operand_queue_mfpu_a
ANNOTATION: "flush_i input tied to 1'b0 at operand_queues_stage.sv:144; no 0to1 or 1to0 transitions"
Toggle flush_i "net flush_i"

CHECKSUM: "1532764271 3998926456"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_queues.i_operand_queue_mfpu_b
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:172; unreachable assignment operand_queue.sv:127"
Block 7 "1270893570" "ibuf_usage_d = '0;"
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:172; unreachable assignments operand_queue.sv:543-544"
Block 172 "362722431" "select_d = '0;"

CHECKSUM: "1532764271 2109767059"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_queues.i_operand_queue_mfpu_b
ANNOTATION: "flush_i input tied to 1'b0 at operand_queues_stage.sv:172; no 0to1 or 1to0 transitions"
Toggle flush_i "net flush_i"

CHECKSUM: "1532764271 3998926456"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_queues.i_operand_queue_mfpu_c
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:200; unreachable assignment operand_queue.sv:127"
Block 7 "1270893570" "ibuf_usage_d = '0;"
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:200; unreachable assignments operand_queue.sv:543-544"
Block 172 "362722431" "select_d = '0;"

CHECKSUM: "1532764271 2109767059"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_queues.i_operand_queue_mfpu_c
ANNOTATION: "flush_i input tied to 1'b0 at operand_queues_stage.sv:200; no 0to1 or 1to0 transitions"
Toggle flush_i "net flush_i"

CHECKSUM: "1532764271 3998926456"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_queues.i_operand_queue_mask_b
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:292; unreachable assignment operand_queue.sv:127"
Block 7 "1270893570" "ibuf_usage_d = '0;"
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:292; unreachable assignments operand_queue.sv:543-544"
Block 172 "362722431" "select_d = '0;"

CHECKSUM: "1532764271 885747700"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_queues.i_operand_queue_mask_b
ANNOTATION: "flush_i input tied to 1'b0 at operand_queues_stage.sv:292; no 0to1 or 1to0 transitions"
Toggle flush_i "net flush_i"

CHECKSUM: "1532764271 1417162425"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_operand_queues.i_operand_queue_alu_a
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:82; exclude true path only, operand_queue.sv:127"
Branch 2 "949433246" "flush_i" (0) "flush_i 1"
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:82; exclude true path only, operand_queue.sv:542"
Branch 7 "949433246" "flush_i" (0) "flush_i 1"

CHECKSUM: "1532764271 3998926456"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_operand_queues.i_operand_queue_alu_a
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:82; unreachable assignment operand_queue.sv:127"
Block 7 "1270893570" "ibuf_usage_d = '0;"
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:82; unreachable assignments operand_queue.sv:543-544"
Block 172 "362722431" "select_d = '0;"

CHECKSUM: "1532764271 2109767059"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_operand_queues.i_operand_queue_alu_a
ANNOTATION: "flush_i input tied to 1'b0 at operand_queues_stage.sv:82; no 0to1 or 1to0 transitions"
Toggle flush_i "net flush_i"

CHECKSUM: "1532764271 1417162425"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_operand_queues.i_operand_queue_alu_b
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:112; exclude true path only, operand_queue.sv:127"
Branch 2 "949433246" "flush_i" (0) "flush_i 1"
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:112; exclude true path only, operand_queue.sv:542"
Branch 7 "949433246" "flush_i" (0) "flush_i 1"

CHECKSUM: "1532764271 3998926456"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_operand_queues.i_operand_queue_alu_b
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:112; unreachable assignment operand_queue.sv:127"
Block 7 "1270893570" "ibuf_usage_d = '0;"
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:112; unreachable assignments operand_queue.sv:543-544"
Block 172 "362722431" "select_d = '0;"

CHECKSUM: "1532764271 2109767059"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_operand_queues.i_operand_queue_alu_b
ANNOTATION: "flush_i input tied to 1'b0 at operand_queues_stage.sv:112; no 0to1 or 1to0 transitions"
Toggle flush_i "net flush_i"

CHECKSUM: "1532764271 3998926456"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_operand_queues.i_operand_queue_mfpu_a
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:144; unreachable assignment operand_queue.sv:127"
Block 7 "1270893570" "ibuf_usage_d = '0;"
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:144; unreachable assignments operand_queue.sv:543-544"
Block 172 "362722431" "select_d = '0;"

CHECKSUM: "1532764271 2109767059"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_operand_queues.i_operand_queue_mfpu_a
ANNOTATION: "flush_i input tied to 1'b0 at operand_queues_stage.sv:144; no 0to1 or 1to0 transitions"
Toggle flush_i "net flush_i"

CHECKSUM: "1532764271 3998926456"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_operand_queues.i_operand_queue_mfpu_b
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:172; unreachable assignment operand_queue.sv:127"
Block 7 "1270893570" "ibuf_usage_d = '0;"
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:172; unreachable assignments operand_queue.sv:543-544"
Block 172 "362722431" "select_d = '0;"

CHECKSUM: "1532764271 2109767059"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_operand_queues.i_operand_queue_mfpu_b
ANNOTATION: "flush_i input tied to 1'b0 at operand_queues_stage.sv:172; no 0to1 or 1to0 transitions"
Toggle flush_i "net flush_i"

CHECKSUM: "1532764271 3998926456"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_operand_queues.i_operand_queue_mfpu_c
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:200; unreachable assignment operand_queue.sv:127"
Block 7 "1270893570" "ibuf_usage_d = '0;"
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:200; unreachable assignments operand_queue.sv:543-544"
Block 172 "362722431" "select_d = '0;"

CHECKSUM: "1532764271 2109767059"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_operand_queues.i_operand_queue_mfpu_c
ANNOTATION: "flush_i input tied to 1'b0 at operand_queues_stage.sv:200; no 0to1 or 1to0 transitions"
Toggle flush_i "net flush_i"

CHECKSUM: "1532764271 3998926456"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_operand_queues.i_operand_queue_mask_b
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:292; unreachable assignment operand_queue.sv:127"
Block 7 "1270893570" "ibuf_usage_d = '0;"
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:292; unreachable assignments operand_queue.sv:543-544"
Block 172 "362722431" "select_d = '0;"

CHECKSUM: "1532764271 885747700"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_operand_queues.i_operand_queue_mask_b
ANNOTATION: "flush_i input tied to 1'b0 at operand_queues_stage.sv:292; no 0to1 or 1to0 transitions"
Toggle flush_i "net flush_i"

CHECKSUM: "1532764271 1417162425"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[2].i_lane.i_operand_queues.i_operand_queue_alu_a
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:82; exclude true path only, operand_queue.sv:127"
Branch 2 "949433246" "flush_i" (0) "flush_i 1"
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:82; exclude true path only, operand_queue.sv:542"
Branch 7 "949433246" "flush_i" (0) "flush_i 1"

CHECKSUM: "1532764271 3998926456"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[2].i_lane.i_operand_queues.i_operand_queue_alu_a
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:82; unreachable assignment operand_queue.sv:127"
Block 7 "1270893570" "ibuf_usage_d = '0;"
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:82; unreachable assignments operand_queue.sv:543-544"
Block 172 "362722431" "select_d = '0;"

CHECKSUM: "1532764271 2109767059"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[2].i_lane.i_operand_queues.i_operand_queue_alu_a
ANNOTATION: "flush_i input tied to 1'b0 at operand_queues_stage.sv:82; no 0to1 or 1to0 transitions"
Toggle flush_i "net flush_i"

CHECKSUM: "1532764271 1417162425"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[2].i_lane.i_operand_queues.i_operand_queue_alu_b
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:112; exclude true path only, operand_queue.sv:127"
Branch 2 "949433246" "flush_i" (0) "flush_i 1"
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:112; exclude true path only, operand_queue.sv:542"
Branch 7 "949433246" "flush_i" (0) "flush_i 1"

CHECKSUM: "1532764271 3998926456"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[2].i_lane.i_operand_queues.i_operand_queue_alu_b
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:112; unreachable assignment operand_queue.sv:127"
Block 7 "1270893570" "ibuf_usage_d = '0;"
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:112; unreachable assignments operand_queue.sv:543-544"
Block 172 "362722431" "select_d = '0;"

CHECKSUM: "1532764271 2109767059"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[2].i_lane.i_operand_queues.i_operand_queue_alu_b
ANNOTATION: "flush_i input tied to 1'b0 at operand_queues_stage.sv:112; no 0to1 or 1to0 transitions"
Toggle flush_i "net flush_i"

CHECKSUM: "1532764271 3998926456"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[2].i_lane.i_operand_queues.i_operand_queue_mfpu_a
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:144; unreachable assignment operand_queue.sv:127"
Block 7 "1270893570" "ibuf_usage_d = '0;"
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:144; unreachable assignments operand_queue.sv:543-544"
Block 172 "362722431" "select_d = '0;"

CHECKSUM: "1532764271 2109767059"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[2].i_lane.i_operand_queues.i_operand_queue_mfpu_a
ANNOTATION: "flush_i input tied to 1'b0 at operand_queues_stage.sv:144; no 0to1 or 1to0 transitions"
Toggle flush_i "net flush_i"

CHECKSUM: "1532764271 3998926456"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[2].i_lane.i_operand_queues.i_operand_queue_mfpu_b
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:172; unreachable assignment operand_queue.sv:127"
Block 7 "1270893570" "ibuf_usage_d = '0;"
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:172; unreachable assignments operand_queue.sv:543-544"
Block 172 "362722431" "select_d = '0;"

CHECKSUM: "1532764271 2109767059"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[2].i_lane.i_operand_queues.i_operand_queue_mfpu_b
ANNOTATION: "flush_i input tied to 1'b0 at operand_queues_stage.sv:172; no 0to1 or 1to0 transitions"
Toggle flush_i "net flush_i"

CHECKSUM: "1532764271 3998926456"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[2].i_lane.i_operand_queues.i_operand_queue_mfpu_c
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:200; unreachable assignment operand_queue.sv:127"
Block 7 "1270893570" "ibuf_usage_d = '0;"
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:200; unreachable assignments operand_queue.sv:543-544"
Block 172 "362722431" "select_d = '0;"

CHECKSUM: "1532764271 2109767059"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[2].i_lane.i_operand_queues.i_operand_queue_mfpu_c
ANNOTATION: "flush_i input tied to 1'b0 at operand_queues_stage.sv:200; no 0to1 or 1to0 transitions"
Toggle flush_i "net flush_i"

CHECKSUM: "1532764271 3998926456"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[2].i_lane.i_operand_queues.i_operand_queue_mask_b
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:292; unreachable assignment operand_queue.sv:127"
Block 7 "1270893570" "ibuf_usage_d = '0;"
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:292; unreachable assignments operand_queue.sv:543-544"
Block 172 "362722431" "select_d = '0;"

CHECKSUM: "1532764271 885747700"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[2].i_lane.i_operand_queues.i_operand_queue_mask_b
ANNOTATION: "flush_i input tied to 1'b0 at operand_queues_stage.sv:292; no 0to1 or 1to0 transitions"
Toggle flush_i "net flush_i"

CHECKSUM: "1532764271 1417162425"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[3].i_lane.i_operand_queues.i_operand_queue_alu_a
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:82; exclude true path only, operand_queue.sv:127"
Branch 2 "949433246" "flush_i" (0) "flush_i 1"
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:82; exclude true path only, operand_queue.sv:542"
Branch 7 "949433246" "flush_i" (0) "flush_i 1"

CHECKSUM: "1532764271 3998926456"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[3].i_lane.i_operand_queues.i_operand_queue_alu_a
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:82; unreachable assignment operand_queue.sv:127"
Block 7 "1270893570" "ibuf_usage_d = '0;"
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:82; unreachable assignments operand_queue.sv:543-544"
Block 172 "362722431" "select_d = '0;"

CHECKSUM: "1532764271 2109767059"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[3].i_lane.i_operand_queues.i_operand_queue_alu_a
ANNOTATION: "flush_i input tied to 1'b0 at operand_queues_stage.sv:82; no 0to1 or 1to0 transitions"
Toggle flush_i "net flush_i"

CHECKSUM: "1532764271 1417162425"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[3].i_lane.i_operand_queues.i_operand_queue_alu_b
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:112; exclude true path only, operand_queue.sv:127"
Branch 2 "949433246" "flush_i" (0) "flush_i 1"
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:112; exclude true path only, operand_queue.sv:542"
Branch 7 "949433246" "flush_i" (0) "flush_i 1"

CHECKSUM: "1532764271 3998926456"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[3].i_lane.i_operand_queues.i_operand_queue_alu_b
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:112; unreachable assignment operand_queue.sv:127"
Block 7 "1270893570" "ibuf_usage_d = '0;"
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:112; unreachable assignments operand_queue.sv:543-544"
Block 172 "362722431" "select_d = '0;"

CHECKSUM: "1532764271 2109767059"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[3].i_lane.i_operand_queues.i_operand_queue_alu_b
ANNOTATION: "flush_i input tied to 1'b0 at operand_queues_stage.sv:112; no 0to1 or 1to0 transitions"
Toggle flush_i "net flush_i"

CHECKSUM: "1532764271 3998926456"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[3].i_lane.i_operand_queues.i_operand_queue_mfpu_a
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:144; unreachable assignment operand_queue.sv:127"
Block 7 "1270893570" "ibuf_usage_d = '0;"
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:144; unreachable assignments operand_queue.sv:543-544"
Block 172 "362722431" "select_d = '0;"

CHECKSUM: "1532764271 2109767059"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[3].i_lane.i_operand_queues.i_operand_queue_mfpu_a
ANNOTATION: "flush_i input tied to 1'b0 at operand_queues_stage.sv:144; no 0to1 or 1to0 transitions"
Toggle flush_i "net flush_i"

CHECKSUM: "1532764271 3998926456"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[3].i_lane.i_operand_queues.i_operand_queue_mfpu_b
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:172; unreachable assignment operand_queue.sv:127"
Block 7 "1270893570" "ibuf_usage_d = '0;"
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:172; unreachable assignments operand_queue.sv:543-544"
Block 172 "362722431" "select_d = '0;"

CHECKSUM: "1532764271 2109767059"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[3].i_lane.i_operand_queues.i_operand_queue_mfpu_b
ANNOTATION: "flush_i input tied to 1'b0 at operand_queues_stage.sv:172; no 0to1 or 1to0 transitions"
Toggle flush_i "net flush_i"

CHECKSUM: "1532764271 3998926456"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[3].i_lane.i_operand_queues.i_operand_queue_mfpu_c
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:200; unreachable assignment operand_queue.sv:127"
Block 7 "1270893570" "ibuf_usage_d = '0;"
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:200; unreachable assignments operand_queue.sv:543-544"
Block 172 "362722431" "select_d = '0;"

CHECKSUM: "1532764271 2109767059"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[3].i_lane.i_operand_queues.i_operand_queue_mfpu_c
ANNOTATION: "flush_i input tied to 1'b0 at operand_queues_stage.sv:200; no 0to1 or 1to0 transitions"
Toggle flush_i "net flush_i"

CHECKSUM: "1532764271 3998926456"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[3].i_lane.i_operand_queues.i_operand_queue_mask_b
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:292; unreachable assignment operand_queue.sv:127"
Block 7 "1270893570" "ibuf_usage_d = '0;"
ANNOTATION: "flush_i tied to 1'b0 at operand_queues_stage.sv:292; unreachable assignments operand_queue.sv:543-544"
Block 172 "362722431" "select_d = '0;"

CHECKSUM: "1532764271 885747700"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[3].i_lane.i_operand_queues.i_operand_queue_mask_b
ANNOTATION: "flush_i input tied to 1'b0 at operand_queues_stage.sv:292; no 0to1 or 1to0 transitions"
Toggle flush_i "net flush_i"
