namespace eval fpga_audit {}

proc fpga_audit::execute {checkpoint session token} {
    global package_root
    require_vivado
    if {![regexp {^[0-9a-f]{12}$} $token]} { error "Invalid audit token" }
    if {![file isfile $checkpoint] || [file size $checkpoint] == 0 ||
        ![string equal -nocase [file extension $checkpoint] .dcp]} {
        error "Existing nonempty routed checkpoint required: $checkpoint"
    }
    if {![file isdirectory $session]} { error "Audit session directory missing: $session" }
    if {[current_project -quiet] ne ""} { error "Checkpoint audit requires a fresh Vivado session" }
    set name audit_$token
    set dir [file join $package_root reports $name]
    set marker [file join $session completed_audit.txt]
    if {[file exists $dir] || [file exists $marker]} { error "Audit output already exists; use a new session/token" }
    file mkdir $dir
    # open_checkpoint restores the archived netlist, constraints and routing.
    # Do not open the package XPR or re-apply the working tree's constraints.
    set code [catch {
        open_checkpoint [file normalize $checkpoint]
        report_route_status -file [file join $dir route_status.rpt]
        foreach check {ROUTED_FULLY ERRORS_IN_ROUTES} expected {1 0} {
            set value [report_route_status -boolean_check $check]
            if {![string is boolean -strict $value]} {
                error "Cannot verify $check: [list $value]. Inspect $dir/route_status.rpt."
            }
            if {[expr {!!$value}] != $expected} {
                error "Checkpoint is not fully/error-free routed ($check=$value). Inspect $dir/route_status.rpt."
            }
        }
        require_no_multiple_drivers $dir
        write_reports $name true
        foreach kind {max min} {
            set paths [get_timing_paths -delay_type $kind -max_paths 1]
            if {[llength $paths] != 1} { error "Missing $kind timing path; audit was not accepted" }
            set slack [get_property SLACK $paths]
            if {![fpga_checks::finite $slack] || $slack < 0} {
                error "Timing not met or unconstrained: $kind slack=[list $slack]. Inspect $dir/timing_summary.rpt."
            }
            puts "AUDIT $kind SLACK=$slack"
        }
    } result options]
    set close_code [catch {
        if {[current_project -quiet] ne ""} { close_project }
    } close_result close_options]
    if {$code} { return -options $options $result }
    if {$close_code} { return -options $close_options $close_result }
    set out [open $marker w]
    set code [catch {puts $out $name} result options]
    set close_code [catch {close $out} close_result close_options]
    if {$code} { return -options $options $result }
    if {$close_code} { return -options $close_options $close_result }
    puts "AUDIT checks passed: $dir. Manual CDC/DRC/methodology/coverage review is still required."
}
