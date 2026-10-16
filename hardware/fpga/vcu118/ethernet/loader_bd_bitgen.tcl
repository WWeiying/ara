# Bitgen for the isolated, reviewed J10 loader. This never programs a device.
proc loader_bitgen {output tag board_repo} {
    if {[version -short] ne "2020.1"} { error "Expected Vivado 2020.1" }
    if {![regexp {^_[A-Za-z0-9_]+$} $tag]} { error "Invalid output tag" }
    set checkpoint [file join $output loader_routed${tag}.dcp]
    set gate [file join $output route_gate${tag}.txt]
    set skew [file join $output bus_skew_routed${tag}.rpt]
    set bit [file join $output loader${tag}.bit]
    if {![file isfile $checkpoint] || ![file isfile $gate] || ![file isfile $skew] ||
        ![file isdirectory $board_repo] || [file exists $bit]} {
        error "Missing reviewed input or bitstream already exists"
    }
    set channel [open $gate r]
    set gate_text [read $channel]
    close $channel
    if {![string match *AUTOMATED_ROUTE_GATES_PASS* $gate_text]} {
        error "Routed timing/DRC gate did not pass"
    }
    set channel [open $skew r]
    set skew_text [read $channel]
    close $channel
    if {[regexp {Slack \(VIOLATED\)} $skew_text] ||
        ![regexp {Slack \(MET\)} $skew_text]} {
        error "Bus-skew report missing passing paths or contains a violation"
    }
    set_param board.repoPaths [list [file normalize $board_repo]]
    open_checkpoint $checkpoint
    report_drc -name loader_bitgen_drc -file [file join $output drc_bitgen${tag}.rpt]
    foreach violation [get_drc_violations -quiet -name loader_bitgen_drc] {
        set severity [get_property SEVERITY $violation]
        if {$severity eq "Error" || $severity eq "Critical Warning"} {
            error "Bitgen DRC gate failed: $violation ($severity)"
        }
    }
    foreach type {max min} {
        set path [get_timing_paths -delay_type $type -max_paths 1]
        if {[llength $path] != 1} { error "Missing $type timing path" }
        set slack [get_property SLACK $path]
        if {![string is double -strict $slack] || $slack < 0} {
            error "$type timing gate failed: $slack"
        }
        puts "TIMING_$type SLACK=$slack"
    }
    write_bitstream -file $bit
    write_debug_probes -file [file join $output loader${tag}.ltx]
    if {![file isfile $bit]} { error "Bitstream not written" }
    puts "BITSTREAM_GENERATED_NOT_PROGRAMMED $bit"
    close_design
}

if {[llength $argv] != 3} {
    error "Usage: loader_bd_bitgen.tcl OUTPUT TAG BOARD_REPO"
}
if {[catch {loader_bitgen {*}$argv} message options]} {
    puts stderr [dict get $options -errorinfo]
    exit 1
}
exit 0
