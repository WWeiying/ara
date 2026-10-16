set ::stall_capture_test 1
source [file join [file dirname [info script]] capture_stall_ila.tcl]
proc open_hw_manager {} { lappend ::events manager }
proc connect_hw_server {args} { lappend ::events server }
proc get_hw_targets {} { return $::targets }
proc open_hw_target {target} { lappend ::events target }
proc get_hw_devices {args} { return dev }
proc current_hw_device {dev} {}
proc set_property {property value object} { lappend ::properties [list $property $value] }
proc refresh_hw_device {dev} {}
proc get_hw_ilas {args} { return $::cores }
proc report_property {args} { return mock_properties }
proc create_hw_probe {flag mapping name core} {
    if {$flag ne "-map" || $mapping ne [format {probe0[%d:0]} [expr {$::width-1}]] ||
        $name ne [format {stall_raw[%d:0]} [expr {$::width-1}]]} {
        error "Unexpected raw probe map"
    }
}
proc run_hw_ila {flag core} {
    if {$flag ne "-trigger_now"} { error "Must capture immediately" }
    lappend ::events arm
}
proc wait_on_hw_ila {flag timeout core} {
    if {$flag ne "-timeout" || $timeout != 0.5} { error "Capture must be bounded" }
    if {$::timeout} { error "Capture timeout" }
}
proc upload_hw_ila_data {core} { lappend ::events upload; return data }
proc write_hw_ila_data {args} { lappend ::events export }
proc close_hw_target {target} { lappend ::events close_target }
proc disconnect_hw_server {} { lappend ::events disconnect }
proc close_hw_manager {} { lappend ::events close_manager }
proc assert {expression message} {
    if {![uplevel 1 [list expr $expression]]} { error $message }
}
set f [file tempfile root]
close $f
file delete $root
file mkdir $root
set ltx [file join $root matched.ltx]
close [open $ltx w]
try {
    foreach scenario {pass scalar_pass wrong_target missing_core ambiguous_core timeout bad_width} {
        set ::events {}
        set ::properties {}
        set ::targets localhost:3121/xilinx_tcf/Digilent/210308A3B79F
        set ::cores ila
        set ::timeout 0
        set ::width 579
        switch -- $scenario {
            wrong_target { set ::targets localhost:3121/xilinx_tcf/Digilent/other }
            missing_core { set ::cores {} }
            ambiguous_core { set ::cores {ila other_ila} }
            timeout { set ::timeout 1 }
            scalar_pass { set ::width 416 }
            bad_width { set ::width 0 }
        }
        set out [file join $root $scenario]
        set error [catch {stall_capture::run $ltx $out $::width} message]
        assert {$error == ($scenario ni {pass scalar_pass})} "Wrong outcome: $scenario $message"
        if {$scenario eq "bad_width"} {
            assert {$::events eq {}} "Invalid width accessed board"
            continue
        }
        assert {[lindex $::events end] eq "close_manager"} "Connection not cleaned up"
        if {$scenario in {pass scalar_pass}} {
            assert {[file exists [file join $out complete.txt]]} "Missing completion"
            assert {$::events eq {manager server target arm upload export export export close_target disconnect close_manager}} "Unexpected capture operations"
        } else {
            assert {![file exists [file join $out complete.txt]]} "Failure marked complete"
            assert {[lsearch -exact $::events upload] == -1} "Uploaded after failed precondition"
        }
    }
    puts "STALL_CAPTURE_FLOW_TESTS_PASS (mock commands, no board access)"
} finally {
    file delete -force $root
}
