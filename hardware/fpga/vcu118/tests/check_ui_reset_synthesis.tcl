# Structural synthesis check only, not board timing signoff.
if {[llength $argv]!=1} {error "Expected isolated output directory"}
set out [lindex $argv 0]
if {[catch {
    create_project -in_memory -part xcvu9p-flga2104-2L-e
    read_verilog -sv [list [file join $out rstgen.sv] [file join $out rstgen_bypass.sv] [file join $out dut.sv]]
    set_property verilog_define {SYNTHESIS ARA_FPGA_DDR2} [current_fileset]
    # Unit-level structure check: omit board I/O buffers around reset_out.
    synth_design -top reset_dut -part xcvu9p-flga2104-2L-e -flatten_hierarchy none -no_iobuf
    create_clock -period 3.333 [get_ports dram_axi_clk]
    set sync [get_cells -hier -filter {NAME =~ i_ui_rstgen/* && REF_NAME == FDCE}]
    if {[llength $sync]!=4} {error "Expected four retained UI synchronization registers"}
    foreach cell $sync {
        if {![get_property ASYNC_REG $cell]} {error "Missing ASYNC_REG on $cell"}
    }
    set distribution [get_cells -hier -filter {NAME == ui_resetn_reg && REF_NAME == FDCE}]
    if {[llength $distribution]!=1} {error "Missing ordinary reset distribution register"}
    foreach prop {ASYNC_REG DONT_TOUCH} {
        if {[get_property $prop $distribution] in {1 true TRUE}} {error "Distribution register protected by $prop"}
    }
    set q [get_pins -of_objects $distribution -filter {REF_PIN_NAME == Q}]
    set output_net [get_nets -segments -of_objects [get_ports reset_out]]
    if {[llength [get_pins -of_objects $output_net -filter {DIRECTION == OUT}]]!=1 ||
        [get_property NAME [get_pins -of_objects $output_net -filter {DIRECTION == OUT}]] ne [get_property NAME $q]} {
        error "Output not driven by distribution register"
    }
    set f [open [file join $out distribution_properties.rpt] w]
    puts $f [report_property -all -return_string $distribution]
    close $f
    write_verilog [file join $out mapped.v]
    write_checkpoint [file join $out reset_synth.dcp]
    set f [open [file join $out passed.txt] w]
    puts $f "Four ASYNC_REG stages retained; ordinary FDCE drives reset output. Not physical signoff."
    close $f
    close_project
} message]} {
    puts stderr $::errorInfo
    exit 1
}
exit 0
