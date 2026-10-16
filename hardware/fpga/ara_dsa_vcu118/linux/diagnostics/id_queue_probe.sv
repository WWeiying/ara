// SPDX-License-Identifier: SHL-0.51
module id_queue_probe (
  input logic clk_i, rst_ni,
  input logic [1:0] inp_id_i, oup_id_i,
  input logic [31:0] inp_data_i,
  input logic inp_req_i, oup_req_i, oup_pop_i,
  output logic [1:0] inp_gnt_o, oup_gnt_o, oup_data_valid_o, full_o, empty_o,
  output logic [1:0][31:0] oup_data_o
);
  for(genvar mode=0;mode<2;mode++) begin: gen_mode
    id_queue #(.ID_WIDTH(2),.CAPACITY(4),.FULL_BW(mode),.data_t(logic[31:0])) dut (
      .clk_i,.rst_ni,.inp_id_i,.oup_id_i,.inp_data_i,.inp_req_i,.oup_req_i,.oup_pop_i,
      .inp_gnt_o(inp_gnt_o[mode]),.oup_gnt_o(oup_gnt_o[mode]),
      .oup_data_valid_o(oup_data_valid_o[mode]),.oup_data_o(oup_data_o[mode]),
      .full_o(full_o[mode]),.empty_o(empty_o[mode]),
      .exists_data_i('0),.exists_mask_i('0),.exists_req_i('0)
    );
  end
endmodule
