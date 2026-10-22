# Read-only snapshots on the existing image; no signal forces or deposits.
set root ara_tb.dut.i_ara_soc.i_system
set signals [list \
  $root.i_ara.i_dispatcher.state_q \
  $root.i_ara.i_dispatcher.ara_idle_i \
  $root.i_ara.i_dispatcher.store_pending_i \
  $root.i_ara.i_dispatcher.core_st_pending_o \
  $root.i_ara.i_vlsu.i_vstu.idle_o \
  $root.i_ara.i_vlsu.i_vstu.store_pending_o \
  $root.i_ara.i_vlsu.i_vstu.vinsn_queue_q \
  $root.i_ara.i_vlsu.i_vstu.issue_cnt_bytes_q \
  $root.i_ara.i_vlsu.i_vstu.axi_len_q \
  $root.i_ara.i_vlsu.i_vstu.stu_operand_valid \
  $root.i_ara.i_vlsu.i_vstu.mask_valid_q \
  $root.i_ara.i_vlsu.i_addrgen.state_q \
  $root.i_ara.i_vlsu.i_addrgen.axi_addrgen_state_q \
  $root.i_ara.i_vlsu.i_addrgen.axi_addrgen_queue_empty \
  $root.i_ara.i_vlsu.i_vldu.idle_o \
  $root.i_ariane.gen_accelerator.i_acc_dispatcher.acc_disp_loads_pending \
  $root.i_ariane.gen_accelerator.i_acc_dispatcher.acc_disp_stores_pending \
  $root.i_ariane.gen_accelerator.i_acc_dispatcher.acc_spec_loads_pending \
  $root.i_ariane.gen_accelerator.i_acc_dispatcher.acc_spec_stores_pending \
  $root.i_ariane.gen_accelerator.i_acc_dispatcher.wait_acc_store_q \
  $root.i_ariane.gen_accelerator.i_acc_dispatcher.acc_req_o \
  $root.i_ariane.gen_accelerator.i_acc_dispatcher.acc_resp_i]
run 22000 ns
foreach s $signals { puts "SNAP22000 $s"; if {[catch {get $s} value]} {puts "UNAVAILABLE $value"} else {puts $value} }
run 1000 ns
foreach s $signals { puts "SNAP23000 $s"; if {[catch {get $s} value]} {puts "UNAVAILABLE $value"} else {puts $value} }
quit
