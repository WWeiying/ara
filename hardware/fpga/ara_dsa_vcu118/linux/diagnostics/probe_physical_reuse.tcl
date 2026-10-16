# Read-only physical comparison and incremental matching, not acceptance.
proc mark {out name} {
    set f [open [file join $out stage.txt] w]
    puts $f $name
    close $f
    puts "PROBE_STAGE $name"
    flush stdout
}
proc inspect_design {out label checkpoint} {
    mark $out opening_$label
    open_checkpoint $checkpoint
    set dir [file join $out $label]
    file mkdir $dir
    set fifo {i_dram_wrapper/gen_cdc.i_axi_cdc_mig/i_axi_cdc_dst/i_cdc_fifo_gray_src_r}
    set f [open [file join $dir cells.tsv] w]
    puts $f "cell\tref\tloc\tbel"
    foreach c [get_cells -quiet -hierarchical -filter "NAME =~ $fifo/*"] {
        if {[get_property IS_PRIMITIVE $c]} {
            puts $f "$c\t[get_property REF_NAME $c]\t[get_property LOC $c]\t[get_property BEL $c]"
        }
    }
    close $f
    set f [open [file join $dir nets.tsv] w]
    puts $f "net\tsinks\tdriver"
    foreach n [get_nets -quiet -hierarchical -filter "NAME =~ $fifo/*"] {
        set sinks [get_pins -quiet -of_objects $n -filter {DIRECTION == IN}]
        if {[llength $sinks] >= 32} {
            puts $f "$n\t[llength $sinks]\t[get_pins -quiet -of_objects $n -filter {DIRECTION == OUT}]"
        }
    }
    close $f
    foreach clock {mmcm_clkout0 clk_50_clkwiz IntRx_ClkOut0} {
        set c [get_clocks -quiet $clock]
        if {[llength $c] != 1} {error "Missing clock $clock"}
        report_timing -from $c -to $c -delay_type max -max_paths 20 \
            -file [file join $dir ${clock}_paths.rpt]
    }
    set pin [get_pins -quiet {i_dram_wrapper/gen_cdc.i_axi_cdc_mig/i_axi_cdc_dst/i_cdc_fifo_gray_src_r/gen_fpga_write.gen_slice[1].gen_word[23].word_q_reg[26]/CE}]
    if {[llength $pin]} {
        report_timing -to $pin -delay_type max -max_paths 1 \
            -file [file join $dir same_endpoint.rpt]
    }
    close_design
}
if {[catch {
    if {[llength $argv] != 4} {error "Expected old_routed new_routed new_opt output"}
    lassign $argv old current optimized out
    foreach path [list $old $current $optimized] {
        if {![file isfile $path]} {error "Missing checkpoint $path"}
    }
    set_param general.maxThreads 8
    inspect_design $out old $old
    inspect_design $out current $current
    mark $out incremental_matching
    # The new optimized netlist remains authoritative; reference supplies
    # matching placement/routing only. Never write or program the old netlist.
    open_checkpoint $optimized
    read_checkpoint -incremental $old
    report_incremental_reuse -file [file join $out incremental_reuse.rpt]
    close_design
    mark $out collected_requires_review
} message]} {
    puts stderr $::errorInfo
    if {[info exists out]} {mark $out failed}
    exit 1
}
exit 0
