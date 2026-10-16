# Explicit physical continuation; the ordinary managed-run gate is unchanged.
namespace eval fpga_physical {}

proc fpga_physical::stage {session name} {
    set f [open [file join $session stage.txt] w]
    puts $f $name
    close $f
    puts "PHYSICAL_STAGE $name"
    flush stdout
}

proc fpga_physical::review_reports {dir} {
    set reasons {}
    set timing [fpga_checks::read_report [file join $dir check_timing.rpt]]
    foreach check {no_clock unconstrained_internal_endpoints multiple_clock generated_clocks loops latch_loops} {
        set pattern [format {checking %s \(([0-9]+)\)} $check]
        if {![regexp $pattern $timing -> count]} { error "Missing check_timing category: $check" }
        if {$count != 0} { lappend reasons "$check=$count" }
    }
    set cdc [fpga_checks::read_report [file join $dir cdc.rpt]]
    if {![regexp {ID\s+Severity\s+Count\s+Description} $cdc]} { error "Unrecognized CDC report" }
    # Vendor hierarchy alone is not a waiver. Non-clean CDC needs path review.
    foreach line [split $cdc \n] {
        if {[regexp {^\s*(CDC-[0-9]+)\s+(Critical|Warning)\s+([0-9]+)\s+} $line -> id severity count] && $count > 0} {
            lappend reasons "$id $severity=$count"
        }
    }
    foreach name {drc methodology} {
        set report [fpga_checks::read_report [file join $dir $name.rpt]]
        if {![regexp {Violations found:\s*([0-9]+)} $report -> count]} { error "Unrecognized $name report" }
        if {$count > 0} { lappend reasons "$name findings=$count (review required, not necessarily errors)" }
    }
    return $reasons
}

proc fpga_physical::execute {package parent session token} {
    if {![regexp {^synth_[0-9a-f]{12}$} $parent] || ![regexp {^[0-9a-f]{12}$} $token] ||
        ![file isdirectory $session]} { error "Invalid physical continuation arguments" }
    global fpga_profile design_top max_threads
    if {$fpga_profile ne "host_ethernet"} { error "Continuation requires host_ethernet" }
    stage $session preflight
    open_package_project
    set_param general.maxThreads $max_threads
    fpga_run::check_ips
    fpga_run::reusable $parent {*synth_design Complete*} ${design_top}.dcp
    open_run $parent
    require_no_multiple_drivers [file join $session preflight]
    require_no_combinational_loops [file join $session preflight]
    set paths [get_timing_paths -quiet -delay_type max -max_paths 1]
    if {[llength $paths] != 1} { error "Missing synthesis setup path" }
    set slack [get_property SLACK $paths]
    if {![fpga_checks::finite $slack] || $slack < 0} { error "Synthesis setup failed: $slack" }
    puts "SYNTHESIS_SETUP_PASS $slack; physical min-delay/skew deferral explicitly authorized"
    close_design

    set name impl_$token
    if {[file exists [file join $session $name]]} { error "Implementation directory already exists" }
    set run [fpga_run::clone_run impl_1 $name $parent]
    # Routed setup failures are dominated by long nets, including an SLR round trip.
    set_property STEPS.PLACE_DESIGN.ARGS.DIRECTIVE ExtraNetDelay_high $run
    set_property STEPS.PHYS_OPT_DESIGN.IS_ENABLED true $run
    set_property STEPS.PHYS_OPT_DESIGN.ARGS.DIRECTIVE ExploreWithAggressiveHoldFix $run
    current_run -implementation $run
    stage $session implementation
    launch_runs $name -jobs 1 -dir $session -to_step route_design
    fpga_run::wait_checked $name {*route_design Complete*} [file join $session $name]
    check_run $name {*route_design Complete*}
    open_run $name
    stage $session routed_reports
    set dir [file join $session reports]
    file mkdir $dir
    report_route_status -file [file join $dir route_status.rpt]
    foreach check {ROUTED_FULLY ERRORS_IN_ROUTES} expected {1 0} {
        set value [report_route_status -boolean_check $check]
        if {![string is boolean -strict $value] || [expr {!!$value}] != $expected} {
            error "Route integrity failed: $check=$value"
        }
    }
    require_no_multiple_drivers $dir
    write_reports $dir true
    fpga_warning_details::write $dir
    # Strict setup, hold AND pulse/skew. No synthesis deferral applies here.
    fpga_run::require_timing $dir
    set reasons [review_reports $dir]
    if {[llength $reasons]} {
        set f [open [file join $session review_required.txt] w]
        puts $f [join $reasons \n]
        close $f
        stage $session review_required
        close_project
        return
    }
    stage $session bitstream
    set out [file join $session bitstream_host_ethernet]
    file mkdir $out
    write_debug_probes [file join $out $design_top.ltx]
    # Native bitgen DRC stays enabled; no severity or timing overrides.
    write_bitstream [file join $out $design_top.bit]
    foreach ext {bit ltx} { fpga_run::nonempty [file join $out $design_top.$ext] }
    close_project
    stage $session bitstream_complete_not_programmed
}
