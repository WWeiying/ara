# Offline control-flow tests. This does not emulate Vivado synthesis or timing.
# Load the host clock library before removing a command its loader may use.
clock format [clock seconds] -format {%Y-%m-%d %H:%M:%S}
# Reproduce the missing command in the Windows Vivado 2020.1 interpreter.
if {[llength [info commands try]]} { rename try {} }
source [file join [file dirname [info script]] .. scripts common.tcl]
source [file join [file dirname [info script]] .. scripts run_support.tcl]
set sandbox [file normalize [lindex $argv 0]]
if {$sandbox eq "" || [file exists $sandbox]} { error "Pass a new temporary directory" }
file mkdir $sandbox
set package_root $sandbox
set project_name ara_dsa_vcu118
set token 012345abcdef
set parent synth_abcdef012345
set synth_hook [file normalize [file join [file dirname [info script]] .. scripts synth_pre.tcl]]

proc assert {condition message} {
    if {![uplevel 1 [list expr $condition]]} { error "ASSERT: $message" }
}
proc put {path contents} {
    file mkdir [file dirname $path]
    set f [open $path w]; puts -nonewline $f $contents; close $f
}
proc setup {scenario} {
    set ::scenario $scenario
    set ::session [file join $::sandbox $scenario]
    file mkdir $::session
    set ::launched {}
    set ::created {}
    set ::copied {}
    set ::args_seen {}
    set ::polls 0
    set ::reported {}
    set ::driver_checks {}
    set ::closed 0
    file mkdir [file join $::package_root scripts]
    file copy -force $::synth_hook [file join $::package_root scripts synth_pre.tcl]
    if {$scenario eq "missing_hook"} { file delete [file join $::package_root scripts synth_pre.tcl] }
    foreach ip {clkwiz vio ddr4} {
        put [file join $::session old ${ip}_synth_1 ${ip}.dcp] checkpoint
    }
    put [file join $::session old $::parent ${::project_name}.dcp] checkpoint
    put [file join $::session old synth_1 exception.log] old-error
    if {$scenario eq "missing_dcp"} { file delete [file join $::session old vio_synth_1 vio.dcp] }
    if {$scenario eq "empty_dcp"} { put [file join $::session old vio_synth_1 vio.dcp] "" }
    if {$scenario eq "existing_dir"} { file mkdir [file join $::session synth_$::token] }
}
proc open_package_project {} {}
proc get_runs {args} {
    set name [lindex $args end]
    if {$::scenario eq "missing_run" && $name eq "vio_synth_1"} { return {} }
    if {$name in {synth_1 impl_1 clkwiz_synth_1 vio_synth_1 ddr4_synth_1} ||
        $name eq $::parent || $name in $::created} { return $name }
    return {}
}
proc get_ips {args} {
    set name [lindex $args end]
    if {$::scenario eq "missing_ip" && $name eq "vio"} { return {} }
    return $name
}
proc get_property {key object} {
    switch -- $key {
        DIRECTORY { return [file join $::session old $object] }
        NEEDS_REFRESH {
            return [expr {($::scenario eq "stale_ip" && $object eq "vio_synth_1") ||
                ($::scenario in {stale_parent inspect_stale} && $object eq $::parent)}]
        }
        IS_LOCKED { return [expr {$::scenario eq "locked_ip" && $object eq "vio"}] }
        STATUS {
            if {$::scenario eq "incomplete_ip" && $object eq "vio_synth_1"} { return Failed }
            if {$object in $::launched} {
                incr ::polls
                if {$::scenario eq "failed_status"} { return "synth_design ERROR" }
                if {$::scenario in {quiet_phase delayed_log_crash log_cancelled log_canceled log_stackfree}
                    && $::polls < 3} { return Running }
                if {[string match impl_* $object]} { return "route_design Complete!" }
            }
            return "synth_design Complete!"
        }
        FLOW { return "Vivado [expr {$object eq "impl_1" ? "Implementation" : "Synthesis"}] 2020" }
        STRATEGY { return Defaults }
        CONSTRSET { return constrs_1 }
        PART { return xcvu9p-flga2104-2L-e }
        SRCSET { return sources_1 }
        STEPS.SYNTH_DESIGN.ARGS.FLATTEN_HIERARCHY { return none }
        STEPS.SYNTH_DESIGN.TCL.PRE { return [expr {$::scenario eq "hook" ? "custom.tcl" : ""}] }
        STEPS.PHYS_OPT_DESIGN.IS_ENABLED { return true }
        SLACK { return [expr {$::scenario eq "bad_timing" ? -1 : 0.5}] }
        default { error "Unexpected get_property: $key" }
    }
}
proc create_run {name args} { lappend ::created $name; set ::args_seen $args }
proc list_property {object} {
    return {SRCSET STATUS DIRECTORY STEPS.SYNTH_DESIGN.ARGS.FLATTEN_HIERARCHY
        STEPS.SYNTH_DESIGN.TCL.PRE STEPS.PHYS_OPT_DESIGN.IS_ENABLED}
}
proc set_property {property value object} { dict set ::copied $property $value }
proc set_param {args} {}
proc current_run {args} {}
proc launch_runs {name args} {
    assert {$name in $::created} "only launch new top-level runs"
    set ::launch_args $args
    lappend ::launched $name
    set dir [file join $::session $name]
    file mkdir $dir
    switch -- $::scenario {
        launcher_error { put [file join $dir exception.log] "Permission denied" }
        error_marker { put [file join $dir .vivado.error.rst] "" }
        crash { put [file join $dir hs_err_pid99.log] crash }
        log_cancelled {
            put [file join $dir runme.log] "[string repeat {INFO: DSP mapping completed.} 4000]\r\nAn unrecoverable error has occurred, synthesis cancelled.\r\nTclStackFree: incorrect freePtr. Call out of sequence?\r\n"
        }
        log_canceled {
            put [file join $dir runme.log] "An unrecoverable error has occurred, synthesis canceled."
        }
        log_stackfree {
            put [file join $dir runme.log] "Start Timing Optimization\nTclStackFree: incorrect freePtr. Call out of sequence?"
        }
        benign_log {
            put [file join $dir runme.log] {# puts "An unrecoverable error has occurred"
# puts "TclStackFree: incorrect freePtr. Call out of sequence?"
WARNING: an error message in RTL text is not a tool crash.
Start Timing Optimization
}
        }
    }
}
rename after real_after
proc after {args} {
    assert {[lindex $args 0] == 5000} "bounded monitor interval"
    if {$::scenario eq "delayed_log_crash"} {
        put [file join $::session synth_$::token runme.log] \
            "An unrecoverable error has occurred, synthesis cancelled.\n"
    }
}
proc open_run {name} {
    if {$::scenario in {inspect inspect_stale inspect_open_error}} {
        assert {[info exists ::ara_cdc_inspect_legacy] && $::ara_cdc_inspect_legacy} \
            "only inspection may open a legacy status netlist"
        if {$::scenario eq "inspect_open_error"} {
            return -code error -errorcode {ARA TEST OPEN} "Cannot open checkpoint"
        }
    } else {
        assert {![info exists ::ara_cdc_inspect_legacy]} "no legacy bypass for synthesis or implementation"
    }
}
proc write_reports {name {reject_loops false}} {
    set ::reported $name
    if {$::scenario eq "route_loop" && $reject_loops} { error "Combinational loops remain" }
}
proc close_project {} { set ::closed 1 }
proc close_design {} {}
proc require_no_combinational_loops {dir} {
    if {$::scenario eq "loop"} { error "Combinational loops remain" }
}
proc require_no_multiple_drivers {dir} {
    lappend ::driver_checks $dir
    if {$::scenario in {synth_multidriver impl_multidriver} ||
        ($::scenario eq "route_multidriver" && [string match impl_* [file tail $dir]])} {
        error "Multiple drivers remain"
    }
}
proc get_timing_paths {args} {
    if {$::scenario eq "no_timing"} { return {} }
    return path
}
# Any accidental IP rebuild, reset, deletion, or bitstream generation is an error.
foreach forbidden {reset_runs delete_runs generate_target create_ip_run upgrade_ip write_bitstream} {
    proc $forbidden {args} { error "Forbidden command was called" }
}

