# Reopen an existing managed synthesis. No launch, save, placement or routing.
if {[llength $argv] != 3} { error "Usage: project.xpr synth_run new_output" }
lassign $argv project run output
if {![file isfile $project] || ![regexp {^synth_[0-9a-f]{12}$} $run] ||
    [file exists $output]} { error "Invalid/read-only inspection arguments" }
file mkdir $output
open_project $project
if {![string match {*synth_design Complete*} [get_property STATUS [get_runs $run]]]} {
    error "Synthesis did not complete"
}
open_run $run
set f [open [file join $output setup.tsv] w]
puts $f "slack\tstartpoint\tendpoint"
set paths [get_timing_paths -delay_type max -max_paths 2000 -nworst 1 -slack_lesser_than 0]
foreach path $paths {
    puts $f "[get_property SLACK $path]\t[get_property STARTPOINT_PIN $path]\t[get_property ENDPOINT_PIN $path]"
}
close $f
if {[llength $paths] >= 2000} { error "Setup enumeration capped; incomplete audit" }
puts "SETUP_PATHS [llength $paths]"
report_timing -delay_type max -max_paths 2000 -nworst 1 -slack_lesser_than 0 \
    -file [file join $output setup_all.rpt]
set f [open [file join $output hold_by_clock.tsv] w]
puts $f "clock\tslack\tstartpoint\tendpoint"
foreach clk [get_clocks] {
    foreach path [get_timing_paths -delay_type min -to $clk -max_paths 5 -nworst 1 -slack_lesser_than 0] {
        puts $f "$clk\t[get_property SLACK $path]\t[get_property STARTPOINT_PIN $path]\t[get_property ENDPOINT_PIN $path]"
    }
}
close $f
close_project
set f [open [file join $output complete.txt] w]
puts $f "Read-only inspection complete; setup paths=[llength $paths]; hold rows are samples per clock, not exhaustive."
close $f
