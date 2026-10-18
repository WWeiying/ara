// SPDX-License-Identifier: SHL-0.51
// Share scalar ordered ADD across physical Lanes. The Lane FSM still owns
// element order, seed insertion and architectural completion. This backend
// only arbitrates requests and returns each rounded result to its owner.
module shared_ordered_adder import ara_pkg::*; import fpnew_pkg::*; #(
  parameter int unsigned NrLanes = 4,
  parameter int unsigned NrUnits = 1,
  parameter int unsigned NrClients = NrLanes,
  parameter fpu_support_e FPUSupport = FPUSupportHalfSingleDouble,
  localparam int LaneWidth = (NrClients > 1) ? $clog2(NrClients) : 1
)(
  input logic clk_i, rst_ni,
  input ordered_add_request_t [NrClients-1:0] request_i,
  input logic [NrClients-1:0] valid_i,
  output logic [NrClients-1:0] ready_o,
  output ordered_add_response_t [NrClients-1:0] response_o,
  output logic [NrClients-1:0] response_valid_o,
  input logic [NrClients-1:0] response_ready_i
);
  typedef logic [LaneWidth-1:0] lane_t;
  typedef struct packed { lane_t lane; logic [8:0] original; } owner_t;
  localparam fpu_features_t Features = '{
    Width: 64, EnableVectors: 1'b0, EnableNanBox: 1'b0,
    FpFmtMask: {RVVF(FPUSupport), RVVD(FPUSupport), RVVH(FPUSupport), RVVB(FPUSupport), RVVHA(FPUSupport), RVVBA(FPUSupport)},
    IntFmtMask: {logic'(RVVB(FPUSupport) || RVVBA(FPUSupport)), 1'b1, 1'b1, 1'b1}};
  localparam fpu_implementation_t Implementation = '{
    PipeRegs: '{'{default: 1}, '{default: 0}, '{default: 0}, '{default: 0}, '{default: 0}},
    UnitTypes: '{'{default: PARALLEL}, '{default: DISABLED}, '{default: DISABLED},
                 '{default: DISABLED}, '{default: DISABLED}},
    PipeConfig: AFTER};
  for (genvar unit_idx = 0; unit_idx < NrUnits; unit_idx++) begin : gen_unit
    lane_t round_robin_q, locked_lane_q, selected;
    logic locked_q, found, in_ready, raw_in_ready, out_valid, out_ready;
    logic busy_q, can_accept;
    ordered_add_request_t request;
    ordered_add_response_t response;
    owner_t owner_in, owner_out;
    // Permit only one outstanding operation per shared unit so responses
    // cannot reorder results
    // or change the selected response while its owning Lane is backpressured.
    // A consumed response can be replaced on the same edge: no extra bubble.
    assign can_accept = !busy_q || (out_valid && out_ready);
    assign in_ready = raw_in_ready && can_accept;
    always_ff @(posedge clk_i or negedge rst_ni) begin
      if (!rst_ni) busy_q <= 1'b0;
      else case ({found && in_ready, out_valid && out_ready})
        2'b10: busy_q <= 1'b1;
        2'b01: busy_q <= 1'b0;
        default:;
      endcase
    end
    always_comb begin
      selected = locked_lane_q;
      found = 1'b0;
      if (locked_q) begin
        found = valid_i[locked_lane_q];
      end else begin
