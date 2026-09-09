# VCU118 pin assignments from pulp-platform/cheshire, a315a828.
# SPDX-License-Identifier: SHL-0.51
create_clock -period 4.000 -name sys_clk [get_ports sys_clk_p]
set_property PACKAGE_PIN E12 [get_ports sys_clk_p]
set_property PACKAGE_PIN D12 [get_ports sys_clk_n]
set_property IOSTANDARD LVDS [get_ports {sys_clk_p sys_clk_n}]
set_property PACKAGE_PIN L19 [get_ports sys_reset]
set_property IOSTANDARD LVCMOS12 [get_ports sys_reset]
set_property PACKAGE_PIN AW25 [get_ports uart_rx_i]
set_property PACKAGE_PIN BB21 [get_ports uart_tx_o]
set_property IOSTANDARD LVCMOS18 [get_ports {uart_rx_i uart_tx_o}]
# External CPU debug TAP at J53, NOT the FPGA configuration USB-JTAG.
set_property PACKAGE_PIN N28 [get_ports jtag_tms_i]
set_property PACKAGE_PIN M30 [get_ports jtag_tdi_i]
set_property PACKAGE_PIN N30 [get_ports jtag_tdo_o]
set_property PACKAGE_PIN P30 [get_ports jtag_tck_i]
set_property IOSTANDARD LVCMOS12 [get_ports {jtag_tms_i jtag_tdi_i jtag_tdo_o jtag_tck_i}]
set_property PULLDOWN true [get_ports jtag_tck_i]
set_property PULLUP true [get_ports {jtag_tms_i jtag_tdi_i}]
# All DDR pins and electrical constraints come from the generated DDR4 IP XDC.
set_property BITSTREAM.CONFIG.SPI_BUSWIDTH 4 [current_design]
