# Read-only review of the existing synthesis, not a timing waiver.
lassign $argv package out
if {[llength $argv] != 2 || [file exists $out]} {error "Expected package and new output directory"}
file mkdir $out
source [file join $package scripts common.tcl]
source [file join $package scripts run_support.tcl]
set_param general.maxThreads 4
open_package_project
set runs [get_runs -quiet synth_debfe7e4727b]
if {[llength $runs] != 1 || [get_property STATUS $runs] ne "synth_design Complete!"} {
    error "Expected completed frozen dual synthesis"
}
open_run $runs
set prefix {gen_ddr2.i_dram_wrapper_c2/gen_channel_c2.i_dram/inst/}
set f [open [file join $out clocks.tsv] w]
puts $f "clock\tsource"
foreach clock [get_clocks] {
    foreach pin [get_property SOURCE_PINS $clock] {
        puts $f "[get_property NAME $clock]\t$pin"
    }
}
close $f
set f [open [file join $out paths.tsv] w]
puts $f "from\tto\tslack\tsource\tdestination"
foreach from {mmcm_clkout0 mmcm_clkout0} to {mmcm_clkout0 mmcm_clkout6} expected {581 1} {
    foreach clock_name [list $from $to] {
        set clock [get_clocks -quiet $clock_name]
        if {[llength $clock] != 1} {error "Missing clock $clock_name"}
        set sources [get_property SOURCE_PINS $clock]
        if {[llength $sources] != 1 || ![string match ${prefix}* [lindex $sources 0]]} {
            error "Clock $clock_name does not belong to C2: $sources"
        }
    }
    set paths [get_timing_paths -delay_type min -from [get_clocks $from] -to [get_clocks $to] \
        -slack_lesser_than 0 -nworst 1 -max_paths 1000]
    if {[llength $paths] != $expected} {error "Changed negative endpoint count: $from -> $to: [llength $paths]"}
    foreach path $paths {
        set source [get_property STARTPOINT_PIN $path]
        set dest [get_property ENDPOINT_PIN $path]
        set slack [get_property SLACK $path]
        if {![string match ${prefix}* $source] || ![string match ${prefix}* $dest]} {
            error "Negative path leaves the C2 MIG: $source -> $dest"
        }
        if {![fpga_checks::finite $slack] || $slack < -0.403} {error "Unexpected slack $slack"}
        puts $f "$from\t$to\t$slack\t$source\t$dest"
    }
    report_timing -delay_type min -from [get_clocks $from] -to [get_clocks $to] \
        -slack_lesser_than 0 -nworst 1 -max_paths 1000 -file [file join $out ${from}_to_${to}.rpt]
}
close $f
set f [open [file join $out review_complete.txt] w]
puts $f "C2 path inventory complete; not placed/routed timing acceptance"
close $f
close_project
exit
