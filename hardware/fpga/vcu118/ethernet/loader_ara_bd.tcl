# Reuse the tested loader, replacing only its board clock buffer and DDR endpoint.
# IP generation/validation only: no synthesis, implementation or board access.
set ::loader_bd_library_only 1
source [file join [file dirname [info script]] loader_bd_build.tcl]

proc loader_ara_bd {output board_repo} {
    loader_bd::run $output $board_repo cdma
    open_project [file join $output project eth_loader_bd.xpr]
    open_bd_design [get_files */loader_bd.bd]

    set ui_clock_net [get_bd_nets -of_objects [get_bd_pins ddr/c0_ddr4_ui_clk]]
    set ui_reset_net [get_bd_nets -of_objects [get_bd_pins ddr/c0_ddr4_ui_clk_sync_rst]]
    set sys_clock_net [get_bd_nets -of_objects [get_bd_pins sys_clk_250_buffer/IBUF_OUT]]
    delete_bd_objs [get_bd_intf_nets -of_objects [get_bd_intf_pins ddr/C0_DDR4_S_AXI]]
    delete_bd_objs [get_bd_intf_ports ddr4_sdram_c1_062]
    delete_bd_objs [get_bd_intf_ports sys_clk_250]
    delete_bd_objs [get_bd_cells ddr] [get_bd_cells sys_clk_250_buffer]

    set sys [create_bd_port -dir I -type clk -freq_hz 250000000 sys_clk]
    connect_bd_net -net $sys_clock_net $sys [get_bd_pins clock/clk_in1]
    set ui [create_bd_port -dir I -type clk -freq_hz 300000000 ui_clk]
    connect_bd_net -net $ui_clock_net $ui [get_bd_pins ddr_fabric/aclk]
    set rst [create_bd_port -dir I -type rst ui_reset]
    set_property CONFIG.POLARITY ACTIVE_HIGH $rst
    connect_bd_net -net $ui_reset_net $rst [get_bd_pins rst_ddr_300M/ext_reset_in]

    set memory [create_bd_intf_port -mode Master -vlnv xilinx.com:interface:aximm_rtl:1.0 M_DDR]
    set_property -dict [list CONFIG.PROTOCOL AXI4 CONFIG.ADDR_WIDTH 32 \
        CONFIG.DATA_WIDTH 512 CONFIG.HAS_BURST 1 \
        CONFIG.HAS_LOCK 1 CONFIG.HAS_CACHE 1 CONFIG.HAS_PROT 1 \
        CONFIG.HAS_QOS 1 CONFIG.HAS_REGION 0 CONFIG.HAS_WSTRB 1 \
        CONFIG.HAS_BRESP 1 CONFIG.HAS_RRESP 1 CONFIG.NUM_READ_OUTSTANDING 16 \
        CONFIG.NUM_WRITE_OUTSTANDING 16] $memory
    set_property CONFIG.ASSOCIATED_BUSIF M_DDR $ui
    set_property CONFIG.ASSOCIATED_RESET ui_reset $ui
    connect_bd_intf_net [get_bd_intf_pins ddr_fabric/M00_AXI] $memory
    set segment [get_bd_addr_segs -of_objects $memory]
    if {[llength $segment] != 1} { error "Expected one external DDR segment: $segment" }
    foreach space {mb/Data dma/Data_SG dma/Data_MM2S dma/Data_S2MM cdma/Data} {
        assign_bd_address -target_address_space [get_bd_addr_spaces $space] \
            -offset 0x80000000 -range 2G $segment
    }
    validate_bd_design
    # SmartConnect restores input IDs internally; its external port has no ID.
    # Never silently truncate an ID if propagation changes this contract.
    foreach {name expected} {ADDR_WIDTH 32 DATA_WIDTH 512 ID_WIDTH 0 PROTOCOL AXI4} {
        if {[get_property CONFIG.$name $memory] ne $expected} {
            error "Unexpected loader boundary $name=[get_property CONFIG.$name $memory]"
        }
    }
    save_bd_design
    set bd [get_files */loader_bd.bd]
    generate_target all $bd
    set wrapper [make_wrapper -files $bd -top]
    set report [open [file join $output ara_boundary.txt] w]
    puts $report "WRAPPER $wrapper"
    foreach name {ADDR_WIDTH DATA_WIDTH ID_WIDTH PROTOCOL FREQ_HZ} {
        puts $report "$name [get_property CONFIG.$name $memory]"
    }
    foreach space {mb/Data dma/Data_SG dma/Data_MM2S dma/Data_S2MM cdma/Data} {
        foreach seg [get_bd_addr_segs -of_objects [get_bd_addr_spaces $space]] {
            puts $report "MAP $space $seg [get_property OFFSET $seg] [get_property RANGE $seg]"
        }
    }
    close $report
    if {[llength [get_bd_cells -hier -filter {VLNV =~ xilinx.com:ip:ddr4:*}]]} {
        error "Loader must not contain a second DDR controller"
    }
    close_project
    puts "ARA_LOADER_BOUNDARY_VALIDATED $output"
}

if {![info exists ::loader_ara_library_only]} {
    if {[catch {loader_ara_bd {*}$argv} message options]} {
        puts stderr [dict get $options -errorinfo]
        exit 1
    }
    exit 0
}
