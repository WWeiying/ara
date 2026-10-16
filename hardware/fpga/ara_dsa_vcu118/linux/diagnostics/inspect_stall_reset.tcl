# Bounded, read-only reset connectivity comparison between routed checkpoints.
proc emit_reset_cells {out roots} {
    set seen [dict create]
    set queue {}
    foreach c $roots { lappend queue [list $c 0] }
    while {[llength $queue]} {
        lassign [lindex $queue 0] cell depth
        set queue [lrange $queue 1 end]
        set name [get_property NAME $cell]
        if {[dict exists $seen $name]} { continue }
        dict set seen $name 1
        if {[dict size $seen] > 512} { error "Reset inventory exceeded bounded cell budget" }
        puts $out [list CELL $name DEPTH $depth REF [get_property REF_NAME $cell]]
        foreach prop {INIT IS_C_INVERTED IS_D_INVERTED IS_R_INVERTED IS_CLR_INVERTED IS_PRE_INVERTED} {
            if {$prop in [list_property $cell]} {
                puts $out [list PROPERTY $name $prop [get_property $prop $cell]]
            }
        }
        foreach pin [get_pins -quiet -of_objects $cell -filter {DIRECTION == IN}] {
            set nets [get_nets -quiet -segments -of_objects $pin]
            set drivers {}
            if {[llength $nets]} {
                set drivers [get_pins -quiet -leaf -of_objects $nets -filter {DIRECTION == OUT}]
            }
            set names {}
            if {[llength $drivers]} { set names [lsort [get_property NAME $drivers]] }
            puts $out [list INPUT [get_property NAME $pin] DRIVERS $names]
            if {$depth < 3} {
                foreach driver $drivers {
                    foreach parent [get_cells -quiet -of_objects $driver] {
                        lappend queue [list $parent [expr {$depth + 1}]]
                    }
                }
            }
        }
    }
    puts $out [list TOTAL_CELLS [dict size $seen]]
}
if {[catch {
    if {[llength $argv] != 4} { error "Expected package original observation output" }
    lassign $argv package original observation output
    if {[file exists $output]} { error "Output already exists" }
    file mkdir $output
    set_param board.repoPaths [linsert [get_param board.repoPaths] 0 [file join $package board_files]]
    if {[llength [get_board_parts -quiet xilinx.com:vcu118:part0:2.4]] != 1} {
        error "Missing frozen board definition"
    }
    set_msg_config -id {Board 49-67} -new_severity ERROR
    set_param general.maxThreads 8
    foreach label {original observation} checkpoint [list $original $observation] {
        puts "RESET_INSPECT opening $label"
        flush stdout
        open_checkpoint $checkpoint
        set prefix i_dram_wrapper/i_eth_loader/i_loader/loader_bd_i
        set roots {}
        set out [open [file join $output $label.txt] w]
        foreach pattern [list \
            $prefix/rst_clock_100M/U0/ACTIVE_LOW_PR_OUT_DFF* \
            $prefix/mac/inst/eth_buf/U0/COMBINE_RESETS/*/ClkA_reset_inst/sync_rst1_reg \
            $prefix/mac/inst/eth_buf/U0/COMBINE_RESETS/*/ClkB_reset_inst/async_rst0_reg \
            $prefix/mac/inst/mac/inst/bd_a4d5_mac_0_core/sync*/async_rst0_reg \
            $prefix/mac/inst/pcs_pma/inst/clock_reset_i/reset_sync_ctrl_rst/reset_sync1] {
            set cells [get_cells -quiet -hierarchical -filter "NAME =~ $pattern && IS_PRIMITIVE == 1"]
            puts $out [list MATCH $pattern COUNT [llength $cells]]
            set roots [concat $roots $cells]
        }
        if {![llength $roots]} { error "No reset roots resolved" }
        emit_reset_cells $out $roots
        close $out
        close_design
        puts "RESET_INSPECT collected $label"
        flush stdout
    }
    set out [open [file join $output completed.txt] w]
    puts $out "collected_not_equivalence_proven"
    close $out
} message]} {
    puts stderr $::errorInfo
    exit 1
}
exit 0
