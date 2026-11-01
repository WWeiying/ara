# Export a mapped gate-level Verilog netlist from an isolated DC checkpoint.
#
# Required environment variables:
#   DDC_INPUT       absolute path to a mapped .ddc checkpoint
#   VERILOG_OUTPUT  absolute output path for the gate-level Verilog
#   DC_WORK_DIR     absolute v1-dc work directory containing global_scripts
#
# The script intentionally does not read RTL or alter the source synthesis
# run.  It is used to turn a completed mapped checkpoint into a simulation
# input for SAIF generation.

if {![info exists env(DDC_INPUT)] || ![info exists env(VERILOG_OUTPUT)] ||
    ![info exists env(DC_WORK_DIR)]} {
    error "DDC_INPUT, VERILOG_OUTPUT, and DC_WORK_DIR are required"
}

set dc_work_dir [file normalize $env(DC_WORK_DIR)]
set setup_dir [file join $dc_work_dir global_scripts]
set output_file [file normalize $env(VERILOG_OUTPUT)]

# Recreate the same library/link setup as the source synthesis run without
# relying on the source run's current working directory or its GUI regex.
source [file join $setup_dir synopsys_dc.setup.env]
set GUI_WORK_DIR $dc_work_dir
set GUI_STD_LIBRARY "BWP12T"
set GUI_IP_LIBRARY "t28sram"
set GUI_PVT "tc"
set GUI_DONTUSE_FILE [file join $setup_dir dc_dont_use.tcl]
source [file join $setup_dir synopsys_dc.setup.main]

set_app_var report_default_significant_digits 3
read_ddc [file normalize $env(DDC_INPUT)]
if {![link]} {
    error "Mapped checkpoint failed to link"
}

file mkdir [file dirname $output_file]
set hierarchy_opt "-hierarchy"
eval write -format verilog -output $output_file $hierarchy_opt
puts "MAPPED_NETLIST_EXPORTED $output_file"
quit
