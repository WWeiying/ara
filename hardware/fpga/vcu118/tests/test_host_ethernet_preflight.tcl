set ::eth_preflight_library_only 1
source [file join [file dirname [info script]] host_ethernet_preflight.tcl]
set root [lindex $argv 0]
set repository [file join $root {board repo}]
file mkdir [file join $repository vcu118 2.4]
foreach name {board.xml part0_pins.xml preset.xml} {
    set stream [open [file join $repository vcu118 2.4 $name] w]
    puts $stream "fixture"
    close $stream
}
set stream [open [file join $root requested_config.tsv] r]
set rows [split [string trim [read $stream]] \n]
close $stream
set expected [dict create]
foreach row $rows { lassign [split $row \t] key value; dict set expected $key $value }

proc assert {condition message} { if {![uplevel 1 [list expr $condition]]} { error $message } }
proc version {args} { if {$::mode eq "wrong_version"} { return 2023.2 }; return 2020.1 }
proc get_projects {args} { if {$::mode eq "existing_project"} { return user_project }; return {} }
proc set_param {key value} {
    assert {$key eq "board.repoPaths"} "Unexpected parameter $key"
    assert {[llength $value] == 1} "Expected one repository"
    assert {[file isdirectory [lindex $value 0]]} "Nonexistent board repository"
    assert {[lindex $value 0] eq [file normalize $::repository]} "Path not normalized"
    assert {[string first "\\" [lindex $value 0]] < 0} "Backslash passed to board parser"
    set ::repo_param $value
}
proc get_param {key} {
    assert {$key eq "board.repoPaths"} "Unexpected parameter $key"
    return $::repo_param
}
proc create_project {args} { lappend ::calls project; file mkdir [lindex $args 1] }
proc current_project {} { return $::project }
proc get_board_parts {args} {
    if {$::mode eq "missing_board_definition"} { return {} }
    return xilinx.com:vcu118:part0:2.4
}
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
    # Catalog observed in uploaded evidence 6f546884471657d46d4b6ba10b646f743174f264.
    # Filter real entries, never fabricate an object for an unmatched exact query.
    set catalog {
        xilinx.com:ip:axi_ethernet:7.2
        xilinx.com:ip:gig_ethernet_pcs_pma:16.2
        xilinx.com:ip:tri_mode_ethernet_mac:9.0
    }
    if {$::mode eq "old_catalog"} { set catalog [lreplace $catalog 0 0 xilinx.com:ip:axi_ethernet:7.1] }
    if {$::mode eq "future_catalog"} { set catalog [lreplace $catalog 0 0 xilinx.com:ip:axi_ethernet:8.0] }
    if {$::mode eq "multiple_catalog"} { lappend catalog xilinx.com:ip:axi_ethernet:8.0 }
    if {$::mode eq "duplicate_catalog"} { lappend catalog xilinx.com:ip:axi_ethernet:7.2 }
    return [lsearch -all -inline -glob $catalog [lindex $args end]]
}
proc get_ips {args} { return eth_j10 }
proc create_ip {args} {
    lappend ::calls create_ip
    set vlnv [lindex $args 1]
    assert {$vlnv eq "xilinx.com:ip:axi_ethernet:7.2"} "Wrong IP"
    assert {[llength [get_ipdefs -all -quiet $vlnv]] == 1} "IP is not uniquely present in catalog"
}
proc list_property {object} {
    if {$object eq "eth_j10"} {
        set keys [dict keys $::expected]
        if {$::mode eq "unsupported_property"} { set keys [lsearch -all -inline -not -exact $keys CONFIG.ENABLE_LVDS] }
        return $keys
    }
    return {VLNV REQUIRES_LICENSE}
}
proc get_property {key object} {
    switch $key {
        FILE_TYPE { return Verilog }
        NAME { return $object }
        REQUIRES_LICENSE { return [expr {$object ne "xilinx.com:ip:gig_ethernet_pcs_pma:16.2"}] }
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
    if {$::mode eq "stdout_before_example"} { close stdout }
}
proc open_example_project {args} {
    lappend ::calls example
    assert {[lsearch -exact $args -in_process] >= 0} "Would spawn GUI"
    assert {[lsearch -exact $args -force] < 0} "Must not overwrite example"
    assert {[lsearch -exact $args -quiet] < 0} "Must not suppress example errors"
    if {$::mode eq "example_failure"} { error "mock example failure" }
    set ::project eth_j10_example
    if {$::mode eq "stdout_chan_closed_in_example"} {
        chan close stdout
        puts stdout "must fail"
    }
    if {$::mode in {stdout_closed_in_example stdout_closed_on_success}} {
        close stdout
        if {$::mode eq "stdout_closed_in_example"} { puts stdout "must fail" }
    }
}
proc get_files {args} {
    if {$::mode eq "missing_constraints"} { return top.v }
    return {top.v example.xdc}
}
proc close_project {} { lappend ::calls close }

set modes {success normalized_property wrong_version existing_project missing_repository missing_board_file missing_board_definition missing_ip old_catalog future_catalog multiple_catalog duplicate_catalog unsupported_property ignored_property status_failure generation_failure example_failure missing_constraints}
if {[llength $argv] == 2} { set modes [list [lindex $argv 1]] }
foreach mode $modes {
    set output [file join $root $mode]
    file mkdir $output
    file copy [file join $root requested_config.tsv] $output
    set effective [dict create]
    set project eth_preflight
    set calls {}
    set selected_repository [file join $repository .]
    if {$mode eq "missing_repository"} { set selected_repository [file join $repository absent] }
    if {$mode eq "missing_board_file"} {
        set selected_repository [file join $repository empty]
        file mkdir $selected_repository
    }
    set result [eth_preflight::run $output $selected_repository]
    foreach command {::close ::chan} {
        assert {[trace info execution $command] eq {}} "Example trace leaked: $command"
    }
    set f [open [file join $output stages.tsv] r]
    set status [read $f]
    close $f
    if {$mode in {success normalized_property multiple_catalog}} {
        assert {$result == 1} "Success rejected: $status"
        assert {[string first FAIL $status] < 0 && [string first SKIP $status] < 0} "Incomplete success"
    } else {
        assert {$result == 0} "Failure accepted: $mode"
        assert {[string first FAIL $status] >= 0} "Failure reason missing: $mode"
    }
    if {$mode in {wrong_version existing_project missing_repository missing_board_file missing_board_definition missing_ip old_catalog future_catalog duplicate_catalog unsupported_property ignored_property}} {
        assert {[lsearch -exact $calls generate] < 0} "Unsafe generation: $mode"
    }
    if {$mode in {existing_project missing_repository missing_board_file}} {
        assert {[llength $calls] == 0} "Existing project touched"
    }
    if {$mode in {missing_ip old_catalog future_catalog duplicate_catalog}} {
        assert {[lsearch -exact $calls create_ip] < 0} "IP created without supported unique definition"
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
    if {$mode eq "success"} {
        foreach phase {startup before_example after_example} {
            assert {[string first "CONSOLE $phase STDOUT_OK=1" $report] >= 0} "Missing channel evidence: $phase"
        }
        assert {[string first "BOARD_REPO_NORMALIZED [file normalize $repository]" $report] >= 0} "Missing path evidence"
        assert {[string first "EXISTS=1" $report] >= 0} "Missing file existence evidence"
        foreach vlnv {axi_ethernet:7.2 gig_ethernet_pcs_pma:16.2 tri_mode_ethernet_mac:9.0} {
            assert {[string first "xilinx.com:ip:$vlnv" $report] >= 0} "Observed catalog entry missing: $vlnv"
        }
        assert {[string first "SELECTED_AXI_IP xilinx.com:ip:axi_ethernet:7.2" $report] >= 0} "Selected IP missing"
        assert {[string first "REQUIRES_LICENSE = 1" $report] >= 0} "Catalog license requirement lost"
    }
    if {$mode eq "missing_board_definition"} {
        assert {[string first "AVAILABLE_VCU118_BOARDS" $report] >= 0} "Missing board discovery evidence"
    }
    if {$mode eq "example_failure"} {
        assert {[string first "mock example failure" $report] >= 0} "Original error lost"
        assert {[string first "CONSOLE after_example STDOUT_OK=1" $report] >= 0} "Missing failure channel check"
        assert {[string first "EXAMPLE_RETURN_CODE 1" $report] >= 0} "Missing failure code"
    }
    if {$mode eq "stdout_before_example"} {
        assert {[lsearch -exact $calls example] < 0} "Example called with missing stdout"
        assert {[string first "CONSOLE before_example STDOUT_OK=0" $report] >= 0} "Missing pre-example channel failure"
    }
    if {$mode in {stdout_closed_in_example stdout_closed_on_success stdout_chan_closed_in_example}} {
        assert {[string first "CONSOLE after_example STDOUT_OK=0" $report] >= 0} "Missing post-example channel failure"
        assert {[string first "STDOUT_CLOSE " $report] >= 0} "Missing stdout close trace"
        assert {[string first "STDOUT_CLOSE_FRAME" $report] >= 0} "Missing close call site"
        assert {[string first "example\tFAIL" $status] >= 0} "Example accepted with lost stdout"
        assert {[string first "example_inventory\tSKIP" $status] >= 0} "Inventoried failed example"
    }
}
puts stderr "PASS: Ethernet preflight ([llength $modes] scenarios, no synthesis or hardware commands mocked)"
