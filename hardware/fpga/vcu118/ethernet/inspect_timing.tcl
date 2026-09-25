# Read-only classification of routed negative-slack paths.
if {[llength $argv] != 1 || ![file isfile [lindex $argv 0]]} {
    error "Usage: inspect_timing.tcl routed.dcp"
}
open_checkpoint [lindex $argv 0]
set paths [get_timing_paths -delay_type max -max_paths 200 -slack_lesser_than 0]
puts "NEGATIVE_PATH_COUNT [llength $paths]"
foreach path $paths {
    set start [get_property NAME [get_property STARTPOINT_PIN $path]]
    set endpoint [get_property NAME [get_property ENDPOINT_PIN $path]]
    set slack [get_property SLACK $path]
    puts [format "NEGATIVE_PATH %.3f %s -> %s" $slack $start $endpoint]
}
