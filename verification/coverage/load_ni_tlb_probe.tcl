# Read-only control and external AXI observations. No stop, force or deposit.
set core ara_tb.dut.i_ara_soc.i_system.i_ariane
set load ${core}.ex_stage_i.lsu_i.i_load_unit
set objects [list ara_tb.clk ara_tb.rst_n ${core}.noc_req_o ${core}.noc_resp_i]
foreach name {state_q valid_i dtlb_hit_i stall_ni paddr_ni not_commit_time inflight_stores
              page_offset_matches_i commit_tran_id_i lsu_ctrl_i req_port_i req_port_o ex_i flush_i} {
    lappend objects ${load}.${name}
}
if {[catch {
    set fid [dump -file load-ni-tlb.vpd -type VPD]
    foreach path $objects {
        show -type $path
        set count [dump -add $path -fid $fid -depth 0 -aggregates]
        if {![string is integer -strict $count] || $count <= 0} {error "Unavailable object $path"}
        puts "LOAD_NI_PROBE_OBJECT $path"
    }
    puts "LOAD_NI_PROBE_READY"
    run
} failure]} {
    puts "LOAD_NI_PROBE_ERROR $failure"
    exit 1
}
