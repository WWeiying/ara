# VCU118 UG1224: U21 Q1, 250 MHz LVDS, HP bank 41 (C2 SLR).
create_clock -period 4.000 -name c2_sys_clk [get_ports c2_sys_clk_p]
set_property PACKAGE_PIN AW26 [get_ports c2_sys_clk_p]
set_property PACKAGE_PIN AW27 [get_ports c2_sys_clk_n]
set_property IOSTANDARD LVDS [get_ports {c2_sys_clk_p c2_sys_clk_n}]
