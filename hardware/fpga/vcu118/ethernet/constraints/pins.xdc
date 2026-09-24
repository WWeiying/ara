# VCU118 2.4 board XML and UG1224 Table 3-25. Not the vendor example LOC file.
foreach {port pin standard} {
    clk_in_p G31 DIFF_SSTL12 clk_in_n F31 DIFF_SSTL12
    sys_rst L19 LVCMOS12
    mgt_clk_p AT22 LVDS mgt_clk_n AU22 LVDS
    sgmii_txp AU21 DIFF_HSTL_I_DCI_18 sgmii_txn AV21 DIFF_HSTL_I_DCI_18
    sgmii_rxp AU24 DIFF_HSTL_I_DCI_18 sgmii_rxn AV24 DIFF_HSTL_I_DCI_18
    mdio AR23 LVCMOS18 mdio_mdc AV23 LVCMOS18 phy_rst_n BA21 LVCMOS18
} {
    set_property PACKAGE_PIN $pin [get_ports $port]
    set_property IOSTANDARD $standard [get_ports $port]
}
set_property OUTPUT_IMPEDANCE RDRV_48_48 [get_ports {sgmii_txp sgmii_txn}]
set_property ODT RTT_48 [get_ports {sgmii_rxp sgmii_rxn}]
set_property DIFF_TERM TRUE [get_ports {mgt_clk_p mgt_clk_n}]
create_clock -name system_clock -period 3.333 [get_ports clk_in_p]
# PCS/PMA scoped clocks.xdc supplies the PHY reference clock (1.600 ns).
