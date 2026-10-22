# Read-only observation; no force, reset, software hint or DUT-state writes.
set dtlb ara_tb.dut.i_ara_soc.i_system.i_ariane.ex_stage_i.lsu_i.gen_mmu.i_cva6_mmu.i_dtlb
set load ara_tb.dut.i_ara_soc.i_system.i_ariane.ex_stage_i.lsu_i.i_load_unit
set objects [list ara_tb.clk ara_tb.rst_n ara_tb.dut.i_ara_soc.i_system.i_ara_commit_monitor.cycle_q]
foreach name {update_i replace_en lu_hit lu_hit_o lu_access_i lu_vaddr_i lu_asid_i plru_tree_q flush_i s_st_enbl_i content_q tags_q} {
    lappend objects ${dtlb}.${name}
}
foreach name {pop_ld_o valid_i translation_req_o dtlb_hit_i vaddr_o paddr_i dtlb_ppn_i flush_i ex_i} {
    lappend objects ${load}.${name}
}
if {[catch {
    set fid [dump -file dtlb-ppn-swap.vpd -type VPD]
    foreach path $objects {
        show -type $path
        set count [dump -add $path -fid $fid -depth 0 -aggregates]
        if {![string is integer -strict $count] || $count <= 0} {error "Unavailable object $path"}
        puts "DTLB_PPN1200_OBJECT $path"
    }
    puts "DTLB_PPN1200_READY"
    run
} failure]} {
    puts "DTLB_PPN1200_ERROR $failure"
    exit 1
}