set failures 0
foreach scenario {healthy quiet_phase benign_log missing_run missing_ip incomplete_ip stale_ip locked_ip
    missing_dcp empty_dcp hook missing_hook existing_dir launcher_error error_marker crash failed_status
    log_cancelled log_canceled log_stackfree delayed_log_crash
    implementation stale_parent bad_timing no_timing loop route_loop synth_multidriver impl_multidriver route_multidriver
    inspect inspect_stale inspect_open_error} {
    setup $scenario
    set stage synth
    set use_parent -
    if {$scenario in {implementation stale_parent bad_timing no_timing loop route_loop impl_multidriver route_multidriver}} {
        set stage impl
        set use_parent $parent
    }
    if {$scenario in {inspect inspect_stale inspect_open_error}} { set stage inspect; set use_parent $parent }
    set code [catch {fpga_run::execute $stage $session $token $use_parent} message options]
    set success [expr {$scenario in {healthy quiet_phase benign_log implementation inspect inspect_stale}}]
    if {[catch {
        assert {$code == !$success} "$scenario: unexpected result ($message)"
        assert {![info exists ::ara_cdc_inspect_legacy]} "legacy bypass must be scoped to open_run"
        if {$scenario eq "inspect_open_error"} {
            assert {$message eq "Cannot open checkpoint"} "preserve original failure message"
            assert {[dict get $options -errorcode] eq "ARA TEST OPEN"} "preserve original error code"
            assert {[string first open_run [dict get $options -errorinfo]] >= 0} "preserve failure stack"
        }
        assert {[llength $launched] <= 1} "only one run launched"
        assert {[file exists [file join $session completed_run.txt]] == $success} "completion marker"
        assert {[file exists [file join $session old synth_1 exception.log]]} "old artifacts preserved"
        if {$scenario in {log_cancelled log_canceled log_stackfree delayed_log_crash}} {
            assert {[string first "runme.log" $message] >= 0} "crash error identifies the log"
            assert {[string first "unrecoverable error" $message] >= 0 ||
                [string first "TclStackFree" $message] >= 0} "crash error preserves the diagnostic"
            assert {$polls == ($scenario eq "delayed_log_crash" ? 1 : 0)} \
                "detect log-only crashes despite stale Running status"
            assert {$reported eq ""} "crashed synthesis must not generate success reports"
            assert {[file exists [file join $session synth_$token runme.log]]} "crash evidence preserved"
        }
        if {$success && $stage ne "inspect"} {
            assert {[llength $driver_checks] == ($stage eq "synth" ? 1 : 2)} "check synthesized and routed netlists"
            assert {[dict get $copied STEPS.SYNTH_DESIGN.ARGS.FLATTEN_HIERARCHY] eq "none"} "options copied"
            assert {[dict get $launch_args -dir] eq $session} "fresh output directory"
            assert {$reported eq "${stage}_$token" && $closed} "reports and clean close"
            if {$stage eq "synth"} {
                assert {[dict get $copied STEPS.SYNTH_DESIGN.TCL.PRE] eq
                    [file join $package_root scripts synth_pre.tcl]} "worker must execute strict synthesis hook"
            }
        }
        if {$stage eq "inspect"} {
            assert {![llength $driver_checks]} "historical inspection remains diagnostic only"
            assert {![llength $created] && ![llength $launched]} "inspection must not create/launch runs"
            if {$success} {
                assert {$reported eq "inspect_$token" && $closed} "inspection writes separate reports"
            } else {
                assert {$reported eq ""} "failed inspection must not report success"
            }
        }
        if {$scenario in {loop impl_multidriver}} { assert {![llength $launched]} "block implementation before launch" }
        if {$scenario in {synth_multidriver impl_multidriver route_multidriver}} {
            assert {$message eq "Multiple drivers remain"} "driver gate diagnostic preserved"
            assert {$reported eq ""} "reject before expensive reports and success marker"
            if {$scenario eq "route_multidriver"} {
                assert {[llength $driver_checks] == 2 && [llength $launched] == 1} "post-route gate must run"
            }
        }
        if {$scenario eq "implementation"} {
            assert {[dict get $args_seen -parent_run] eq $parent} "new implementation uses recorded synthesis"
            assert {[dict get $launch_args -to_step] eq "route_design"} "route-only implementation"
        }
        if {$scenario in {missing_run missing_ip incomplete_ip stale_ip locked_ip missing_dcp
            empty_dcp hook missing_hook existing_dir stale_parent}} {
            assert {[llength $launched] == 0 && [llength $created] == 0} "preflight must stop before creation"
        }
    } failure]} {
        incr failures
        puts stderr "FAIL $scenario: $failure"
    } else { puts "PASS $scenario" }
}
if {$failures} { exit 1 }
