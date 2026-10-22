# Procedure-only imports in global scope; never invoke a standalone DWC session.
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/report_c910_combo742.tcl}
proc combo_dwc_primitives {} {
    set stream [open {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/qualify_dwc_points742.tcl} r]
    set body [read $stream]
    close $stream
    set start [string first {proc dw_need } $body]
    set end [string first {proc dw_session } $body]
    if {$start < 0 || $end <= $start} {error "Frozen DWC procedure boundary differs"}
    # Existing global FSM/native primitives are already installed. Do not source
    # DWC's nested batch loader, which would overwrite fx_audit and the hook.
    uplevel #0 [string range $body $start [expr {$end - 1}]]
}
proc apply_reviewed_waivers {id} {
    global env fx_groups fx_stream p740_scopes p740_root_names combo_groups combo_has_dwc dw_groups dw_toggles dw_stream
    if {$id ne "CoverageTable.1"} {error "Wrong table"}
    source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]
    set deadline [expr {[clock seconds]+60}]
    while {![file exists [file join $env(DVE_COVERAGE_OUTPUT) live-ready]]} {
        if {[clock seconds] >= $deadline} {error "Live gate timeout"}
        after 100
    }
    if {$combo_has_dwc} {
        combo_dwc_primitives
        set dw_stream [open [file join $env(DVE_COVERAGE_OUTPUT) dwc-audit.tsv] {WRONLY CREAT EXCL}]
    }
    set p740_scopes [list ara_tb.dut.i_ara_soc.i_system]
    set p740_root_names(ara_tb.dut.i_ara_soc.i_system) i_system
    set fx_stream [open [file join $env(DVE_COVERAGE_OUTPUT) exact-audit.tsv] {WRONLY CREAT EXCL}]
    set failed [catch {
        p740_save initial-empty.el
        combo_audit initial before 0
        p740_summary raw
        combo_load combined.el
        combo_audit applied selected 1
        p740_save applied.el
        p740_summary applied
        combo_reset
        combo_audit reset reset 0
        p740_save reset-empty.el
        p740_summary reset
        combo_load applied.el
        combo_audit reloaded reloaded 1
        p740_save reloaded.el
        p740_summary reloaded
        combo_reset
        combo_audit final final 0
        p740_save final-empty.el
        p740_summary final
    } message]
    if {$failed} {
        set stream [open [file join $env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $stream "$message\n$::errorInfo"
        close $stream
    }
    set cleanup [catch {combo_reset; p740_save cleanup-empty.el} detail]
    close $fx_stream
    if {$combo_has_dwc} {close $dw_stream}
    if {$failed || $cleanup} {error "COMBO742_FAILED $message cleanup=$detail"}
    puts COMBO742_NATIVE_DONE
}
