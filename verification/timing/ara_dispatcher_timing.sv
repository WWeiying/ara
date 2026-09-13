// SPDX-License-Identifier: SHL-0.51
// Full dispatcher with the SoC's interface types; no tied functional inputs.
module ara_dispatcher_timing import ara_pkg::*; import dispatcher_check_pkg::*; (
    input logic clk_i, rst_ni,
    input accelerator_req_t acc_req_i,
    output accelerator_resp_t acc_resp_o,
    output logic response_valid_o,
    output ara_req_t ara_req_o,
    output logic ara_req_valid_o,
    input logic ara_req_ready_i,
    input ara_resp_t ara_resp_i,
    input logic ara_resp_valid_i, ara_idle_i, sldu_idle_i,
    output logic sldu_drain_o,
    input logic [NrLanes-1:0][4:0] fflags_ex_i,
    input logic [NrLanes-1:0] fflags_ex_valid_i,
    output logic lsu_ex_flush_o,
    input logic lsu_ex_flush_done_i,
    input logic [NrLanes-1:0] vxsat_flag_i,
    output ara_pkg::vxrm_t [NrLanes-1:0] alu_vxrm_o,
    output logic core_st_pending_o,
    input logic load_complete_i, store_complete_i, store_pending_i
  );
  ara_dispatcher #(.NrLanes(NrLanes), .VLEN(VLEN), .CVA6Cfg(CVA6Cfg),
      .ara_req_t(ara_req_t), .ara_resp_t(ara_resp_t),
      .accelerator_req_t(accelerator_req_t), .accelerator_resp_t(accelerator_resp_t))
      i_dispatcher (.*);
  assign response_valid_o=acc_resp_o.resp_valid;
endmodule
