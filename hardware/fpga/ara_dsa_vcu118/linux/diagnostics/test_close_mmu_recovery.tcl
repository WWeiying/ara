set root [lindex $argv 0]
if {$root eq "" || [file exists $root]} {error "Use a new test directory"}
file mkdir $root
set script [file join [file dirname [info script]] close_mmu_recovery.tcl]
foreach mode {pass wrong_source wrong_count worse_slack bad_route blackbox timing_fail} {
    set i [interp create]
    interp eval $i [list set mode $mode]
    interp eval $i [list set argv [list input.dcp package $root]]
    interp eval $i {
        rename source real_source
        proc source {path} {}
        proc set_param {args} {}
        proc get_param {args} {return {}}
        proc get_board_parts {args} {return board}
        proc set_msg_config {args} {}
        proc open_checkpoint {args} {}
        proc get_cells {args} {expr {$::mode eq "blackbox" ? "bad" : ""}}
        proc report_route_status {args} {
            if {[lindex $args 1] eq "ROUTED_FULLY"} {return [expr {$::mode ne "bad_route"}]}
            return 0
        }
        proc report_timing_summary {args} {}
        proc get_timing_paths {args} {expr {$::mode eq "wrong_count" ? "p1" : "p1 p2"}}
        proc get_property {name path} {
            switch $name {
                STARTPOINT_PIN {
                    if {$::mode eq "wrong_source"} {return different/C}
                    return {i_dram_wrapper/i_ui_rstgen/i_rstgen_bypass/synch_regs_q_reg[3]/C}
                }
                ENDPOINT_PIN {return i_dram_wrapper/gen_cdc.i_axi_cdc_mig/test/CLR}
                SLACK {expr {$::mode eq "worse_slack" ? -0.1 : -0.007}}
            }
        }
        proc report_timing {args} {}
        proc phys_opt_design {args} {set ::optimized 1}
        proc route_design {args} {}
        proc write_checkpoint {args} {}
        proc report_bus_skew {args} {}
        proc close_design {} {}
        namespace eval fpga_run {}
        proc fpga_run::require_timing {args} {
            if {$::mode eq "timing_fail"} {error "timing failed"}
        }
        proc exit {code} {return -code error "EXIT=$code"}
    }
    catch {interp eval $i [list real_source $script]} result
    set expected [expr {$mode eq "pass" ? 0 : 1}]
    if {$result ne "EXIT=$expected"} {error "$mode unexpected result: $result"}
    set optimized [interp eval $i {info exists ::optimized}]
    if {$optimized != ($mode in {pass timing_fail})} {error "$mode optimization gate failed"}
    interp delete $i
}
puts "PASS: seven recovery closure gate scenarios"
