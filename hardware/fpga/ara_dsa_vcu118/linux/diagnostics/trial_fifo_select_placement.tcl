# Isolate the effect of DONT_TOUCH on local read selectors, not CDC pointers.
if {[llength $argv]!=2} {error "Expected placed checkpoint output"}
lassign $argv checkpoint out
proc selector_stage {value} {
    set f [open [file join $::out stage.txt] w]
    puts $f $value
    close $f
    puts "FIFO_SELECTOR_TRIAL $value"
    flush stdout
}
if {[catch {
    set_param general.maxThreads 8
    selector_stage open_checkpoint
    open_checkpoint $checkpoint
    set targets {}
    foreach wrapper {i_dram_wrapper gen_ddr2.i_dram_wrapper_c2} {
        set pattern $wrapper/gen_cdc.i_axi_cdc_mig/i_axi_cdc_dst/i_cdc_fifo_gray_dst_w/gen_fpga_read.gen_slice*.select_q_reg*
        set cells [get_cells -quiet -hier -filter "NAME =~ $pattern && REF_NAME =~ FD*"]
        if {[llength $cells]<32 || [llength $cells]>1024} {error "Unexpected selector inventory: $wrapper"}
        foreach cell $cells {
            if {[get_property ASYNC_REG $cell] in {1 true TRUE}} {error "Refuse synchronizer modification: $cell"}
            if {[get_property DONT_TOUCH $cell] ni {1 true TRUE}} {error "Expected protected selector: $cell"}
            lappend targets [get_property NAME $cell]
        }
    }
    set f [open [file join $out changed_properties.tsv] w]
    puts $f "object\tproperty\tbefore\tafter"
    foreach name $targets {
        # Tcl list expansion strips Vivado collection object typing.
        set cell [get_cells -quiet -hier -filter "NAME == $name"]
        if {[llength $cell]!=1} {error "Selector disappeared: $name"}
        puts $f "[get_property NAME $cell]\tDONT_TOUCH\t[get_property DONT_TOUCH $cell]\t0"
        set_property DONT_TOUCH false $cell
        set q [get_pins -of_objects $cell -filter {REF_PIN_NAME == Q}]
        foreach net [get_nets -segments -of_objects $q] {
            if {[get_property DONT_TOUCH $net] in {1 true TRUE}} {
                puts $f "[get_property NAME $net]\tDONT_TOUCH\t1\t0"
                set_property DONT_TOUCH false $net
            }
        }
    }
    close $f
    selector_stage optimize_local_selectors
    phys_opt_design -directive AggressiveFanoutOpt
    write_checkpoint [file join $out selectors_placed.dcp]
    selector_stage reports
    foreach clock {mmcm_clkout0 mmcm_clkout0_1} {
        report_timing -delay_type max -group $clock -max_paths 20 -nworst 1 \
            -path_type full_clock_expanded -file [file join $out ${clock}_data.rpt]
    }
    report_timing_summary -file [file join $out timing_summary.rpt]
    report_bus_skew -file [file join $out bus_skew.rpt]
    selector_stage complete_selector_experiment_not_reset_fix_not_signoff
    close_design
} message]} {
    puts stderr $::errorInfo
    selector_stage failed
    exit 1
}
exit 0
