# Implementation-only constraints: retain hierarchy in synthesis so CDC
# endpoints can be identified and a missing match is a hard failure.
set async_pins [get_pins -hierarchical -filter \
    {NAME =~ *i_dram_wrapper*async_data* || NAME =~ *i_dram_wrapper*async_wptr* || NAME =~ *i_dram_wrapper*async_rptr*}]
if {![llength $async_pins]} { error "DDR AXI CDC pins not found; do not implement unconstrained." }
# 3 ns is conservative for the configured DDR4 UI period and 20 ns SoC period.
# Never cut both clocks as asynchronous: doing so would override this bound.
set_max_delay -datapath_only 3.0 -through $async_pins
set_false_path -hold -through $async_pins
set ui_clocks [get_clocks -of_objects [get_pins i_dram_wrapper/i_dram/c0_ddr4_ui_clk]]
if {![llength $ui_clocks]} { error "DDR UI generated clock not found." }
foreach clock $ui_clocks {
    if {[get_property PERIOD $clock] < 3.0} { error "DDR UI is faster than CDC constraint assumption." }
}
# Async-reset assertion is intentional; rstgen synchronizes deassertion.
set rst_pins [get_pins -hierarchical -filter {NAME =~ *i_rstgen/rst_ni || NAME =~ *i_ui_rstgen/rst_ni}]
if {![llength $rst_pins]} { error "Expected reset synchronizers not found." }
set_false_path -through $rst_pins
