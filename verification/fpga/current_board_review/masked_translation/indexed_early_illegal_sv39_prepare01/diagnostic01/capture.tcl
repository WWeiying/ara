onerror {quit}
run -absolute 79000ns
set fid [dump -file diagnostic.fsdb -type FSDB]
dump -add {ara_tb.clk} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara_commit_monitor.cycle_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.state_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.axi_addrgen_state_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.idx_op_error_d} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.idx_op_error_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.idx_final_vaddr_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.idx_vaddr_valid_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.mmu_req_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.mmu_req_d} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.mmu_valid_i} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.addrgen_exception_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.ara_idle} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.store_pending} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.lsu_ex_flush_lane} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.lsu_ex_flush_done} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.lsu_ex_state_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_vstu.vinsn_queue_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_vstu.exception_pending_q} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_vstu.store_complete_o} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.ara_axi_req} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.ara_axi_resp} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.ara_axi_req_delayed} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.ara_axi_resp_delayed} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.ariane_axi_req} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.ariane_axi_resp} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.inval_valid} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.inval_ready} -aggregates -fid $fid
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ariane.ex_stage_i.lsu_i} -depth 2 -aggregates -fid $fid
run -absolute 83000ns
dump -disable -fid $fid
dump -flush $fid
run -absolute 85000ns
puts DIAGNOSTIC_COMPLETE_AT_85000NS
quit
