set root [lindex $argv 0]
if {$root eq "" || [file exists $root]} {error "Supply new test directory"}
set script [file join [file dirname [info script]] repair_dual_control_fanout.tcl]
rename source real_source
proc source {args} {}
rename exit real_exit
proc exit {code} {return -code error -errorcode [list TEST_EXIT $code] "exit $code"}
foreach name {set_param open_checkpoint close_design report_timing_summary report_timing report_bus_skew} {
    proc $name {args} {}
}
proc get_param {args} {return {}}
proc dual_cdc_preflight {args} {if {$::scenario eq "bad_cdc"} {error "CDC failure"}}
proc get_cells {args} {
    if {$::scenario eq "missing"} {return {}}
    return [string range [lindex $args end] 8 end]
}
proc get_property {key obj} {
    switch $key {
        REF_NAME {return FDCE}
        ASYNC_REG {return [expr {$::scenario eq "sync"}]}
        DONT_TOUCH {return [expr {$::scenario eq "protected"}]}
        NAME {return $obj}
        default {error "Unexpected property"}
    }
}
proc get_pins {args} {return pin}
proc get_nets {args} {
    if {[lsearch -exact $args -hier]>=0} {return {net1 net2 net3 net4 net5 net6}}
    return net[incr ::net_index]
}
proc phys_opt_design {args} {lappend ::calls [lindex $args 0]}
proc write_checkpoint {args} {lappend ::calls checkpoint}
foreach scenario {healthy bad_cdc missing sync protected} {
    set out [file join $root $scenario]; file mkdir $out
    set ::argv [list input.dcp tools package $out]; set calls {}; set net_index 0
    catch {real_source $script} message options
    set expected [expr {$scenario ne "healthy"}]
    if {[dict get $options -errorcode] ne [list TEST_EXIT $expected]} {error "Bad result: $scenario / $options"}
    if {$expected && [llength $calls]} {error "Changed protected or invalid netlist"}
    if {!$expected && $calls ne {-force_replication_on_nets checkpoint -placement_opt checkpoint}} {error "Wrong sequence: $calls"}
    if {[llength [control_targets]]!=6} {error "Wrong target count"}
    if {[lindex [control_targets] 2] ne {i_dram_wrapper/gen_ethernet.i_eth_loader/i_loader/loader_bd_i/ddr_fabric/inst/s01_entry_pipeline/s01_mmu/inst/gen_endpoint.w_state_reg[0]}} {error "Lost index escaping"}
    puts "PASS $scenario"
}
