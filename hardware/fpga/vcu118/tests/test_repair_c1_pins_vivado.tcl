# Real Vivado object-query regression, not a mock of get_pins/get_property.
set ::c1_repair_test_mode true
source [file join [file dirname [info script]] .. ethernet repair_c1_routed.tcl]
if {[catch {
    create_project -in_memory -part xcvu9p-flga2104-2L-e
    link_design -part xcvu9p-flga2104-2L-e -top c1_pin_lookup_test
    set name {gen_slice[2].gen_word[9].word_q_reg[31]}
    create_cell -reference FDRE $name
    set endpoint $name/CE
    set pin [c1_repair::endpoint_pin $endpoint]
    if {[get_property REF_PIN_NAME $pin] ne "CE"} {error "Not a CE pin"}
    set escaped [string map [list {[} {\[} {]} {\]}] $endpoint]
    if {[llength [get_pins -quiet $escaped]]} {error "Unexpected SDC escape behavior"}
    foreach bad [list ${name}/NO_SUCH_PIN */CE] {
        if {![catch {c1_repair::endpoint_pin $bad}]} {error "Accepted missing/nonexact pin: $bad"}
    }
    create_cell -reference LUT6 decode
    create_net ce_net
    connect_net -net [get_nets ce_net] -objects [concat [get_pins decode/O] $pin]
    set net [get_nets -quiet -of_objects $pin]
    set drivers [get_pins -quiet -leaf -of_objects $net -filter {DIRECTION == OUT}]
    set cell [get_cells -quiet -of_objects $drivers]
    if {[get_property NAME $cell] ne "decode" || [get_property REF_NAME $cell] ne "LUT6"} {
        error "Unexpected real net-driver lookup"
    }
    if {![c1_repair::safe_driver i_dram_wrapper/gen_cdc.i_axi_cdc_mig/decode \
        [get_property REF_NAME $cell] [get_property ASYNC_REG $cell] [get_property DONT_TOUCH $cell]]} {
        error "Real combinational driver properties rejected"
    }
    close_project
    puts "PASS: real Vivado indexed-pin and combinational-driver queries"
} message]} {puts stderr $::errorInfo; exit 1}
exit 0
