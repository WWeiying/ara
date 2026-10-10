module masked_indexed_vlsu_probe #(
    parameter int unsigned NrLanes = 4
) (
    input logic clk_i,
    input logic rst_ni,
    input logic idx_mode,
    input logic idx_is_load,
    input ara_pkg::vid_t idx_id,
    input logic idx_valid,
    input logic idx_ready,
    input logic [63:0] idx_addr,
    input logic [15:0] idx_remaining,
    input logic [7:0] lane_ptr,
    input logic [7:0] elem_ptr,
    input logic [15:0] vstart,
    input logic [15:0] vl,
    input logic predicate_valid,
    input logic predicate_active,
    input logic mmu_req,
    input logic ar_valid,
    input logic ar_ready,
    input logic aw_valid,
    input logic aw_ready,
    input logic descriptor_push,
    input logic descriptor_skip,
    input logic exception_valid,
    input logic [63:0] exception_addr,
    input logic issue_valid,
    input ara_pkg::vid_t issue_id,
    input logic issue_vm,
    input logic [NrLanes-1:0] mask_valid,
    input logic [NrLanes*8-1:0] mask_data,
    input logic mask_ready,
    input logic [NrLanes-1:0] mask_input_valid,
    input logic [NrLanes*8-1:0] mask_input_data,
    input logic store_issue_valid,
    input ara_pkg::vid_t store_issue_id,
    input logic store_issue_vm,
    input logic [NrLanes-1:0] store_mask_valid,
    input logic [NrLanes*8-1:0] store_mask_data,
    input logic store_mask_ready,
    input logic [NrLanes-1:0] store_mask_input_valid,
    input logic [NrLanes*8-1:0] store_mask_input_data
);
  longint unsigned cycle;
  logic idx_valid_q;
  logic [63:0] idx_addr_q;
  logic [NrLanes-1:0] mask_valid_q;
  logic [NrLanes-1:0] mask_input_valid_q;
  logic issue_valid_q;
  logic [NrLanes-1:0] store_mask_valid_q;
  logic [NrLanes-1:0] store_mask_input_valid_q;
  logic store_issue_valid_q;

  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      cycle <= 0;
      idx_valid_q <= 1'b0;
      idx_addr_q <= '0;
      mask_valid_q <= '0;
      mask_input_valid_q <= '0;
      issue_valid_q <= 1'b0;
      store_mask_valid_q <= '0;
      store_mask_input_valid_q <= '0;
      store_issue_valid_q <= 1'b0;
    end else begin
      cycle <= cycle + 1;
      idx_valid_q <= idx_valid;
      idx_addr_q <= idx_addr;
      mask_valid_q <= mask_valid;
      mask_input_valid_q <= mask_input_valid;
      issue_valid_q <= issue_valid;
      store_mask_valid_q <= store_mask_valid;
      store_mask_input_valid_q <= store_mask_input_valid;
      store_issue_valid_q <= store_issue_valid;
      if (idx_mode && (exception_valid ||
          (descriptor_push && descriptor_skip) ||
          (idx_valid && (!idx_valid_q || idx_addr != idx_addr_q || idx_ready)) ||
          (idx_is_load && issue_valid && !issue_vm &&
           (mask_valid != mask_valid_q ||
            mask_input_valid != mask_input_valid_q ||
            issue_valid != issue_valid_q)) ||
          (!idx_is_load && store_issue_valid && !store_issue_vm &&
           (store_mask_valid != store_mask_valid_q ||
            store_mask_input_valid != store_mask_input_valid_q ||
            store_issue_valid != store_issue_valid_q)))) begin
        $display("[MASKED_IDX_PROBE] cyc=%0d id=%0d load=%0b idx=%0b/%0b addr=%h left=%0d lane=%0d elem=%0d vstart=%0d vl=%0d pred=%0b/%0b mmu=%0b ar=%0b/%0b aw=%0b/%0b desc=%0b skip=%0b ex=%0b exaddr=%h ld_issue=%0b:%0d vm=%0b mask=%b:%h ready=%0b mask_in=%b:%h st_issue=%0b:%0d vm=%0b mask=%b:%h ready=%0b mask_in=%b:%h",
                 cycle, idx_id, idx_is_load,
                 idx_valid, idx_ready, idx_addr, idx_remaining,
                 lane_ptr, elem_ptr, vstart, vl, predicate_valid, predicate_active, mmu_req,
                 ar_valid, ar_ready, aw_valid, aw_ready, descriptor_push,
                 descriptor_skip,
                 exception_valid, exception_addr, issue_valid, issue_id, issue_vm,
                 mask_valid, mask_data, mask_ready,
                 mask_input_valid, mask_input_data,
                 store_issue_valid, store_issue_id, store_issue_vm,
                 store_mask_valid, store_mask_data, store_mask_ready,
                 store_mask_input_valid, store_mask_input_data);
      end
      if (idx_mode && descriptor_push && descriptor_skip) begin
        assert (predicate_valid && !predicate_active &&
                !mmu_req && !ar_valid && !aw_valid && !exception_valid)
          else $fatal(1, "masked indexed skip generated an address or memory request");
      end
    end
  end
