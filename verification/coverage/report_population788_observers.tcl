# One consolidated session. Existing compact and passive library files stay sealed.
# The host must supply absolute, pinned library paths and exact cv_* selection.
proc observers788_install {} {
    global observers788_compact_library observers788_native_library cv_scopes
    if {$cv_scopes ne [list ara_tb.dut.i_ara_soc.i_system.i_ara_cvxif_dut_bind ara_tb.dut.i_ara_soc.i_system.i_ara_cvxif_dut_bind.cvxif]} {
        error "Foreign observer scope selection"
    }
    set ::cv_test_only 1
    uplevel #0 [list source $observers788_native_library]
    uplevel #0 [list source $observers788_compact_library]
    foreach command {cv_audit cv_apply compact777_summary compact777_load compact777_save} {
        if {[llength [info commands $command]] != 1} {error "Missing sealed library procedure: $command"}
    }
    rename compact777_session observers788_original_session
    rename apply_reviewed_waivers observers788_original_entry
}

proc observers788_session {} {
    uplevel #0 [list source [file join $::env(DVE_COVERAGE_OUTPUT) root-selection.tcl]]
    uplevel #0 [list source $::compact_root_helper]
    if {[llength $::p740_scopes] != 73} {error "Exact73 summary roots required"}
    file rename [file join $::env(DVE_COVERAGE_OUTPUT) summary.csv.partial] [file join $::env(DVE_COVERAGE_OUTPUT) raw.csv]
    compact777_save initial-empty.el
    compact777_summary raw
    observers788_audit before
    compact777_load combined.el
    observers788_apply
    observers788_audit selected
    compact777_save applied.el
    compact777_summary applied
    cv_reset
    compact777_save reset-empty.el
    compact777_summary reset
    observers788_audit reset
    compact777_load applied.el
    observers788_audit reloaded
    compact777_save reloaded.el
    compact777_summary reloaded
    cv_reset
    compact777_save final-empty.el
    compact777_summary final
    observers788_audit final
}

proc observers788_audit {stage} {
    set availability {}
    foreach metric {Line Condition Branch FSM Toggle Assert Group} {
        set loaded [gui_has_metric -metric $metric]
        cv_need [expr {$loaded eq "0" || $loaded eq "1"}] "Unknown metric availability"
        if {$loaded} {set boolean true} else {set boolean false}
        lappend availability "\"$metric\":$boolean"
        if {$metric eq "Assert" || $metric eq "Group"} {
            if {$loaded} {cv_snapshot $stage $metric 0 $::cv_root}
            continue
        }
        cv_need $loaded "Required global code metric missing"
        set i 0
        foreach scope $::cv_scopes {
            if {![info exists ::observers788_capacity($scope,$metric)]} {error "Missing compiled capacity"}
            if {$::observers788_capacity($scope,$metric) == 0} {
                set f [open [file join $::env(DVE_COVERAGE_OUTPUT) ${stage}_${metric}_${i}.skipped.json] {WRONLY CREAT EXCL}]
                puts $f "\{\"status\":\"SKIPPED_COMPILED_ZERO\",\"scope\":\"$scope\",\"metric\":\"$metric\",\"capacity\":0\}"
                close $f
            } else {cv_snapshot $stage $metric $i $scope}
            incr i
        }
    }
    set f [open [file join $::env(DVE_COVERAGE_OUTPUT) ${stage}_availability.json] {WRONLY CREAT EXCL}]
    puts $f "\{[join $availability ,]\}"; close $f
}

proc observers788_apply {} {
    foreach scope $::cv_scopes {
        foreach metric {Line Condition Branch FSM Toggle} {
            if {$::observers788_capacity($scope,$metric) == 0} {continue}
            p740_root
            p740_select $scope
            gui_exclude_items -id CoverageTable.1 -selected -metric $metric -annotation $::cv_annotation
        }
    }
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
    cv_need [expr {[gui_cov_excl_review -isEmpty] == 1}] "Observer exclusions need review"
}

proc apply_reviewed_waivers {id} {
    if {$id ne "CoverageTable.1"} {error "Unexpected table"}
    set failed [catch {observers788_session} message]
    set cleanup_failed [catch {cv_reset; compact777_save cleanup-empty.el} cleanup]
    if {$failed} {puts "COMPACT777_FAILED: $message"; error $message}
    if {$cleanup_failed} {puts "COMPACT777_FAILED: $cleanup"; error $cleanup}
    puts OBSERVERS788_NATIVE_FIVE_PHASE_DONE
    puts COMPACT777_FIVE_PHASE_DONE
}

# Install before defining the final entry: sourcing the compact library overwrites it.
rename apply_reviewed_waivers observers788_final_entry
uplevel #0 [list source [file join $::env(DVE_COVERAGE_OUTPUT) root-selection.tcl]]
observers788_install
rename observers788_final_entry apply_reviewed_waivers
