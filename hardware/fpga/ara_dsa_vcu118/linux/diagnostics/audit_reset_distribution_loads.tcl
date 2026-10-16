# Read-only trace of the synthesized reset tree, including polarity conversion.
if {[llength $argv]!=3} {error "Expected package run output"}
lassign $argv package run out
if {[catch {
    file mkdir $out
    set ::env(ARA_FPGA_PROFILE) dual_ddr_ethernet
    source [file join $package scripts common.tcl]
    open_package_project
    open_run $run
    set f [open [file join $out reset_tree.tsv] w]
    puts $f "wrapper\tkind\tpin\tcell_type\tinit"
    foreach wrapper {i_dram_wrapper gen_ddr2.i_dram_wrapper_c2} {
        set dist [get_cells -quiet -hier -filter "NAME == $wrapper/ui_resetn_reg"]
        if {[llength $dist]!=1} {error "Missing distribution register: $wrapper"}
        set q [get_pins -of_objects $dist -filter {REF_PIN_NAME == Q}]
        set direct [get_pins -of_objects [get_nets -segments -of_objects $q] -filter {DIRECTION == IN && IS_LEAF}]
        set endpoints [all_fanout -flat -endpoints_only -from $q]
        puts "RESET_TREE $wrapper DIRECT=[llength $direct] ENDPOINTS=[llength $endpoints]"
        foreach pins [list $direct $endpoints] kind {direct endpoint} {
            foreach pin $pins {
                set cell [get_cells -quiet -of_objects $pin]
                puts $f "$wrapper\t$kind\t[get_property NAME $pin]\t[get_property REF_NAME $cell]\t[get_property INIT $cell]"
            }
        }
        report_property -all $dist -file [file join $out [file tail $wrapper]_distribution.rpt]
    }
    close $f
    close_project
} message]} {puts stderr $::errorInfo; exit 1}
exit 0
