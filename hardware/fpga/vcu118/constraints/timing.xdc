# FPGA J53 TAP: <=1 MHz TCK, high/low >=400 ns, TMS/TDI change on falling TCK.
# TCK is sampled as data at >=50 MHz. No JTAG clock, clock-route waiver or
# asynchronous clock group. First-stage input/TDO budgets live in cdc.xdc.
# RX is bounded to its first synchronizer D pin in cdc.xdc. Do not invent
# a synchronous external launch clock for this asynchronous serial input.
set_max_delay 70.0 -to [get_ports uart_tx_o]
set_false_path -hold -to [get_ports uart_tx_o]
set_false_path -from [get_ports sys_reset]
