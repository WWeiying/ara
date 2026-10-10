# Reuse frozen FMA vector selection/export primitives, without invoking its session.
proc c910_primitives {} {
    set stream [open $::c910_fma_tcl r]
    set body [read $stream]
    close $stream
    set marker {if {[catch {fma_session} message]} }
    set position [string first $marker $body]
    if {$position < 0} {error "Frozen FMA entry boundary changed"}
    uplevel #0 [string range $body 0 [expr {$position - 1}]]
}
proc c910_bind {stage instance} {
    global fma_names fma_rows fma_seen env
    set fma_names [lindex $instance 1]
    set fma_rows {}
    set fma_seen {}
    gui_list_action -id CoverageTable.1 -column Toggle [lindex $instance 0]
    fma_need [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Toggle"}] "Not Toggle"
    gui_list_expand -id CovDetail.1 -all {<root>}
    gui_process_events -mstime 100
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) native_${stage}_[lindex $instance 3].tsv] w]
    puts $stream "handle\tpath\tmeta\tname"
    fma_walk [gui_list_get -id CovDetail.1 -firstChild] $stream
    close $stream
    fma_need [expr {[llength $fma_rows] == 158}] "Not158 exact native rows"
    foreach name [concat $fma_names [lindex $instance 2]] {
        set count 0
        foreach seen $fma_seen {if {$seen eq $name} {incr count}}
        fma_need [expr {$count == 1}] "Missing/duplicate target or protection $name"
    }
    puts [exec $::fma_python -B $::fma_helper inventory --output $env(DVE_COVERAGE_OUTPUT) --stage $stage --index [lindex $instance 3]]
    return $fma_rows
}
proc c910_session {} {
    global env fma_instances fma_design fma_vdb fma_test fma_python fma_helper c910_fma_tcl
    source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]
    c910_primitives
    gui_open_cov -hier $fma_design -testdir [list $fma_vdb] -test [list $fma_test] -merge C9101264NativeOnly
    gui_list_expand -id CoverageTable.1 -all {<root>}
    fma_save initial-empty.el
    foreach instance $fma_instances {
        set before [c910_bind before $instance]
        foreach row $before {
            fma_select $row
            gui_exclude_items -id CovDetail.1 -selected -annotation {Approved unchanged C910 internal arithmetic datapath integration scope; all ports/control/round and other signals retained}
        }
        gui_exclusion -id CoverageTable.1 -recalculate
        fma_need [expr {[gui_cov_excl_review -isEmpty] == 1}] "Exclusion needs review"
        fma_need [expr {[c910_bind selected $instance] eq $before}] "Target identity changed"
    }
    fma_save first.el
    fma_check first.el
    gui_exclusion -reset
    foreach instance $fma_instances {c910_bind reset $instance}
    fma_save reset-empty.el
    gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) first.el]]
    gui_exclusion -id CoverageTable.1 -recalculate
    fma_need [expr {[gui_cov_excl_review -isEmpty] == 1}] "Reload needs review"
    foreach instance $fma_instances {c910_bind reloaded $instance}
    fma_save second.el
    fma_check second.el
    gui_exclusion -reset
    foreach instance $fma_instances {c910_bind final $instance}
    fma_save final-empty.el
    puts C910_SRT_NATIVE_CAPTURE_DONE
}
if {![info exists ::c910_test_only]} {
    if {[catch {c910_session} message]} {
        puts "C910_SRT_NATIVE_CAPTURE_FAILED $message"
        puts $::errorInfo
        catch {gui_exclusion -reset}
        catch {fma_save cleanup-empty.el}
    }
    gui_exit -noprompt
}
