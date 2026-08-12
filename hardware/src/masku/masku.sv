// Copyright 2021 ETH Zurich and University of Bologna.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Author: Matheus Cavalcante <matheusd@iis.ee.ethz.ch>
// Author: Matteo Perotti <mperotti@iis.ee.ethz.ch>
// Description:
// This is Ara's mask unit. It fetches operands from any one the lanes, and
// then sends back to them whether the elements are predicated or not.
// This unit is shared between all the functional units who can execute
// predicated instructions.

module masku import ara_pkg::*; import rvv_pkg::*; #(
    parameter  int  unsigned NrLanes   = 0,
    parameter  int  unsigned VLEN      = 0,
    parameter  type          vaddr_t   = logic, // Type used to address vector register file elements
    parameter  type          pe_req_t  = logic,
    parameter  type          pe_resp_t = logic,
    // Dependant parameters. DO NOT CHANGE!
    localparam int  unsigned DataWidth = $bits(elen_t), // Width of the lane datapath
    localparam int  unsigned StrbWidth = DataWidth/8,
    localparam type          strb_t    = logic [StrbWidth-1:0], // Byte-strobe type
    localparam type          vlen_t    = logic[$clog2(VLEN+1)-1:0]
  ) (
    input  logic                                       clk_i,
    input  logic                                       rst_ni,
    // Interface with the main sequencer
    input  pe_req_t                                    pe_req_i,
    input  logic                                       pe_req_valid_i,
    input  logic     [NrVInsn-1:0]                     pe_vinsn_running_i,
    output logic                                       pe_req_ready_o,
    output pe_resp_t                                   pe_resp_o,
    output elen_t                                      result_scalar_o,
    output logic                                       result_scalar_valid_o,
    // Interface with the lanes
    input  elen_t    [NrLanes-1:0][NrMaskFUnits+2-1:0] masku_operand_i,
    input  logic     [NrLanes-1:0][NrMaskFUnits+2-1:0] masku_operand_valid_i,
    output logic     [NrLanes-1:0][NrMaskFUnits+2-1:0] masku_operand_ready_o,
    output logic     [NrLanes-1:0]                     masku_result_req_o,
    output vid_t     [NrLanes-1:0]                     masku_result_id_o,
    output vaddr_t   [NrLanes-1:0]                     masku_result_addr_o,
    output elen_t    [NrLanes-1:0]                     masku_result_wdata_o,
    output strb_t    [NrLanes-1:0]                     masku_result_be_o,
    input  logic     [NrLanes-1:0]                     masku_result_gnt_i,
    input  logic     [NrLanes-1:0]                     masku_result_final_gnt_i,
    output logic     [NrLanes-1:0]                     masku_vrgat_req_valid_o,
    input  logic     [NrLanes-1:0]                     masku_vrgat_req_ready_i,
    output vrgat_req_t                                 masku_vrgat_req_o,
    // Interface with the VFUs
    output strb_t    [NrLanes-1:0]                     mask_o,
    output logic     [NrLanes-1:0]                     mask_valid_o,
    output logic                                       mask_valid_lane_o,
    output vfu_e                                         mask_target_fu_o,
    input  logic     [NrLanes-1:0]                     lane_mask_ready_i,
    input  logic                                       vldu_mask_ready_i,
    input  logic                                       vstu_mask_ready_i,
    input  logic                                       sldu_mask_ready_i
  );

  import cf_math_pkg::idx_width;

  // Pointers
  //
  // We need a pointer to which bit on the full VRF word we are reading mask operands from.
  logic [idx_width(DataWidth*NrLanes):0] mask_pnt_d, mask_pnt_q;
  // We need a pointer to which bit on the full VRF word we are writing results to.
  logic [idx_width(DataWidth*NrLanes):0] vrf_pnt_d, vrf_pnt_q;

  // Remaining elements of the current instruction in the read operand phase
  vlen_t read_cnt_d, read_cnt_q;
  vlen_t mask_aligned_vstart;
  // Remaining elements of the current instruction in the issue phase
  vlen_t issue_cnt_d, issue_cnt_q;
  // Remaining elements of the current instruction to be validated in the result queue
  vlen_t processing_cnt_d, processing_cnt_q;
  // Remaining elements of the current instruction in the commit phase
  vlen_t commit_cnt_d, commit_cnt_q;

  ////////////////
  //  Operands  //
  ////////////////

  // Information about which is the target FU of the request
  masku_fu_e masku_operand_fu;

  // ALU/FPU result (shuffled)
  elen_t [NrLanes-1:0] masku_operand_alu;
  logic  [NrLanes-1:0] masku_operand_alu_valid;
  logic  [NrLanes-1:0] masku_operand_alu_ready;

  // ALU/FPU result (deshuffled)
  logic  [NrLanes*DataWidth-1:0] masku_operand_alu_seq;

  // vd (shuffled)
  elen_t [NrLanes-1:0] masku_operand_vd;
  logic  [NrLanes-1:0] masku_operand_vd_valid;
  logic  [NrLanes-1:0] masku_operand_vd_ready;

  // vd (deshuffled)
  logic  [NrLanes*DataWidth-1:0] masku_operand_vd_seq;
  logic  [     NrLanes-1:0] masku_operand_vd_seq_valid;

  // Mask
  elen_t [NrLanes-1:0] masku_operand_m;
  logic  [NrLanes-1:0] masku_operand_m_valid;
  logic  [NrLanes-1:0] masku_operand_m_ready;

  // Mask deshuffled
  logic  [NrLanes*DataWidth-1:0] masku_operand_m_seq;

  // Insn-queue related signal
  pe_req_t vinsn_issue;

  logic  [NrLanes*DataWidth-1:0] bit_enable_mask;
  logic  [NrLanes*DataWidth-1:0] alu_result_compressed_seq;

  // Performs all shuffling and deshuffling of mask operands (including masks for mask instructions)
  // Furthermore, it buffers certain operands that would create long critical paths
  masku_operands #(
    .NrLanes  ( NrLanes   ),
    .pe_req_t ( pe_req_t  ),
    .pe_resp_t( pe_resp_t )
  ) i_masku_operands (
    .clk_i                         (                       clk_i ),
    .rst_ni                        (                      rst_ni ),
    // Control logic
    .masku_fu_i                    (            masku_operand_fu ),
    .vinsn_issue_i                 (                 vinsn_issue ),
    .vrf_pnt_i                     (                   vrf_pnt_q ),
    // Operands coming from lanes
    .masku_operand_valid_i         (       masku_operand_valid_i ),
    .masku_operand_ready_o         (       masku_operand_ready_o ),
    .masku_operands_i              (             masku_operand_i ),
    // Operands prepared for mask unit execution
    .masku_operand_alu_o           (           masku_operand_alu ),
    .masku_operand_alu_valid_o     (     masku_operand_alu_valid ),
    .masku_operand_alu_ready_i     (     masku_operand_alu_ready ),
    .masku_operand_alu_seq_o       (       masku_operand_alu_seq ),
    .masku_operand_alu_seq_valid_o (                             ),
    .masku_operand_alu_seq_ready_i (                          '0 ),
    .masku_operand_vd_o            (            masku_operand_vd ),
    .masku_operand_vd_valid_o      (      masku_operand_vd_valid ),
    .masku_operand_vd_ready_i      (      masku_operand_vd_ready ),
    .masku_operand_vd_seq_o        (        masku_operand_vd_seq ),
    .masku_operand_vd_seq_valid_o  (  masku_operand_vd_seq_valid ),
    .masku_operand_vd_seq_ready_i  (                          '0 ),
    .masku_operand_m_o             (             masku_operand_m ),
    .masku_operand_m_valid_o       (       masku_operand_m_valid ),
    .masku_operand_m_ready_i       (       masku_operand_m_ready ),
    .masku_operand_m_seq_o         (         masku_operand_m_seq ),
    .masku_operand_m_seq_valid_o   (                             ),
    .masku_operand_m_seq_ready_i   (                          '0 ),
    .bit_enable_mask_o             (             bit_enable_mask ),
    .alu_result_compressed_seq_o   (   alu_result_compressed_seq )
  );

  // Local Parameter for mask logical instructions
  //
  // Don't change this parameter!
  localparam integer unsigned VrgatherParallelism = 1;

  // Local Parameter for mask logical instructions
  //
  // Don't change this parameter!
  localparam integer unsigned VmLogicalParallelism = NrLanes*DataWidth;

  // Local Parameter VMSBF, VMSIF, VMSOF
  //
  localparam integer unsigned VmsxfParallelism = NrLanes < 4 ? 2 : NrLanes/2;
  // Ancillary signals
  logic [VmsxfParallelism-1:0] vmsbf_buffer;
  logic [NrLanes*DataWidth-1:0] alu_result_vmsif_vm;
  logic [NrLanes*DataWidth-1:0] alu_result_vmsbf_vm;
  logic [NrLanes*DataWidth-1:0] alu_result_vmsof_vm;

  // Local Parameter VIOTA, VID
  //
  // How many output results are computed in parallel by VIOTA
  localparam integer unsigned ViotaParallelism = NrLanes < 4 ? 2 : NrLanes/2;
  // Check if parameters are within range
  if (ViotaParallelism > NrLanes || ViotaParallelism % 2 != 0) begin
    $fatal(1, "Parameter ViotaParallelism cannot be higher than NrLanes and should be a power of 2.");
  end
  // VLENMAX can be 64Ki elements at most - 16 bit per adder are enough
  logic [ViotaParallelism-1:0] [idx_width(RISCV_MAX_VLEN)-1:0] viota_res;
  logic [idx_width(RISCV_MAX_VLEN)-1:0] viota_acc, viota_acc_d, viota_acc_q;
  // Ancillary signal to tweak the VRF byte-enable, accounting for an unbalanced write,
  // i.e., when the number of elements does not perfectly divide NrLanes
  logic [3:0] elm_per_lane; // From 0 to 8 elements per lane
  logic [NrLanes-1:0] additional_elm; // There can be an additional element for some lanes
  // BE signals for VIOTA
  logic [NrLanes*DataWidth/8-1:0] be_viota_seq_d, be_viota_seq_q, be_vrgat_seq_d, be_vrgat_seq_q;
  logic [NrLanes*DataWidth/8-1:0] be_masku_alu_shuf;

  // Local Parameter VcpopParallelism and VfirstParallelism
  //
  // Description: Parameters VcpopParallelism and VfirstParallelism enable time multiplexing of vcpop.m and vfirst.m instruction.
  //
  // Legal range VcpopParallelism:   {16, 32, 64, 128, ... , DataWidth*NrLanes} // DataWidth = 64
  // Legal range VfirstParallelism: {16, 32, 64, 128, ... , DataWidth*NrLanes} // DataWidth = 64
  //
  // Execution time example for vcpop.m (similar for vfirst.m):
  // VcpopParallelism = 64; VLEN = 1024; vl = 1024
  // t_vcpop.m = VLEN/VcpopParallelism = 8 [Cycles]
  localparam int VcpopParallelism   = 16;
  localparam int VfirstParallelism = 16;
  // derived parameters
  localparam int MAX_VcpopParallelism_VFIRST = (VcpopParallelism > VfirstParallelism) ? VcpopParallelism : VfirstParallelism;
  localparam int N_SLICES_CPOP   = NrLanes * DataWidth / VcpopParallelism;
  localparam int N_SLICES_VFIRST = NrLanes * DataWidth / VfirstParallelism;
  // Check if parameters are within range
  if (((VcpopParallelism & (VcpopParallelism - 1)) != 0) || (VcpopParallelism < 8)) begin
    $fatal(1, "Parameter VcpopParallelism must be power of 2.");
  end else if (((VfirstParallelism & (VfirstParallelism - 1)) != 0) || (VfirstParallelism < 8)) begin
    $fatal(1, "Parameter VfirstParallelism must be power of 2.");
  end

  // VFIRST and VCPOP Signals
  logic  [NrLanes*DataWidth-1:0]              vcpop_operand;
  logic  [$clog2(VcpopParallelism):0]              popcount;
  logic  [$clog2(VLEN):0]                popcount_d, popcount_q;
  logic  [$clog2(VfirstParallelism)-1:0]          vfirst_count;
  logic  [$clog2(VLEN)-1:0]              vfirst_count_d, vfirst_count_q;
  logic                                  vfirst_found_d, vfirst_found_q;
  logic                                  vfirst_empty;
  // counter to keep track of how many slices of the vcpop_operand have been processed
  logic [VcpopParallelism-1:0]                    vcpop_slice_raw, vcpop_slice;
  logic [VfirstParallelism-1:0]                  vfirst_slice_raw, vfirst_slice;

  // vmsbf, vmsif, vmsof, viota, vid, vcpop, vfirst variables
  logic  [NrLanes*DataWidth-1:0] masku_operand_alu_seq_m;
  logic  [NrLanes*DataWidth-1:0] alu_result_vm, alu_result_vm_m, alu_result_vm_shuf;
  logic                          found_one, found_one_d, found_one_q;

  // How many elements we are processing per cycle
  logic [idx_width(NrLanes*DataWidth):0] delta_elm_d, delta_elm_q;

  // MASKU Alu: is a VRF word result or a scalar result fully valid?
  logic out_vrf_word_valid, out_scalar_valid;

  ////////////////////////////////
  //  Vector instruction queue  //
  ////////////////////////////////

  // We store a certain number of in-flight vector instructions.
  // To avoid any hazards between masked vector instructions, the mask
  // unit is only capable of handling one vector instruction at a time.
  // Optimizing this unit is left as future work.

  localparam VInsnQueueDepth = MaskuInsnQueueDepth;

  struct packed {
    pe_req_t [VInsnQueueDepth-1:0] vinsn;

    // We also need to count how many instructions are queueing to be
    // issued/committed, to avoid accepting more instructions than
    // we can handle.
    logic [idx_width(VInsnQueueDepth)-1:0] issue_cnt;
    logic [idx_width(VInsnQueueDepth)-1:0] commit_cnt;
  } vinsn_queue_d, vinsn_queue_q;

  // Is the vector instruction queue full?
  logic vinsn_queue_full;
  assign vinsn_queue_full = (vinsn_queue_q.commit_cnt == VInsnQueueDepth);

  // Do we have a vector instruction ready to be issued?
  logic    vinsn_issue_valid;
  assign vinsn_issue       = vinsn_queue_q.vinsn[0];
  assign vinsn_issue_valid = (vinsn_queue_q.issue_cnt != '0);

  // Do we have a vector instruction with results being committed?
  pe_req_t vinsn_commit;
  logic    vinsn_commit_valid;
  assign vinsn_commit       = vinsn_queue_q.vinsn[0];
  assign vinsn_commit_valid = (vinsn_queue_q.commit_cnt != '0);

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      vinsn_queue_q <= '0;
    end else begin
      vinsn_queue_q <= vinsn_queue_d;
    end
  end

  ///////////////////
  //  Mask queues  //
  ///////////////////

  localparam int unsigned MaskQueueDepth = 2;

  // There is a mask queue per lane, holding the operands that were not
  // yet used by the corresponding lane.

  // Mask queue
  strb_t [MaskQueueDepth-1:0][NrLanes-1:0] mask_queue_d, mask_queue_q;
  logic  [MaskQueueDepth-1:0][NrLanes-1:0] mask_queue_valid_d, mask_queue_valid_q;
  vfu_e  [MaskQueueDepth-1:0]               mask_queue_target_d, mask_queue_target_q;
  // We need two pointers in the mask queue. One pointer to
  // indicate with `strb_t` we are currently writing into (write_pnt),
  // and one pointer to indicate which `strb_t` we are currently
  // reading from and writing into the lanes (read_pnt).
  logic  [idx_width(MaskQueueDepth)-1:0]   mask_queue_write_pnt_d, mask_queue_write_pnt_q;
  logic  [idx_width(MaskQueueDepth)-1:0]   mask_queue_read_pnt_d, mask_queue_read_pnt_q;
  // We need to count how many valid elements are there in this mask queue.
  logic  [idx_width(MaskQueueDepth):0]     mask_queue_cnt_d, mask_queue_cnt_q;

  // Is the mask queue full?
  logic mask_queue_full;
  assign mask_queue_full = (mask_queue_cnt_q == MaskQueueDepth);
  // Is the mask queue empty?
  logic mask_queue_empty;
  assign mask_queue_empty = (mask_queue_cnt_q == '0);

  always_ff @(posedge clk_i or negedge rst_ni) begin: p_mask_queue_ff
    if (!rst_ni) begin
      mask_queue_q           <= '0;
      mask_queue_valid_q     <= '0;
      mask_queue_target_q    <= '{default: VFU_None};
      mask_queue_write_pnt_q <= '0;
      mask_queue_read_pnt_q  <= '0;
      mask_queue_cnt_q       <= '0;
    end else begin
      mask_queue_q           <= mask_queue_d;
      mask_queue_valid_q     <= mask_queue_valid_d;
      mask_queue_target_q    <= mask_queue_target_d;
      mask_queue_write_pnt_q <= mask_queue_write_pnt_d;
      mask_queue_read_pnt_q  <= mask_queue_read_pnt_d;
      mask_queue_cnt_q       <= mask_queue_cnt_d;
    end
  end


`ifndef SYNTHESIS
  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_MASK_TARGET") &&
        ((vinsn_issue_valid && vinsn_issue.op == VFNMSUB) ||
         (!mask_queue_empty &&
          mask_queue_target_q[mask_queue_read_pnt_q] == VFU_MFpu))) begin
      $display("[ARA_MASK_TARGET] t=%0t issue_v=%0b op=%0d id=%0d issue_fu=%0d cnt=%0d rp=%0d wp=%0d head_fu=%0d head_v=%b lane_r=%b ld_r=%0b st_r=%0b sl_r=%0b commit=%0d read=%0d",
               $time, vinsn_issue_valid, vinsn_issue.op, vinsn_issue.id,
               vinsn_issue.vfu, mask_queue_cnt_q, mask_queue_read_pnt_q,
               mask_queue_write_pnt_q, mask_target_fu_o,
               mask_queue_valid_q[mask_queue_read_pnt_q], lane_mask_ready_i,
               vldu_mask_ready_i, vstu_mask_ready_i, sldu_mask_ready_i,
               commit_cnt_q, read_cnt_q);
    end
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_MASK_QUEUE_ALL") &&
        (!mask_queue_empty || pe_req_valid_i)) begin
      $display("[ARA_MASK_QUEUE_ALL] t=%0t req=%0b/%0b op=%0d id=%0d fu=%0d vm=%0b iq=%0d mask_cnt=%0d rp=%0d wp=%0d target=%0d valid=%b lane_r=%b commit=%0d read=%0d",
               $time, pe_req_valid_i, pe_req_ready_o, pe_req_i.op,
               pe_req_i.id, pe_req_i.vfu, pe_req_i.vm,
               vinsn_queue_q.issue_cnt, mask_queue_cnt_q,
               mask_queue_read_pnt_q, mask_queue_write_pnt_q,
               mask_queue_target_q[mask_queue_read_pnt_q],
               mask_queue_valid_q[mask_queue_read_pnt_q], lane_mask_ready_i,
               commit_cnt_q, read_cnt_q);
    end
  end
`endif

  /////////////////////
  //  Result queues  //
  /////////////////////

  localparam int unsigned ResultQueueDepth = 2;

  // There is a result queue per lane, holding the results that were not
  // yet accepted by the corresponding lane.
  typedef struct packed {
    vid_t id;
    vaddr_t addr;
    elen_t wdata;
    strb_t be;
  } payload_t;

  // Result queue
  payload_t [ResultQueueDepth-1:0][NrLanes-1:0] result_queue_d, result_queue_q;
  logic     [ResultQueueDepth-1:0][NrLanes-1:0] result_queue_valid_d, result_queue_valid_q;
  // We need two pointers in the result queue. One pointer to
  // indicate with `payload_t` we are currently writing into (write_pnt),
  // and one pointer to indicate which `payload_t` we are currently
  // reading from and writing into the lanes (read_pnt).
  logic     [idx_width(ResultQueueDepth)-1:0]   result_queue_write_pnt_d, result_queue_write_pnt_q;
  logic     [idx_width(ResultQueueDepth)-1:0]   result_queue_read_pnt_d, result_queue_read_pnt_q;
  // We need to count how many valid elements are there in this result queue.
  logic     [idx_width(ResultQueueDepth):0]     result_queue_cnt_d, result_queue_cnt_q;
  // Vector to register the final grants from the operand requesters, which indicate
  // that the result was actually written in the VRF (while the normal grant just says
  // that the result was accepted by the operand requester stage
  logic     [NrLanes-1:0]                       result_final_gnt_d, result_final_gnt_q;

  // Result queue
  elen_t [NrLanes-1:0] result_queue_background_data;
  elen_t [NrLanes-1:0] result_queue_mask_seq;
  logic  [NrLanes*DataWidth-1:0] result_queue_active_mask_seq;
  logic  [NrLanes*DataWidth-1:0] background_data_init_seq, background_data_init_shuf;

  // Is the result queue full?
  logic result_queue_full;
  assign result_queue_full = (result_queue_cnt_q == ResultQueueDepth);
  // Is the result queue empty?
  logic result_queue_empty;
  assign result_queue_empty = (result_queue_cnt_q == '0);

  always_ff @(posedge clk_i or negedge rst_ni) begin: p_result_queue_ff
    if (!rst_ni) begin
      result_queue_q           <= '0;
      result_queue_valid_q     <= '0;
      result_queue_write_pnt_q <= '0;
      result_queue_read_pnt_q  <= '0;
      result_queue_cnt_q       <= '0;
    end else begin
      result_queue_q           <= result_queue_d;
      result_queue_valid_q     <= result_queue_valid_d;
      result_queue_write_pnt_q <= result_queue_write_pnt_d;
      result_queue_read_pnt_q  <= result_queue_read_pnt_d;
      result_queue_cnt_q       <= result_queue_cnt_d;
    end
  end

  ////////////////////
  //  ALU counters  //
  ////////////////////

  // What is the minimum supported parallelism?
  localparam int unsigned MIN_MASKU_ALU_WIDTH = 1; // VrgatherParallelism

  localparam int unsigned IN_READY_CNT_WIDTH = idx_width(NrLanes * DataWidth / MIN_MASKU_ALU_WIDTH);
  typedef logic [IN_READY_CNT_WIDTH-1:0] in_ready_cnt_t;
  logic in_ready_cnt_en, in_ready_cnt_clr;
  in_ready_cnt_t in_ready_cnt_delta_q, in_ready_cnt_q;
  in_ready_cnt_t in_ready_threshold_d, in_ready_threshold_q;

  assign in_ready_cnt_delta_q = 1;

  // Counter to trigger the input ready.
  // Ready triggered when all the slices of the VRF word have been consumed.
  delta_counter #(
    .WIDTH(IN_READY_CNT_WIDTH)
  ) i_in_ready_cnt (
    .clk_i,
    .rst_ni,
    .clear_i(in_ready_cnt_clr    ),
    .en_i   (in_ready_cnt_en     ),
    .load_i (1'b0                ),
    .down_i (1'b0                ),
    .delta_i(in_ready_cnt_delta_q),
    .d_i    ('0                  ),
    .q_o    (in_ready_cnt_q      ),
    .overflow_o(/* Unused */)
  );

  localparam int unsigned IN_M_READY_CNT_WIDTH = idx_width(NrLanes * DataWidth / MIN_MASKU_ALU_WIDTH);
  typedef logic [IN_M_READY_CNT_WIDTH-1:0] in_m_ready_cnt_t;
  logic in_m_ready_cnt_en, in_m_ready_cnt_clr;
  in_m_ready_cnt_t in_m_ready_cnt_q, in_m_ready_cnt_delta_q;
  in_ready_cnt_t in_m_ready_threshold_d, in_m_ready_threshold_q;

  assign in_m_ready_cnt_delta_q = 1;

  // Counter to trigger the input ready.
  // Ready triggered when all the slices of the VRF word have been consumed.
  delta_counter #(
    .WIDTH(IN_M_READY_CNT_WIDTH)
  ) i_in_m_ready_cnt (
    .clk_i,
    .rst_ni,
    .clear_i(in_m_ready_cnt_clr    ),
    .en_i   (in_m_ready_cnt_en     ),
    .load_i (1'b0                  ),
    .down_i (1'b0                  ),
    .delta_i(in_m_ready_cnt_delta_q),
    .d_i    ('0                    ),
    .q_o    (in_m_ready_cnt_q      ),
    .overflow_o(/* Unused */)
  );

  localparam int unsigned OUT_VALID_CNT_WIDTH = idx_width(NrLanes * DataWidth / MIN_MASKU_ALU_WIDTH);
  typedef logic [OUT_VALID_CNT_WIDTH-1:0] out_valid_cnt_t;
  logic out_valid_cnt_en, out_valid_cnt_clr;
  out_valid_cnt_t out_valid_cnt_q, out_valid_cnt_delta_q;
  out_valid_cnt_t out_valid_threshold_d, out_valid_threshold_q;

  assign out_valid_cnt_delta_q = 1;

  // Counter to trigger the output valid.
  // Valid triggered when all the slices of the VRF word have been consumed.
  delta_counter #(
    .WIDTH(OUT_VALID_CNT_WIDTH)
  ) i_out_valid_cnt (
    .clk_i,
    .rst_ni,
    .clear_i(out_valid_cnt_clr    ),
    .en_i   (out_valid_cnt_en     ),
    .load_i (1'b0                 ),
    .down_i (1'b0                 ),
    .delta_i(out_valid_cnt_delta_q),
    .d_i    ('0                   ),
    .q_o    (out_valid_cnt_q      ),
    .overflow_o(/* Unused */)
  );

  // How many (64*NrLanes)-bit VRF words we can get, maximum?
  localparam int unsigned MAX_NUM_VRF_WORDS = VLEN / NrLanes / 8;
  logic iteration_cnt_clr;
  logic [idx_width(MAX_NUM_VRF_WORDS)-1:0] iteration_cnt_q, iteration_cnt_delta_q;

  assign iteration_cnt_delta_q = 1;

  // Iteration count for masked instructions
  // One iteration == One full output slice processed
  delta_counter #(
    .WIDTH(idx_width(MAX_NUM_VRF_WORDS))
  ) i_iteration_cnt (
    .clk_i,
    .rst_ni,
    .clear_i(iteration_cnt_clr    ),
    .en_i   (out_valid_cnt_clr    ),
    .load_i (1'b0                 ),
    .down_i (1'b0                 ),
    .delta_i(iteration_cnt_delta_q),
    .d_i    ('0                   ),
    .q_o    (iteration_cnt_q      ),
    .overflow_o(/* Unused */)
  );

  ///////////////////////////////
  //// VRGATHER / VCOMPRESS  ////
  ///////////////////////////////

  // How deep are the VRGATHER/VCOMPRESS address/index FIFOs?
  localparam int unsigned VrgatFifoDepth = 3;

  // Mask bit sequentially selected by the m-operand delta counter
  // VRGATHER: used as a mask bit by the MASKU ALU (write-back phase of VRGATHER)
  // VCOMPRESS: used as an index bit to build the next index for address generation (first phase of VCOMPRESS)
  logic vrgat_m_seq_bit;

  // Sequential indicator to track that end of the vcompress issue phase
  logic vcompress_issue_end_d, vcompress_issue_end_q;

  // How many elements will the current vcompress write?
  vlen_t vcompress_cnt_d, vcompress_cnt_q;

  vlen_t effective_elm_cnt;

  // Sequential counter for vcompress
  vlen_t vrgat_cnt_d, vrgat_cnt_q;
  logic vcompress_bit;

  // FIFO-related signals
  logic vrgat_req_fifo_empty, vrgat_req_fifo_full, vrgat_req_fifo_push, vrgat_req_fifo_pop;
  logic vrgat_idx_fifo_empty, vrgat_idx_fifo_full, vrgat_idx_fifo_push, vrgat_idx_fifo_pop;

  max_vlen_t vrgat_req_idx_d, vrgat_req_idx_q;
  vrgat_req_t vrgat_req_d, vrgat_req_q;

  vew_e vrgat_req_eew_d;
  logic [4:0] vrgat_req_vs_d;
  logic vrgat_req_is_last_req_d, vrgat_req_no_data_d;

  // If VRGATHEREI16, vsew == EW16 -> shift-by-1
  logic [1:0] vrgat_eff_vsew;
  assign vrgat_eff_vsew = (pe_req_i.op == VRGATHEREI16) ? 2'b1 : unsigned'(pe_req_i.vtype.vsew);

  assign vrgat_req_eew_d = vinsn_issue.vtype.vsew;
  assign vrgat_req_vs_d  = vinsn_issue.vs2;

  // Build the address from the index
  assign vrgat_req_d = '{
    id          : vinsn_issue.id,
    idx         : vrgat_req_idx_d / NrLanes,
    eew         : vrgat_req_eew_d,
    vs          : vrgat_req_vs_d,
    is_last_req : vrgat_req_is_last_req_d,
    no_data     : vrgat_req_no_data_d
  };

  // Broadcast the address request to all the lanes
  assign masku_vrgat_req_o = vrgat_req_q;

  // A mask for the valid to keep up only the unshaked ones and hide the others
  logic [NrLanes-1:0] vrgat_req_valid_mask_d, vrgat_req_valid_mask_q;

  // Synchronize the handshake between MASKU and lanes since we are making a single request
  // to all the lanes, which can also answer individually
  always_comb begin
    logic [NrLanes-1:0] vrgat_req_accepted;

    vrgat_req_fifo_pop = 1'b0;
    vrgat_req_accepted = vrgat_req_valid_mask_q;

    for (int lane = 0; lane < NrLanes; lane++) begin
      // Keep valid asserted until this lane accepts the current FIFO head.
      masku_vrgat_req_valid_o[lane] = ~vrgat_req_fifo_empty & ~vrgat_req_valid_mask_q[lane];
      if (masku_vrgat_req_valid_o[lane] && masku_vrgat_req_ready_i[lane])
        vrgat_req_accepted[lane] = 1'b1;
    end

    vrgat_req_valid_mask_d = vrgat_req_fifo_empty ? '0 : vrgat_req_accepted;
    // Advance only after every lane has accepted this same FIFO entry.
    if (~vrgat_req_fifo_empty && &vrgat_req_accepted) begin
      vrgat_req_fifo_pop = 1'b1;
      vrgat_req_valid_mask_d = '0;
    end
  end

  // Overflow after 16-bits
  logic vrgat_idx_overflow;
  // VRGATHER out-of-range indicator. VCOMPRESS reuses this FIFO bit to mark
  // an end-of-input entry that carries no source-data request.
  logic vrgat_idx_oor_d, vrgat_idx_oor_q;
  // Last vcompress index
  logic vcompress_last_idx_d, vcompress_last_idx_q;

  // Save the indices into the MASKU ALU vrgather/vcompress queue for later use
  // Also, save if one of the indices is out of range and if this is the last VCOMPRESS index
  fifo_v3 #(
    .DATA_WIDTH($clog2(RISCV_MAX_VLEN) + 2),
    .DEPTH     (VrgatFifoDepth            )
  ) i_fifo_vrgat_idx (
    .clk_i,
    .rst_ni,
    .flush_i   (1'b0),
    .testmode_i(1'b0),
    .full_o    (vrgat_idx_fifo_full           ),
    .empty_o   (vrgat_idx_fifo_empty          ),
    .usage_o   (/* unused */                  ),
    .data_i    ({vcompress_last_idx_d, vrgat_idx_oor_d, vrgat_req_idx_d}),
    .push_i    (vrgat_idx_fifo_push           ),
    .data_o    ({vcompress_last_idx_q, vrgat_idx_oor_q, vrgat_req_idx_q}),
    .pop_i     (vrgat_idx_fifo_pop            )
  );

  // Send the address request to the lanes
  fifo_v3 #(
    .dtype(vrgat_req_t   ),
    .DEPTH(VrgatFifoDepth)
  ) i_fifo_vrgat_req (
    .clk_i,
    .rst_ni,
    .flush_i   (1'b0),
    .testmode_i(1'b0),
    .full_o    (vrgat_req_fifo_full ),
    .empty_o   (vrgat_req_fifo_empty),
    .usage_o   (/* unused */         ),
    .data_i    (vrgat_req_d         ),
    .push_i    (vrgat_req_fifo_push ),
    .data_o    (vrgat_req_q         ),
    .pop_i     (vrgat_req_fifo_pop  )
  );

  ////////////////////////////
  //// Scalar result reg  ////
  ////////////////////////////

  elen_t result_scalar_d;
  logic  result_scalar_valid_d;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      result_scalar_o       <= '0;
      result_scalar_valid_o <= '0;
    end else begin
      result_scalar_o       <= result_scalar_d;
      result_scalar_valid_o <= result_scalar_valid_d;
    end
  end

  ////////////////
  //  Mask ALU  //
  ////////////////

  elen_t [NrLanes-1:0] alu_result;

  // assign operand slices to be processed by popcount and lzc
  assign vcpop_slice_raw  = vcpop_operand[(in_ready_cnt_q[idx_width(N_SLICES_CPOP)-1:0] * VcpopParallelism) +: VcpopParallelism];
  assign vfirst_slice_raw = vcpop_operand[(in_ready_cnt_q[idx_width(N_SLICES_VFIRST)-1:0] * VfirstParallelism) +: VfirstParallelism];

  // The final scalar-mask slice can contain fewer valid elements than the
  // parallel datapath width. Tail bits in the fetched mask word are
  // architectural state, but must not contribute to vcpop or terminate
  // vfirst when their index is at or above vl.
  for (genvar i = 0; i < VcpopParallelism; i++) begin : gen_vcpop_active_slice
    assign vcpop_slice[i] = vcpop_slice_raw[i] && (issue_cnt_q > vlen_t'(i));
  end
  for (genvar i = 0; i < VfirstParallelism; i++) begin : gen_vfirst_active_slice
    assign vfirst_slice[i] = vfirst_slice_raw[i] && (issue_cnt_q > vlen_t'(i));
  end

  // Population count for vcpop.m instruction
  popcount #(
    .INPUT_WIDTH (VcpopParallelism)
  ) i_popcount (
    .data_i    (vcpop_slice),
    .popcount_o(popcount     )
  );

  // Trailing zero counter
  lzc #(
    .WIDTH(VfirstParallelism),
    .MODE (0)
  ) i_clz (
    .in_i    (vfirst_slice ),
    .cnt_o   (vfirst_count ),
    .empty_o (vfirst_empty )
  );

  // Vector instructions currently running
  logic [NrVInsn-1:0] vinsn_running_d, vinsn_running_q;

  // Interface with the main sequencer
  pe_resp_t pe_resp;

  // Effective MASKU stride in case of VSLIDEUP
  // MASKU receives chunks of 64 * NrLanes mask bits from the lanes
  // VSLIDEUP only needs the bits whose index >= than its stride
  // So, the operand requester does not send vl mask bits to MASKU
  // and trims all the unused 64 * NrLanes mask bits chunks
  // Therefore, the stride needs to be trimmed, too
  elen_t trimmed_stride;

  // Information about which is the target FU of the request
  assign masku_operand_fu = (vinsn_issue.op inside {[VMFEQ:VMFGE]}) ? MaskFUMFpu : MaskFUAlu;

  always_comb begin
    // Tail-agnostic bus
    alu_result          = '1;
    alu_result_vm       = '1;
    alu_result_vm_m     = '1;
    alu_result_vm_shuf  = '1;
    alu_result_vmsif_vm = '1;
    alu_result_vmsbf_vm = '1;
    alu_result_vmsof_vm = '1;
    alu_result_vm       = '1;

    vcpop_operand = '0;

    vrgat_m_seq_bit = 1'b0;

    // The result mask should be created here since the output is a non-mask vector
    be_viota_seq_d = be_viota_seq_q;

    // Create a bit-masked ALU sequential vector
    masku_operand_alu_seq_m = masku_operand_alu_seq
                            & (masku_operand_m_seq | {NrLanes*DataWidth{vinsn_issue.vm}});

    // VMSBF, VMSIF, VMSOF default assignments
    found_one           = found_one_q;
    found_one_d         = found_one_q;
    vmsbf_buffer        = '0;
    // VIOTA default assignments
    viota_acc   = viota_acc_q;
    viota_acc_d = viota_acc_q;
    for (int i = 0; i < ViotaParallelism; i++) viota_res[i] = '0;

    be_vrgat_seq_d = be_vrgat_seq_q;

    // Mark architectural mask-result bits that this output word may update.
    // The old-vd merge happens at packed mask-bit granularity, so every mask
    // producer needs the exact [vstart, vl) window rather than only the number
    // of elements left in the final word.
    result_queue_active_mask_seq = '0;
    for (int unsigned i = 0; i < NrLanes*DataWidth; i++) begin
      if (vinsn_issue.op inside {
            [VMFEQ:VMFGE], [VMSEQ:VMSGT], [VMADC:VMSBC],
            [VMSBF:VMSIF], [VMANDNOT:VMXNOR]
          }) begin
        if ((vlen_t'(iteration_cnt_q * NrLanes * DataWidth + i) >=
             vinsn_issue.vstart) &&
            (vlen_t'(iteration_cnt_q * NrLanes * DataWidth + i) <
             vinsn_issue.vl)) begin
          result_queue_active_mask_seq[i] = 1'b1;
        end
      end else if (i < processing_cnt_q) begin
        result_queue_active_mask_seq[i] = 1'b1;
      end
    end

    if (vinsn_issue_valid) begin
      // Evaluate the instruction
      unique case (vinsn_issue.op) inside
        // Mask logical: pass through the result already computed in the ALU. The
        // operation is unmasked. Preserve the restart prefix and, under tail-undisturbed
        // policy, the destination bits at or above vl.
        [VMANDNOT:VMXNOR]: begin
          unique case (vinsn_issue.op)
            VMANDNOT: alu_result_vm_m = ~masku_operand_m_seq & masku_operand_alu_seq;
            VMAND   : alu_result_vm_m =  masku_operand_m_seq & masku_operand_alu_seq;
            VMOR    : alu_result_vm_m =  masku_operand_m_seq | masku_operand_alu_seq;
            VMXOR   : alu_result_vm_m =  masku_operand_m_seq ^ masku_operand_alu_seq;
            VMORNOT : alu_result_vm_m = ~masku_operand_m_seq | masku_operand_alu_seq;
            VMNAND  : alu_result_vm_m = ~(masku_operand_m_seq & masku_operand_alu_seq);
            VMNOR   : alu_result_vm_m = ~(masku_operand_m_seq | masku_operand_alu_seq);
            VMXNOR  : alu_result_vm_m = ~(masku_operand_m_seq ^ masku_operand_alu_seq);
            default : alu_result_vm_m = '1;
          endcase
          if (vinsn_issue.use_vd_op) begin
            for (int unsigned i = 0; i < VmLogicalParallelism; i++) begin
              if ((vlen_t'(iteration_cnt_q * VmLogicalParallelism + i) <
                   vinsn_issue.vstart) ||
                  (!vinsn_issue.vtype.vta &&
                   (vlen_t'(iteration_cnt_q * VmLogicalParallelism + i) >=
                    vinsn_issue.vl))) begin
                alu_result_vm_m[i] = masku_operand_vd_seq[i];
              end
            end
          end
        end
        // Comparisons: mask out the masked out bits of this pre-computed slice
        [VMFEQ:VMSGT]: alu_result_vm_m = alu_result_compressed_seq
                                  | ~(masku_operand_m_seq | {NrLanes*DataWidth{vinsn_issue.vm}});
        // Add/sub-with-carry/borrow are not predicated. When old vd is needed,
        // inactive restart-prefix and tail positions must be AND identities so
        // the background merge preserves vd even if an unused ALU slot is X.
        [VMADC:VMSBC]: begin
          alu_result_vm_m = alu_result_compressed_seq;
          if (vinsn_issue.use_vd_op)
            alu_result_vm_m |= ~result_queue_active_mask_seq;
        end
        // VMSBF, VMSOF, VMSIF: compute a slice of the output and mask out the masked out bits
        [VMSBF:VMSIF] : begin
          vmsbf_buffer[0] = ~(masku_operand_alu_seq_m[in_ready_cnt_q[idx_width(NrLanes*DataWidth/VmsxfParallelism)-1:0] * VmsxfParallelism] | found_one_q);
          for (int i = 1; i < VmsxfParallelism; i++) begin
            vmsbf_buffer[i] = ~((masku_operand_alu_seq_m[in_ready_cnt_q[idx_width(NrLanes*DataWidth/VmsxfParallelism)-1:0] * VmsxfParallelism + i]) | ~vmsbf_buffer[i-1]);
          end
          // Have we found a 1 in the current slice?
          found_one = |(masku_operand_alu_seq_m[in_ready_cnt_q[idx_width(NrLanes*DataWidth/VmsxfParallelism)-1:0] * VmsxfParallelism +: VmsxfParallelism]) | found_one_q;

          alu_result_vmsbf_vm[out_valid_cnt_q[idx_width(NrLanes*DataWidth/VmsxfParallelism)-1:0] * VmsxfParallelism +: VmsxfParallelism] = vmsbf_buffer;
          alu_result_vmsif_vm[out_valid_cnt_q[idx_width(NrLanes*DataWidth/VmsxfParallelism)-1:0] * VmsxfParallelism +: VmsxfParallelism] = {vmsbf_buffer[VmsxfParallelism-2:0], ~found_one_q};
          alu_result_vmsof_vm[out_valid_cnt_q[idx_width(NrLanes*DataWidth/VmsxfParallelism)-1:0] * VmsxfParallelism +: VmsxfParallelism] = ~vmsbf_buffer & {vmsbf_buffer[VmsxfParallelism-2:0], ~found_one_q};

          unique case (vinsn_issue.op)
            VMSBF: alu_result_vm = alu_result_vmsbf_vm;
            VMSIF: alu_result_vm = alu_result_vmsif_vm;
            // VMSOF
            default: alu_result_vm = alu_result_vmsof_vm;
          endcase

          // Mask the result
          alu_result_vm_m = (!vinsn_issue.vm) || (vinsn_issue.op inside {[VMADC:VMSBC]}) ? alu_result_vm | ~masku_operand_m_seq : alu_result_vm;
        end
        // VIOTA, VID: compute a slice of the output and mask out the masked elements
        // VID re-uses the VIOTA datapath
        VIOTA, VID: begin
          // Mask the input vector
          // VID uses the same datapath of VIOTA, but with implicit input vector at '1
          masku_operand_alu_seq_m = (vinsn_issue.op == VID)
                                  ? '1 // VID mask does NOT modify the count
                                  : masku_operand_alu_seq
                                    & (masku_operand_m_seq | {NrLanes*DataWidth{vinsn_issue.vm}}); // VIOTA mask DOES modify the count

          // Compute output results on `ViotaParallelism 16-bit adders
          viota_res[0] = viota_acc_q;
          for (int i = 0; i < ViotaParallelism - 1; i++) begin
            viota_res[i+1] = viota_res[i] + masku_operand_alu_seq_m[in_ready_cnt_q[idx_width(NrLanes*DataWidth/ViotaParallelism)-1:0] * ViotaParallelism + i];
          end
          viota_acc = viota_res[ViotaParallelism-1] + masku_operand_alu_seq_m[in_ready_cnt_q[idx_width(NrLanes*DataWidth/ViotaParallelism)-1:0] * ViotaParallelism + ViotaParallelism - 1];

          // This datapath should be relativeley simple:
          // `ViotaParallelism bytes connected, in line, to output byte chunks
          // Multiple limited-width counters should help the synthesizer reduce wiring
          unique case (vinsn_issue.vtype.vsew)
            EW8: for (int i = 0; i < ViotaParallelism; i++) begin
              alu_result_vm_m[out_valid_cnt_q[idx_width(NrLanes*DataWidth/8/ViotaParallelism)-1:0]  * ViotaParallelism * 8  + i*8  +: 8]  = viota_res[i][7:0];
            end
            EW16: for (int i = 0; i < ViotaParallelism; i++) begin
              alu_result_vm_m[out_valid_cnt_q[idx_width(NrLanes*DataWidth/16/ViotaParallelism)-1:0] * ViotaParallelism * 16 + i*16 +: 16] = viota_res[i];
            end
            EW32: for (int i = 0; i < ViotaParallelism; i++) begin
              alu_result_vm_m[out_valid_cnt_q[idx_width(NrLanes*DataWidth/32/ViotaParallelism)-1:0] * ViotaParallelism * 32 + i*32 +: 32] = {{32{1'b0}}, viota_res[i]};
            end
            default: for (int i = 0; i < ViotaParallelism; i++) begin // EW64
              alu_result_vm_m[out_valid_cnt_q[idx_width(NrLanes*DataWidth/64/ViotaParallelism)-1:0] * ViotaParallelism * 64 + i*64 +: 64] = {{48{1'b0}}, viota_res[i]};
            end
          endcase

          // BE signal for VIOTA,VID
          unique case (vinsn_issue.vtype.vsew)
            EW8: for (int i = 0; i < ViotaParallelism; i++) begin
              be_viota_seq_d[out_valid_cnt_q[idx_width(NrLanes*DataWidth/8/ViotaParallelism)-1:0] * ViotaParallelism * 1 + 1*i +: 1] =
                {1{vinsn_issue.vm}} | {1{masku_operand_m_seq[in_m_ready_cnt_q[idx_width(NrLanes*DataWidth/ViotaParallelism)-1:0] * ViotaParallelism + i]}};
            end
            EW16: for (int i = 0; i < ViotaParallelism; i++) begin
              be_viota_seq_d[out_valid_cnt_q[idx_width(NrLanes*DataWidth/16/ViotaParallelism)-1:0] * ViotaParallelism * 2 + 2*i +: 2] =
                {2{vinsn_issue.vm}} | {2{masku_operand_m_seq[in_m_ready_cnt_q[idx_width(NrLanes*DataWidth/ViotaParallelism)-1:0] * ViotaParallelism + i]}};
            end
            EW32: for (int i = 0; i < ViotaParallelism; i++) begin
              be_viota_seq_d[out_valid_cnt_q[idx_width(NrLanes*DataWidth/32/ViotaParallelism)-1:0] * ViotaParallelism * 4 + 4*i +: 4] =
                {4{vinsn_issue.vm}} | {4{masku_operand_m_seq[in_m_ready_cnt_q[idx_width(NrLanes*DataWidth/ViotaParallelism)-1:0] * ViotaParallelism + i]}};
            end
            default: for (int i = 0; i < ViotaParallelism; i++) begin // EW64
              be_viota_seq_d[out_valid_cnt_q[idx_width(NrLanes*DataWidth/64/ViotaParallelism)-1:0] * ViotaParallelism * 8 + 8*i +: 8] =
                {8{vinsn_issue.vm}} | {8{masku_operand_m_seq[in_m_ready_cnt_q[idx_width(NrLanes*DataWidth/ViotaParallelism)-1:0] * ViotaParallelism + i]}};
            end
          endcase
        end
        // VRGATHER, VRGATHEREI16, VCOMPRESS get elements from the vd operand queue (not to complicate the ALU control)
        // Then, they just shuffle the operand in the correct place
        // This operation writes vsew-bit elements with vtype.vsew encoding
        // The vd source can have a different encoding (it gets deshuffled in the masku_operand stage)
        [VRGATHER:VCOMPRESS]: begin
          // Buffer for the current element
          logic [NrLanes*DataWidth-1:0] vrgat_res;
          // Buffer for the current element
          logic [DataWidth-1:0] vrgat_buf;

          // Extract the correct element. An out-of-range gather does not
          // issue a source request, so avoid indexing an absent operand.
          vrgat_res = '1; // Default assignment
          vrgat_buf = '0;
          if (!vrgat_idx_oor_q) begin
            unique case (vinsn_issue.vtype.vsew)
              EW8:  vrgat_buf[0 +: 8] = masku_operand_vd_seq[vrgat_req_idx_q[idx_width(NrLanes*ELENB/1)-1:0] * 8 +: 8];
              EW16: vrgat_buf[0 +: 16] = masku_operand_vd_seq[vrgat_req_idx_q[idx_width(NrLanes*ELENB/2)-1:0] * 16 +: 16];
              EW32: vrgat_buf[0 +: 32] = masku_operand_vd_seq[vrgat_req_idx_q[idx_width(NrLanes*ELENB/4)-1:0] * 32 +: 32];
              default: vrgat_buf[0 +: 64] = masku_operand_vd_seq[vrgat_req_idx_q[idx_width(NrLanes*ELENB/8)-1:0] * 64 +: 64];
            endcase
          end
          unique case (vinsn_issue.vtype.vsew)
            EW8:  vrgat_res[out_valid_cnt_q[idx_width(NrLanes*ELENB/1)-1:0] * 8 +: 8] = vrgat_buf[0 +: 8];
            EW16: vrgat_res[out_valid_cnt_q[idx_width(NrLanes*ELENB/2)-1:0] * 16 +: 16] = vrgat_buf[0 +: 16];
            EW32: vrgat_res[out_valid_cnt_q[idx_width(NrLanes*ELENB/4)-1:0] * 32 +: 32] = vrgat_buf[0 +: 32];
            default: vrgat_res[out_valid_cnt_q[idx_width(NrLanes*ELENB/8)-1:0] * 64 +: 64] = vrgat_buf[0 +: 64];
          endcase

          // BE signal for VRGATHER
		  unique case (vinsn_issue.vtype.vsew)
            EW8: begin
              vrgat_m_seq_bit = masku_operand_m_seq[in_m_ready_cnt_q[idx_width(NrLanes*DataWidth)-1:0]];
              be_vrgat_seq_d[out_valid_cnt_q[idx_width(NrLanes*DataWidth/8)-1:0] * 1 +: 1] =
                {1{vinsn_issue.vm}} | {1{vrgat_m_seq_bit}};
            end
            EW16: begin
              vrgat_m_seq_bit = masku_operand_m_seq[in_m_ready_cnt_q[idx_width(NrLanes*DataWidth)-1:0]];
              be_vrgat_seq_d[out_valid_cnt_q[idx_width(NrLanes*DataWidth/16)-1:0] * 2 +: 2] =
                {2{vinsn_issue.vm}} | {2{vrgat_m_seq_bit}};
            end
            EW32: begin
              vrgat_m_seq_bit = masku_operand_m_seq[in_m_ready_cnt_q[idx_width(NrLanes*DataWidth)-1:0]];
              be_vrgat_seq_d[out_valid_cnt_q[idx_width(NrLanes*DataWidth/32)-1:0] * 4 +: 4] =
                {4{vinsn_issue.vm}} | {4{vrgat_m_seq_bit}};
            end
            default: begin // EW64
              vrgat_m_seq_bit = masku_operand_m_seq[in_m_ready_cnt_q[idx_width(NrLanes*DataWidth)-1:0]];
              be_vrgat_seq_d[out_valid_cnt_q[idx_width(NrLanes*DataWidth/64)-1:0] * 8 +: 8] =
                {8{vinsn_issue.vm}} | {8{vrgat_m_seq_bit}};
            end
          endcase

          alu_result_vm_m = vrgat_res;
        end
        // VCPOP, VFIRST: mask the current slice and feed the popc or lzc unit
        [VCPOP:VFIRST] : begin
          vcpop_operand = (!vinsn_issue.vm) ? masku_operand_alu_seq & masku_operand_m_seq : masku_operand_alu_seq;
        end
        default:;
      endcase

      // A mask destination that reads old vd must preserve every bit outside
      // the architectural update window.  The result queue combines its
      // background with alu_result_vm_m using AND, hence one is the identity.
      if (vinsn_issue.use_vd_op &&
          vinsn_issue.op inside {
            [VMFEQ:VMFGE], [VMSEQ:VMSGT], [VMADC:VMSBC],
            [VMSBF:VMSIF], [VMANDNOT:VMXNOR]
          }) begin
        alu_result_vm_m |= ~result_queue_active_mask_seq;
      end
    end

    // Shuffle the sequential result with vtype.vsew encoding
    for (int b = 0; b < (NrLanes*StrbWidth); b++) begin
      automatic int shuffle_byte              = shuffle_index(b, NrLanes, vinsn_issue.vtype.vsew);
      alu_result_vm_shuf[8*shuffle_byte +: 8] = alu_result_vm_m[8*b +: 8];
    end

    // Shuffle the VIOTA, VID, VRGATHER, VCOMPRESS byte enable signal
    be_masku_alu_shuf = '0;
    for (int b = 0; b < (NrLanes*StrbWidth); b++) begin
      automatic int shuffle_byte  = shuffle_index(b, NrLanes, vinsn_issue.vtype.vsew);
      be_masku_alu_shuf[shuffle_byte] = vinsn_issue.op inside {VRGATHER,VRGATHEREI16} ? be_vrgat_seq_d[b] : be_viota_seq_d[b];
    end

    // Simplify layout handling
    alu_result = alu_result_vm_shuf;

    // Limit the mask/old-vd selection to active elements in the current result word. Without
    // this gate, set bits beyond vl in v0 are ORed into an undisturbed mask destination.
    // Prepare the background data with vtype.vsew encoding
    result_queue_mask_seq = vinsn_issue.op inside {[VIOTA:VID], [VRGATHER:VCOMPRESS]} ? '0 : masku_operand_m_seq | {NrLanes*DataWidth{vinsn_issue.vm}} | {NrLanes*DataWidth{vinsn_issue.op inside {[VMADC:VMSBC]}}};
    if (vinsn_issue.use_vd_op) result_queue_mask_seq &= result_queue_active_mask_seq;
    background_data_init_seq = masku_operand_vd_seq | result_queue_mask_seq;
    background_data_init_shuf = '0;
    for (int b = 0; b < (NrLanes*StrbWidth); b++) begin
      automatic int shuffle_byte                     = shuffle_index(b, NrLanes, vinsn_issue.vtype.vsew);
      background_data_init_shuf[8*shuffle_byte +: 8] = background_data_init_seq[8*b +: 8];
    end

  /////////////////
  //  Mask unit  //
  /////////////////

    // Maintain state
    vinsn_queue_d    = vinsn_queue_q;
    read_cnt_d       = read_cnt_q;
    issue_cnt_d      = issue_cnt_q;
    processing_cnt_d = processing_cnt_q;
    commit_cnt_d     = commit_cnt_q;

    mask_pnt_d     = mask_pnt_q;
    vrf_pnt_d      = vrf_pnt_q;

    popcount_d        = popcount_q;
    vfirst_count_d    = vfirst_count_q;
    vfirst_found_d    = vfirst_found_q;

    mask_queue_d           = mask_queue_q;
    mask_queue_valid_d     = mask_queue_valid_q;
    mask_queue_target_d    = mask_queue_target_q;
    mask_queue_write_pnt_d = mask_queue_write_pnt_q;
    mask_queue_read_pnt_d  = mask_queue_read_pnt_q;
    mask_queue_cnt_d       = mask_queue_cnt_q;

    result_queue_d           = result_queue_q;
    result_queue_valid_d     = result_queue_valid_q;
    result_queue_write_pnt_d = result_queue_write_pnt_q;
    result_queue_read_pnt_d  = result_queue_read_pnt_q;
    result_queue_cnt_d       = result_queue_cnt_q;

    result_final_gnt_d = result_final_gnt_q;

    trimmed_stride = pe_req_i.stride;

    // Predication strobes are produced one full cross-lane data word at a
    // time.  Preserve the position of vstart inside that first data word.
    unique case (pe_req_i.vtype.vsew)
      EW8:    mask_aligned_vstart = (pe_req_i.vstart >> $clog2(NrLanes * 8))
                                  << $clog2(NrLanes * 8);
      EW16:   mask_aligned_vstart = (pe_req_i.vstart >> $clog2(NrLanes * 4))
                                  << $clog2(NrLanes * 4);
      EW32:   mask_aligned_vstart = (pe_req_i.vstart >> $clog2(NrLanes * 2))
                                  << $clog2(NrLanes * 2);
      default: mask_aligned_vstart = (pe_req_i.vstart >> $clog2(NrLanes))
                                   << $clog2(NrLanes);
    endcase

    out_vrf_word_valid = 1'b0;
    out_scalar_valid   = 1'b0;

    // Vector instructions currently running
    vinsn_running_d = vinsn_running_q & pe_vinsn_running_i;

    // Mask the response, by default
    pe_resp = '0;

    // We are not ready, by default
    masku_operand_alu_ready    = '0;
    masku_operand_m_ready      = '0;
    masku_operand_vd_ready     = '0;

    // Unmasked non-MASKU requests do not consume MASKU state. A request that
    // does consume it is ready only when both the instruction context and all
    // mask words from the preceding context have drained.
    pe_req_ready_o = (pe_req_i.vm && pe_req_i.vfu != VFU_MaskUnit) ||
                     (!vinsn_queue_full && mask_queue_empty &&
                      !vinsn_running_q[pe_req_i.id]);

    // scalar path signals
    result_scalar_d       = result_scalar_o;
    result_scalar_valid_d = result_scalar_valid_o;

    // Don't handshake the inputs
    in_ready_cnt_en   = 1'b0;
    in_m_ready_cnt_en = 1'b0;
    out_valid_cnt_en  = 1'b0;

    // Result queue background data
    for (int unsigned lane = 0; lane < NrLanes; lane++)
      result_queue_background_data[lane] = result_queue_q[result_queue_write_pnt_q][lane].wdata;

    // Maintain state
    delta_elm_d = delta_elm_q;
    in_ready_threshold_d   = in_ready_threshold_q;
    in_m_ready_threshold_d = in_m_ready_threshold_q;
    out_valid_threshold_d  = out_valid_threshold_q;

    in_ready_cnt_clr   = 1'b0;
    in_m_ready_cnt_clr = 1'b0;
    out_valid_cnt_clr  = 1'b0;
    iteration_cnt_clr  = 1'b0;

    ////////////////////////////
    //  Predicated execution  //
    ////////////////////////////

    // Instructions that run in other units, but need mask strobes for predicated execution

    // Is there space in the result queue?
    if (!mask_queue_full) begin
      // Copy data from the mask operands into the mask queue
      for (int vrf_seq_byte = 0; vrf_seq_byte < NrLanes*StrbWidth; vrf_seq_byte++) begin
        // Map vrf_seq_byte to the corresponding byte in the VRF word.
        automatic int vrf_byte = shuffle_index(vrf_seq_byte, NrLanes, vinsn_issue.vtype.vsew);

        // At which lane, and what is the byte offset in that lane, of the byte vrf_byte?
        // NOTE: This does not work if the number of lanes is not a power of two.
        // If that is needed, the following two lines must be changed accordingly.
        automatic int vrf_lane   = vrf_byte >> $clog2(StrbWidth);
        automatic int vrf_offset = vrf_byte[idx_width(StrbWidth)-1:0];

        // The VRF pointer can be broken into a byte offset, and a bit offset
        automatic int vrf_pnt_byte_offset = mask_pnt_q >> $clog2(StrbWidth);
        automatic int vrf_pnt_bit_offset  = mask_pnt_q[idx_width(StrbWidth)-1:0];

        // A single bit from the mask operands can be used several times, depending on the eew.
        automatic int mask_seq_bit  = vrf_seq_byte >> int'(vinsn_issue.vtype.vsew);
        automatic int mask_seq_byte = (mask_seq_bit >> $clog2(StrbWidth)) + vrf_pnt_byte_offset;
        // Shuffle this source byte
        automatic int mask_byte     = shuffle_index(mask_seq_byte, NrLanes, vinsn_issue.eew_vmask);
        // Account for the bit offset
        automatic int mask_bit = (mask_byte << $clog2(StrbWidth)) +
          mask_seq_bit[idx_width(StrbWidth)-1:0] + vrf_pnt_bit_offset;

        // At which lane, and what is the bit offset in that lane, of the mask operand from
        // mask_seq_bit?
        automatic int mask_lane   = mask_bit >> idx_width(DataWidth);
        automatic int mask_offset = mask_bit[idx_width(DataWidth)-1:0];

        // Copy the mask operand
        mask_queue_d[mask_queue_write_pnt_q][vrf_lane][vrf_offset] =
          masku_operand_m[mask_lane][mask_offset];
      end

      // Is there an instruction ready to be issued?
      if (vinsn_issue_valid && ((vinsn_issue.vfu != VFU_MaskUnit) || (vinsn_issue.op inside {[VMADC:VMSBC]}))) begin
        // Is there place in the mask queue to write the mask operands?
        // Did we receive the mask bits on the MaskM channel?
        if (!vinsn_issue.vm && &masku_operand_m_valid) begin
          // Account for the used operands
          mask_pnt_d += NrLanes * (1 << (int'(EW64) - vinsn_issue.vtype.vsew));

          // Increment result queue pointers and counters
          mask_queue_cnt_d += 1;
          if (mask_queue_write_pnt_q == MaskQueueDepth-1)
            mask_queue_write_pnt_d = '0;
          else
            mask_queue_write_pnt_d = mask_queue_write_pnt_q + 1;

          // Account for the operands that were issued
          read_cnt_d = read_cnt_q - NrLanes * (1 << (int'(EW64) - vinsn_issue.vtype.vsew));
          if (read_cnt_q < NrLanes * (1 << (int'(EW64) - vinsn_issue.vtype.vsew)))
            read_cnt_d = '0;

          // Trigger the request signal
          mask_queue_valid_d[mask_queue_write_pnt_q] = {NrLanes{1'b1}};
          mask_queue_target_d[mask_queue_write_pnt_q] = vinsn_issue.vfu;

          // Are there lanes with no valid elements?
          // If so, mute their request signal
          // VMADC/VMSBC are balanced across lanes before MASKU compresses the
          // per-lane carry bits.  Keep dummy tail lanes valid so every lane
          // produces the same number of beats; inactive result bits are
          // discarded by result_queue_active_mask_seq.
          if (read_cnt_q < NrLanes &&
              !(vinsn_issue.op inside {[VMADC:VMSBC]}))
            mask_queue_valid_d[mask_queue_write_pnt_q] = (1 << read_cnt_q) - 1;

          // Consumed all valid bytes from the lane operands
          if (mask_pnt_d == NrLanes*DataWidth || read_cnt_d == '0) begin
            // Request another beat
            masku_operand_m_ready = '1;
            // Reset the pointer
            mask_pnt_d = '0;
          end
        end
      end
    end

    // Send Mask Operands to the VFUs
    for (int lane = 0; lane < NrLanes; lane++) begin: send_operand
      mask_valid_o[lane] = mask_queue_valid_q[mask_queue_read_pnt_q][lane];
      mask_o[lane]       = mask_queue_q[mask_queue_read_pnt_q][lane];
      // Received a grant from the VFUs.
      // The VLDU and the VSTU acknowledge all the operands at once.
      // Only accept the acknowledgement from the lanes if the current instruction is executing there.
      // Deactivate the request, but do not bump the pointers for now.
      if ((lane_mask_ready_i[lane] && mask_valid_o[lane] &&
           (mask_target_fu_o inside {VFU_Alu, VFU_MFpu, VFU_MaskUnit})) ||
          (vldu_mask_ready_i && mask_target_fu_o == VFU_LoadUnit) ||
          (vstu_mask_ready_i && mask_target_fu_o == VFU_StoreUnit) ||
          (sldu_mask_ready_i && mask_target_fu_o == VFU_SlideUnit)) begin
        mask_queue_valid_d[mask_queue_read_pnt_q][lane] = 1'b0;
        mask_queue_d[mask_queue_read_pnt_q][lane]       = '0;
      end
    end: send_operand

    // Is this operand going to the lanes?
    mask_target_fu_o  = mask_queue_empty ? VFU_None :
                                           mask_queue_target_q[mask_queue_read_pnt_q];
    mask_valid_lane_o = mask_target_fu_o inside {VFU_Alu, VFU_MFpu, VFU_MaskUnit};

    // All lanes accepted the VRF request
    if (!(|mask_queue_valid_d[mask_queue_read_pnt_q])) begin
      // There is something waiting to be written
      if (!mask_queue_empty) begin
        // Increment the read pointer
        if (mask_queue_read_pnt_q == MaskQueueDepth-1)
          mask_queue_read_pnt_d = 0;
        else
          mask_queue_read_pnt_d = mask_queue_read_pnt_q + 1;

        // Reset the queue
        mask_queue_d[mask_queue_read_pnt_q] = '0;
        mask_queue_target_d[mask_queue_read_pnt_q] = VFU_None;

        // Decrement the counter of mask operands waiting to be used
        mask_queue_cnt_d -= 1;

        // Decrement the counter of remaining vector elements waiting to be used
        if (vldu_mask_ready_i || vstu_mask_ready_i || sldu_mask_ready_i || vinsn_issue.vm || (vinsn_issue.vfu != VFU_MaskUnit)) begin
          commit_cnt_d = commit_cnt_q - NrLanes * (1 << (int'(EW64) - vinsn_commit.vtype.vsew));
          if (commit_cnt_q < (NrLanes * (1 << (int'(EW64) - vinsn_commit.vtype.vsew))))
            commit_cnt_d = '0;
        end
      end
    end

    ////////////////////////
    //  Index generation  //
    ////////////////////////

    // VRGATHER, VCOMPRESS require index generation and ad-hoc operand requesters
    // The indices come from the VALU, while the operands will pass through the Vd operand queue (MaskB)
    // This implementation is simple and unoptimized:
    // We ask all the lanes in parallel for a precise index, and we will get a balanced payload from them.
    // Only one element of the payload is important, the rest is discarded.
    // This can be easily optimized by asking only the correct lane and by handling unbalanced payloads.

    vrgat_cnt_d = vrgat_cnt_q;

    vrgat_req_idx_d = '0;
    vrgat_idx_fifo_push = 1'b0;
    vrgat_req_fifo_push = 1'b0;

    // Track if an index overflow occurred past the 16 sampled bits
    vrgat_idx_overflow = 1'b0;

    // Track if the index is out of range
    vrgat_idx_oor_d = 1'b0;

    vcompress_bit = 1'b0;

    vrgat_req_is_last_req_d = 1'b0;
    vrgat_req_no_data_d = 1'b0;

    vcompress_last_idx_d = 1'b0;

    vcompress_issue_end_d = vcompress_issue_end_q;

    vcompress_cnt_d = vcompress_cnt_q;

    // Control counters in the pre-issue phase
    if (vinsn_issue_valid) begin
      unique case (vinsn_issue.op)
        VCOMPRESS: begin
          // Select the current enable bit
          vcompress_bit = masku_operand_alu_seq[vrgat_cnt_q[idx_width(NrLanes*DataWidth)-1:0]];
          // Select the current index
          vrgat_req_idx_d = vrgat_cnt_q;
          if (&masku_operand_alu_valid && ~vrgat_idx_fifo_full &&
              (vcompress_bit || (vrgat_cnt_q == (vinsn_issue.vl - 1))
               ? ~vrgat_req_fifo_full : 1'b1)) begin
            // Check vrgat_m_seq_bit: we can use this since VRGATHER and VCOMPRESS are mutually exclusive
            // and the masku_operand_m is used in different ways
            if (vcompress_bit) begin
              // Push this index and address if the fifos are free and if the mask bit is set
              vrgat_idx_fifo_push = 1'b1;
              vrgat_req_fifo_push = 1'b1;
              // Increase the number of elements to write
              vcompress_cnt_d = vcompress_cnt_q + 1;
            end else if (vrgat_cnt_q == (vinsn_issue.vl - 1)) begin
              // Preserve stream order when the final mask bit is zero.  This
              // pair of sentinels ends both the MASKU result stream and the
              // lane request stream without reading a nonexistent source.
              vrgat_idx_fifo_push = 1'b1;
              vrgat_idx_oor_d = 1'b1;
              vrgat_req_fifo_push = 1'b1;
              vrgat_req_no_data_d = 1'b1;
            end
          end
        end
        VRGATHER,
        VRGATHEREI16: begin
          // Find the maximum vector length. VLMAX = LMUL * VLEN / SEW.
          automatic int unsigned vlmax = (VLEN/8) >> vinsn_issue.vtype.vsew;
          unique case (vinsn_issue.vtype.vlmul)
            LMUL_1  : vlmax <<= 0;
            LMUL_2  : vlmax <<= 1;
            LMUL_4  : vlmax <<= 2;
            LMUL_8  : vlmax <<= 3;
            // Fractional LMUL
            LMUL_1_2: vlmax >>= 1;
            LMUL_1_4: vlmax >>= 2;
            LMUL_1_8: vlmax >>= 3;
            default:;
          endcase

          // VRGATHER: treat the index as a vtype.vsew-bit number
          if (vinsn_issue.op == VRGATHER) begin
            unique case (vinsn_issue.vtype.vsew)
              EW8: begin
                vrgat_req_idx_d = {8'b0, masku_operand_alu_seq[vrgat_cnt_q[idx_width(NrLanes*DataWidth/8)-1:0] * 8 +: 8]};
              end
              EW16: begin
                vrgat_req_idx_d = masku_operand_alu_seq[vrgat_cnt_q[idx_width(NrLanes*DataWidth/16)-1:0] * 16 +: 16];
              end
              EW32: begin
                vrgat_req_idx_d = masku_operand_alu_seq[vrgat_cnt_q[idx_width(NrLanes*DataWidth/32)-1:0] * 32 +: 16];
                vrgat_idx_overflow = |masku_operand_alu_seq[vrgat_cnt_q[idx_width(NrLanes*DataWidth/32)-1:0] * 32 + 16 +: 32 - 16];
              end
              default: begin // EW64
                vrgat_req_idx_d = masku_operand_alu_seq[vrgat_cnt_q[idx_width(NrLanes*DataWidth/64)-1:0] * 64 +: 16];
                vrgat_idx_overflow = |masku_operand_alu_seq[vrgat_cnt_q[idx_width(NrLanes*DataWidth/64)-1:0] * 64 + 16 +: 64 - 16];
              end
            endcase
          end else begin
            // VRGATHEREI16: treat the index as a 16-bit number
            vrgat_req_idx_d = masku_operand_alu_seq[vrgat_cnt_q[idx_width(NrLanes*DataWidth/16)-1:0] * 16 +: 16];
          end

          // VRGATHER.v[x|i] splats one scalar into Vd. The scalar is not truncated
          if (vinsn_issue.use_scalar_op) begin
            vrgat_req_idx_d = vinsn_issue.scalar_op[15:0];
            vrgat_idx_overflow = |vinsn_issue.scalar_op[16 +: ELEN - 16];
          end

          vrgat_idx_oor_d = (vrgat_req_idx_d >= vlmax) | vrgat_idx_overflow;

          // Proceed if the FIFOs are not full
          if (&masku_operand_alu_valid && ~vrgat_idx_fifo_full && ~vrgat_req_fifo_full) begin
            // Push the index no matter what
            vrgat_idx_fifo_push = 1'b1;
            // Request to the lanes only if the index is within range
            if (!vrgat_idx_oor_d) begin
              vrgat_req_fifo_push = 1'b1;
            end else if (vrgat_cnt_q == (vinsn_issue.vl - 1)) begin
              // The result path can synthesize zero for an out-of-range index,
              // but the lanes still need an explicit end-of-stream token.
              vrgat_req_fifo_push = 1'b1;
              vrgat_req_no_data_d = 1'b1;
            end
          end
        end
        default:;
      endcase
    end

    // Handle the counters
    if (vinsn_issue.op inside {[VRGATHER:VCOMPRESS]} && &masku_operand_alu_valid &&
        (vrgat_idx_fifo_push ||
         ((vinsn_issue.op == VCOMPRESS) && ~vrgat_idx_fifo_full &&
          ~vcompress_bit && (vrgat_cnt_q != (vinsn_issue.vl - 1))))) begin
      // Count up if we could process the current input chunk
      vrgat_cnt_d = vrgat_cnt_q + 1;
      in_ready_cnt_en = 1'b1;

      // We either finished or we need to ask a new idx operand
      if ((in_ready_cnt_q[idx_width(NrLanes*DataWidth)-1:0] == in_ready_threshold_q) || (vrgat_cnt_q == (vinsn_issue.vl - 1))) begin
        in_ready_cnt_clr = 1'b1;
        masku_operand_alu_ready = '1;
        // Check if we are over
        if (vrgat_cnt_q == (vinsn_issue.vl - 1)) begin
          vrgat_cnt_d = '0;
          vcompress_last_idx_d = (vinsn_issue.op == VCOMPRESS);
          // End of the pre-issue phase
          vrgat_req_is_last_req_d = 1'b1;
        end
      end
    end

    ///////////////////////
    // MASKU ALU Control //
    ///////////////////////

    // Instructions that natively run in the MASKU

    // The main data packets come from the lanes' ALUs.
    // Also, mask- and tail-undisturbed policies are implemented by fetching the destination register,
    // which is the default value of the result queue.

    // Almost all the operations are time multiplexed. Moreover, some operations (e.g., VIOTA) work on
    // different input and output data widths, meaning that the input ready and the final output valid
    // are not always synchronized.

    vrgat_idx_fifo_pop = 1'b0;

    // How many elements {VIOTA|VID|VRGATHER|VRGATHEREI16} are writing to each lane
    // VCOMPRESS follows its own counter
    effective_elm_cnt = vinsn_issue.op == VCOMPRESS ? vcompress_cnt_q : processing_cnt_q;
    elm_per_lane = effective_elm_cnt / NrLanes;
    if ((effective_elm_cnt / NrLanes) > 4'b1000)
      elm_per_lane = 4'b1000;
    for (int l = 0; l < NrLanes; l++) additional_elm[l] = effective_elm_cnt[idx_width(NrLanes)-1:0] > l;

    // Default operand queue assignment
    for (int unsigned lane = 0; lane < NrLanes; lane++) begin
      result_queue_d[result_queue_write_pnt_q][lane] = '{
        wdata: result_queue_q[result_queue_write_pnt_q][lane].wdata, // Retain the last-cycle's data
		// VIOTA, VID generate a non-mask vector and should comply with undisturbed policy
        // This means that we can use the byte-enable signal
        be   : vinsn_issue.op inside {[VIOTA:VID],[VRGATHER:VCOMPRESS]}
               ? be(elm_per_lane + additional_elm[lane], vinsn_issue.vtype.vsew) & be_masku_alu_shuf[lane*StrbWidth +: StrbWidth]
               : '1,
        addr : vaddr(vinsn_issue.vd, NrLanes, VLEN) + iteration_cnt_q,
        id   : vinsn_issue.id
      };
    end

    // Is there an instruction ready to be issued?
    if (vinsn_issue_valid && vinsn_issue.op inside {[VMFEQ:VCOMPRESS]}) begin
      // Compute one slice if we can write and the necessary inputs are valid
      // VID does not require any operand, while VRGATHER/VCOMPRESS's ALU operand is just preprocessed to get the indices.
      // Therefore, VRGATHER/VCOMPRESS's operand are special. Only the vd operand works in the MASKU ALU.
      if (!result_queue_full && (&masku_operand_alu_valid || vinsn_issue.op inside {VID,[VRGATHER:VCOMPRESS]})
                             && (&masku_operand_vd_valid ||
                                 ((vinsn_issue.op inside {VRGATHER, VRGATHEREI16}) &&
                                  !vrgat_idx_fifo_empty && vrgat_idx_oor_q) ||
                                 ((vinsn_issue.op == VCOMPRESS) &&
                                  vcompress_last_idx_q && vrgat_idx_oor_q) ||
                                 (!vinsn_issue.use_vd_op && !(vinsn_issue.op inside {[VRGATHER:VCOMPRESS]})))
                             && (&masku_operand_m_valid   ||
                                 (vinsn_issue.vm &&
                                  !(vinsn_issue.op inside {[VMANDNOT:VMXNOR]})) ||
                                 vinsn_issue.op inside {[VMADC:VMSBC]})
                             && (!vrgat_idx_fifo_empty    || !(vinsn_issue.op inside {[VRGATHER:VCOMPRESS]}))) begin

        if ((vinsn_issue.op == VCOMPRESS) && vcompress_last_idx_q && vrgat_idx_oor_q) begin
          // A zero final mask bit has no source element to fetch. Its FIFO
          // position proves that all selected indices precede this point. If
          // those indices produced a partial output word, publish it before
          // ending; an empty selection produces no VRF write at all.
          vrgat_idx_fifo_pop = 1'b1;
          vcompress_issue_end_d = 1'b1;
          if (out_valid_cnt_q != '0) begin
            out_valid_cnt_clr = 1'b1;
            out_vrf_word_valid = 1'b1;
          end
        end else begin
          // Write the result queue on the background data - either vd or the previous result
          // The mask vector writes at 1 (tail-agnostic ok value) both the background body
          // elements that will be written by the MASKU ALU and the tail elements.
          for (int unsigned lane = 0; lane < NrLanes; lane++) begin
            result_queue_background_data[lane] = (out_valid_cnt_q != '0)
                                               ? result_queue_q[result_queue_write_pnt_q][lane].wdata
                                               : vinsn_issue.op inside {[VIOTA:VID], [VRGATHER:VCOMPRESS]} ? '1 : background_data_init_shuf[lane*DataWidth +: DataWidth];
          end
          for (int unsigned lane = 0; lane < NrLanes; lane++) begin
            // The alu_result has all the bits at 1 except for the portion of bits to write.
            // The masking is already applied in the MASKU ALU.
            result_queue_d[result_queue_write_pnt_q][lane].wdata = result_queue_background_data[lane] & alu_result[lane];
          end
          // Write the scalar accumulator
          popcount_d = popcount_q + popcount;
          if (vinsn_issue.op == VFIRST && !vfirst_found_q) begin
            vfirst_count_d = vfirst_count_q +
                (vfirst_empty ? VfirstParallelism : vfirst_count);
            vfirst_found_d = !vfirst_empty;
          end

          // Bump MASKU ALU state
          found_one_d = found_one;
          viota_acc_d = viota_acc;
          vrf_pnt_d   = vrf_pnt_q + delta_elm_q;
          if (vinsn_issue.op inside {[VRGATHER:VCOMPRESS]}) vrgat_idx_fifo_pop = 1'b1;

          // Increment the input, input-mask, and output slice counters
          if (!(vinsn_issue.op inside {[VRGATHER:VCOMPRESS]})) in_ready_cnt_en = 1'b1;
          if (!(vinsn_issue.op inside {[VMADC:VMSBC]})) in_m_ready_cnt_en = 1'b1;
          out_valid_cnt_en  = 1'b1;

          // Account for the elements that have been processed
          issue_cnt_d = issue_cnt_q - delta_elm_q;
          if (issue_cnt_q < delta_elm_q)
            issue_cnt_d = '0;

          // Request new input (by completing ready-valid handshake) once all slices have been processed
          // Alu input is accessed in different widths
          // VRGATHER and VCOMPRESS handle the ALU operand for the index generation before the MASKU ALU gets the operands
          if (((in_ready_cnt_q == in_ready_threshold_q) || (issue_cnt_d == '0)) &&
              !(vinsn_issue.op inside {[VRGATHER:VCOMPRESS]})) begin
            in_ready_cnt_clr = 1'b1;
            if (vinsn_issue.op != VID) begin
              masku_operand_alu_ready = '1;
            end
          end
          // Mask is always accessed at bit level
          // VMADC, VMSBC handle masks in the mask queue
          if (((in_m_ready_cnt_q == in_m_ready_threshold_q) || (issue_cnt_d == '0)) &&
              !(vinsn_issue.op inside {[VMADC:VMSBC]})) begin
            in_m_ready_cnt_clr = 1'b1;
            if (!vinsn_issue.vm ||
                vinsn_issue.op inside {[VMANDNOT:VMXNOR]}) begin
              masku_operand_m_ready = '1;
            end
          end

          // This vcompress has written less than vl elements
          if (vinsn_issue.op == VCOMPRESS)
            vcompress_issue_end_d = vcompress_last_idx_q;
          // Write to the result queue if the entry is full or if this is the last output
          // if this is the last output slice of the vector.
          // Also, handshake the vd input, which follows the output.
          if (vinsn_issue.op inside {[VRGATHER:VCOMPRESS]}) masku_operand_vd_ready = '1;
          if ((out_valid_cnt_q == out_valid_threshold_q) || (issue_cnt_d == '0) ||
              ((vinsn_issue.op == VCOMPRESS) && vcompress_last_idx_q)) begin
            out_valid_cnt_clr = 1'b1;
            // Handshake vd input
            if (vinsn_issue.use_vd_op) begin
              masku_operand_vd_ready = '1;
            end
            // Assert valid result queue output
            out_vrf_word_valid = !vd_scalar(vinsn_issue.op);
          end

          // Complete scalar mask operations only after all requested operand words
          // have been consumed.  In particular, VFIRST must not leave words from
          // its early match in AluB or MaskM for the following instruction.
          if (issue_cnt_d == '0) begin
            // Assert valid scalar output
            out_scalar_valid = vd_scalar(vinsn_issue.op);
          end

          // Have we finished insn execution? Clear MASKU ALU state
          if (issue_cnt_d == '0) begin
            be_viota_seq_d = '1; // Default: write
            be_vrgat_seq_d = '1; // Default: write
            viota_acc_d    = '0;
            found_one_d    = '0;
          end
        end
      end
    end

    // Write VRF words to the result queue
    if (out_vrf_word_valid) begin
      // The compression pointer addresses bits within one MASKU result word.
      // Start the next result word at bit zero after publishing this one.
      vrf_pnt_d = '0;

      // Write to the lanes
      result_queue_valid_d[result_queue_write_pnt_q] = {NrLanes{1'b1}};

      // Increment result queue pointers and counters
      result_queue_cnt_d += 1;
      result_queue_write_pnt_d = result_queue_write_pnt_q + 1;
      if (result_queue_write_pnt_q == ResultQueueDepth-1) begin
        result_queue_write_pnt_d = '0;
      end

      // Clear MASKU ALU state
      be_viota_seq_d = '1;
      be_vrgat_seq_d = '1;

      // Account for the written results
      // VIOTA and VID do not write bits!
      processing_cnt_d = vinsn_issue.op inside {[VIOTA:VID], [VRGATHER:VRGATHEREI16]} ? processing_cnt_q - ((NrLanes * DataWidth / 8) >> vinsn_issue.vtype.vsew) : processing_cnt_q - NrLanes * DataWidth;
      // Account for the written results by VCOMPRESS
      if (vinsn_issue.op == VCOMPRESS) begin
        if (vcompress_cnt_d < ((NrLanes * DataWidth / 8) >> vinsn_issue.vtype.vsew))
          vcompress_cnt_d = '0;
        else
          vcompress_cnt_d = vcompress_cnt_d -
              ((NrLanes * DataWidth / 8) >> vinsn_issue.vtype.vsew);
      end
    end

    // The scalar result has been sent to and acknowledged by the dispatcher
    if (out_scalar_valid) begin
      result_scalar_d = (vinsn_issue.op == VCPOP) ? popcount_d :
                        (vfirst_found_d ? vfirst_count_d : elen_t'(-1));
      result_scalar_valid_d = '1;

      // The instruction is over
      issue_cnt_d       = '0;
      processing_cnt_d  = '0;
      commit_cnt_d      = '0;
    end

    // Finished issuing results
    if (vinsn_issue_valid && (
          ((vinsn_issue.vm || vinsn_issue.vfu == VFU_MaskUnit) && issue_cnt_d == '0) ||
          ((vinsn_issue.op == VCOMPRESS) && vcompress_issue_end_q) ||
          (!(vinsn_issue.vm || vinsn_issue.vfu == VFU_MaskUnit) && read_cnt_d  == '0))) begin
      // The instruction finished its issue phase
      vinsn_queue_d.issue_cnt -= 1;
    end

    //////////////
    //  Commit  //
    //////////////

    for (int lane = 0; lane < NrLanes; lane++) begin: result_write
      masku_result_req_o[lane]   = result_queue_valid_q[result_queue_read_pnt_q][lane];
      masku_result_addr_o[lane]  = result_queue_q[result_queue_read_pnt_q][lane].addr;
      masku_result_id_o[lane]    = result_queue_q[result_queue_read_pnt_q][lane].id;
      masku_result_wdata_o[lane] = result_queue_q[result_queue_read_pnt_q][lane].wdata;
      masku_result_be_o[lane]    = result_queue_q[result_queue_read_pnt_q][lane].be;

      // Update the final gnt vector
      result_final_gnt_d[lane] |= masku_result_final_gnt_i[lane];

      // Received a grant from the VRF.
      // Deactivate the request, but do not bump the pointers for now.
      if (masku_result_req_o[lane] && masku_result_gnt_i[lane]) begin
        result_queue_valid_d[result_queue_read_pnt_q][lane] = 1'b0;
        result_queue_d[result_queue_read_pnt_q][lane]       = '0;
        // Reset the final gnt vector since we are now waiting for another final gnt
        result_final_gnt_d[lane] = 1'b0;
      end
    end: result_write

    // All lanes accepted the VRF request
    if (!(|result_queue_valid_d[result_queue_read_pnt_q]) &&
      (&result_final_gnt_d || (commit_cnt_q > (NrLanes * DataWidth)))) begin
      // There is something waiting to be written
      if (!result_queue_empty) begin
        // Increment the read pointer
        if (result_queue_read_pnt_q == ResultQueueDepth-1)
          result_queue_read_pnt_d = 0;
        else
          result_queue_read_pnt_d = result_queue_read_pnt_q + 1;

        // Decrement the counter of results waiting to be written
        result_queue_cnt_d -= 1;

        // Reset the queue
        result_queue_d[result_queue_read_pnt_q] = '0;

        // Decrement the counter of remaining vector elements waiting to be written
        if (!(vinsn_commit.op inside {VSE})) begin
          if (vinsn_commit.op inside {[VIOTA:VID],[VRGATHER:VCOMPRESS]}) begin
            commit_cnt_d = commit_cnt_q - ((NrLanes * DataWidth / 8) >> unsigned'(vinsn_commit.vtype.vsew));
            if (commit_cnt_q < ((NrLanes * DataWidth / 8) >> unsigned'(vinsn_commit.vtype.vsew)))
              commit_cnt_d = '0;
          end else begin
            commit_cnt_d = commit_cnt_q - NrLanes * DataWidth;
            if (commit_cnt_q < (NrLanes * DataWidth))
              commit_cnt_d = '0;
          end
        end
      end
    end

    // Finished committing the results of a vector instruction
    if (vinsn_commit_valid && ((commit_cnt_d == '0) ||
        ((vinsn_commit.op == VCOMPRESS) &&
         !(|result_queue_valid_q[result_queue_read_pnt_q]) && vcompress_issue_end_q))) begin
      // Clear the iteration counter
      out_valid_cnt_clr = 1'b1;

      // Clear the vrf pointer for comparisons
      vrf_pnt_d = '0;

      // Clear the vcompress issue-end indicator
      vcompress_cnt_d = '0;

      // Clear the iteration counter
      iteration_cnt_clr = 1'b1;

      if (&result_final_gnt_d || vd_scalar(vinsn_commit.op) ||
          vinsn_commit.vfu != VFU_MaskUnit ||
          ((vinsn_commit.op == VCOMPRESS) && vcompress_issue_end_q &&
           result_queue_empty)) begin
        // Mark the vector instruction as being done
        pe_resp.vinsn_done[vinsn_commit.id] = 1'b1;

        // Clear the vcompress end indicator
        vcompress_issue_end_d = 1'b0;

        // Update the commit counters and pointers
        vinsn_queue_d.commit_cnt -= 1;
      end
    end

    ///////////////////////////
    // Commit scalar results //
    ///////////////////////////

    // This is one cycle after asserting out_scalar_valid
    // Ara's frontend is always ready to accept the scalar result
    if (result_scalar_valid_o) begin
      // Reset result_scalar
      result_scalar_d       = '0;
      result_scalar_valid_d = '0;

      // Clear the iteration counter
      iteration_cnt_clr = 1'b1;

      // Reset the popcount and vfirst_count
      popcount_d     = '0;
      vfirst_count_d = '0;
      vfirst_found_d = 1'b0;
    end

    //////////////////////////////
    //  Accept new instruction  //
    //////////////////////////////

    // Full mask words preceding the slide offset are skipped by the lane
    // operand requester. MASKU therefore only needs the offset within the
    // first word it receives.
    trimmed_stride = pe_req_i.stride % (NrLanes * DataWidth);

    // MASKU owns one set of read/issue/commit counters. Do not replace that
    // context while queue entries from the preceding instruction can still
    // update those counters. Per-lane spill registers may continue draining
    // the tagged old entries independently.
    if (!vinsn_queue_full && mask_queue_empty && pe_req_valid_i &&
        !vinsn_running_q[pe_req_i.id] &&
        (!pe_req_i.vm || pe_req_i.vfu == VFU_MaskUnit)) begin
      vinsn_queue_d.vinsn[0]       = pe_req_i;
      vinsn_running_d[pe_req_i.id] = 1'b1;

      // Initialize counters
      if (vinsn_queue_d.issue_cnt == '0) begin
        // The instruction queue has depth one, so a newly accepted request
        // starts a fresh MASKU execution context.  Reset all slice-local
        // counters here as an invariant; early-terminating operations such as
        // VCOMPRESS and VFIRST need not reach every normal per-word clear.
        in_ready_cnt_clr   = 1'b1;
        in_m_ready_cnt_clr = 1'b1;
        out_valid_cnt_clr  = 1'b1;
        iteration_cnt_clr  = 1'b1;
        vcompress_issue_end_d = 1'b0;

        issue_cnt_d      = pe_req_i.vl;
        processing_cnt_d = pe_req_i.vl;
        read_cnt_d       = pe_req_i.vl;
        mask_pnt_d       = '0;

        // Zero-length scalar mask operations have no operand slice from which
        // the normal completion path could generate their architectural result.
        if (pe_req_i.vl == '0 && pe_req_i.op inside {VCPOP, VFIRST}) begin
          result_scalar_d       = (pe_req_i.op == VCPOP) ? '0 : elen_t'(-1);
          result_scalar_valid_d = 1'b1;
        end

        if (!pe_req_i.vm && pe_req_i.vfu != VFU_MaskUnit &&
            pe_req_i.vstart != '0) begin
          read_cnt_d = (pe_req_i.vstart >= pe_req_i.vl)
                     ? '0
                     : pe_req_i.vl - mask_aligned_vstart;
          mask_pnt_d = mask_aligned_vstart % (NrLanes * DataWidth);
        end

        // Trim skipped words
        if (pe_req_i.op == VSLIDEUP) begin
          issue_cnt_d      -= vlen_t'(pe_req_i.stride);
          processing_cnt_d -= vlen_t'(pe_req_i.stride);
          case (pe_req_i.vtype.vsew)
            EW8:  begin
              read_cnt_d -= (vlen_t'(pe_req_i.stride) >> $clog2(NrLanes << 3)) << $clog2(NrLanes << 3);
              mask_pnt_d  = (vlen_t'(trimmed_stride) >> $clog2(NrLanes << 3)) << $clog2(NrLanes << 3);
            end
            EW16: begin
              read_cnt_d -= (vlen_t'(pe_req_i.stride) >> $clog2(NrLanes << 2)) << $clog2(NrLanes << 2);
              mask_pnt_d  = (vlen_t'(trimmed_stride) >> $clog2(NrLanes << 2)) << $clog2(NrLanes << 2);
            end
            EW32: begin
              read_cnt_d -= (vlen_t'(pe_req_i.stride) >> $clog2(NrLanes << 1)) << $clog2(NrLanes << 1);
              mask_pnt_d  = (vlen_t'(trimmed_stride) >> $clog2(NrLanes << 1)) << $clog2(NrLanes << 1);
            end
            EW64: begin
              read_cnt_d -= (vlen_t'(pe_req_i.stride) >> $clog2(NrLanes)) << $clog2(NrLanes);
              mask_pnt_d  = (vlen_t'(trimmed_stride) >> $clog2(NrLanes)) << $clog2(NrLanes);
            end
            default:;
          endcase
        end

        // Initialize ALU MASKU counters and pointers
        unique case (pe_req_i.op) inside
          [VMFEQ:VMSGT]: begin
            // Mask to mask - encoded
            delta_elm_d = NrLanes << (EW64 - pe_req_i.eew_vs2[1:0]);

            in_ready_threshold_d   = 0;
            in_m_ready_threshold_d = (DataWidth >> (EW64 - pe_req_i.eew_vs2[1:0]))-1;
            out_valid_threshold_d  = (DataWidth >> (EW64 - pe_req_i.eew_vs2[1:0]))-1;
          end
          [VMADC:VMSBC]: begin
            // Mask to mask - encoded
            delta_elm_d = NrLanes << (EW64 - pe_req_i.eew_vs2[1:0]);

            in_ready_threshold_d   = 0;
            in_m_ready_threshold_d = (DataWidth >> (EW64 - pe_req_i.eew_vs2[1:0]))-1;
            out_valid_threshold_d  = (DataWidth >> (EW64 - pe_req_i.eew_vs2[1:0]))-1;
          end
          [VMANDNOT:VMXNOR]: begin
            // Mask to mask
            delta_elm_d = VmLogicalParallelism;

            in_ready_threshold_d   = NrLanes*DataWidth/VmLogicalParallelism-1;
            in_m_ready_threshold_d = NrLanes*DataWidth/VmLogicalParallelism-1;
            out_valid_threshold_d  = NrLanes*DataWidth/VmLogicalParallelism-1;
          end
          [VMSBF:VMSIF]: begin
            // Mask to mask
            delta_elm_d = VmsxfParallelism;

            in_ready_threshold_d   = NrLanes*DataWidth/VmsxfParallelism-1;
            in_m_ready_threshold_d = NrLanes*DataWidth/VmsxfParallelism-1;
            out_valid_threshold_d  = NrLanes*DataWidth/VmsxfParallelism-1;
          end
          [VIOTA:VID]: begin
            // Mask to non-mask
            delta_elm_d = ViotaParallelism;

            in_ready_threshold_d   = NrLanes*DataWidth/ViotaParallelism-1;
            in_m_ready_threshold_d = NrLanes*DataWidth/ViotaParallelism-1;
            out_valid_threshold_d  = ((NrLanes*DataWidth/8/ViotaParallelism) >> pe_req_i.vtype.vsew[1:0])-1;
          end
          VCPOP: begin
            popcount_d = '0;

            // Mask to scalar
            delta_elm_d = VcpopParallelism;

            in_ready_threshold_d   = NrLanes*DataWidth/VcpopParallelism-1;
            in_m_ready_threshold_d = NrLanes*DataWidth/VcpopParallelism-1;
            out_valid_threshold_d  = '0;
          end
          VFIRST: begin
            vfirst_count_d = '0;
            vfirst_found_d = 1'b0;

            // Mask to scalar
            delta_elm_d = VfirstParallelism;

            in_ready_threshold_d   = NrLanes*DataWidth/VfirstParallelism-1;
            in_m_ready_threshold_d = NrLanes*DataWidth/VfirstParallelism-1;
            out_valid_threshold_d  = '0;
          end
          default: begin // VRGATHER, VRGATHEREI16, VCOMPRESS
            delta_elm_d = 1;

            in_ready_threshold_d   = pe_req_i.op == VCOMPRESS ? NrLanes*DataWidth-1 : ((NrLanes*DataWidth/8) >> vrgat_eff_vsew)-1;
            in_m_ready_threshold_d = NrLanes*DataWidth-1;
            out_valid_threshold_d  = ((NrLanes*DataWidth/8) >> pe_req_i.vtype.vsew[1:0])-1;

            vrgat_cnt_d = '0;
          end
        endcase

        // Reset the final grant vector
        // Be aware: this works only if the insn queue length is 1
        result_final_gnt_d = '0;
      end
      if (vinsn_queue_d.commit_cnt == '0) begin
        commit_cnt_d = pe_req_i.vl;
        if (!pe_req_i.vm && pe_req_i.vfu != VFU_MaskUnit &&
            pe_req_i.vstart != '0) begin
          commit_cnt_d = (pe_req_i.vstart >= pe_req_i.vl)
                       ? '0
                       : pe_req_i.vl - mask_aligned_vstart;
        end
        // Trim skipped words
        // A regular vslideup does not write elements below its offset.  A
        // vslide1up does write element zero from the scalar operand, so its
        // predicate stream must cover the full destination range.
        if (pe_req_i.op == VSLIDEUP && !pe_req_i.use_scalar_op)
          commit_cnt_d -= vlen_t'(pe_req_i.stride);
      end

      // Bump pointers and counters of the vector instruction queue
      vinsn_queue_d.issue_cnt += 1;
      vinsn_queue_d.commit_cnt += 1;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      vinsn_running_q         <= '0;
      read_cnt_q              <= '0;
      issue_cnt_q             <= '0;
      processing_cnt_q        <= '0;
      commit_cnt_q            <= '0;
      vrf_pnt_q               <= '0;
      mask_pnt_q              <= '0;
      pe_resp_o               <= '0;
      result_final_gnt_q      <= '0;
      popcount_q              <= '0;
      vfirst_count_q          <= '0;
      vfirst_found_q          <= 1'b0;
      delta_elm_q             <= '0;
      in_ready_threshold_q    <= '0;
      in_m_ready_threshold_q  <= '0;
      out_valid_threshold_q   <= '0;
      viota_acc_q             <= '0;
      found_one_q             <= '0;
      be_viota_seq_q          <= '1; // Default: write
      be_vrgat_seq_q          <= '1; // Default: write
      vrgat_req_valid_mask_q  <= '0;
      vrgat_cnt_q             <= '0;
      vcompress_issue_end_q   <= '0;
      vcompress_cnt_q         <= '0;
    end else begin
      vinsn_running_q         <= vinsn_running_d;
      read_cnt_q              <= read_cnt_d;
      issue_cnt_q             <= issue_cnt_d;
      processing_cnt_q        <= processing_cnt_d;
      commit_cnt_q            <= commit_cnt_d;
      vrf_pnt_q               <= vrf_pnt_d;
      mask_pnt_q              <= mask_pnt_d;
      pe_resp_o               <= pe_resp;
      result_final_gnt_q      <= result_final_gnt_d;
      popcount_q              <= popcount_d;
      vfirst_count_q          <= vfirst_count_d;
      vfirst_found_q          <= vfirst_found_d;
      delta_elm_q             <= delta_elm_d;
      in_ready_threshold_q    <= in_ready_threshold_d;
      in_m_ready_threshold_q  <= in_m_ready_threshold_d;
      out_valid_threshold_q   <= out_valid_threshold_d;
      viota_acc_q             <= viota_acc_d;
      found_one_q             <= found_one_d;
      be_viota_seq_q          <= be_viota_seq_d;
      be_vrgat_seq_q          <= be_vrgat_seq_d;
      vrgat_req_valid_mask_q  <= vrgat_req_valid_mask_d;
      vrgat_cnt_q             <= vrgat_cnt_d;
      vcompress_issue_end_q   <= vcompress_issue_end_d;
      vcompress_cnt_q         <= vcompress_cnt_d;
    end
  end

`ifdef FOR_VERIFY
  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_VRGATHER536") &&
        vinsn_issue_valid && vinsn_issue.op == VRGATHER &&
        vinsn_issue.vd == 5'd20 && vinsn_issue.vl == 30 &&
        vinsn_issue.vtype.vsew == EW64) begin
      if (vrgat_idx_fifo_push || vrgat_idx_fifo_pop || out_vrf_word_valid) begin
        $display("[ARA_VRGATHER536] t=%0t scan=%0d raw_idx=%h idx=%0d ovf=%0b oor_in=%0b push=%0b fifo_idx=%0d fifo_oor=%0b pop=%0b vd_v=%b vd_r=%b vd=%h out_slot=%0d out_word=%0b out_data=%h",
                 $time, vrgat_cnt_q,
                 masku_operand_alu_seq[
                   vrgat_cnt_q[idx_width(NrLanes*DataWidth/64)-1:0] * 64 +: 64],
                 vrgat_req_idx_d, vrgat_idx_overflow, vrgat_idx_oor_d,
                 vrgat_idx_fifo_push, vrgat_req_idx_q, vrgat_idx_oor_q,
                 vrgat_idx_fifo_pop, masku_operand_vd_valid,
                 masku_operand_vd_ready, masku_operand_vd_seq,
                 out_valid_cnt_q, out_vrf_word_valid,
                 result_queue_d[result_queue_write_pnt_q]);
      end
    end
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_VCOMPRESS415") &&
        vinsn_issue_valid && vinsn_issue.op == VCOMPRESS) begin
      if (vrgat_idx_fifo_push || vrgat_idx_fifo_pop ||
          (&masku_operand_vd_valid && !vrgat_idx_fifo_empty) ||
          out_vrf_word_valid || vcompress_issue_end_q) begin
        $display("[ARA_VCOMPRESS415] t=%0t id=%0d vl=%0d sew=%0d scan=%0d maskbit=%0b mask_v=%b mask_r=%b mask=%h idx_push=%0b idx_full=%0b idx_empty=%0b idx_head=%0d oor=%0b last=%0b idx_pop=%0b req_push=%0b req_full=%0b vd_v=%b vd_r=%b vd=%h issue_cnt=%0d commit_cnt=%0d rq_cnt=%0d out_cnt=%0d vrf_pnt=%0d comp_cnt=%0d alu=%h out_word=%0b out_be=%h issue_end=%0b",
                 $time, vinsn_issue.id, vinsn_issue.vl,
                 vinsn_issue.vtype.vsew, vrgat_cnt_q, vcompress_bit,
                 masku_operand_alu_valid, masku_operand_alu_ready,
                 masku_operand_alu_seq,
                 vrgat_idx_fifo_push, vrgat_idx_fifo_full,
                 vrgat_idx_fifo_empty, vrgat_req_idx_q, vrgat_idx_oor_q,
                 vcompress_last_idx_q, vrgat_idx_fifo_pop,
                 vrgat_req_fifo_push, vrgat_req_fifo_full,
                 masku_operand_vd_valid, masku_operand_vd_ready,
                 masku_operand_vd_seq, issue_cnt_q, commit_cnt_q,
                 result_queue_cnt_q,
                 out_valid_cnt_q, vrf_pnt_q, vcompress_cnt_q,
                 alu_result_vm_m, out_vrf_word_valid,
                 result_queue_d[result_queue_write_pnt_q][0].be,
                 vcompress_issue_end_q);
      end
    end
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_VMSOF_STALL") &&
        ((pe_req_valid_i && pe_req_i.op == VMSOF && pe_req_i.vd == 5'd22) ||
         (vinsn_issue.op == VMSOF && vinsn_issue.vd == 5'd22))) begin
      $display("[ARA_VMSOF_MASKU] t=%0t req=%0b/%0b id=%0d issue=%0b op=%0d cnt=%0d->%0d proc=%0d->%0d commit=%0d->%0d alu=%b/%b vd=%b/%b mask=%b/%b rq=%0d full=%0b in=%0d/%0d out=%0d/%0d done=%b",
               $time, pe_req_valid_i, pe_req_ready_o, vinsn_issue.id,
               vinsn_issue_valid, vinsn_issue.op, issue_cnt_q, issue_cnt_d,
               processing_cnt_q, processing_cnt_d, commit_cnt_q, commit_cnt_d,
               masku_operand_alu_valid, masku_operand_alu_ready,
               masku_operand_vd_valid, masku_operand_vd_ready,
               masku_operand_m_valid, masku_operand_m_ready,
               result_queue_cnt_q, result_queue_full,
               in_ready_cnt_q, in_ready_threshold_q,
               out_valid_cnt_q, out_valid_threshold_q, pe_resp_o.vinsn_done);
    end
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_VMSBF") && vinsn_issue_valid &&
        vinsn_issue.op inside {[VMSBF:VMSIF]} && !result_queue_full &&
        &masku_operand_alu_valid && &masku_operand_vd_valid &&
        (&masku_operand_m_valid || vinsn_issue.vm)) begin
      $display("[ARA_VMSBF] t=%0t id=%0d op=%0d vl=%0d vstart=%0d vm=%0b eew=%0d iter=%0d in=%0d out=%0d src=%h pred=%h old=%h masked_src=%h raw=%h active=%h alu=%h bg=%h wr=%h",
               $time, vinsn_issue.id, vinsn_issue.op, vinsn_issue.vl,
               vinsn_issue.vstart, vinsn_issue.vm, vinsn_issue.vtype.vsew,
               iteration_cnt_q, in_ready_cnt_q, out_valid_cnt_q,
               masku_operand_alu_seq, masku_operand_m_seq,
               masku_operand_vd_seq, masku_operand_alu_seq_m,
               alu_result_vm, result_queue_active_mask_seq,
               alu_result_vm_m, background_data_init_seq,
               result_queue_d[result_queue_write_pnt_q]);
    end
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_SCALAR_MASK") &&
        ((pe_req_valid_i && pe_req_i.op inside {VCPOP, VFIRST}) ||
         (vinsn_issue_valid && vinsn_issue.op inside {VCPOP, VFIRST}) ||
         result_scalar_valid_o || out_scalar_valid)) begin
      $display("[ARA_MASK_SCALAR] t=%0t req=%0b/%0b req_op=%0d req_vs2=%0d req_eew=%0d issue=%0b op=%0d vs2=%0d eew=%0d issue_cnt=%0d->%0d in=%0d raw=%h active=%h pc=%0d acc=%0d->%0d alu=%b/%b lane=%h seq=%h mask=%b/%b out=%0b result=%0b val=%h done=%b",
               $time, pe_req_valid_i, pe_req_ready_o, pe_req_i.op,
               pe_req_i.vs2, pe_req_i.eew_vs2,
               vinsn_issue_valid, vinsn_issue.op, vinsn_issue.vs2,
               vinsn_issue.eew_vs2, issue_cnt_q, issue_cnt_d,
               in_ready_cnt_q, vcpop_slice_raw, vcpop_slice, popcount,
               popcount_q, popcount_d,
               masku_operand_alu_valid, masku_operand_alu_ready,
               masku_operand_alu, masku_operand_alu_seq,
               masku_operand_m_valid, masku_operand_m_ready,
               out_scalar_valid, result_scalar_valid_o, result_scalar_o,
               pe_resp.vinsn_done);
    end
  end

  logic [6:0] debug_vfirst_cycle_q;
  logic [6:0] debug_maskcmp_cycle_q;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      debug_vfirst_cycle_q <= '0;
    end else if (!(vinsn_issue_valid && vinsn_issue.op == VFIRST)) begin
      debug_vfirst_cycle_q <= '0;
    end else if (debug_vfirst_cycle_q != '1) begin
      debug_vfirst_cycle_q <= debug_vfirst_cycle_q + 1'b1;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      debug_maskcmp_cycle_q <= '0;
    end else if (!(vinsn_issue_valid && vinsn_issue.op == VMSGTU)) begin
      debug_maskcmp_cycle_q <= '0;
    end else if (debug_maskcmp_cycle_q != '1) begin
      debug_maskcmp_cycle_q <= debug_maskcmp_cycle_q + 1'b1;
    end
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_VFIRST")) begin
      if (pe_req_valid_i && pe_req_ready_o && pe_req_i.op == VFIRST) begin
        $display("[ARA_VFIRST_ACCEPT] t=%0t id=%0d vl=%0d vstart=%0d vm=%0b vs2=v%0d issue_q=%0d commit_q=%0d running=%b",
                 $time, pe_req_i.id, pe_req_i.vl, pe_req_i.vstart,
                 pe_req_i.vm, pe_req_i.vs2, vinsn_queue_q.issue_cnt,
                 vinsn_queue_q.commit_cnt, vinsn_running_q);
      end
      if (vinsn_issue_valid && vinsn_issue.op == VFIRST &&
          debug_vfirst_cycle_q < 7'd64) begin
        $display("[ARA_VFIRST_STATE] t=%0t age=%0d id=%0d issue=%0d processing=%0d commit=%0d alu_v=%b alu_r=%b mask_v=%b mask_r=%b rq=%0d mq=%0d in=%0d/%0d inm=%0d/%0d out=%0d/%0d empty=%0b slice=%h scalar=%0b done=%b",
                 $time, debug_vfirst_cycle_q, vinsn_issue.id, issue_cnt_q,
                 processing_cnt_q, commit_cnt_q, masku_operand_alu_valid,
                 masku_operand_alu_ready, masku_operand_m_valid,
                 masku_operand_m_ready, result_queue_cnt_q, mask_queue_cnt_q,
                 in_ready_cnt_q, in_ready_threshold_q, in_m_ready_cnt_q,
                 in_m_ready_threshold_q, out_valid_cnt_q,
                 out_valid_threshold_q, vfirst_empty, vfirst_slice,
                 result_scalar_valid_o, pe_resp.vinsn_done);
      end
    end
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_MASKCMP")) begin
      if (pe_req_valid_i && pe_req_ready_o && pe_req_i.op == VMSGTU) begin
        $display("[ARA_MASKCMP_ACCEPT] t=%0t id=%0d vl=%0d vstart=%0d vm=%0b vd=v%0d vs2=v%0d use_vd_op=%0b eew_vs2=%0d eew_vd=%0d",
                 $time, pe_req_i.id, pe_req_i.vl, pe_req_i.vstart,
                 pe_req_i.vm, pe_req_i.vd, pe_req_i.vs2,
                 pe_req_i.use_vd_op, pe_req_i.eew_vs2, pe_req_i.eew_vd_op);
      end
      if (vinsn_issue_valid && vinsn_issue.op == VMSGTU &&
          debug_maskcmp_cycle_q < 7'd64) begin
        $display("[ARA_MASKCMP_STATE] t=%0t age=%0d id=%0d issue=%0d processing=%0d commit=%0d alu_v=%b alu_r=%b vd_v=%b vd_r=%b mask_v=%b mask_r=%b rq_cnt=%0d rq_v=%b rq_req=%b rq_gnt=%b rq_final=%b final_q=%b in=%0d/%0d inm=%0d/%0d out=%0d/%0d out_word=%0b done=%b",
                 $time, debug_maskcmp_cycle_q, vinsn_issue.id, issue_cnt_q,
                 processing_cnt_q, commit_cnt_q, masku_operand_alu_valid,
                 masku_operand_alu_ready, masku_operand_vd_valid,
                 masku_operand_vd_ready, masku_operand_m_valid,
                 masku_operand_m_ready, result_queue_cnt_q,
                 result_queue_valid_q[result_queue_read_pnt_q],
                 masku_result_req_o, masku_result_gnt_i,
                 masku_result_final_gnt_i, result_final_gnt_q,
                 in_ready_cnt_q, in_ready_threshold_q, in_m_ready_cnt_q,
                 in_m_ready_threshold_q, out_valid_cnt_q,
                 out_valid_threshold_q, out_vrf_word_valid,
                 pe_resp.vinsn_done);
      end
    end
  end

`ifdef FOR_VERIFY
  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_VMXOR_TAIL") &&
        vinsn_issue_valid && vinsn_issue.op == VMXOR &&
        vinsn_issue.vd == 5'd18 && !result_queue_full &&
        &masku_operand_alu_valid && &masku_operand_vd_valid &&
        &masku_operand_m_valid) begin
      $display("[ARA_VMXOR_TAIL] t=%0t id=%0d vl=%0d vstart=%0d vsew=%0d eew_a=%0d eew_m=%0d eew_vd=%0d iter=%0d src_a=%h src_m=%h old_vd=%h active=%h alu=%h bg=%h wr=%h",
               $time, vinsn_issue.id, vinsn_issue.vl, vinsn_issue.vstart,
               vinsn_issue.vtype.vsew, vinsn_issue.eew_vs2,
               vinsn_issue.eew_vs1, vinsn_issue.eew_vd_op,
               iteration_cnt_q, masku_operand_alu_seq,
               masku_operand_m_seq, masku_operand_vd_seq,
               result_queue_active_mask_seq, alu_result_vm_m,
               background_data_init_seq,
               result_queue_d[result_queue_write_pnt_q]);
    end
  end
`endif

  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_VMSLEU14")) begin
      if (pe_req_valid_i && pe_req_ready_o && pe_req_i.op == VMSLEU &&
          pe_req_i.vd == 5'd7) begin
        $display("[ARA_VMSLEU14_ACCEPT] t=%0t id=%0d vl=%0d vstart=%0d vm=%0b vsew=%0d use_vd=%0b",
                 $time, pe_req_i.id, pe_req_i.vl, pe_req_i.vstart,
                 pe_req_i.vm, pe_req_i.vtype.vsew, pe_req_i.use_vd_op);
      end
      if (vinsn_issue_valid && vinsn_issue.op == VMSLEU &&
          vinsn_issue.vd == 5'd7 && !result_queue_full &&
          &masku_operand_alu_valid && &masku_operand_vd_valid) begin
        $display("[ARA_VMSLEU14_DATA] t=%0t id=%0d issue=%0d proc=%0d in=%0d/%0d out=%0d/%0d alu_cmp=%h active=%h old=%h merged=%h out_word=%0b",
                 $time, vinsn_issue.id, issue_cnt_q, processing_cnt_q,
                 in_ready_cnt_q, in_ready_threshold_q, out_valid_cnt_q,
                 out_valid_threshold_q, alu_result_compressed_seq,
                 result_queue_active_mask_seq, masku_operand_vd_seq,
                 result_queue_d[result_queue_write_pnt_q], out_vrf_word_valid);
      end
    end
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_SEGMENT_MASK")) begin
      if (pe_req_valid_i && pe_req_ready_o && !pe_req_i.vm &&
          pe_req_i.vfu == VFU_StoreUnit) begin
        $display("[ARA_SEG_MASK_ACCEPT] t=%0t id=%0d op=%0d vl=%0d vstart=%0d vsew=%0d eew_mask=%0d aligned=%0d read=%0d commit=%0d pnt=%0d",
                 $time, pe_req_i.id, pe_req_i.op, pe_req_i.vl,
                 pe_req_i.vstart, pe_req_i.vtype.vsew, pe_req_i.eew_vmask,
                 mask_aligned_vstart, read_cnt_d, commit_cnt_d, mask_pnt_d);
      end
      if (vinsn_issue_valid && !vinsn_issue.vm &&
          vinsn_issue.vfu == VFU_StoreUnit && &masku_operand_m_valid &&
          !mask_queue_full) begin
        $display("[ARA_SEG_MASK_IN] t=%0t id=%0d vl=%0d vstart=%0d read=%0d pnt=%0d operand=%h operand_seq=%h queue=%h valid=%b",
                 $time, vinsn_issue.id, vinsn_issue.vl, vinsn_issue.vstart,
                 read_cnt_q, mask_pnt_q, masku_operand_m, masku_operand_m_seq,
                 mask_queue_d[mask_queue_write_pnt_q],
                 mask_queue_valid_d[mask_queue_write_pnt_q]);
      end
      if (vinsn_issue_valid && vinsn_issue.vfu == VFU_StoreUnit &&
          vstu_mask_ready_i && |mask_valid_o) begin
        $display("[ARA_SEG_MASK_OUT] t=%0t id=%0d vl=%0d vstart=%0d commit=%0d mask=%h valid=%b",
                 $time, vinsn_issue.id, vinsn_issue.vl, vinsn_issue.vstart,
                 commit_cnt_q, mask_o, mask_valid_o);
      end
    end
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_VREDMIN_MASK")) begin
      if (pe_req_valid_i && pe_req_ready_o && pe_req_i.op == VREDMIN &&
          pe_req_i.vd == 5'd19) begin
        $display("[ARA_VREDMIN_MASK_ACCEPT] t=%0t id=%0d vl=%0d vstart=%0d vsew=%0d eew_mask=%0d issue=%0d read=%0d pnt=%0d",
                 $time, pe_req_i.id, pe_req_i.vl, pe_req_i.vstart,
                 pe_req_i.vtype.vsew, pe_req_i.eew_vmask, issue_cnt_d,
                 read_cnt_d, mask_pnt_d);
      end
      if (vinsn_issue_valid && vinsn_issue.op == VREDMIN &&
          vinsn_issue.vd == 5'd19 && &masku_operand_m_valid &&
          !mask_queue_full) begin
        $display("[ARA_VREDMIN_MASK_IN] t=%0t id=%0d read=%0d pnt=%0d operand=%h queued=%h",
                 $time, vinsn_issue.id, read_cnt_q, mask_pnt_q,
                 masku_operand_m, mask_queue_d[mask_queue_write_pnt_q]);
      end
      if (vinsn_issue_valid && vinsn_issue.op == VREDMIN &&
          vinsn_issue.vd == 5'd19 && |mask_valid_o) begin
        $display("[ARA_VREDMIN_MASK_OUT] t=%0t id=%0d read=%0d pnt=%0d target=%0d mask=%h valid=%b ready=%b",
                 $time, vinsn_issue.id, read_cnt_q, mask_pnt_q,
                 mask_target_fu_o, mask_o, mask_valid_o, lane_mask_ready_i);
      end
    end
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_MASK_VSTART") && out_vrf_word_valid &&
        vinsn_issue.op inside {[VMANDNOT:VMXNOR]}) begin
      $display("[ARA_MASK_VSTART] t=%0t op=%0d vl=%0d vstart=%0d iter=%0d vd_valid=%b alu_valid=%b old=%h computed=%h merged=%h",
               $time, vinsn_issue.op, vinsn_issue.vl, vinsn_issue.vstart,
               iteration_cnt_q, masku_operand_vd_valid, masku_operand_alu_valid,
               masku_operand_vd_seq, masku_operand_alu_seq, alu_result_vm_m);
    end
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_SLIDE_MASK")) begin
      if (pe_req_valid_i && pe_req_ready_o && pe_req_i.op inside {VSLIDEUP, VSLIDEDOWN}) begin
        $display("[ARA_MASKU_SLIDE_ACCEPT] t=%0t id=%0d vl=%0d stride=%0d vm=%0b vsew=%0d trimmed=%0d init_mask_pnt=%0d init_read=%0d init_issue=%0d",
                 $time, pe_req_i.id, pe_req_i.vl, pe_req_i.stride, pe_req_i.vm,
                 pe_req_i.vtype.vsew, trimmed_stride, mask_pnt_d, read_cnt_d,
                 issue_cnt_d);
      end
      if (vinsn_issue_valid && vinsn_issue.op inside {VSLIDEUP, VSLIDEDOWN} &&
          !vinsn_issue.vm && &masku_operand_m_valid && !mask_queue_full) begin
        $display("[ARA_MASKU_SLIDE_MASK_IN] t=%0t id=%0d mask_pnt=%0d read=%0d issue=%0d data=%h queued=%h",
                 $time, vinsn_issue.id, mask_pnt_q, read_cnt_q, issue_cnt_q,
                 masku_operand_m, mask_queue_d[mask_queue_write_pnt_q]);
      end
      if (vinsn_issue_valid && vinsn_issue.op inside {VSLIDEUP, VSLIDEDOWN} &&
          sldu_mask_ready_i && |mask_valid_o) begin
        $display("[ARA_MASKU_SLIDE_MASK_OUT] t=%0t id=%0d valid=%b mask=%h commit=%0d",
                 $time, vinsn_issue.id, mask_valid_o, mask_o, commit_cnt_q);
      end
    end
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_VRGATHER") && vinsn_issue_valid &&
        vinsn_issue.op inside {VRGATHER, VRGATHEREI16}) begin
      if (vrgat_idx_fifo_push || (!vrgat_idx_fifo_empty &&
          (vrgat_idx_oor_q || &masku_operand_vd_valid))) begin
        $display("[ARA_VRGATHER] t=%0t id=%0d scalar=%0b idx=%0d oor_in=%0b idx_empty=%0b oor_head=%0b req_push=%0b vd_valid=%b issue=%0d processing=%0d",
                 $time, vinsn_issue.id, vinsn_issue.use_scalar_op,
                 vrgat_req_idx_d, vrgat_idx_oor_d, vrgat_idx_fifo_empty,
                 vrgat_idx_oor_q, vrgat_req_fifo_push, masku_operand_vd_valid,
                 issue_cnt_q, processing_cnt_q);
      end
    end
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_VRGATHER_SCALAR") &&
        vinsn_issue_valid && vinsn_issue.op == VRGATHER &&
        vinsn_issue.use_scalar_op && &masku_operand_vd_valid) begin
      $display("[ARA_VRGATHER_SCALAR] t=%0t id=%0d vd=%0d vl=%0d sew=%0d idx=%0d issue=%0d processing=%0d out_cnt=%0d src=%h alu=%h out=%h",
               $time, vinsn_issue.id, vinsn_issue.vd, vinsn_issue.vl,
               vinsn_issue.vtype.vsew, vrgat_req_idx_q, issue_cnt_q,
               processing_cnt_q, out_valid_cnt_q, masku_operand_vd_seq,
               alu_result, result_queue_d[result_queue_write_pnt_q]);
    end
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_MASK_CARRY")) begin
      if (pe_req_valid_i && pe_req_ready_o &&
          pe_req_i.op inside {[VMADC:VMSBC]}) begin
        $display("[ARA_MASK_CARRY_ACCEPT] t=%0t id=%0d op=%0d vd=%0d vl=%0d vstart=%0d vta=%0b use_vd=%0b issue=%0d processing=%0d",
                 $time, pe_req_i.id, pe_req_i.op, pe_req_i.vd, pe_req_i.vl,
                 pe_req_i.vstart, pe_req_i.vtype.vta, pe_req_i.use_vd_op,
                 issue_cnt_d, processing_cnt_d);
      end
      if (vinsn_issue_valid && vinsn_issue.op inside {[VMADC:VMSBC]} &&
          !result_queue_full && &masku_operand_alu_valid) begin
        $display("[ARA_MASK_CARRY_OPERANDS] t=%0t id=%0d op=%0d use_vd=%0b vd_valid=%b vd=%h alu_valid=%b alu=%h issue=%0d processing=%0d in=%0d out=%0d",
                 $time, vinsn_issue.id, vinsn_issue.op, vinsn_issue.use_vd_op,
                 masku_operand_vd_valid, masku_operand_vd_seq,
                 masku_operand_alu_valid, masku_operand_alu_seq,
                 issue_cnt_q, processing_cnt_q, in_ready_cnt_q,
                 out_valid_cnt_q);
      end
      if (out_vrf_word_valid && vinsn_issue.op inside {[VMADC:VMSBC]}) begin
        $display("[ARA_MASK_CARRY_RESULT] t=%0t id=%0d vl=%0d vstart=%0d vta=%0b use_vd=%0b active=%h old=%h computed=%h background=%h result=%h",
                 $time, vinsn_issue.id, vinsn_issue.vl, vinsn_issue.vstart,
                 vinsn_issue.vtype.vta, vinsn_issue.use_vd_op,
                 result_queue_active_mask_seq, masku_operand_vd_seq,
                 alu_result_vm_m, background_data_init_seq,
                 result_queue_d[result_queue_write_pnt_q]);
      end
    end
  end
`endif

endmodule : masku