`ifdef ARA_RED_STATIC_ORDERED_ARBITER
        // Two fixed-index priority scans replace variable indexing and modulo
        // arithmetic. The second scan overwrites the wraparound choice with
        // the first requester at/after the registered rotation point.
        for (int lane = NrClients-1; lane >= 0; lane--) begin
          if ((lane % NrUnits == unit_idx) && valid_i[lane]) begin
            selected = lane_t'(lane);
            found = 1'b1;
          end
        end
        for (int lane = NrClients-1; lane >= 0; lane--) begin
          if ((lane % NrUnits == unit_idx) && valid_i[lane] && lane >= round_robin_q)
            selected = lane_t'(lane);
        end
`else
        for (int offset = 0; offset < NrClients; offset++) begin
          // Four Lane clients plus an optional RCE client; constant modulo.
          if (!found && (((int'(round_robin_q) + offset) % NrClients) % NrUnits == unit_idx) &&
              valid_i[(int'(round_robin_q) + offset) % NrClients]) begin
            selected = lane_t'((int'(round_robin_q) + offset) % NrClients);
            found = 1'b1;
          end
        end
`endif
      end
      request = request_i[selected];
      owner_in = '{lane: selected, original: request.tag};
      out_ready = response_ready_i[owner_out.lane];
    end
    always_ff @(posedge clk_i or negedge rst_ni) begin
      if (!rst_ni) begin
        round_robin_q <= lane_t'(unit_idx);
        locked_lane_q <= lane_t'(unit_idx);
        locked_q <= 1'b0;
      end else if (found) begin
        if (in_ready) begin
          round_robin_q <= selected == NrClients-1 ? '0 : selected + 1'b1;
          locked_q <= 1'b0;
        end else begin
          locked_q <= 1'b1;
          locked_lane_q <= selected;
        end
      end
    end
`ifdef ARA_RED_COMPACT_ORDERED_BACKEND
    // Share alignment, addition and normalization across FP16/32/64.
    // The request-to-response latency remains one edge (AFTER semantics).
    // Result, exception flags and owner retain the original backpressure rules.
    logic [NUM_FP_FORMATS-1:0][63:0] format_result;
    status_t [NUM_FP_FORMATS-1:0] format_status;
    ordered_add_response_t response_q;
    owner_t owner_q;
    logic [63:0] shared_result;
    status_t shared_status;
    shared_scalar_fp_add i_format_shared_add (
      .clk_i, .rst_ni, .a_i(request.operands[1]), .b_i(request.operands[2]),
      .format_i(request.dst_fmt), .rnd_mode_i(request.rm),
      .result_o(shared_result), .status_o(shared_status)
    );
    for (genvar fmt = 0; fmt < NUM_FP_FORMATS; fmt++) begin : gen_format
      if (Features.FpFmtMask[fmt] &&
          (fmt == FP16 || fmt == FP32 || fmt == FP64)) begin : gen_shared
        assign format_result[fmt] = shared_result;
        assign format_status[fmt] = shared_status;
      end else if (Features.FpFmtMask[fmt]) begin : gen_enabled
        // Preserve optional nonstandard formats outside the production config.
        localparam int Width = fp_width(fp_format_e'(fmt));
        logic [2:0][Width-1:0] operands;
        logic [Width-1:0] result;
        for (genvar op = 0; op < 3; op++) begin : gen_operand
          assign operands[op] = request.operands[op][Width-1:0];
        end
        fpnew_fma #(.FpFormat(fp_format_e'(fmt)), .NumPipeRegs(0),
          .TagType(logic), .AuxType(logic)) i_add (
          .clk_i, .rst_ni, .operands_i(operands), .is_boxed_i('1),
          .rnd_mode_i(request.rm), .op_i(ADD), .op_mod_i(1'b0),
          .tag_i(1'b0), .mask_i(request.mask), .aux_i(1'b0),
          .in_valid_i(1'b1), .in_ready_o(), .flush_i(1'b0),
          .result_o(result), .status_o(format_status[fmt]),
          .extension_bit_o(), .tag_o(), .mask_o(), .aux_o(),
          .out_valid_o(), .out_ready_i(1'b1), .busy_o());
        // fpnew scalar ADD always NaN-boxes narrow results. Input boxing
        // checks remain disabled, as required for RVV's unboxed operands.
        assign format_result[fmt] = {{(64-Width){1'b1}}, result};
      end else begin : gen_disabled
        assign format_result[fmt] = '0;
        assign format_status[fmt] = '0;
      end
    end
    assign raw_in_ready = 1'b1;
    assign out_valid = busy_q;
    assign response = response_q;
    assign owner_out = owner_q;
    always_ff @(posedge clk_i or negedge rst_ni) begin
      if (!rst_ni) begin
        response_q <= '0;
        owner_q <= '0;
      end else if (found && in_ready) begin
        response_q.result <= format_result[request.dst_fmt];
        response_q.status <= format_status[request.dst_fmt] & {5{request.mask}};
        response_q.tag <= request.tag;
        owner_q <= owner_in;
      end
    end
`ifndef SYNTHESIS
    a_supported_format: assert property (@(posedge clk_i) disable iff (!rst_ni)
      found && in_ready |-> Features.FpFmtMask[request.dst_fmt])
      else $error("unsupported format at compact shared ADD");
`endif
`else
    fpnew_top #(.Features(Features), .Implementation(Implementation),
      .DivSqrtSel(PULP), .TagType(owner_t), .TrueSIMDClass(1), .EnableSIMDMask(1)) i_add (
      .clk_i, .rst_ni, .hart_id_i('0), .flush_i(1'b0),
      .rnd_mode_i(request.rm), .op_i(ADD), .op_mod_i(1'b0), .vectorial_op_i(1'b0),
      .operands_i(request.operands), .tag_i(owner_in), .simd_mask_i(request.mask),
      .src_fmt_i(request.src_fmt), .dst_fmt_i(request.dst_fmt), .int_fmt_i(request.int_fmt),
      .in_valid_i(found && can_accept), .in_ready_o(raw_in_ready), .result_o(response.result),
      .status_o(response.status), .tag_o(owner_out), .out_valid_o(out_valid),
      .out_ready_i(out_ready), .busy_o()
    );
    assign response.tag = owner_out.original;
`endif
    for (genvar lane = 0; lane < NrClients; lane++) begin : gen_route
      if (lane % NrUnits == unit_idx) begin : gen_member
        assign ready_o[lane] = found && selected == lane && in_ready;
        assign response_o[lane] = response;
        assign response_valid_o[lane] = out_valid && owner_out.lane == lane;
      end
    end
`ifndef SYNTHESIS
    a_locked_source_stays_valid: assert property (@(posedge clk_i) disable iff (!rst_ni)
      locked_q |-> valid_i[locked_lane_q]) else $error("ordered source withdrew a stalled request");
    a_output_owner_in_group: assert property (@(posedge clk_i) disable iff (!rst_ni)
      out_valid |-> (owner_out.lane < NrClients && owner_out.lane % NrUnits == unit_idx))
      else $error("ordered shared result owner is outside its group");
    a_stalled_input_stable: assert property (@(posedge clk_i) disable iff (!rst_ni)
      found && !in_ready |=> found && $stable({request, owner_in}))
      else $error("ordered shared input changed under backpressure");
    a_stalled_output_stable: assert property (@(posedge clk_i) disable iff (!rst_ni)
      out_valid && !out_ready |=> out_valid && $stable({response, owner_out}))
      else $error("ordered shared response changed under backpressure");
`endif
  end
`ifndef SYNTHESIS
  initial begin
    assert (NrLanes == 4 && (NrClients == 4 || NrClients == 5) && (NrUnits == 1 || NrUnits == 2) && FPUSupport != FPUSupportNone)
      else $fatal(1, "shared ordered experiment requires four FP-enabled Lanes and one/two units");
  end
`endif
endmodule
