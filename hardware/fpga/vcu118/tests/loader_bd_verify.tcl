# Read-only Vivado check of an already generated loader BD.
proc verify_loader_bd {project build_script} {
    if {[version -short] ne "2020.1"} { error "Expected Vivado 2020.1" }
    set ::loader_bd_library_only 1
    source $build_script
    open_project $project
    set design [get_files -quiet */loader_bd.bd]
    if {[llength $design] != 1} { error "Expected one loader BD" }
    open_bd_design $design
    validate_bd_design
    foreach {left right} {
        mac/m_axis_rxd dma/S_AXIS_S2MM
        mac/m_axis_rxs dma/S_AXIS_STS
        mac/s_axis_txc dma/M_AXIS_CNTRL
        mac/s_axis_txd dma/M_AXIS_MM2S
    } {
        loader_bd::require_pair $left $right
        puts "STREAM_PAIR $left $right"
    }
    foreach space {mb/Data dma/Data_SG dma/Data_MM2S dma/Data_S2MM} {
        loader_bd::require_ddr_map stdout $space
    }
    close_project
    puts "LOADER_BD_VERIFY_PASS"
}

if {[llength $argv] != 2} { error "Usage: loader_bd_verify.tcl PROJECT BUILD_SCRIPT" }
if {[catch {verify_loader_bd {*}$argv} message options]} {
    puts stderr [dict get $options -errorinfo]
    exit 1
}
exit 0
