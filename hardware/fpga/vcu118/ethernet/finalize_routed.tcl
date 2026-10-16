# Checkpoint-only repair. No source import or constraint reapplication.
proc finalize_routed {package checkpoint out} {
    source [file join $package scripts common.tcl]
    require_vivado
    if {[current_project -quiet] ne ""} {error "Fresh session required"}
    if {![file isfile $checkpoint] || ![file size $checkpoint]} {error "Missing checkpoint"}
    if {[file exists $out]} {error "Output must be new"}
    file mkdir $out
    set code [catch {
        open_checkpoint $checkpoint
        check_pulsed_latches [file join $out before] false
        route_design -finalize
        write_checkpoint [file join $out ara_dsa_vcu118_routed.dcp]
        check_pulsed_latches [file join $out after]
        foreach check {ROUTED_FULLY ERRORS_IN_ROUTES} expected {1 0} {
            set value [report_route_status -boolean_check $check]
            if {![string is boolean -strict $value] || $value != $expected} {
                error "Routing rejected: $check=$value"
            }
        }
    } result options]
    set close_code [catch {close_project} close_result close_options]
    if {$code} {return -options $options $result}
    if {$close_code} {return -options $close_options $close_result}
}
if {![info exists finalize_test_mode]} {
    if {[llength $argv] != 3} {error "Expected package checkpoint new_output"}
    finalize_routed {*}$argv
}
