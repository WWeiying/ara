# Observation only; no force, reset or internal-state writes.
set dtlb ara_tb.dut.i_ara_soc.i_system.i_ariane.ex_stage_i.lsu_i.gen_mmu.i_cva6_mmu.i_dtlb
set objects [list ara_tb.clk ara_tb.rst_n]
foreach name {update_i replace_en lu_hit lu_hit_o lu_access_i lu_vaddr_i lu_asid_i plru_tree_q flush_i content_q tags_q} {
    lappend objects ${dtlb}.${name}
}
if {[catch {
    set fid [dump -file dtlb-ppn-swap.vpd -type VPD]
    foreach path $objects {
        show -type $path
        set count [dump -add $path -fid $fid -depth 0 -aggregates]
        if {![string is integer -strict $count] || $count <= 0} {error "Unavailable object $path"}
        puts "DTLB_PPN_OBJECT $path"
    }
    puts "DTLB_PPN_READY"
    run
} failure]} {
    puts "DTLB_PPN_ERROR $failure"
    exit 1
}
