# Applied to the linked netlist, not an OOC IP. No blanket asynchronous groups.
proc eth_diag_timing {} {
    set sync_d [get_pins -hier -regexp {.*axi_eth_ex_des_data_sync_reg0/D}]
    if {![llength $sync_d]} { error "Missing reviewed example bit synchronizers" }
    # Use real timing startpoints across IP hierarchy, not intermediate Q/LUT
    # pins (which can segment paths) or a wildcard covering every clock domain.
    set sync_from [all_fanin -flat -startpoints_only $sync_d]
    if {![llength $sync_from]} { error "Missing bit-synchronizer timing startpoints" }
    eth_build::note "TIMING_SYNC FROM=$sync_from TO=$sync_d"
    set_max_delay 8.0 -datapath_only -from $sync_from -to $sync_d

    # RX FIFO publishes a read pointer with a toggle and samples it only after
    # synchronization (rx_client_fifo.v:725-764). Bound the bundled data path.
    set pointer_d [get_pins -hier -regexp {i_fifo/rx_fifo_i/wr_rd_addr_reg\[[0-9]+\]/D}]
    if {[llength $pointer_d] != 6} { error "Expected six RX FIFO bundled pointer bits, found $pointer_d" }
    # Only rd_addr[11:6] carries the bundled data. Reset, toggle and CE/feedback
    # logic feeding wr_rd_addr are not members of this six-bit skew group.
    set pointer_c [get_pins -hier -regexp {i_fifo/rx_fifo_i/rd_addr_reg\[(6|7|8|9|10|11)\]/C}]
    if {[llength $pointer_c] != 6} { error "Expected six RX FIFO source clock pins, found $pointer_c" }
    eth_build::note "TIMING_POINTER FROM=$pointer_c TO=$pointer_d"
    set_max_delay 8.0 -datapath_only -from $pointer_c -to $pointer_d
    set_bus_skew 8.0 -from $pointer_c -to $pointer_d

    # Only the async assertion pins of explicit reset synchronizers are excepted.
    set reset_pre [get_pins -hier -regexp {.*axi_eth_ex_des_reset_sync[0-3]_reg/PRE}]
    if {![llength $reset_pre]} { error "Missing reviewed FIFO reset synchronizers" }
    set_false_path -to $reset_pre
    set own_pre [get_pins -hier -regexp {i_(ctrl|packet)_reset/stages_reg\[[0-2]\]/PRE}]
    if {[llength $own_pre] != 6} { error "Expected six diagnostic reset synchronizer PRE pins" }
    set_false_path -to $own_pre
    set_false_path -from [get_ports sys_rst]

    set ctrl_clock [get_clocks -of_objects [get_pins i_jtag/aclk]]
    if {[llength $ctrl_clock] != 1} { error "Expected one management clock for output pad budgets" }
    eth_build::note "TIMING_PADS FROM=$ctrl_clock TO=phy_rst_n,mdio,mdio_mdc"
    # Independent PHY reset is asynchronous to the PHY; require bounded routing.
    set_max_delay 20.0 -datapath_only -from $ctrl_clock -to [get_ports phy_rst_n]
    # Slow MDIO: host management will use divider 49 (1 MHz at 100 MHz).
    # These pad budgets are not a complete source-synchronous MDIO signoff.
    # The IP has its own MDIO multicycle/first-stage exceptions; retain/report them.
    set_max_delay 20.0 -datapath_only -from $ctrl_clock -to [get_ports {mdio mdio_mdc}]
    set mdio_port [get_ports mdio]
    set mdio_to [all_fanout -flat -endpoints_only $mdio_port]
    if {![llength $mdio_to]} { error "Missing MDIO input timing endpoints" }
    eth_build::note "TIMING_MDIO_INPUT FROM=$mdio_port TO=$mdio_to"
    set_max_delay 20.0 -datapath_only -from $mdio_port -to $mdio_to
}
