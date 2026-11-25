# Read only the mapped chip, not the RTL. Run in a fresh report directory.
set flow $env(OLD_FLOW)
source $flow/global_scripts/synopsys_dc.setup.env
set_app_var target_library $STD_LIBRARY_LIST(BWP12T,tc)
set_app_var synthetic_library dw_foundation.sldb
set libs "* $target_library $synthetic_library"
foreach key [array names IP_LIBRARY_LIST *,tc] {append libs " $IP_LIBRARY_LIST($key)"}
set_app_var link_library $libs
set_host_options -max_cores 4
read_ddc $flow/outputs/ara_soc_dc.ddc
current_design ara_soc
if {![link]} {exit 1}
set ara i_system/i_ara
foreach {name endpin} [list \
    resident $ara/gen_lanes_1__i_lane/gen_resident_pv_i_resident_pv/accum_q_reg_1__60_/D \
    vmfpu $ara/gen_lanes_1__i_lane/i_vfus/i_vmfpu/result_queue_q_reg_1__wdata__63_/D \
    akv $ara/i_vlsu/i_akv_engine/v_read_address_q_reg_63_/D \
    qbs_acc $ara/i_vlsu/i_qbs_engine/i_compute_engine/i_fp_accumulator/accumulator_data_q_reg_3__4__12_/D] {
    set ep [get_pins -quiet $endpin]
    if {[sizeof_collection $ep] != 1} {error "missing endpoint: $endpin"}
    redirect ${name}.tim {report_timing -to $ep -group clk_i -delay_type max -max_paths 1 -nosplit -significant_digits 4}
}
puts "SCOPED_REPORT_COMPLETE"
exit
