# Require the actual two-channel top netlist, not the isolated reset unit.
proc check_dual_reset_netlist {out} {
    set f [open [file join $out reset_structure.tsv] w]
    puts $f "wrapper\tsynchronizers\tdistribution\tdirect_loads\treset_endpoints"
    foreach wrapper {i_dram_wrapper gen_ddr2.i_dram_wrapper_c2} {
        set sync [get_cells -quiet -hier -filter "NAME =~ $wrapper/i_ui_rstgen/* && REF_NAME == FDCE"]
        if {[llength $sync]!=4} {error "Expected four UI reset synchronization stages: $wrapper"}
        foreach cell $sync {
            if {[get_property ASYNC_REG $cell] ni {1 true TRUE}} {error "Unprotected reset synchronizer: $cell"}
        }
        set dist [get_cells -quiet -hier -filter "NAME == $wrapper/ui_resetn_reg && REF_NAME == FDCE"]
        if {[llength $dist]!=1} {error "Missing new reset distribution stage: $wrapper"}
        foreach prop {ASYNC_REG DONT_TOUCH} {
            if {[get_property $prop $dist] in {1 true TRUE}} {error "Distribution stage cannot replicate: $prop / $dist"}
        }
        set clr [get_pins -of_objects $dist -filter {REF_PIN_NAME == CLR}]
        # CLR is active high; Vivado inserts an inverter after rst_no.
        set drivers [all_fanin -flat -startpoints_only -to $clr]
        if {[llength $drivers]!=1 || ![string match $wrapper/i_ui_rstgen/* [get_property NAME $drivers]]} {
            error "Distribution reset not driven by retained synchronization chain: $wrapper"
        }
        set q [get_pins -of_objects $dist -filter {REF_PIN_NAME == Q}]
        set loads [get_pins -of_objects [get_nets -segments -of_objects $q] -filter {DIRECTION == IN && IS_LEAF}]
        # Active-low RTL reset becomes LUT inverters feeding active-high CLR/PRE.
        # Count reset endpoints through that combinational tree, not LUT inputs.
        set endpoints [all_fanout -flat -endpoints_only -from $q]
        set resets [filter $endpoints {REF_PIN_NAME == CLR || REF_PIN_NAME == PRE}]
        if {[llength $resets]<100} {error "Reset distribution does not reach UI reset endpoints: $wrapper"}
        puts $f "$wrapper\t4\t[get_property NAME $dist]\t[llength $loads]\t[llength $resets]"
    }
    close $f
}
if {![info exists ::dual_reset_library_only]} {
    if {[llength $argv]!=3} {error "Expected package synthesis_run output"}
    lassign $argv package run out
    if {[catch {
        set ::env(ARA_FPGA_PROFILE) dual_ddr_ethernet
        source [file join $package scripts common.tcl]
        open_package_project
        open_run $run
        check_dual_reset_netlist $out
        close_project
    } message]} {puts stderr $::errorInfo; exit 1}
    exit 0
}
