set scripts [file normalize [file join [file dirname [info script]] .. scripts]]
set scratch [file normalize [lindex $argv 0]]
if {[llength $argv] != 1 || [file exists $scratch]} { error "Pass a new scratch directory" }
file mkdir $scratch
source $scripts/common.tcl
proc assert {condition message} {
    if {![uplevel 1 [list expr $condition]]} { error "ASSERT: $message" }
}
proc put {path data} { set f [open $path w]; puts $f $data; close $f }
proc create_project {args} { error "No project creation allowed" }
proc current_project {args} { return "" }
proc open_checkpoint {path} { set ::opened $path }
proc close_design {} { incr ::closed }
proc get_pins {args} {
    set pin [lindex $args end]
    set host [expr {$::fpga_profile ne "baseline"}]
    if {$::case eq "wrong_profile"} { set host [expr {!$host}] }
    if {[string match gen_host* $pin]} { return [expr {$host ? $pin : {}}] }
    return [expr {$::fpga_profile eq "dual_ddr" ? $pin : {}}]
}
proc require_no_multiple_drivers {dir} {
    lappend ::gates drivers
    if {$::case eq "drivers"} { error "Multiple drivers remain" }
}
proc write_reports {dir reject_loops} {
    assert {$reject_loops} "loop and physical checks required"
    assert {$dir eq [file join $::out reports]} "reports isolated in output"
    lappend ::gates reports
    if {$::case eq "reports"} { error "CDC/loop check failed" }
}
proc get_timing_paths {args} {
    if {[string match *no_timing $::case]} { return {} }
    return [lindex $args 2]
}
proc get_property {key object} {
    assert {$key eq "SLACK"} "read measured slack"
    if {[string match *negative $::case] && $object eq "min"} { return -0.01 }
    if {$::case eq "infinite"} { return inf }
    return 0.5
}
proc write_debug_probes {path} { put $path probes }
proc write_bitstream {path} {
    lappend ::gates bitgen
    if {[string match *native_drc $::case]} { error "Vivado bitgen DRC failed" }
    put $path bitstream
}
# Keep the tested gate mocks above when the entry point sources common.tcl.
rename source real_source
proc source {path} {
    if {[file tail $path] eq "common.tcl"} {
        uplevel #0 [list real_source $::scripts/config.tcl]
    } else { uplevel 1 [list real_source $path] }
}
put $scratch/ara_dsa_vcu118_routed.dcp checkpoint
foreach profile {baseline host dual_ddr} {
    set ::env(ARA_FPGA_PROFILE) $profile
    foreach case {healthy wrong_profile drivers reports no_timing negative infinite native_drc audited_healthy audited_no_timing audited_negative audited_native_drc} {
        set gates {}; set closed 0; set opened ""
        set out $scratch/${profile}_$case
        set mode [expr {[string match audited_* $case] ? "audited" : "full"}]
        set argv [list $scratch/ara_dsa_vcu118_routed.dcp $out $mode]
        set failed [catch {source $scripts/write_profile_bit.tcl} message]
        assert {$failed == ($case ni {healthy audited_healthy})} "$profile/$case: $message"
        assert {$closed == 1} "always close design, including gate failure"
        if {$case in {healthy audited_healthy}} {
            set expected [expr {$mode eq "full" ? {drivers reports bitgen} : {drivers bitgen}}]
            assert {$gates eq $expected} "required gates before bitgen"
            assert {[file size $out/ara_dsa_vcu118.bit] > 0} "bit produced"
        } else {
            assert {![file exists $out/ara_dsa_vcu118.bit]} "no successful bit on failure"
            if {$case ni {native_drc audited_native_drc}} { assert {"bitgen" ni $gates} "gate failure blocks bitgen" }
        }
    }
}
unset ::env(ARA_FPGA_PROFILE)
puts "PASS: 36 profile bitgen gate scenarios (mocked, no synthesis)"
