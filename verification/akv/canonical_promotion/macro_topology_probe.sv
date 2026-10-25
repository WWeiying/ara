// Zero-clock structural smoke for the checked functional macro models only.
module akv_resource_q_macro_probe (
  input logic [5:0] address,
  input logic [255:0] write_data
);
  initial $display("AKV_RESOURCE_MACRO role=q address_bits=%0d data_bits=%0d path=%m",
                   $bits(address), $bits(write_data));
endmodule

module akv_resource_kv_macro_probe (
  input logic [6:0] address,
  input logic [255:0] write_data
);
  initial $display("AKV_RESOURCE_MACRO role=kv address_bits=%0d data_bits=%0d path=%m",
                   $bits(address), $bits(write_data));
endmodule

module akv_resource_topology_finish;
  initial begin
    #1;
    $display("AKV_RESOURCE_TOPOLOGY_END");
    $finish;
  end
endmodule

bind TS1N28HPCPUHDSVTB64X256M1SWBSO
    akv_resource_q_macro_probe i_q_geometry_probe (.address(A), .write_data(D));
bind TS1N28HPCPUHDSVTB128X256M1SWBSO
    akv_resource_kv_macro_probe i_kv_geometry_probe (.address(A), .write_data(D));
bind akv_engine_synth_wrapper akv_resource_topology_finish i_topology_finish();
