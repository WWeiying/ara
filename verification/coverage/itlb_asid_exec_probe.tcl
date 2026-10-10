# Observation only; no DUT or TB force, stop or reset.
set itlb ara_tb.dut.i_ara_soc.i_system.i_ariane.ex_stage_i.lsu_i.gen_mmu.i_cva6_mmu.i_itlb
set core ara_tb.dut.i_ara_soc.i_system.i_ariane
set objects [list ara_tb.clk ara_tb.rst_n ${core}.noc_req_o ${core}.noc_resp_i]
foreach name {update_i replace_en lu_hit_o lu_access_i lu_asid_i lu_vaddr_i plru_tree_q flush_i s_st_enbl_i} {
    lappend objects ${itlb}.${name}
}
if {[catch {
    set fid [dump -file itlb-exec.vpd -type VPD]
    foreach path $objects {
        show -type $path
        set count [dump -add $path -fid $fid -depth 0 -aggregates]
        if {![string is integer -strict $count] || $count <= 0} {error "Unavailable object $path"}
        puts "ITLB_EXEC_OBJECT $path"
    }
    puts "ITLB_EXEC_READY"
    run
} failure]} {
    puts "ITLB_EXEC_ERROR $failure"
    exit 1
}
