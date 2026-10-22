# Read-only focused VPD. No memories, forces, deposits or RTL additions.
set root ara_tb.dut.i_ara_soc.i_system.i_ara
set required [list ara_tb.clk ara_tb.rst_n]
set optional [list]
for {set lane 0} {$lane < 4} {incr lane} {
    set scope [format {%s.gen_lanes[%d].i_lane} $root $lane]
    set req ${scope}.i_operand_requester
    foreach name {operand_request_i operand_request_valid_i operand_request_ready_o
                  requester_metadata_q operand_payload operand_issued_o vrf_req_o
                  vrf_addr_o vrf_wen_o vrf_tgt_opqueue_o} {
        lappend required ${req}.${name}
    }
    foreach name {rdata rdata_valid_q tgt_opqueue_q} {
        lappend optional ${scope}.i_vrf.${name}
    }
}
foreach name {vinsn_issue iteration_cnt_q masku_operand_vd_seq masku_operand_vd_valid
              masku_operand_alu_seq alu_result_compressed_seq result_queue_active_mask_seq
              background_data_init_seq alu_result_vm_m out_vrf_word_valid masku_result_req_o
              masku_result_wdata_o masku_result_be_o masku_result_addr_o} {
    lappend optional ${root}.i_masku.${name}
}
if {[catch {
    set fid [dump -file mask-compare-known.vpd -type VPD]
    foreach path $required {
        show -type $path
        set count [dump -add $path -fid $fid -depth 0 -aggregates]
        if {![string is integer -strict $count] || $count <= 0} {error "Unavailable required object $path"}
        puts "MC_PROBE_REQUIRED $path"
    }
    foreach path $optional {
        if {[catch {
            show -type $path
            set count [dump -add $path -fid $fid -depth 0 -aggregates]
            if {![string is integer -strict $count] || $count <= 0} {error "Unavailable object"}
        } unavailable]} {
            puts "MC_PROBE_OPTIONAL_UNAVAILABLE $path [string map [list \n { } \r { }] $unavailable]"
        } else {
            puts "MC_PROBE_OPTIONAL_CAPTURED $path"
        }
    }
    puts MC_PROBE_READY
    run
} failure]} {
    puts "MC_PROBE_ERROR $failure"
    exit 1
}
