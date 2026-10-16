# One bounded halt/backtrace sample, then resume the isolated loader CPU.
if {[llength $argv] != 1} { error "Usage: loader_mb_trace.tcl HW_SERVER_URL" }
set connected 0
set stopped 0
set status [catch {
    connect -url [lindex $argv 0]
    set connected 1
    targets -set -filter {name == "MicroBlaze #0"} -index 0
    stop
    set stopped 1
    puts "LOADER_HALT_STATE [targets]"
    puts "LOADER_STOPPED_PC [rrd pc]"
    foreach reg {r1 r15 r19 r23 msr} {
        puts "LOADER_REG_$reg [rrd $reg]"
    }
    puts "LOADER_BACKTRACE [backtrace]"
} message options]
if {$stopped} { catch {con} }
if {$connected} { catch {disconnect} }
if {$status} {
    puts stderr "LOADER_TRACE_ERROR $message"
    exit 1
}
puts "LOADER_RESUMED"
