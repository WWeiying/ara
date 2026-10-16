# Elaborate and synthesize the isolated loader BD; no bitstream or board access.
namespace eval loader_synth {
    proc run {output} {
        if {[version -short] ne "2020.1"} { error "Expected Vivado 2020.1" }
        set project [file join $output project eth_loader_bd.xpr]
        if {![file isfile $project]} { error "Missing loader BD project: $project" }
        set report [file join $output synth_report.txt]
        if {[file exists $report]} { error "Synthesis report already exists: $report" }
        open_project $project
        set design [get_files -quiet */loader_bd.bd]
        if {[llength $design] != 1} { error "Expected one loader BD, got $design" }
        generate_target all $design
        set wrapper [make_wrapper -files $design -top]
        if {![file isfile $wrapper]} { error "Wrapper not generated: $wrapper" }
        add_files -norecurse $wrapper
        set_property top loader_bd_wrapper [current_fileset]
        update_compile_order -fileset sources_1
        report_compile_order -file [file join $output compile_order.rpt]
        launch_runs synth_1 -jobs 4
        wait_on_run synth_1
        set status [get_property STATUS [get_runs synth_1]]
        if {$status ne "synth_design Complete!"} {
            error "Synthesis did not complete: $status"
        }
        open_run synth_1
        set channel [open $report {WRONLY CREAT EXCL}]
        puts $channel "SYNTH_COMPLETE $status"
        puts $channel "TOP [get_property TOP [current_fileset]]"
        foreach cell [get_cells -hier -quiet -filter {IS_BLACKBOX == 1}] {
            puts $channel "BLACKBOX $cell"
        }
        close $channel
        report_utilization -file [file join $output utilization_synth.rpt]
        close_project
        puts "LOADER_SYNTH_COMPLETE $output"
    }
}

if {[llength $argv] != 1} { error "Usage: loader_bd_synth.tcl OUTPUT" }
if {[catch {loader_synth::run {*}$argv} message options]} {
    puts stderr [dict get $options -errorinfo]
    exit 1
}
exit 0
