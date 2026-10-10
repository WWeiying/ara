# Exact AKV read-owner profile; no force or source/image changes.
if {[catch {
    set base ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_akv_engine.i_read_engine
    set wave akv-canonical-kfault.vpd
    set fid [dump -file $wave -type VPD]
    foreach name {
        clk_i rst_ni en_ld_st_translation_i plan_state_q
        range_valid_i range_ready_o range_vaddr_i range_bytes_i range_tag_i
        mmu_req_o mmu_vaddr_o mmu_valid_i mmu_paddr_i
        mmu_exception_valid_i mmu_exception_i physical_check_valid_o
        physical_check_addr_o physical_range_allowed_i planner_fault_event
        planner_fault_kind planner_fault_vaddr planner_fault_tag fault_pending_q
        fault_kind_o fault_vaddr_o fault_mmu_exception_o
        fault_valid_o fault_ready_i burst_fifo_count_q range_fifo_count_q
        response_drain_q axi_ar_valid_o axi_ar_ready_i axi_ar_o.addr
        axi_r_valid_i axi_r_ready_o axi_r_i.last axi_r_i.resp
        completion_valid_o completion_ready_i ar_stalled_q
        planner_fault_mmu_exception response_fault_event
    } {
        set object ${base}.${name}
        show -type $object
        set added [dump -add $object -fid $fid -depth 0 -aggregates]
        if {![string is integer -strict $added] || $added <= 0} {
            error "Missing exact object $object"
        }
        puts "AKV_KFAULT_OBJECT $object"
    }
    puts "AKV_KFAULT_PROBE_READY"
    while {1} {
        run 100 ns
        if {[file exists $wave] && [file size $wave] >= 132120576} {
            error "Focused VPD capacity boundary; reject incomplete capture"
        }
    }
} failure]} {
    puts stderr "AKV_KFAULT_PROBE_REJECT $failure"
    exit 1
}
