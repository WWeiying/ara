// SPDX-License-Identifier: SHL-0.51

// Simulation-only counters for quantized LLM kernels.  The monitor observes
// existing handshakes and queue state; it does not alter the synthesized DUT.
module llm_perf_monitor import ara_pkg::*; import rvv_pkg::*; #(
    parameter int unsigned NrLanes = 1,
    parameter int unsigned NrVFUs = 7,
    parameter int unsigned NrVInsn = 8,
    parameter int unsigned VLenWidth = 11,
    parameter int unsigned AxiDataWidth = 64,
    parameter int unsigned QueueCountWidth = 3
  ) (
    input logic clk_i,
    input logic rst_ni,
    input logic active_i,
    input logic [7:0] phase_i,
    input logic [1:0] retired_inst_count_i,
    input logic [1:0] retired_vector_inst_count_i,

    input logic req_valid_i,
    input logic req_ready_i,
    input ara_op_e req_op_i,
    input logic [VLenWidth-1:0] req_vl_i,
    input vew_e req_vsew_i,
    input logic [1:0] req_cvt_resize_i,
    input logic req_vm_i,
    input logic [2:0] req_nf_i,

    input logic ara_idle_i,
    input logic lane_active_i,
    input logic [NrLanes-1:0] lane_inflight_i,
    input logic [NrLanes-1:0][1:0] lane_alu_operand_fire_i,
    input logic [NrLanes-1:0][2:0] lane_mfpu_operand_fire_i,
    input logic [NrLanes-1:0] alu_exec_fire_i,
    input logic [NrLanes-1:0] int_mul_exec_fire_i,
    input logic [NrLanes-1:0] int_mac_exec_fire_i,
    input logic [NrLanes-1:0][3:0] int_mul_exec_elements_i,
    input vew_e [NrLanes-1:0] int_mul_exec_vsew_i,
    input logic [NrLanes-1:0] int_div_exec_fire_i,
    input logic [NrLanes-1:0] fp_exec_fire_i,
    input logic [NrLanes-1:0] alu_result_fire_i,
    input logic [NrLanes-1:0] mfpu_result_fire_i,
    input logic [NrLanes-1:0][7:0] alu_result_be_i,
    input logic [NrLanes-1:0][7:0] mfpu_result_be_i,

    input logic [NrVFUs-1:0][QueueCountWidth-1:0] queue_occ_i,
    input logic [NrVFUs-1:0] queue_ready_i,
    input logic [NrVInsn-1:0] vinsn_running_i,
    input logic queue_resource_block_i,
    input logic no_vid_block_i,
    input logic lane_desync_block_i,
    input logic operand_block_i,
    input logic mask_block_i,
    input logic slide_block_i,
    input logic hazard_block_i,
    input logic scalar_result_wait_i,

    input logic axi_ar_valid_i,
    input logic axi_ar_ready_i,
    input logic [7:0] axi_ar_len_i,
    input logic [2:0] axi_ar_size_i,
    input logic axi_r_valid_i,
    input logic axi_r_ready_i,
    input logic axi_r_last_i,
    input logic axi_aw_valid_i,
    input logic axi_aw_ready_i,
    input logic [7:0] axi_aw_len_i,
    input logic [2:0] axi_aw_size_i,
    input logic axi_w_valid_i,
    input logic axi_w_ready_i,
    input logic [AxiDataWidth/8-1:0] axi_w_strb_i,
    input logic axi_b_valid_i,
    input logic axi_b_ready_i
  );

  localparam int unsigned NumPhases = 4;

  typedef struct {
    logic [63:0] cycles;
    logic [63:0] backend_busy_cycles;
    logic [63:0] lane_active_cycles;
    logic [63:0] req_valid_cycles;
    logic [63:0] req_fire_count;
    logic [63:0] req_blocked_cycles;
    logic [63:0] vector_element_count;
    logic [63:0] retired_inst_count;
    logic [63:0] retired_vector_inst_count;
    logic [63:0] retired_scalar_inst_count;

    logic [63:0] load_count;
    logic [63:0] load_unit_count;
    logic [63:0] load_strided_count;
    logic [63:0] load_indexed_count;
    logic [63:0] store_count;
    logic [63:0] store_unit_count;
    logic [63:0] store_strided_count;
    logic [63:0] store_indexed_count;
    logic [63:0] bitwise_count;
    logic [63:0] shift_count;
    logic [63:0] int_alu_count;
    logic [63:0] int_mul_count;
    logic [63:0] int_widen_mul_count;
    logic [63:0] int_mac_count;
    logic [63:0] int_widen_mac_count;
    logic [63:0] int_reduction_count;
    logic [63:0] fp_reduction_count;
    logic [63:0] narrow_count;
    logic [63:0] fp_arith_count;
    logic [63:0] permute_count;
    logic [63:0] mask_count;
    logic [63:0] scalar_move_count;
    logic [63:0] other_count;

    logic [63:0] unit_load_span_bytes;
    logic [63:0] unit_store_span_bytes;
    logic [63:0] masked_mem_count;
    logic [63:0] axi_ar_count;
    logic [63:0] axi_ar_bytes;
    logic [63:0] axi_r_beat_count;
    logic [63:0] axi_r_bus_bytes;
    logic [63:0] axi_aw_count;
    logic [63:0] axi_aw_bytes;
    logic [63:0] axi_w_beat_count;
    logic [63:0] axi_w_useful_bytes;
    logic [63:0] axi_b_count;
    logic [63:0] axi_ar_stall_cycles;
    logic [63:0] axi_r_stall_cycles;
    logic [63:0] axi_aw_stall_cycles;
    logic [63:0] axi_w_stall_cycles;
    logic [63:0] read_outstanding_occ_sum;
    logic [63:0] read_outstanding_max;

    logic [63:0] queue_occ_sum;
    logic [63:0] queue_occ_max;
    logic [63:0] queue_full_cycles;
    logic [63:0] inflight_occ_sum;
    logic [63:0] inflight_occ_max;
    logic [63:0] queue_resource_block_cycles;
    logic [63:0] no_vid_block_cycles;
    logic [63:0] lane_desync_block_cycles;
    logic [63:0] operand_block_cycles;
    logic [63:0] mask_block_cycles;
    logic [63:0] slide_block_cycles;
    logic [63:0] hazard_block_cycles;
    logic [63:0] scalar_result_wait_cycles;
    logic [63:0] lane_alu_operand_fires;
    logic [63:0] lane_mfpu_operand_fires;
    logic [63:0] lane_inflight_slot_cycles;
    logic [63:0] compute_active_cycles;
    logic [63:0] compute_lane_slot_fires;
    logic [63:0] compute_unit_lane_fires;
    logic [63:0] alu_exec_active_cycles;
    logic [63:0] alu_exec_lane_fires;
    logic [63:0] mfpu_exec_active_cycles;
    logic [63:0] mfpu_exec_lane_fires;
    logic [63:0] int_mul_exec_lane_fires;
    logic [63:0] int_mac_exec_lane_fires;
    logic [63:0] int_mac_element_count;
    logic [63:0] int_mac_element_capacity;
    logic [63:0] int_mac_exec_lane_fires_ew8;
    logic [63:0] int_mac_exec_lane_fires_ew16;
    logic [63:0] int_mac_exec_lane_fires_ew32;
    logic [63:0] int_mac_exec_lane_fires_ew64;
    logic [63:0] int_mac_element_count_ew8;
    logic [63:0] int_mac_element_count_ew16;
    logic [63:0] int_mac_element_count_ew32;
    logic [63:0] int_mac_element_count_ew64;
    logic [63:0] int_div_exec_lane_fires;
    logic [63:0] fp_exec_lane_fires;
    logic [63:0] alu_result_lane_fires;
    logic [63:0] mfpu_result_lane_fires;
    logic [63:0] alu_result_active_bytes;
    logic [63:0] mfpu_result_active_bytes;
  } llm_perf_t;

  llm_perf_t stats_q [NumPhases];
  logic active_q;
  logic [63:0] read_outstanding_q;

  function automatic logic is_bitwise(ara_op_e op);
    return op inside {VAND, VOR, VXOR};
  endfunction

  function automatic logic is_shift(ara_op_e op);
    return op inside {VSSRL, VSSRA, VSLL, VSRL, VSRA};
  endfunction

  function automatic logic is_int_reduction(ara_op_e op);
    return op inside {VREDSUM, VREDAND, VREDOR, VREDXOR, VREDMINU, VREDMIN,
                      VREDMAXU, VREDMAX, VWREDSUMU, VWREDSUM};
  endfunction

  function automatic logic is_fp_reduction(ara_op_e op);
    return op inside {VFREDUSUM, VFREDOSUM, VFREDMIN, VFREDMAX,
                      VFWREDUSUM, VFWREDOSUM};
  endfunction

  function automatic logic is_fp_arith(ara_op_e op);
    return op inside {[VFADD:VFCVTFF]};
  endfunction

  function automatic logic is_mask_op(ara_op_e op);
    return op inside {[VMFEQ:VMXNOR]} || op inside {VMSBF, VMSOF, VMSIF,
                                                    VIOTA, VID, VCPOP, VFIRST};
  endfunction

  function automatic llm_perf_t sample(input llm_perf_t current);
    llm_perf_t next;
    logic req_fire;
    logic ar_fire, r_fire, aw_fire, w_fire, b_fire;
    logic classified;
    logic [63:0] queue_occ;
    logic [63:0] inflight_occ;
    logic [63:0] alu_fires;
    logic [63:0] mfpu_fires;
    logic [63:0] lane_inflight_slots;
    logic [63:0] alu_exec_fires;
    logic [63:0] int_mul_exec_fires;
    logic [63:0] int_mac_exec_fires;
    logic [63:0] int_mac_elements;
    logic [63:0] int_mac_capacity;
    logic [63:0] int_mac_fires_by_sew [4];
    logic [63:0] int_mac_elements_by_sew [4];
    logic [63:0] int_div_exec_fires;
    logic [63:0] fp_exec_fires;
    logic [NrLanes-1:0] mfpu_exec_fire;
    logic [NrLanes-1:0] compute_lane_fire;
    logic [63:0] mfpu_exec_fires;
    logic [63:0] alu_result_fires;
    logic [63:0] mfpu_result_fires;
    logic [63:0] alu_result_bytes;
    logic [63:0] mfpu_result_bytes;
    logic [63:0] memory_span;
    logic [63:0] read_outstanding_next;

    next = current;
    req_fire = req_valid_i && req_ready_i;
    ar_fire = axi_ar_valid_i && axi_ar_ready_i;
    r_fire = axi_r_valid_i && axi_r_ready_i;
    aw_fire = axi_aw_valid_i && axi_aw_ready_i;
    w_fire = axi_w_valid_i && axi_w_ready_i;
    b_fire = axi_b_valid_i && axi_b_ready_i;
    queue_occ = '0;
    for (int unsigned i = 0; i < NrVFUs; i++) queue_occ += queue_occ_i[i];
    inflight_occ = $countones(vinsn_running_i);
    alu_fires = $countones(lane_alu_operand_fire_i);
    mfpu_fires = $countones(lane_mfpu_operand_fire_i);
    lane_inflight_slots = $countones(lane_inflight_i);
    alu_exec_fires = $countones(alu_exec_fire_i);
    int_mul_exec_fires = $countones(int_mul_exec_fire_i);
    int_mac_exec_fires = $countones(int_mac_exec_fire_i);
    int_div_exec_fires = $countones(int_div_exec_fire_i);
    fp_exec_fires = $countones(fp_exec_fire_i);
    mfpu_exec_fire = int_mul_exec_fire_i | int_div_exec_fire_i | fp_exec_fire_i;
    compute_lane_fire = alu_exec_fire_i | mfpu_exec_fire;
    mfpu_exec_fires = $countones(mfpu_exec_fire);
    alu_result_fires = $countones(alu_result_fire_i);
    mfpu_result_fires = $countones(mfpu_result_fire_i);
    int_mac_elements = '0;
    int_mac_capacity = '0;
    for (int unsigned sew = 0; sew < 4; sew++) begin
      int_mac_fires_by_sew[sew] = '0;
      int_mac_elements_by_sew[sew] = '0;
    end
    alu_result_bytes = '0;
    mfpu_result_bytes = '0;
    for (int unsigned lane = 0; lane < NrLanes; lane++) begin
      if (int_mac_exec_fire_i[lane]) begin
        int_mac_elements += int_mul_exec_elements_i[lane];
        if (int_mul_exec_vsew_i[lane] inside {[EW8:EW64]}) begin
          int_mac_capacity += 64'd8 >> unsigned'(int_mul_exec_vsew_i[lane]);
          int_mac_fires_by_sew[unsigned'(int_mul_exec_vsew_i[lane])]++;
          int_mac_elements_by_sew[unsigned'(int_mul_exec_vsew_i[lane])] +=
            int_mul_exec_elements_i[lane];
        end
      end
      if (alu_result_fire_i[lane])
        alu_result_bytes += $countones(alu_result_be_i[lane]);
      if (mfpu_result_fire_i[lane])
        mfpu_result_bytes += $countones(mfpu_result_be_i[lane]);
    end
    memory_span = (64'(req_vl_i) << unsigned'(req_vsew_i)) *
                  (64'(req_nf_i) + 1'b1);
    read_outstanding_next = read_outstanding_q;
    unique case ({ar_fire, r_fire && axi_r_last_i})
      2'b10: read_outstanding_next++;
      2'b01: if (read_outstanding_next != 0) read_outstanding_next--;
      default:;
    endcase

    next.cycles++;
    next.backend_busy_cycles += !ara_idle_i;
    next.lane_active_cycles += lane_active_i;
    next.req_valid_cycles += req_valid_i;
    next.req_fire_count += req_fire;
    next.req_blocked_cycles += req_valid_i && !req_ready_i;
    if (req_fire) next.vector_element_count += req_vl_i;
    next.retired_inst_count += retired_inst_count_i;
    next.retired_vector_inst_count += retired_vector_inst_count_i;
    next.retired_scalar_inst_count += retired_inst_count_i - retired_vector_inst_count_i;

    next.queue_occ_sum += queue_occ;
    if (queue_occ > next.queue_occ_max) next.queue_occ_max = queue_occ;
    next.queue_full_cycles += |(~queue_ready_i);
    next.inflight_occ_sum += inflight_occ;
    if (inflight_occ > next.inflight_occ_max) next.inflight_occ_max = inflight_occ;
    next.queue_resource_block_cycles += queue_resource_block_i;
    next.no_vid_block_cycles += no_vid_block_i;
    next.lane_desync_block_cycles += lane_desync_block_i;
    next.operand_block_cycles += operand_block_i;
    next.mask_block_cycles += mask_block_i;
    next.slide_block_cycles += slide_block_i;
    next.hazard_block_cycles += hazard_block_i;
    next.scalar_result_wait_cycles += scalar_result_wait_i;
    next.lane_alu_operand_fires += alu_fires;
    next.lane_mfpu_operand_fires += mfpu_fires;
    next.lane_inflight_slot_cycles += lane_inflight_slots;
    next.compute_active_cycles += |compute_lane_fire;
    next.compute_lane_slot_fires += $countones(compute_lane_fire);
    next.compute_unit_lane_fires += alu_exec_fires + mfpu_exec_fires;
    next.alu_exec_active_cycles += |alu_exec_fire_i;
    next.alu_exec_lane_fires += alu_exec_fires;
    next.mfpu_exec_active_cycles += |mfpu_exec_fire;
    next.mfpu_exec_lane_fires += mfpu_exec_fires;
    next.int_mul_exec_lane_fires += int_mul_exec_fires;
    next.int_mac_exec_lane_fires += int_mac_exec_fires;
    next.int_mac_element_count += int_mac_elements;
    next.int_mac_element_capacity += int_mac_capacity;
    next.int_mac_exec_lane_fires_ew8 += int_mac_fires_by_sew[EW8];
    next.int_mac_exec_lane_fires_ew16 += int_mac_fires_by_sew[EW16];
    next.int_mac_exec_lane_fires_ew32 += int_mac_fires_by_sew[EW32];
    next.int_mac_exec_lane_fires_ew64 += int_mac_fires_by_sew[EW64];
    next.int_mac_element_count_ew8 += int_mac_elements_by_sew[EW8];
    next.int_mac_element_count_ew16 += int_mac_elements_by_sew[EW16];
    next.int_mac_element_count_ew32 += int_mac_elements_by_sew[EW32];
    next.int_mac_element_count_ew64 += int_mac_elements_by_sew[EW64];
    next.int_div_exec_lane_fires += int_div_exec_fires;
    next.fp_exec_lane_fires += fp_exec_fires;
    next.alu_result_lane_fires += alu_result_fires;
    next.mfpu_result_lane_fires += mfpu_result_fires;
    next.alu_result_active_bytes += alu_result_bytes;
    next.mfpu_result_active_bytes += mfpu_result_bytes;

    next.axi_ar_count += ar_fire;
    if (ar_fire) next.axi_ar_bytes +=
      (64'(axi_ar_len_i) + 1'b1) << axi_ar_size_i;
    next.axi_r_beat_count += r_fire;
    next.axi_r_bus_bytes += r_fire * (AxiDataWidth / 8);
    next.axi_aw_count += aw_fire;
    if (aw_fire) next.axi_aw_bytes +=
      (64'(axi_aw_len_i) + 1'b1) << axi_aw_size_i;
    next.axi_w_beat_count += w_fire;
    if (w_fire) next.axi_w_useful_bytes += $countones(axi_w_strb_i);
    next.axi_b_count += b_fire;
    next.axi_ar_stall_cycles += axi_ar_valid_i && !axi_ar_ready_i;
    next.axi_r_stall_cycles += axi_r_valid_i && !axi_r_ready_i;
    next.axi_aw_stall_cycles += axi_aw_valid_i && !axi_aw_ready_i;
    next.axi_w_stall_cycles += axi_w_valid_i && !axi_w_ready_i;
    next.read_outstanding_occ_sum += read_outstanding_q;
    if (read_outstanding_next > next.read_outstanding_max)
      next.read_outstanding_max = read_outstanding_next;

    if (req_fire) begin
      classified = 1'b1;
      unique case (req_op_i)
        VLE: begin
          next.load_count++;
          next.load_unit_count++;
          next.unit_load_span_bytes += memory_span;
          next.masked_mem_count += !req_vm_i;
        end
        VLSE: begin next.load_count++; next.load_strided_count++; next.masked_mem_count += !req_vm_i; end
        VLXE: begin next.load_count++; next.load_indexed_count++; next.masked_mem_count += !req_vm_i; end
        VSE: begin
          next.store_count++;
          next.store_unit_count++;
          next.unit_store_span_bytes += memory_span;
          next.masked_mem_count += !req_vm_i;
        end
        VSSE: begin next.store_count++; next.store_strided_count++; next.masked_mem_count += !req_vm_i; end
        VSXE: begin next.store_count++; next.store_indexed_count++; next.masked_mem_count += !req_vm_i; end
        default: classified = 1'b0;
      endcase

      if (!classified && is_bitwise(req_op_i)) next.bitwise_count++;
      else if (!classified && is_shift(req_op_i)) next.shift_count++;
      else if (!classified && req_op_i inside {[VADD:VASUB]}) next.int_alu_count++;
      else if (!classified && req_op_i inside {VMUL, VMULH, VMULHU, VMULHSU, VSMUL}) begin
        next.int_mul_count++;
        if (req_cvt_resize_i == CVT_WIDE) next.int_widen_mul_count++;
      end else if (!classified && req_op_i inside {VMACC, VNMSAC, VMADD, VNMSUB}) begin
        next.int_mac_count++;
        if (req_cvt_resize_i == CVT_WIDE) next.int_widen_mac_count++;
      end else if (!classified && is_int_reduction(req_op_i)) next.int_reduction_count++;
      else if (!classified && is_fp_reduction(req_op_i)) next.fp_reduction_count++;
      else if (!classified && req_op_i inside {VNCLIP, VNCLIPU, VNSRL, VNSRA}) next.narrow_count++;
      else if (!classified && is_fp_arith(req_op_i)) next.fp_arith_count++;
      else if (!classified && req_op_i inside {VRGATHER, VRGATHEREI16, VCOMPRESS,
                                               VSLIDEUP, VSLIDEDOWN}) next.permute_count++;
      else if (!classified && is_mask_op(req_op_i)) next.mask_count++;
      else if (!classified && req_op_i inside {VMVSX, VFMVSF, VMVXS, VFMVFS})
        next.scalar_move_count++;
      else if (!classified) next.other_count++;
    end
    return next;
  endfunction

  task automatic print_row(input string testcase, input string phase,
                           input llm_perf_t value, input integer fd);
    $fdisplay(fd,
      "[LLM_PERF] case=%s phase=%s nr_lanes=%0d cycles=%0d backend_busy_cycles=%0d lane_active_cycles=%0d lane_inflight_slot_cycles=%0d compute_active_cycles=%0d compute_lane_slot_fires=%0d compute_unit_lane_fires=%0d alu_exec_active_cycles=%0d alu_exec_lane_fires=%0d mfpu_exec_active_cycles=%0d mfpu_exec_lane_fires=%0d int_mul_exec_lane_fires=%0d int_mac_exec_lane_fires=%0d int_mac_element_count=%0d int_mac_element_capacity=%0d int_mac_exec_lane_fires_ew8=%0d int_mac_exec_lane_fires_ew16=%0d int_mac_exec_lane_fires_ew32=%0d int_mac_exec_lane_fires_ew64=%0d int_mac_element_count_ew8=%0d int_mac_element_count_ew16=%0d int_mac_element_count_ew32=%0d int_mac_element_count_ew64=%0d int_div_exec_lane_fires=%0d fp_exec_lane_fires=%0d alu_result_lane_fires=%0d mfpu_result_lane_fires=%0d alu_result_active_bytes=%0d mfpu_result_active_bytes=%0d req_valid_cycles=%0d req_fire_count=%0d req_blocked_cycles=%0d vector_element_count=%0d retired_inst_count=%0d retired_vector_inst_count=%0d retired_scalar_inst_count=%0d load_count=%0d load_unit_count=%0d load_strided_count=%0d load_indexed_count=%0d store_count=%0d store_unit_count=%0d store_strided_count=%0d store_indexed_count=%0d bitwise_count=%0d shift_count=%0d int_alu_count=%0d int_mul_count=%0d int_widen_mul_count=%0d int_mac_count=%0d int_widen_mac_count=%0d int_reduction_count=%0d fp_reduction_count=%0d narrow_count=%0d fp_arith_count=%0d permute_count=%0d mask_count=%0d scalar_move_count=%0d other_count=%0d unit_load_span_bytes=%0d unit_store_span_bytes=%0d masked_mem_count=%0d axi_ar_count=%0d axi_ar_bytes=%0d axi_r_beat_count=%0d axi_r_bus_bytes=%0d axi_aw_count=%0d axi_aw_bytes=%0d axi_w_beat_count=%0d axi_w_useful_bytes=%0d axi_b_count=%0d axi_ar_stall_cycles=%0d axi_r_stall_cycles=%0d axi_aw_stall_cycles=%0d axi_w_stall_cycles=%0d read_outstanding_occ_sum=%0d read_outstanding_max=%0d queue_occ_sum=%0d queue_occ_max=%0d queue_full_cycles=%0d inflight_occ_sum=%0d inflight_occ_max=%0d queue_resource_block_cycles=%0d no_vid_block_cycles=%0d lane_desync_block_cycles=%0d operand_block_cycles=%0d mask_block_cycles=%0d slide_block_cycles=%0d hazard_block_cycles=%0d scalar_result_wait_cycles=%0d lane_alu_operand_fires=%0d lane_mfpu_operand_fires=%0d",
      testcase, phase, NrLanes, value.cycles, value.backend_busy_cycles,
      value.lane_active_cycles,
      value.lane_inflight_slot_cycles, value.compute_active_cycles,
      value.compute_lane_slot_fires, value.compute_unit_lane_fires,
      value.alu_exec_active_cycles, value.alu_exec_lane_fires,
      value.mfpu_exec_active_cycles, value.mfpu_exec_lane_fires,
      value.int_mul_exec_lane_fires, value.int_mac_exec_lane_fires,
      value.int_mac_element_count, value.int_mac_element_capacity,
      value.int_mac_exec_lane_fires_ew8, value.int_mac_exec_lane_fires_ew16,
      value.int_mac_exec_lane_fires_ew32, value.int_mac_exec_lane_fires_ew64,
      value.int_mac_element_count_ew8, value.int_mac_element_count_ew16,
      value.int_mac_element_count_ew32, value.int_mac_element_count_ew64,
      value.int_div_exec_lane_fires,
      value.fp_exec_lane_fires, value.alu_result_lane_fires,
      value.mfpu_result_lane_fires, value.alu_result_active_bytes,
      value.mfpu_result_active_bytes,
      value.req_valid_cycles, value.req_fire_count, value.req_blocked_cycles,
      value.vector_element_count, value.retired_inst_count,
      value.retired_vector_inst_count, value.retired_scalar_inst_count,
      value.load_count, value.load_unit_count,
      value.load_strided_count, value.load_indexed_count, value.store_count,
      value.store_unit_count, value.store_strided_count, value.store_indexed_count,
      value.bitwise_count, value.shift_count, value.int_alu_count, value.int_mul_count,
      value.int_widen_mul_count, value.int_mac_count, value.int_widen_mac_count,
      value.int_reduction_count, value.fp_reduction_count, value.narrow_count,
      value.fp_arith_count, value.permute_count, value.mask_count,
      value.scalar_move_count, value.other_count, value.unit_load_span_bytes,
      value.unit_store_span_bytes, value.masked_mem_count, value.axi_ar_count,
      value.axi_ar_bytes, value.axi_r_beat_count, value.axi_r_bus_bytes,
      value.axi_aw_count, value.axi_aw_bytes, value.axi_w_beat_count,
      value.axi_w_useful_bytes, value.axi_b_count, value.axi_ar_stall_cycles,
      value.axi_r_stall_cycles, value.axi_aw_stall_cycles,
      value.axi_w_stall_cycles, value.read_outstanding_occ_sum,
      value.read_outstanding_max, value.queue_occ_sum, value.queue_occ_max,
      value.queue_full_cycles, value.inflight_occ_sum, value.inflight_occ_max,
      value.queue_resource_block_cycles, value.no_vid_block_cycles,
      value.lane_desync_block_cycles, value.operand_block_cycles,
      value.mask_block_cycles, value.slide_block_cycles, value.hazard_block_cycles,
      value.scalar_result_wait_cycles, value.lane_alu_operand_fires,
      value.lane_mfpu_operand_fires);
  endtask

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      active_q <= 1'b0;
      read_outstanding_q <= '0;
      for (int unsigned phase = 0; phase < NumPhases; phase++)
        stats_q[phase] <= '{default: '0};
    end else begin
      active_q <= active_i;

      if (!active_q && active_i) begin
        for (int unsigned phase = 0; phase < NumPhases; phase++)
          stats_q[phase] <= '{default: '0};
        stats_q[0] <= sample('{default: '0});
        if (phase_i inside {[1:3]}) stats_q[phase_i] <= sample('{default: '0});
        read_outstanding_q <= '0;
      end else if (active_i) begin
        stats_q[0] <= sample(stats_q[0]);
        if (phase_i inside {[1:3]}) stats_q[phase_i] <= sample(stats_q[phase_i]);

        unique case ({axi_ar_valid_i && axi_ar_ready_i,
                      axi_r_valid_i && axi_r_ready_i && axi_r_last_i})
          2'b10: read_outstanding_q <= read_outstanding_q + 1'b1;
          2'b01: if (read_outstanding_q != 0)
                   read_outstanding_q <= read_outstanding_q - 1'b1;
          default: read_outstanding_q <= read_outstanding_q;
        endcase
      end

      if (active_q && !active_i) begin
        string testcase;
        integer fd;
        void'($value$plusargs("TESTCASE=%s", testcase));
        fd = $fopen($sformatf("llm_perf_report_%s.log", testcase), "a");
        print_row(testcase, "total", stats_q[0], fd);
        print_row(testcase, "quantize", stats_q[1], fd);
        print_row(testcase, "pack", stats_q[2], fd);
        print_row(testcase, "matmul", stats_q[3], fd);
        $fclose(fd);
        $display("[LLM_PERF] wrote llm_perf_report_%s.log", testcase);
      end
    end
  end

endmodule
