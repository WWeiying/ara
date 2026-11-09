// SPDX-License-Identifier: Apache-2.0
// Test-only replacement for the arithmetic slice in the frozen PV checker.
`ifndef RESIDENT_TEST_SHARED_FMA
`define RESIDENT_TEST_SHARED_FMA 0
`endif

module resident_vmfpu_adapter #(
  parameter fpnew_pkg::opgroup_e OpGroup = fpnew_pkg::ADDMUL,
  parameter fpnew_pkg::fp_format_e FpFormat = fpnew_pkg::FP16,
  parameter int unsigned Width = 64,
  parameter logic EnableVectors = 1'b1,
  parameter int unsigned NumPipeRegs = 3,
  parameter fpnew_pkg::pipe_config_t PipeConfig = fpnew_pkg::DISTRIBUTED,
  parameter type TagType = logic [3:0],
  localparam int unsigned NUM_OPERANDS = fpnew_pkg::num_operands(OpGroup),
  localparam int unsigned NUM_LANES = fpnew_pkg::num_lanes(Width, FpFormat, EnableVectors)
) (
  input logic clk_i,
  input logic rst_ni,
  input logic [NUM_OPERANDS-1:0][Width-1:0] operands_i,
  input logic [NUM_OPERANDS-1:0] is_boxed_i,
  input fpnew_pkg::roundmode_e rnd_mode_i,
  input fpnew_pkg::operation_e op_i,
  input logic op_mod_i,
  input logic vectorial_op_i,
  input TagType tag_i,
  input logic [NUM_LANES-1:0] simd_mask_i,
  input logic in_valid_i,
  output logic in_ready_o,
  input logic flush_i,
  output logic [Width-1:0] result_o,
  output fpnew_pkg::status_t status_o,
  output logic extension_bit_o,
  output TagType tag_o,
  output logic out_valid_o,
  input logic out_ready_i,
  output logic busy_o,
  input logic borrow_busy_i
);
  import ara_pkg::*;
  import rvv_pkg::*;
  import fpnew_pkg::*;

  localparam int NrLanes = 4;
  localparam int VLEN = 1024;
  localparam bit SharedFma = `RESIDENT_TEST_SHARED_FMA;
  // The package is a user configuration, not the elaborated hardware structure.
  localparam config_pkg::cva6_cfg_t NativeConfig =
      build_config_pkg::build_config(cva6_config_pkg::cva6_cfg);
  localparam int VRFBSizePerLane = VLEN * 32 / NrLanes / 8;
  typedef logic [$clog2(VRFBSizePerLane)-1:0] vaddr_t;
  typedef logic [$clog2(VLEN+1)-1:0] vlen_t;

  // Keep the complete production lane.sv operation type, including unused fields.
  typedef struct packed {
    vid_t id;
    ara_op_e op;
    logic vm;
    logic use_vs1;
    logic use_vs2;
    logic use_vd_op;
    logic preserve_narrow_vd;
    elen_t scalar_op;
    logic use_scalar_op;
    logic skip_sldu_operand;
    vfu_e vfu;
    logic [4:0] vd;
    logic use_vd;
    logic swap_vs2_vd_op;
    roundmode_e fp_rm;
    logic wide_fp_imm;
    resize_e cvt_resize;
    vlen_t vl;
    vlen_t vstart;
    vtype_t vtype;
  } vfu_operation_t;

  typedef enum logic [2:0] {
    Idle, NativeOffer, NativeWait, Acquire, Owned, DeferredOffer, DeferredWait
  } state_t;
  state_t state_q;
  logic [2:0] native_index_q;
  vfu_operation_t native_operation;
  elen_t [2:0] native_operands;
  elen_t native_expected;
  logic [4:0] native_expected_flags;
  logic [2:0] native_operand_pending_q, native_operand_valid;
  logic native_offer, native_active_q, native_written_q;
  logic [4:0] native_flags_q;
  int unsigned native_stall_q, native_age_q, preparation_age_q;
  logic native_ready, native_result_valid, native_result_grant;
  vid_t native_result_id;
  vaddr_t native_result_addr;
  elen_t native_result_data;
  logic [7:0] native_result_be;
  logic [NrVInsn-1:0] native_done;
  logic [4:0] native_flags;
  logic native_flags_valid, native_vxsat;
  logic [2:0] native_operand_ready;
  logic native_red_complete, native_any_active, native_red_valid;
  logic native_slide_ready, native_mask_valid, native_mask_ready;
  elen_t native_mask_data;

  logic ref_ready, ref_result_valid, ref_flags_valid, ref_vxsat;
  vid_t ref_result_id;
  vaddr_t ref_result_addr;
  elen_t ref_result_data, ref_mask_data;
  logic [7:0] ref_result_be;
  logic [NrVInsn-1:0] ref_done;
  logic [4:0] ref_flags;
  logic [2:0] ref_operand_ready;
  logic ref_red_complete, ref_any_active, ref_red_valid;
  logic ref_slide_ready, ref_mask_valid, ref_mask_ready;

  logic acquire, acquire_ready, owned, release_owner, release_ready;
  logic private_valid, private_ready, private_result_valid;
  elen_t private_result;
  logic [3:0] private_result_tag;
  logic [4:0] private_result_flags;
  logic [15:0] private_tags_q;
  int unsigned private_pending_q;
  logic native_fire, private_fire, private_return;

  // Totals deliberately survive reset; reset cancels only accepted transactions.
  longint unsigned total_native_accept = 0, total_native_done = 0;
  longint unsigned total_native_cancel = 0, total_acquires = 0, total_releases = 0;
  longint unsigned total_native_stalls = 0, total_private_stalls = 0;
  longint unsigned total_private_issue = 0, total_private_return = 0;
  longint unsigned total_private_cancel = 0, total_collisions = 0;
  longint unsigned total_miter_cycles = 0, total_grant_stalls = 0;
  longint unsigned total_native_flag_events = 0, total_reset_owned = 0;
  longint unsigned total_native_ops [4] = '{default:0};
  logic private_input_held_q, private_output_held_q, native_output_held_q;
  logic [202:0] private_input_saved_q;
  logic [72:0] private_output_saved_q;
  logic [$bits(vid_t)+$bits(vaddr_t)+72-1:0] native_output_saved_q;

  always_comb begin
    native_operation = '0;
    native_operation.id = vid_t'(native_index_q);
    native_operation.op = VFMACC;
    native_operation.vm = 1'b1;
    native_operation.use_vs1 = 1'b1;
    native_operation.use_vs2 = 1'b1;
    native_operation.use_vd_op = native_index_q == 0;
    native_operation.vfu = VFU_MFpu;
    native_operation.vd = 5'(20 + native_index_q);
    native_operation.use_vd = 1'b1;
    native_operation.fp_rm = RNE;
    native_operation.cvt_resize = CVT_SAME;
    native_operation.vl = vlen_t'(4);
    native_operation.vtype = '{vill:1'b0, vma:1'b1, vta:1'b1,
                               vsew:EW16, vlmul:LMUL_1};
    // VMFPU takes vs1 in [0], vs2 in [1], and the accumulator in [2].
    native_operands[0] = {4{16'h3c00}};
    native_operands[1] = {4{16'h4000}};
    native_operands[2] = {4{16'h4200}};
    native_expected = {4{16'h4500}}; // 1 * 2 + 3 = 5
    native_expected_flags = '0;
    case (native_index_q)
      1: begin
        native_operation.op = VFMUL;
        native_operands[0] = {4{16'h4000}};
        native_operands[1] = {4{16'h4200}};
        native_expected = {4{16'h4600}}; // 2 * 3 = 6
      end
      2: begin
        native_operation.op = VFDIV;
        native_operands[0] = {4{16'h4000}}; // divisor
        native_operands[1] = {4{16'h4600}}; // dividend
        native_expected = {4{16'h4200}}; // 6 / 2 = 3
      end
      3: begin
        native_operation.op = VFMAX;
        native_operands[0] = {4{16'h3c00}};
        native_operands[1] = {4{16'h7c01}}; // signaling NaN
        native_expected = {4{16'h3c00}};
        native_expected_flags = 5'b10000; // maximumNumber(sNaN, 1): NV
      end
      4: begin
        native_operation.op = VFMUL;
        native_operands[0] = {4{16'hbc00}};
        native_operands[1] = {4{16'h4000}};
        native_expected = {4{16'hc000}}; // deferred probe: -1 * 2 = -2
      end
      default: ;
    endcase
  end

  assign native_offer = rst_ni && (state_q inside {NativeOffer, Owned, DeferredOffer});
  assign native_operand_valid = native_active_q ? native_operand_pending_q : '0;
  assign native_fire = native_offer && native_ready;
  assign native_result_grant = native_active_q && native_result_valid && native_stall_q >= 3;
  // The first offer deliberately collides with acquisition; native must win.
  assign acquire = rst_ni && borrow_busy_i && (state_q inside {NativeOffer, Acquire});
  assign release_owner = rst_ni && state_q == Owned && !borrow_busy_i &&
                         private_pending_q == 0;
  assign private_valid = rst_ni && owned && in_valid_i;
  assign in_ready_o = rst_ni && owned && private_ready;
  assign out_valid_o = rst_ni && private_result_valid;
  assign result_o = private_result;
  assign tag_o = TagType'(private_result_tag);
  assign status_o = status_t'(private_result_flags);
  assign extension_bit_o = 1'b1;
  assign busy_o = owned || native_active_q || private_pending_q != 0;
  assign private_fire = in_valid_i && in_ready_o;
  assign private_return = out_valid_o && out_ready_i;

  vmfpu #(
    .NrLanes(NrLanes), .VLEN(VLEN), .SharedFma(SharedFma), .EnableResidentPv(1'b1),
    .CVA6Cfg(NativeConfig),
    .FPUSupport(FPUSupportHalfSingleDouble), .FPExtSupport(FPExtSupportEnable),
    .FixPtSupport(FixedPointEnable), .vaddr_t(vaddr_t), .vfu_operation_t(vfu_operation_t)
  ) i_vmfpu (
    .clk_i, .rst_ni, .lane_id_i(2'b00), .mfpu_vxsat_o(native_vxsat), .mfpu_vxrm_i('0),
    .fflags_ex_o(native_flags), .fflags_ex_valid_o(native_flags_valid),
    .vfu_operation_i(native_operation), .vfu_operation_valid_i(native_offer),
    .mfpu_ready_o(native_ready), .mfpu_vinsn_done_o(native_done),
    .fpu_red_complete_o(native_red_complete), .reduction_any_active_o(native_any_active),
    .reduction_global_any_active_i(1'b0),
    .mfpu_operand_i(native_operands), .mfpu_operand_valid_i(native_operand_valid),
    .mfpu_operand_ready_o(native_operand_ready),
    .mfpu_result_req_o(native_result_valid), .mfpu_result_id_o(native_result_id),
    .mfpu_result_addr_o(native_result_addr), .mfpu_result_wdata_o(native_result_data),
    .mfpu_result_be_o(native_result_be), .mfpu_result_gnt_i(native_result_grant),
    .mfpu_red_valid_o(native_red_valid), .mfpu_red_ready_i(1'b0),
    .sldu_operand_i('0), .sldu_mfpu_valid_i(1'b0), .sldu_mfpu_ready_o(native_slide_ready),
    .mask_operand_o(native_mask_data), .mask_operand_valid_o(native_mask_valid),
    .mask_operand_ready_i(1'b1), .mask_i(8'hff), .mask_valid_i(1'b0),
    .mask_ready_o(native_mask_ready),
    .resident_acquire_i(acquire), .resident_acquire_ready_o(acquire_ready),
    .resident_owned_o(owned), .resident_release_i(release_owner),
    .resident_release_ready_o(release_ready),
    .resident_valid_i(private_valid), .resident_ready_o(private_ready),
    .resident_operands_i(operands_i), .resident_tag_i(4'(tag_i)),
    .resident_mask_i(simd_mask_i), .resident_rm_i(3'(rnd_mode_i)),
    .resident_result_valid_o(private_result_valid), .resident_result_ready_i(out_ready_i),
    .resident_result_o(private_result), .resident_result_tag_o(private_result_tag),
    .resident_result_flags_o(private_result_flags)
  );

  // The runner renames its admitted original VMFPU; this copy sees no PV traffic.
  vmfpu_baseline #(
    .NrLanes(NrLanes), .VLEN(VLEN), .SharedFma(SharedFma),
    .CVA6Cfg(NativeConfig),
    .FPUSupport(FPUSupportHalfSingleDouble), .FPExtSupport(FPExtSupportEnable),
    .FixPtSupport(FixedPointEnable), .vaddr_t(vaddr_t), .vfu_operation_t(vfu_operation_t)
  ) i_baseline (
    .clk_i, .rst_ni, .lane_id_i(2'b00), .mfpu_vxsat_o(ref_vxsat), .mfpu_vxrm_i('0),
    .fflags_ex_o(ref_flags), .fflags_ex_valid_o(ref_flags_valid),
    .vfu_operation_i(native_operation), .vfu_operation_valid_i(native_offer && !owned),
    .mfpu_ready_o(ref_ready), .mfpu_vinsn_done_o(ref_done),
    .fpu_red_complete_o(ref_red_complete), .reduction_any_active_o(ref_any_active),
    .reduction_global_any_active_i(1'b0),
    .mfpu_operand_i(native_operands), .mfpu_operand_valid_i(native_operand_valid),
    .mfpu_operand_ready_o(ref_operand_ready),
    .mfpu_result_req_o(ref_result_valid), .mfpu_result_id_o(ref_result_id),
    .mfpu_result_addr_o(ref_result_addr), .mfpu_result_wdata_o(ref_result_data),
    .mfpu_result_be_o(ref_result_be), .mfpu_result_gnt_i(native_result_grant),
    .mfpu_red_valid_o(ref_red_valid), .mfpu_red_ready_i(1'b0),
    .sldu_operand_i('0), .sldu_mfpu_valid_i(1'b0), .sldu_mfpu_ready_o(ref_slide_ready),
    .mask_operand_o(ref_mask_data), .mask_operand_valid_o(ref_mask_valid),
    .mask_operand_ready_i(1'b1), .mask_i(8'hff), .mask_valid_i(1'b0),
    .mask_ready_o(ref_mask_ready)
  );

  initial begin
    if (NativeConfig.XLEN != 64 || NativeConfig.TRANS_ID_BITS == 0)
      $fatal(1, "Invalid native hardware configuration");
    if (OpGroup != ADDMUL || FpFormat != FP16 || Width != 64 || !EnableVectors ||
        $bits(TagType) != 4 || PipeConfig != DISTRIBUTED ||
        !(`RESIDENT_TEST_SHARED_FMA inside {0,1}))
      $fatal(1, "Unsupported resident VMFPU adapter configuration");
    $display("VMFPU_ADAPTER_CONFIG shared_fma=%0d checker_pipe_label=%0d", SharedFma, NumPipeRegs);
  end

  always @(negedge rst_ni) begin
    if (native_active_q === 1'b1) total_native_cancel++;
    if (private_pending_q > 0) total_private_cancel += private_pending_q;
    if (owned === 1'b1) total_reset_owned++;
  end

  always @(posedge clk_i or negedge rst_ni) begin : monitor_and_drive
    if (!rst_ni) begin
      state_q <= Idle;
      native_index_q <= '0;
      native_active_q <= 1'b0;
      native_written_q <= 1'b0;
      native_flags_q <= '0;
      native_operand_pending_q <= '0;
      native_stall_q <= 0;
      native_age_q <= 0;
      preparation_age_q <= 0;
      private_pending_q <= 0;
      private_tags_q <= '0;
      private_input_held_q <= 1'b0;
      private_output_held_q <= 1'b0;
      native_output_held_q <= 1'b0;
      private_input_saved_q <= '0;
      private_output_saved_q <= '0;
      native_output_saved_q <= '0;
    end else begin
      if (flush_i) $fatal(1, "Adapter requires shared reset, not an independent FPU flush");
      if (state_q inside {Idle,Owned}) preparation_age_q <= 0;
      else begin
        preparation_age_q <= preparation_age_q + 1;
        if (preparation_age_q >= 4096) $fatal(1, "Native preparation/acquisition watchdog");
      end
      if ($isunknown({owned, acquire_ready, release_ready, in_ready_o, out_valid_o,
                      native_ready, native_result_valid, native_flags_valid, native_done}))
        $fatal(1, "Unknown VMFPU ownership/native handshake");
      if (owned && (private_pending_q != 0 || in_valid_i || out_valid_o))
        assert (!release_ready)
          else $fatal(1, "Release ready asserted with private work outstanding");
      if (native_active_q || native_result_valid || native_flags_valid)
        assert (!acquire_ready)
          else $fatal(1, "Acquire ready asserted with native work outstanding");

      total_miter_cycles++;
      if ({native_result_valid, native_flags_valid, native_done, native_operand_ready,
           native_vxsat, native_red_complete, native_red_valid, native_mask_valid,
           native_mask_ready} !==
          {ref_result_valid, ref_flags_valid, ref_done, ref_operand_ready,
           ref_vxsat, ref_red_complete, ref_red_valid, ref_mask_valid, ref_mask_ready})
        $fatal(1, "VMFPU native miter control mismatch state=%0d op=%0d", state_q, native_index_q);
      if (!owned && {native_ready,native_slide_ready,native_any_active} !==
                    {ref_ready,ref_slide_ready,ref_any_active})
        $fatal(1, "VMFPU native miter readiness mismatch");
      if (native_result_valid &&
          {native_result_data,native_result_be,native_result_id,native_result_addr} !==
          {ref_result_data,ref_result_be,ref_result_id,ref_result_addr})
        $fatal(1, "VMFPU native miter writeback mismatch");
      if (native_flags_valid && native_flags !== ref_flags)
        $fatal(1, "VMFPU native miter flags mismatch");
      if (!native_flags_valid && native_flags !== 5'b0)
        $fatal(1, "Invalid native flags are nonzero: state=%0d owner=%b op=%0d flags=%h ref=%h ref_valid=%b",
                  state_q, owned, native_index_q, native_flags, ref_flags, ref_flags_valid);
      if (native_mask_valid && native_mask_data !== ref_mask_data)
        $fatal(1, "VMFPU native miter mask result mismatch");

      if (owned) begin
        if (native_ready || native_active_q || native_result_valid || (|native_done) ||
            native_flags_valid || native_flags != 0 || (|native_operand_ready) ||
            native_slide_ready || native_mask_valid || native_mask_ready || native_red_valid)
          $fatal(1, "Native acceptance/write/flags leaked during private ownership");
        if (native_offer) total_native_stalls++;
      end else if (private_result_valid || private_result_flags != 0)
        $fatal(1, "Private result/flags leaked outside ownership");
      if (acquire && native_offer) begin
        total_collisions++;
        if (acquire_ready) $fatal(1, "Acquisition bypassed simultaneous native offer");
      end
      if (acquire && acquire_ready) begin
        if (native_active_q || native_result_valid || native_flags_valid || (|native_done))
          $fatal(1, "Acquisition before native drain");
        total_acquires++;
      end
      if (release_owner && release_ready) begin
        if (borrow_busy_i || private_pending_q || out_valid_o || private_valid)
          $fatal(1, "Release before private drain");
        total_releases++;
      end

      // The original controller may withdraw an unaccepted beat on abort.
      if (private_input_held_q && in_valid_i &&
          {operands_i,tag_i,simd_mask_i,rnd_mode_i} !== private_input_saved_q)
        $fatal(1, "Private operands/tag/mask/rm changed under backpressure");
      if (private_output_held_q &&
          (!out_valid_o || {result_o,status_o,tag_o} !== private_output_saved_q))
        $fatal(1, "Private return changed under backpressure");
      private_input_held_q <= in_valid_i && !in_ready_o;
      private_input_saved_q <= {operands_i,tag_i,simd_mask_i,rnd_mode_i};
      private_output_held_q <= out_valid_o && !out_ready_i;
      private_output_saved_q <= {result_o,status_o,tag_o};
      if (in_valid_i && !in_ready_o || out_valid_o && !out_ready_i) total_private_stalls++;
      if (private_return) begin
        if (private_pending_q == 0 || !private_tags_q[private_result_tag])
          $fatal(1, "Unowned/duplicate private return");
        private_tags_q[private_result_tag] <= 1'b0;
        total_private_return++;
      end
      if (private_fire) begin
        if (!borrow_busy_i || op_i != FMADD || op_mod_i || !vectorial_op_i ||
            is_boxed_i != 3'b111 || rnd_mode_i > RMM ||
            $isunknown({operands_i,tag_i,simd_mask_i,rnd_mode_i}))
          $fatal(1, "Invalid private arithmetic contract");
        if (private_tags_q[4'(tag_i)] &&
            !(private_return && private_result_tag == 4'(tag_i)))
          $fatal(1, "Private tag reused before return");
        private_tags_q[4'(tag_i)] <= 1'b1;
        total_private_issue++;
      end
      case ({private_fire,private_return})
        2'b10: private_pending_q <= private_pending_q + 1;
        2'b01: private_pending_q <= private_pending_q - 1;
        default: ;
      endcase

      if (native_output_held_q &&
          (!native_result_valid ||
           {native_result_id,native_result_addr,native_result_data,native_result_be} !== native_output_saved_q))
        $fatal(1, "Native write changed under deterministic grant stall");
      native_output_held_q <= native_result_valid && !native_result_grant;
      native_output_saved_q <= {native_result_id,native_result_addr,native_result_data,native_result_be};
      if (native_flags_valid) begin
        if (!native_active_q) $fatal(1, "Unowned native flags");
        native_flags_q <= native_flags_q | native_flags;
        if (native_flags != 0) total_native_flag_events++;
      end
      if (native_result_valid) begin
        if (!native_active_q || native_written_q ||
            native_result_data !== native_expected || native_result_be !== 8'hff ||
            native_result_id !== native_operation.id ||
            native_result_addr !== vaddr_t'(vaddr(native_operation.vd,NrLanes,VLEN)))
          $fatal(1, "Native exact result mismatch op=%0d data=%h expected=%h",
                    native_index_q,native_result_data,native_expected);
        if (native_result_grant) native_written_q <= 1'b1;
        else begin
          native_stall_q <= native_stall_q + 1;
          total_grant_stalls++;
        end
      end
      if (native_active_q) begin
        native_operand_pending_q <= native_operand_pending_q & ~native_operand_ready;
        native_age_q <= native_age_q + 1;
        if (native_age_q > 4096) $fatal(1, "Native probe watchdog");
      end
      if (|native_done) begin
        if (!native_active_q || native_done !== (NrVInsn'(1) << native_operation.id) ||
            !(native_written_q || native_result_grant) || native_stall_q != 3 ||
            (native_operand_pending_q & ~native_operand_ready) != 0 ||
            (native_flags_q | (native_flags_valid ? native_flags : 5'b0)) !== native_expected_flags)
          $fatal(1, "Native completion/flags mismatch op=%0d flags=%h expected=%h",
                    native_index_q,native_flags_q,native_expected_flags);
        native_active_q <= 1'b0;
        native_operand_pending_q <= '0;
        total_native_done++;
        if (native_index_q < 4) total_native_ops[native_index_q]++;
        if (state_q == NativeWait && native_index_q < 3) begin
          native_index_q <= native_index_q + 1;
          state_q <= NativeOffer;
        end else if (state_q == NativeWait) state_q <= Acquire;
        else if (state_q == DeferredWait) state_q <= Idle;
        else $fatal(1, "Native done in wrong adapter phase");
      end
      if (native_fire) begin
        if (native_active_q || !(state_q inside {NativeOffer,DeferredOffer}) || owned)
          $fatal(1, "Native offer accepted during private ownership or twice");
        native_active_q <= 1'b1;
        native_written_q <= 1'b0;
        native_flags_q <= '0;
        native_operand_pending_q <= native_index_q == 0 ? 3'b111 : 3'b011;
        native_stall_q <= 0;
        native_age_q <= 0;
        total_native_accept++;
        state_q <= state_q == NativeOffer ? NativeWait : DeferredWait;
      end
      case (state_q)
        Idle: if (borrow_busy_i) begin
          native_index_q <= '0;
          state_q <= NativeOffer;
        end
        Acquire: begin
          if (!borrow_busy_i) state_q <= Idle;
          else if (acquire_ready) begin
            native_index_q <= 3'd4;
            state_q <= Owned;
          end
        end
        Owned: if (release_owner && release_ready) state_q <= DeferredOffer;
        default: ;
      endcase
    end
  end

  task automatic finish_gate;
    int unsigned cycles;
    cycles = 0;
    if (rst_ni !== 1'b1 || borrow_busy_i !== 1'b0)
      $fatal(1, "Finish gate requires completed controller command outside reset");
    // Sample between clock edges, after the monitor's nonblocking updates.
    while (state_q !== Idle || owned !== 1'b0 || native_active_q !== 1'b0 ||
           private_pending_q !== 0 || private_tags_q !== 16'b0 ||
           native_result_valid !== 1'b0 || native_flags_valid !== 1'b0 ||
           native_done !== '0 || private_result_valid !== 1'b0 ||
           acquire_ready !== 1'b1) begin
      if (cycles >= 8192)
        $fatal(1, "Finish gate timeout state=%0d owned=%b native=%b private=%0d",
                  state_q,owned,native_active_q,private_pending_q);
      @(negedge clk_i);
      cycles++;
      if (rst_ni !== 1'b1 || borrow_busy_i !== 1'b0)
        $fatal(1, "Reset or new controller command during finish gate");
    end
    assert (state_q === Idle && owned === 1'b0 && native_active_q === 1'b0 &&
            private_pending_q === 0 && private_tags_q === 16'b0)
      else $fatal(1, "Finish gate did not drain adapter ownership");
    assert (total_acquires == total_releases + total_reset_owned)
      else $fatal(1, "Unaccounted acquired owner at finish gate");
    assert (total_native_accept == total_native_done + total_native_cancel)
      else $fatal(1, "Unaccounted accepted native probe at finish gate");
    assert (total_private_issue == total_private_return + total_private_cancel)
      else $fatal(1, "Unaccounted accepted private arithmetic at finish gate");
  endtask

  final begin
    if (total_native_accept != total_native_done + total_native_cancel)
      $fatal(1, "Unaccounted accepted native probe at finish");
    if (total_private_issue != total_private_return + total_private_cancel)
      $fatal(1, "Unaccounted accepted private arithmetic at finish");
    $display("VMFPU_OWNER_COVERAGE native_done=%0d acquires=%0d releases=%0d native_stalls=%0d private_stalls=%0d native_accepted=%0d native_cancelled=%0d private_issued=%0d private_returned=%0d private_cancelled=%0d acquire_collisions=%0d miter_cycles=%0d native_grant_stalls=%0d native_flag_events=%0d reset_owned=%0d native_fma=%0d native_mul=%0d native_div=%0d native_max=%0d",
      total_native_done,total_acquires,total_releases,total_native_stalls,total_private_stalls,
      total_native_accept,total_native_cancel,total_private_issue,total_private_return,
      total_private_cancel,total_collisions,total_miter_cycles,total_grant_stalls,
      total_native_flag_events,total_reset_owned,total_native_ops[0],total_native_ops[1],
      total_native_ops[2],total_native_ops[3]);
  end
endmodule
