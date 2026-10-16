# Export an unprogrammed XSA for Vitis BSP compilation only.
proc export_loader_xsa {output} {
    if {[version -short] ne "2020.1"} { error "Expected Vivado 2020.1" }
    set project [file join $output project eth_loader_bd.xpr]
    set xsa [file join $output loader_no_bitstream.xsa]
    if {![file isfile $project] || [file exists $xsa]} {
        error "Missing project or XSA already exists"
    }
    open_project $project
    set design [get_files -quiet */loader_bd.bd]
    if {[llength $design] != 1} { error "Expected one loader BD" }
    write_hw_platform -fixed -file $xsa
    if {![file isfile $xsa]} { error "XSA was not generated" }
    close_project
    puts "LOADER_XSA_NO_BITSTREAM $xsa"
}

if {[llength $argv] != 1} { error "Usage: loader_bd_export.tcl OUTPUT" }
if {[catch {export_loader_xsa {*}$argv} message options]} {
    puts stderr [dict get $options -errorinfo]
    exit 1
}
exit 0
