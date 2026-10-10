# Reuse pinned51-object session, no context-dependent info-script evaluation.
set stream [open {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/fma_expanded_native_02.tcl} r]
set body [read $stream]; close $stream
set old_annotation {Reviewed unchanged FP32/FP64 local FMA numerical arithmetic integration scope; all other objects and children retained; not IEEE certification}
if {[string first $old_annotation $body] < 0} {error "Frozen annotation boundary differs"}
set body [string map [list $old_annotation {Parent-qualified finite FP16 FMA numerical internals only; all interfaces control flags rounding and children retained; not exhaustive IEEE validation} {FMAExpanded612NativeOnly} {HalfFMA816NativeOnly}] $body]
set marker {if {[catch {fma_session} message]} }
set pos [string first $marker $body]
if {$pos <= 0} {error "Frozen FMA session boundary differs"}
uplevel #0 [string range $body 0 [expr {$pos-1}]]
# Same exact singleton selection, with empty old-selection tokens filtered.
proc fma_select {row} {
    foreach token [fma_flat [gui_list_get_selected -id CovDetail.1 -flat]] {
        if {$token ne ""} {gui_list_select -id CovDetail.1 -unselect [list $token]}
    }
    fma_need [expr {[gui_list_get_selected -id CovDetail.1 -count] == 0}] "Old selection remains"
    set token [lindex $row 0]
    gui_list_select -id CovDetail.1 -select [list $token]
    set selected [fma_flat [gui_list_get_selected -id CovDetail.1 -flat]]
    fma_need [expr {[gui_list_get_selected -id CovDetail.1 -count] == 1 &&
                   ($selected eq $token || $selected eq [lindex $row 1])}] "Exact native selection readback differs"
}
if {![info exists ::half816_test_only]} {
    if {[catch {fma_session} message]} {
        puts "FMA_EXPANDED_NATIVE_CAPTURE_FAILED $message"
        puts $::errorInfo
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $stream $message; puts $stream $::errorInfo; close $stream
        catch {fma_reset; fma_save cleanup-empty.el}
    }
    gui_exit -noprompt
}
