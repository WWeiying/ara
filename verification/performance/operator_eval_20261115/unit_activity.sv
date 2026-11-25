// Passive measurement only. Count accepted work, not queue occupancy.
module operator_unit_activity import ara_pkg::*; import rvv_pkg::*; import fpnew_pkg::*; #(
  parameter int MaskWidth = 4
) (
  input logic clk_i, rst_ni, roi,
  input logic native_valid, native_ready,
  input ara_op_e native_op,
  input fp_format_e native_fmt,
  input logic [MaskWidth-1:0] native_mask,
  input logic resident_owned, resident_valid, resident_ready, resident_fp32,
  input logic [3:0] resident_mask
);
  logic roi_q;
  longint unsigned cycles, native_requests, native_fma_requests, native_fma_elements;
  longint unsigned qk_requests, qk_elements, pv_requests, pv_elements;
  longint unsigned native_blocked, resident_blocked;
  integer elements, semantic_lanes, replication;
  always @(posedge clk_i) begin
    if (!rst_ni) begin
      roi_q=0;
      cycles=0; native_requests=0; native_fma_requests=0; native_fma_elements=0;
      qk_requests=0; qk_elements=0; pv_requests=0; pv_elements=0;
      native_blocked=0; resident_blocked=0;
    end else begin
      if (roi && !roi_q) begin
        cycles=0; native_requests=0; native_fma_requests=0; native_fma_elements=0;
        qk_requests=0; qk_elements=0; pv_requests=0; pv_elements=0;
        native_blocked=0; resident_blocked=0;
      end
      if (roi) begin
        cycles++;
        if (native_valid && native_ready) begin
          native_requests++;
          if (native_op inside {[VFMACC:VFNMSUB]}) begin
            semantic_lanes = native_fmt == FP16 ? 4 : native_fmt == FP32 ? 2 : native_fmt == FP64 ? 1 : 0;
            assert (semantic_lanes != 0 && MaskWidth >= semantic_lanes && MaskWidth % semantic_lanes == 0)
              else $fatal(1,"Operator probe unsupported FMA format/mask %m");
            replication = MaskWidth / semantic_lanes;
            elements=0;
            for (integer i=0; i<MaskWidth; i++)
              if ((i % replication)==0) elements+=int'(native_mask[i]);
            native_fma_requests++;
            native_fma_elements+=elements;
          end
        end
        if (resident_owned && resident_valid && resident_ready) begin
          assert (!$isunknown(resident_mask)) else $fatal(1,"Unknown resident mask %m");
          if (resident_fp32) begin
            assert (resident_mask[3:2]=='0) else $fatal(1,"Bad QK semantic mask %m");
            qk_requests++; qk_elements+=$countones(resident_mask[1:0]);
          end else begin
            pv_requests++; pv_elements+=$countones(resident_mask);
          end
        end
        native_blocked+=native_valid && !native_ready;
        resident_blocked+=resident_owned && resident_valid && !resident_ready;
        assert (!(native_valid && native_ready && resident_owned))
          else $fatal(1,"Overlapping native/resident FPU ownership %m");
      end
      if (!roi && roi_q)
        $display("OPERATOR_UNIT %m cycles=%0d native_requests=%0d native_fma_requests=%0d native_fma_elements=%0d qk_requests=%0d qk_elements=%0d pv_requests=%0d pv_elements=%0d native_blocked=%0d resident_blocked=%0d",
          cycles,native_requests,native_fma_requests,native_fma_elements,
          qk_requests,qk_elements,pv_requests,pv_elements,native_blocked,resident_blocked);
      roi_q=roi;
    end
  end
endmodule

// This campaign fixes FP16/32/64 support: four finest physical FP lanes.
bind vmfpu operator_unit_activity #(.MaskWidth(4)) i_operator_unit_activity (
  .clk_i, .rst_ni, .roi(ara_tb.perf_time_q),
  .native_valid(vfpu_in_valid), .native_ready(vfpu_in_ready),
  .native_op(vinsn_issue_q.op), .native_fmt(fpu_gen.fp_dst_fmt), .native_mask(fpu_gen.vfpu_simd_mask),
  .resident_owned(resident_owned_q), .resident_valid(resident_valid_i),
  .resident_ready(resident_ready_o), .resident_fp32(resident_fp32_i), .resident_mask(resident_mask_i)
);