endmodule

bind vlsu masked_indexed_vlsu_probe #(.NrLanes(NrLanes)) i_masked_indexed_probe (
    .clk_i(clk_i),
    .rst_ni(rst_ni),
    .idx_mode(i_addrgen.pe_req_q.op inside {ara_pkg::VLXE, ara_pkg::VSXE}),
    .idx_is_load(i_addrgen.axi_addrgen_q.is_load),
    .idx_id(i_addrgen.pe_req_q.id),
    .idx_valid(i_addrgen.idx_vaddr_valid_q),
    .idx_ready(i_addrgen.idx_vaddr_ready_d),
    .idx_addr(i_addrgen.idx_final_vaddr_q),
    .idx_remaining(i_addrgen.idx_op_cnt_q),
    .lane_ptr(i_addrgen.word_lane_ptr_q),
    .elem_ptr(i_addrgen.elm_ptr_q),
    .vstart(i_addrgen.pe_req_q.vstart),
    .vl(i_addrgen.pe_req_q.vl),
    .predicate_valid(i_addrgen.idx_predicate_valid),
    .predicate_active(i_addrgen.idx_predicate_active),
    .mmu_req(i_addrgen.mmu_req_o),
    .ar_valid(i_addrgen.axi_ar_valid_o),
    .ar_ready(i_addrgen.axi_ar_ready_i),
    .aw_valid(i_addrgen.axi_aw_valid_o),
    .aw_ready(i_addrgen.axi_aw_ready_i),
    .descriptor_push(i_addrgen.axi_addrgen_queue_push),
    .descriptor_skip(i_addrgen.axi_addrgen_queue.is_skip),
    .exception_valid(i_addrgen.addrgen_exception_o.valid),
    .exception_addr(i_addrgen.addrgen_exception_o.tval),
    .issue_valid(i_vldu.vinsn_issue_valid),
    .issue_id(i_vldu.vinsn_issue_q.id),
    .issue_vm(i_vldu.vinsn_issue_q.vm),
    .mask_valid(i_vldu.mask_valid_q),
    .mask_data(i_vldu.mask_q),
    .mask_ready(i_vldu.mask_ready_d),
    .mask_input_valid(i_vldu.mask_valid_i),
    .mask_input_data(i_vldu.mask_i),
    .store_issue_valid(i_vstu.vinsn_issue_valid),
    .store_issue_id(i_vstu.vinsn_issue_q.id),
    .store_issue_vm(i_vstu.vinsn_issue_q.vm),
    .store_mask_valid(i_vstu.mask_valid_q),
    .store_mask_data(i_vstu.mask_q),
    .store_mask_ready(i_vstu.mask_ready_d),
    .store_mask_input_valid(i_vstu.mask_valid_i),
    .store_mask_input_data(i_vstu.mask_i)
);
