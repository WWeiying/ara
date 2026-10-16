# Read-only evidence for why high-fanout reset optimization did not replicate.
if {[llength $argv]!=2} {error "Expected checkpoint output"}
lassign $argv checkpoint out
if {[catch {
    set_param general.maxThreads 8
    open_checkpoint $checkpoint
    set f [open [file join $out reset_properties.tsv] w]
    puts $f "cell\tproperty\tvalue"
    foreach wrapper {i_dram_wrapper gen_ddr2.i_dram_wrapper_c2} {
        for {set i 0} {$i<4} {incr i} {
            set name [format {%s/i_ui_rstgen/i_rstgen_bypass/synch_regs_q_reg[%d]} $wrapper $i]
            set cell [get_cells -quiet -hierarchical -filter "NAME == $name"]
            if {[llength $cell]!=1} {error "Missing reset register: $name"}
            set props [list_property $cell]
            foreach prop {REF_NAME ASYNC_REG DONT_TOUCH LOC BEL PHYS_OPT_MODIFIED PHYS_OPT_SKIPPED} {
                if {$prop in $props} {puts $f "$name\t$prop\t[get_property $prop $cell]"}
            }
            set pins [get_pins -of_objects $cell -filter {DIRECTION == OUT}]
            set nets [get_nets -segments -of_objects $pins]
            set loads [get_pins -leaf -of_objects $nets -filter {DIRECTION == IN}]
            puts $f "$name\tdirect_load_pins\t[llength $loads]"
        }
    }
    close $f
    foreach clock {mmcm_clkout0 mmcm_clkout0_1} {
        report_timing -delay_type max -group $clock -max_paths 20 -nworst 1 \
            -path_type full_clock_expanded -file [file join $out ${clock}_data.rpt]
    }
    report_timing -delay_type min -max_paths 10 -nworst 1 \
        -path_type full_clock_expanded -file [file join $out hold.rpt]
    close_design
} message]} {
    puts stderr $::errorInfo
    exit 1
}
exit 0
