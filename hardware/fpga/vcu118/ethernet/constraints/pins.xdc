# VCU118 2.4 board XML and UG1224 Table 3-25. Not the vendor example LOC file.
# Keep this declarative: Vivado's XDC reader does not execute Tcl foreach.
set_property -dict {PACKAGE_PIN G31 IOSTANDARD DIFF_SSTL12} [get_ports clk_in_p]
set_property -dict {PACKAGE_PIN F31 IOSTANDARD DIFF_SSTL12} [get_ports clk_in_n]
set_property -dict {PACKAGE_PIN L19 IOSTANDARD LVCMOS12} [get_ports sys_rst]
set_property -dict {PACKAGE_PIN AT22 IOSTANDARD LVDS} [get_ports mgt_clk_p]
set_property -dict {PACKAGE_PIN AU22 IOSTANDARD LVDS} [get_ports mgt_clk_n]
set_property -dict {PACKAGE_PIN AU21 IOSTANDARD DIFF_HSTL_I_DCI_18} [get_ports sgmii_txp]
set_property -dict {PACKAGE_PIN AV21 IOSTANDARD DIFF_HSTL_I_DCI_18} [get_ports sgmii_txn]
set_property -dict {PACKAGE_PIN AU24 IOSTANDARD DIFF_HSTL_I_DCI_18} [get_ports sgmii_rxp]
set_property -dict {PACKAGE_PIN AV24 IOSTANDARD DIFF_HSTL_I_DCI_18} [get_ports sgmii_rxn]
set_property -dict {PACKAGE_PIN AR23 IOSTANDARD LVCMOS18} [get_ports mdio]
set_property -dict {PACKAGE_PIN AV23 IOSTANDARD LVCMOS18} [get_ports mdio_mdc]
set_property -dict {PACKAGE_PIN BA21 IOSTANDARD LVCMOS18} [get_ports phy_rst_n]
set_property OUTPUT_IMPEDANCE RDRV_48_48 [get_ports {sgmii_txp sgmii_txn}]
set_property ODT RTT_48 [get_ports {sgmii_rxp sgmii_rxn}]
set_property DIFF_TERM_ADV TERM_100 [get_ports {mgt_clk_p mgt_clk_n}]
create_clock -name system_clock -period 3.333 [get_ports clk_in_p]
# PCS/PMA scoped clocks.xdc supplies the PHY reference clock (1.600 ns).
