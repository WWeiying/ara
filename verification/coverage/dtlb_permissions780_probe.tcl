# Read-only focused permission/replacement observation. No force or state writes.
set dtlb ara_tb.dut.i_ara_soc.i_system.i_ariane.ex_stage_i.lsu_i.gen_mmu.i_cva6_mmu.i_dtlb
set mmu ara_tb.dut.i_ara_soc.i_system.i_ariane.ex_stage_i.lsu_i.gen_mmu.i_cva6_mmu
set load ara_tb.dut.i_ara_soc.i_system.i_ariane.ex_stage_i.lsu_i.i_load_unit
set objects [list ara_tb.clk ara_tb.rst_n ara_tb.dut.i_ara_soc.i_system.i_ara_commit_monitor.cycle_q]
foreach name {update_i replace_en lu_hit lu_hit_o lu_access_i lu_vaddr_i lu_asid_i plru_tree_q flush_i s_st_enbl_i content_q tags_q asid_to_be_flushed_i vaddr_to_be_flushed_i} {
    lappend objects ${dtlb}.${name}
}
foreach name {pop_ld_o valid_i translation_req_o dtlb_hit_i vaddr_o paddr_i dtlb_ppn_i flush_i ex_i} {
    lappend objects ${load}.${name}
}
foreach name {ld_st_priv_lvl_i sum_i mxr_i lsu_is_store_i lsu_req_i lsu_req_q lsu_vaddr_i lsu_valid_o lsu_exception_o dtlb_pte_q dtlb_hit_q} {
    lappend objects ${mmu}.${name}
}
if {[catch {
    set fid [dump -file dtlb-permissions.vpd -type VPD]
    foreach path $objects {
        show -type $path
        set count [dump -add $path -fid $fid -depth 0 -aggregates]
        if {![string is integer -strict $count] || $count <= 0} {error "Unavailable object $path"}
        puts "DTLB_PERMISSIONS_OBJECT $path"
    }
    puts "DTLB_PERMISSIONS_READY"
    run
} failure]} {
    puts "DTLB_PERMISSIONS_ERROR $failure"
    exit 1
}
