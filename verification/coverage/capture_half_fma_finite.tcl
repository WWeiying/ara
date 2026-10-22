# Read-only focused FMA observation. No reset deposits or internal forcing.
proc hfm_capture {} {
    source half-fma-selection.tcl
    if {[llength $hfm_scopes] != 16} {error "Exact sixteen half FMA scopes required"}
    set fid [dump -file half-fma.vpd -type VPD]
    set objects [list ara_tb.clk ara_tb.rst_n]
    foreach scope $hfm_scopes {
        foreach port {in_valid_i in_ready_o out_valid_o out_ready_i operands_i op_i rnd_mode_i mask_i mask_o result_o status_o} {
            lappend objects ${scope}.${port}
        }
    }
    foreach path $objects {
        show -type $path
        set added [dump -add $path -fid $fid -depth 0 -aggregates]
        if {![string is integer -strict $added] || $added <= 0} {error "Missing focused object: $path"}
    }
    puts HALF_FMA_16_SCOPES_READY
    run
}
if {[catch {hfm_capture} failure]} {
    puts "HALF_FMA_CAPTURE_ERROR $failure"
    exit 1
}
