set ::eth_preflight_library_only 1
source [file join [file dirname [info script]] host_ethernet_preflight.tcl]
set root [lindex $argv 0]
set stream [open [file join $root requested_config.tsv] r]
set rows [split [string trim [read $stream]] \n]
close $stream
set expected [dict create]
foreach row $rows { lassign [split $row \t] key value; dict set expected $key $value }

proc assert {condition message} { if {![uplevel 1 [list expr $condition]]} { error $message } }
proc version {args} { if {$::mode eq "wrong_version"} { return 2023.2 }; return 2020.1 }
proc get_projects {args} { if {$::mode eq "existing_project"} { return user_project }; return {} }
proc set_param {key value} { assert {$key eq "board.repoPaths"} "Unexpected parameter $key" }
proc create_project {args} { lappend ::calls project; file mkdir [lindex $args 1] }
proc current_project {} { return $::project }
proc get_board_parts {args} { return xilinx.com:vcu118:part0:2.4 }
proc set_property {args} {
    if {[lindex $args 0] eq "-dict"} {
        set ::effective [lindex $args 1]
        if {$::mode eq "ignored_property"} { dict set ::effective CONFIG.ENABLE_LVDS false }
        if {$::mode eq "normalized_property"} {
            dict set ::effective CONFIG.ENABLE_LVDS 1
            dict set ::effective CONFIG.lvdsclkrate 625.000
        }
    }
}
proc get_ipdefs {args} {
    if {$::mode eq "missing_ip"} { return {} }
    return [string map {* 7.1} [lindex $args end]]
}
proc get_ips {args} { return eth_j10 }
proc create_ip {args} {
    lappend ::calls create_ip
    assert {[lindex $args 1] eq "xilinx.com:ip:axi_ethernet:7.1"} "Wrong IP"
}
proc list_property {object} {
    if {$object eq "eth_j10"} {
        set keys [dict keys $::expected]
        if {$::mode eq "unsupported_property"} { set keys [lsearch -all -inline -not -exact $keys CONFIG.ENABLE_LVDS] }
        return $keys
    }
    return {VLNV LICENSE}
}
proc get_property {key object} {
    switch $key {
        FILE_TYPE { return Verilog }
        NAME { return $object }
        LICENSE { return "not validated by mock" }
        VLNV { return $object }
        default { if {[dict exists $::effective $key]} { return [dict get $::effective $key] }; return default }
    }
}
proc list_property_value {args} { return {} }
proc report_ip_status {args} {
    lappend ::calls license
    if {$::mode eq "status_failure"} { error "mock report failure" }
    set f [open [lindex $args end] w]
    puts $f "Mock missing/evaluation license: not a hardware authorization"
    close $f
}
proc generate_target {args} {
    lappend ::calls generate
    if {$::mode eq "generation_failure"} { error "mock generation failure" }
}
proc open_example_project {args} {
    lappend ::calls example
    assert {[lsearch -exact $args -in_process] >= 0} "Would spawn GUI"
    assert {[lsearch -exact $args -force] < 0} "Must not overwrite example"
    if {$::mode eq "example_failure"} { error "mock example failure" }
    set ::project eth_j10_example
}
proc get_files {args} {
    if {$::mode eq "missing_constraints"} { return top.v }
    return {top.v example.xdc}
}
proc close_project {} { lappend ::calls close }

foreach mode {success normalized_property wrong_version existing_project missing_ip unsupported_property ignored_property status_failure generation_failure example_failure missing_constraints} {
    set output [file join $root $mode]
    file mkdir $output
    file copy [file join $root requested_config.tsv] $output
    set effective [dict create]
    set project eth_preflight
    set calls {}
    set result [eth_preflight::run $output board_repo]
    set f [open [file join $output stages.tsv] r]
    set status [read $f]
    close $f
    if {$mode in {success normalized_property}} {
        assert {$result == 1} "Success rejected: $status"
        assert {[string first FAIL $status] < 0 && [string first SKIP $status] < 0} "Incomplete success"
    } else {
        assert {$result == 0} "Failure accepted: $mode"
        assert {[string first FAIL $status] >= 0} "Failure reason missing: $mode"
    }
    if {$mode in {wrong_version existing_project missing_ip unsupported_property ignored_property}} {
        assert {[lsearch -exact $calls generate] < 0} "Unsafe generation: $mode"
    }
    if {$mode eq "existing_project"} {
        assert {[llength $calls] == 0} "Existing project touched"
    }
    if {$mode eq "generation_failure"} {
        assert {[lsearch -exact $calls example] < 0} "Example attempted after failed generation"
        assert {[llength [lsearch -all -exact $calls license]] == 2} "Post-failure diagnostics missing"
    }
    set f [open [file join $output preflight.rpt] r]
    set report [read $f]
    close $f
    assert {[string first "PREFLIGHT_COMPLETE" $report] >= 0} "Missing completion marker"
    assert {[string first "BITSTREAM_LICENSE_VERIFIED=false" $report] >= 0} "Incorrect license claim"
}
puts "PASS: Ethernet preflight (11 scenarios, no synthesis or hardware commands mocked)"
