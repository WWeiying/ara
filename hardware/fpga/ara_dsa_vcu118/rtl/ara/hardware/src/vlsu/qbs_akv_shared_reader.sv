// Experimental extraction only; current production RTL is unchanged.
module qbs_akv_shared_reader #(
  parameter int unsigned AxiDataWidth = 128,
  parameter int unsigned AxiAddrWidth = 64,
  parameter int unsigned VAddrWidth = 64,
  parameter int unsigned PAddrWidth = 56,
  parameter type req_t = logic,
  parameter type rsp_t = logic,
  parameter type axi_ar_t = logic,
  parameter type axi_r_t = logic,
  parameter type exception_t = logic
) (
  input logic clk_i,
  input logic rst_ni,
  input logic [1:0] owner_i,
  input logic [1:0] command_fire_i,
  input req_t client_req_i [2],
  output rsp_t client_rsp_o [2],

  input logic core_st_pending_i,
  input logic en_ld_st_translation_i,
  output logic mmu_req_o,
  output logic [VAddrWidth-1:0] mmu_vaddr_o,
  output logic mmu_is_store_o,
  input logic mmu_valid_i,
  input logic [PAddrWidth-1:0] mmu_paddr_i,
  input logic mmu_exception_valid_i,
  input exception_t mmu_exception_i,
  output logic physical_check_valid_o,
  output logic [AxiAddrWidth-1:0] physical_check_addr_o,
  output logic [12:0] physical_check_bytes_o,
  input logic physical_range_allowed_i,
  output axi_ar_t axi_ar_o,
  output logic axi_ar_valid_o,
  input logic axi_ar_ready_i,
  input axi_r_t axi_r_i,
  input logic axi_r_valid_i,
  output logic axi_r_ready_o
);
  typedef logic [15:0] tag_t;
  req_t selected_req;
  rsp_t reader_rsp;

  // Ownership is supplied by the existing command controller, not arbitrated.
  // Invalid ownership is rejected by assertions and selects neither endpoint.
  always_comb begin
    selected_req = '0;
    client_rsp_o[0] = '0;
    client_rsp_o[1] = '0;
    case (owner_i)
      2'b01: begin
        selected_req = client_req_i[0];
        client_rsp_o[0] = reader_rsp;
      end
      2'b10: begin
        selected_req = client_req_i[1];
        client_rsp_o[1] = reader_rsp;
      end
      default: ;
    endcase
  end

  qbs_read_engine #(
    .AxiDataWidth(AxiDataWidth), .AxiAddrWidth(AxiAddrWidth),
    .VAddrWidth(VAddrWidth), .PAddrWidth(PAddrWidth),
    .RangeBytesWidth(16), .ReadOutstanding(2),
    .axi_ar_t(axi_ar_t), .axi_r_t(axi_r_t),
    .exception_t(exception_t), .tag_t(tag_t)
  ) i_read_engine (
    .clk_i, .rst_ni,
    .range_valid_i(selected_req.range_valid),
    .range_ready_o(reader_rsp.range_ready),
    .range_vaddr_i(selected_req.range_vaddr),
    .range_bytes_i(selected_req.range_bytes),
    .range_tag_i(selected_req.range_tag),
    .range_cache_i(selected_req.range_cache),
    .range_prot_i(selected_req.range_prot),
    .data_valid_o(reader_rsp.data_valid), .data_ready_i(selected_req.data_ready),
    .data_o(reader_rsp.data), .data_strb_o(reader_rsp.data_strb),
    .data_offset_o(reader_rsp.data_offset), .data_tag_o(reader_rsp.data_tag),
    .completion_valid_o(reader_rsp.completion_valid),
    .completion_ready_i(selected_req.completion_ready),
    .completion_tag_o(reader_rsp.completion_tag),
    .fault_valid_o(reader_rsp.fault_valid), .fault_ready_i(selected_req.fault_ready),
    .fault_kind_o(reader_rsp.fault_kind), .fault_vaddr_o(reader_rsp.fault_vaddr),
    .fault_tag_o(reader_rsp.fault_tag), .fault_mmu_exception_o(reader_rsp.fault_mmu_exception),
    .core_st_pending_i, .en_ld_st_translation_i,
    .mmu_req_o, .mmu_vaddr_o, .mmu_is_store_o, .mmu_valid_i, .mmu_paddr_i,
    .mmu_exception_valid_i, .mmu_exception_i,
    .physical_check_valid_o, .physical_check_addr_o, .physical_check_bytes_o,
    .physical_range_allowed_i,
    .axi_ar_o, .axi_ar_valid_o, .axi_ar_ready_i, .axi_r_i, .axi_r_valid_i, .axi_r_ready_o,
    // Acceptance can precede the owner register becoming nonzero.
    .counters_clear_i(|command_fire_i),
    .range_count_o(reader_rsp.range_count),
    .translation_count_o(reader_rsp.translation_count),
    .ar_count_o(reader_rsp.ar_count), .r_beat_count_o(reader_rsp.r_beat_count),
    .payload_byte_count_o(reader_rsp.payload_byte_count),
    .store_wait_cycles_o(reader_rsp.store_wait_cycles),
    .r_backpressure_cycles_o(reader_rsp.r_backpressure_cycles),
    .outstanding_occupancy_sum_o(reader_rsp.outstanding_occupancy_sum),
    .outstanding_max_o(reader_rsp.outstanding_max),
    .outstanding_full_cycles_o(reader_rsp.outstanding_full_cycles),
    .busy_o(reader_rsp.busy)
  );

