# Operate on the routed checkpoint only; never launch synthesis/implementation.
source [file join [file dirname [info script]] common.tcl]
require_vivado
if {[llength $argv] != 3} { error "Expected: routed.dcp output_directory full|audited" }
lassign $argv checkpoint out mode
if {$mode ni {full audited}} { error "Unknown bitstream report mode: $mode" }
if {![file isfile $checkpoint] || [file size $checkpoint] == 0} {
    error "Missing/empty routed checkpoint: $checkpoint"
}
if {[current_project -quiet] ne ""} { error "Close the current project first." }
foreach ext {bit ltx} {
    if {[file exists [file join $out $design_top.$ext]]} { error "Output already exists; select a new directory." }
}
file mkdir $out
open_checkpoint $checkpoint
set code [catch {
    # Do not label a baseline checkpoint as a host/dual-DDR bitstream.
    foreach name {jtag_mem jtag_debug} {
        set count [llength [get_pins -quiet gen_host.i_host_bridge/i_$name/aclk]]
        if {$count != ($fpga_profile ne "baseline")} {
            error "Checkpoint $name hierarchy does not match profile $fpga_profile"
        }
    }
    set count [llength [get_pins -quiet gen_ddr2.i_dram_wrapper_c2/soc_clk_i]]
    if {$count != ($fpga_profile eq "dual_ddr")} {
        error "Checkpoint DDR2 hierarchy does not match profile $fpga_profile"
    }
    set reports [file join $out reports]
    require_no_multiple_drivers $reports
    # In audited mode the wrapper has verified the same checkpoint and immutable
    # full-report evidence. Keep live driver/timing checks and native bitgen DRC.
    if {$mode eq "full"} { write_reports $reports true }
    foreach delay {max min} {
        set paths [get_timing_paths -quiet -delay_type $delay -max_paths 1]
        if {[llength $paths] != 1} { error "Missing $delay timing path" }
        set slack [get_property SLACK $paths]
        if {![fpga_checks::finite $slack] || $slack < 0} {
            error "Timing failed: $delay slack=$slack. No bitstream generated."
        }
    }
    write_debug_probes [file join $out $design_top.ltx]
    # Vivado's mandatory bitgen DRC remains enabled; no severity overrides.
    write_bitstream [file join $out $design_top.bit]
    foreach ext {bit ltx} {
        set path [file join $out $design_top.$ext]
        if {![file isfile $path] || [file size $path] == 0} { error "Missing output: $path" }
    }
} result options]
set close_code [catch {close_design} close_result close_options]
if {$code} { return -options $options $result }
if {$close_code} { return -options $close_options $close_result }
puts "BITSTREAM READY: $fpga_profile; $out"
