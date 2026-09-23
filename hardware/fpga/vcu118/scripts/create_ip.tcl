# Real vendor IP only. No synthesis black-box substitutes are supplied.
create_ip -name clk_wiz -vendor xilinx.com -library ip -version 6.0 -module_name clkwiz
set_property -dict [list \
    CONFIG.PRIM_IN_FREQ {250.000} CONFIG.PRIM_SOURCE {No_buffer} \
    CONFIG.USE_RESET {true} CONFIG.RESET_TYPE {ACTIVE_HIGH} \
    CONFIG.NUM_OUT_CLKS {1} CONFIG.CLKOUT1_USED {true} \
    CONFIG.CLK_OUT1_PORT {clk_50} CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {50.000} \
] [get_ips clkwiz]

create_ip -name vio -vendor xilinx.com -library ip -version 3.0 -module_name vio
set_property -dict [list \
    CONFIG.C_NUM_PROBE_IN {1} CONFIG.C_PROBE_IN0_WIDTH {4} \
    CONFIG.C_NUM_PROBE_OUT {3} \
    CONFIG.C_PROBE_OUT0_WIDTH {1} CONFIG.C_PROBE_OUT0_INIT_VAL {0x0} \
    CONFIG.C_PROBE_OUT1_WIDTH {2} CONFIG.C_PROBE_OUT1_INIT_VAL {0x0} \
    CONFIG.C_PROBE_OUT2_WIDTH {1} CONFIG.C_PROBE_OUT2_INIT_VAL {0x1} \
] [get_ips vio]

# One populated VCU118 64-bit DDR4 channel, 2 GiB at physical 0x80000000.
# Settings are based on Cheshire's VCU118 port and AMD board preset 2.4.
set ddr_ips {ddr4 ddr4_sdram_c1_062}
if {$fpga_profile eq "dual_ddr"} { lappend ddr_ips ddr4_c2 ddr4_sdram_c2_062 }
# Both interfaces are present in the bundled vcu118/2.4/board.xml.
# Separate IP instances retain their c0_* ports; the board top maps C2 to c1_*.
foreach {name interface} $ddr_ips {
create_ip -name ddr4 -vendor xilinx.com -library ip -version 2.2 -module_name $name
set_property -dict [list \
    CONFIG.System_Clock {No_Buffer} CONFIG.Reference_Clock {No_Buffer} \
    CONFIG.C0_DDR4_BOARD_INTERFACE $interface \
    CONFIG.C0.DDR4_InputClockPeriod {4000} CONFIG.C0.DDR4_CLKOUT0_DIVIDE {5} \
    CONFIG.C0.DDR4_MemoryPart {MT40A256M16LY-062E} \
    CONFIG.C0.DDR4_TimePeriod {833} CONFIG.C0.DDR4_DataWidth {64} \
    CONFIG.C0.DDR4_DataMask {DM_NO_DBI} CONFIG.C0.DDR4_MCS_ECC {false} \
    CONFIG.C0.DDR4_CasWriteLatency {12} CONFIG.C0.DDR4_CasLatency {18} \
    CONFIG.C0.DDR4_AxiDataWidth {512} CONFIG.C0.DDR4_AxiAddressWidth {31} \
    CONFIG.C0.DDR4_AxiIDWidth {8} CONFIG.C0.BANK_GROUP_WIDTH {1} \
    CONFIG.C0.DDR4_AxiSelection {true} \
] [get_ips $name]
}

if {$fpga_profile ne "baseline"} {
    # PG174 v1.2 user parameter names, not the RTL C_* parameter names.
    # Vivado rejects unsupported properties/values instead of using defaults.
    create_ip -name jtag_axi -vendor xilinx.com -library ip -version 1.2 -module_name jtag_mem
    set_property -dict [list \
        CONFIG.PROTOCOL {0} CONFIG.M_AXI_DATA_WIDTH {64} \
        CONFIG.M_AXI_ADDR_WIDTH {64} CONFIG.M_AXI_ID_WIDTH {2} \
        CONFIG.WR_TXN_QUEUE_LENGTH {16} CONFIG.RD_TXN_QUEUE_LENGTH {16} \
    ] [get_ips jtag_mem]
    create_ip -name jtag_axi -vendor xilinx.com -library ip -version 1.2 -module_name jtag_debug
    set_property -dict [list \
        CONFIG.PROTOCOL {2} CONFIG.M_AXI_DATA_WIDTH {32} \
        CONFIG.M_AXI_ADDR_WIDTH {32} \
    ] [get_ips jtag_debug]
}
generate_target all [get_ips $profile_ips]
# create_ip_run accepts one sub-design, not an IP collection (UG835).
foreach name $profile_ips {
    create_ip_run [get_ips $name]
}
