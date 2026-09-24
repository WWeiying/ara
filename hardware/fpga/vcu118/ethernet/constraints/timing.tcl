# Applied to the linked netlist, not an OOC IP. No blanket asynchronous groups.
proc eth_diag_timing {} {
    set sync_d [get_pins -hier -regexp {.*axi_eth_ex_des_data_sync_reg0/D}]
    if {![llength $sync_d]} { error "Missing reviewed example bit synchronizers" }
    set_max_delay 8.0 -datapath_only -to $sync_d

    # RX FIFO publishes a read pointer with a toggle and samples it only after
    # synchronization (rx_client_fifo.v:725-764). Bound the bundled data path.
    set pointer_d [get_pins -hier -regexp {i_fifo/rx_fifo_i/wr_rd_addr_reg\[[0-9]+\]/D}]
    if {[llength $pointer_d] != 6} { error "Expected six RX FIFO bundled pointer bits, found $pointer_d" }
    set_max_delay 8.0 -datapath_only -to $pointer_d
    set_bus_skew 8.0 -to $pointer_d

    # Only the async assertion pins of explicit reset synchronizers are excepted.
    set reset_pre [get_pins -hier -regexp {.*axi_eth_ex_des_reset_sync[0-3]_reg/PRE}]
    if {![llength $reset_pre]} { error "Missing reviewed FIFO reset synchronizers" }
    set_false_path -to $reset_pre
    set own_pre [get_pins -hier -regexp {i_(ctrl|packet)_reset/stages_reg\[[0-2]\]/PRE}]
    if {[llength $own_pre] != 6} { error "Expected six diagnostic reset synchronizer PRE pins" }
    set_false_path -to $own_pre
    set_false_path -from [get_ports sys_rst]

    # Independent PHY reset is asynchronous to the PHY; require bounded routing.
    set_max_delay 20.0 -datapath_only -to [get_ports phy_rst_n]
    # Slow MDIO: host management will use divider 49 (1 MHz at 100 MHz).
    # These pad budgets are not a complete source-synchronous MDIO signoff.
    # The IP has its own MDIO multicycle/first-stage exceptions; retain/report them.
    set_max_delay 20.0 -datapath_only -to [get_ports {mdio mdio_mdc}]
    set_max_delay 20.0 -datapath_only -from [get_ports mdio]
}