`ifndef SYNTHESIS
  logic [1:0] previous_owner_q, admitted_owner_q;
  initial begin
    assert ($bits(selected_req.range_vaddr) == VAddrWidth &&
            $bits(selected_req.range_bytes) == 16 && $bits(selected_req.range_tag) == 16 &&
            $bits(reader_rsp.data) == AxiDataWidth &&
            $bits(reader_rsp.data_strb) == AxiDataWidth/8 &&
            $bits(reader_rsp.data_offset) == 16 && $bits(reader_rsp.data_tag) == 16 &&
            $bits(reader_rsp.completion_tag) == 16 && $bits(reader_rsp.fault_tag) == 16 &&
            $bits(reader_rsp.fault_vaddr) == VAddrWidth &&
            $bits(reader_rsp.fault_mmu_exception) == $bits(exception_t))
      else $fatal(1, "SHARED_READER_TYPE_WIDTH");
  end
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      previous_owner_q <= '0;
      admitted_owner_q <= '0;
    end else begin
      assert (!$isunknown({owner_i, command_fire_i}) &&
              $onehot0(owner_i) && $onehot0(command_fire_i))
        else $fatal(1, "SHARED_READER_ONEHOT");
      if (reader_rsp.busy || i_read_engine.ar_stalled_q ||
          i_read_engine.response_drain_q || reader_rsp.fault_valid) begin
        assert ($onehot(owner_i) && owner_i == previous_owner_q)
          else $fatal(1, "SHARED_READER_OWNER_CHANGED_LIVE");
      end
      if (|command_fire_i) begin
        assert (!reader_rsp.busy && !axi_ar_valid_o &&
                !i_read_engine.ar_stalled_q && !i_read_engine.response_drain_q &&
                (owner_i == '0 || owner_i == command_fire_i) && !selected_req.range_valid)
          else $fatal(1, "SHARED_READER_BAD_COMMAND_FIRE");
        admitted_owner_q <= command_fire_i;
      end else if (previous_owner_q != '0 && owner_i == '0) begin
        admitted_owner_q <= '0;
      end
      if (|owner_i) begin
        assert (owner_i == admitted_owner_q || owner_i == command_fire_i)
          else $fatal(1, "SHARED_READER_OWNER_NOT_ADMITTED");
      end
      previous_owner_q <= owner_i;
    end
  end
`endif
endmodule
