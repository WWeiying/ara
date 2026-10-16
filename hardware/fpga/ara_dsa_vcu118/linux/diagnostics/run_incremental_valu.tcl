# Keep the repaired netlist authoritative; reuse only reference physical data.
namespace eval valu_incremental {}
proc valu_incremental::stage {out name} {
    set f [open [file join $out stage.txt] w]
    puts $f $name
    close $f
    puts "INCREMENTAL_STAGE $name"
    flush stdout
}
proc valu_incremental::run {optimized reference package out} {
    foreach p [list $optimized $reference] {
        if {![file isfile $p]} {error "Missing checkpoint $p"}
    }
    if {![file isdirectory $out]} {error "Missing output directory"}
    foreach script {common.tcl run_support.tcl} {
        uplevel #0 [list source [file join $package scripts $script]]
    }
    set_param general.maxThreads 8
    stage $out opening_current_netlist
    open_checkpoint $optimized
    stage $out incremental_matching
    read_checkpoint -incremental $reference
    report_incremental_reuse -file [file join $out reuse_before.rpt]
    stage $out incremental_placement
    place_design
    write_checkpoint [file join $out placed.dcp]
    stage $out incremental_routing
    route_design
    # Preserve the result even if subsequent timing or audit fails.
    write_checkpoint [file join $out routed.dcp]
    stage $out reports
    set dir [file join $out reports]
    file mkdir $dir
    report_incremental_reuse -file [file join $out reuse_after.rpt]
    report_route_status -file [file join $dir route_status.rpt]
    foreach check {ROUTED_FULLY ERRORS_IN_ROUTES} expected {1 0} {
        set value [report_route_status -boolean_check $check]
        if {![string is boolean -strict $value] || [expr {!!$value}] != $expected} {
            error "Route integrity failed: $check=$value"
        }
    }
    require_no_multiple_drivers $dir
    write_reports $dir true
    fpga_run::require_timing $dir
    # Passing setup/hold/pulse is not CDC, functional or board acceptance.
    stage $out timing_passed_requires_full_audit
    close_design
}
if {![info exists ::valu_incremental_test_mode]} {
    if {[catch {
        if {[llength $argv] != 4} {error "Expected new_opt old_reference package output"}
        valu_incremental::run {*}$argv
    } message]} {
        puts stderr $::errorInfo
        if {[llength $argv] == 4 && [file isdirectory [lindex $argv 3]]} {
            valu_incremental::stage [lindex $argv 3] failed
        }
        exit 1
    }
    exit 0
}
