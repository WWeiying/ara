# Checkpoints belong to one attempt; final output names remain PNR-compatible.
set dc_run_id "[clock format [clock seconds] -format %Y%m%d_%H%M%S]_[pid]"
set dc_checkpoint_dir "../outputs/checkpoints/$dc_run_id"
file mkdir ../reports $dc_checkpoint_dir

# This installation records a missing-manual CMD-025 during empty startup.
# Keep it visible, but do not confuse it with errors introduced by the flow.
set dc_startup_manual_errors [get_message_info -occurrences CMD-025]
puts "DC_STARTUP_MANUAL_ERRORS=$dc_startup_manual_errors"

proc dc_flow_check_errors {} {
    global dc_startup_manual_errors
    set count [expr {[get_message_info -error_count] - $dc_startup_manual_errors}]
    puts "DC_FLOW_ERROR_COUNT=$count"
    return [expr {$count == 0}]
}

proc dc_flow_stage {stage} {
    global dc_run_id
    set f [open dc.status.tmp w]
    puts $f "run_id=$dc_run_id"
    puts $f "stage=$stage"
    puts $f "updated_utc=[clock format [clock seconds] -gmt 1 -format %Y-%m-%dT%H:%M:%SZ]"
    close $f
    file rename -force dc.status.tmp dc.status
    puts "DC_FLOW_STAGE=$stage run_id=$dc_run_id"
}

proc dc_flow_checkpoint {stage} {
    global dc_checkpoint_dir GUI_DESIGN_NAME
    write -format ddc -hierarchy -output "$dc_checkpoint_dir/${GUI_DESIGN_NAME}_${stage}.ddc"
    write_sdc -version 1.8 "$dc_checkpoint_dir/${GUI_DESIGN_NAME}_${stage}.sdc"
    puts "DC_CHECKPOINT=$dc_checkpoint_dir/${GUI_DESIGN_NAME}_${stage}.ddc"
}

proc dc_flow_elaborate_only {} {
    return [expr {[info exists ::env(DC_ELAB_ONLY)] && $::env(DC_ELAB_ONLY) == 1}]
}
