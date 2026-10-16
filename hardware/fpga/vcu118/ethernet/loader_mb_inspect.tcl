# Read-only processor-state probe; does not reset or halt the MicroBlaze.
if {[llength $argv] < 1} {
    error "Usage: loader_mb_inspect.tcl HW_SERVER_URL ?READ_ADDRESS...?"
}
foreach address [lrange $argv 1 end] {
    if {![regexp {^0x[0-9A-Fa-f]+$} $address]} {
        error "Invalid read address: $address"
    }
}
set connected 0
set status [catch {
    connect -url [lindex $argv 0]
    set connected 1
    targets -set -filter {name == "MicroBlaze #0"} -index 0
    puts "TARGET_STATE [targets]"
    foreach address [lrange $argv 1 end] {
        puts "READ_$address [mrd -value $address]"
    }
    set ticks_before [mrd -value 0x41c00018]
    for {set i 0} {$i < 3} {incr i} {
        puts "PC_SAMPLE_$i [rrd pc]"
        after 1000
    }
    set ticks_after [mrd -value 0x41c00018]
    puts "TIMER1_TICKS_IN_3S [expr {($ticks_after - $ticks_before) & 0xffffffff}]"
} message options]
if {$connected} { catch {disconnect} }
if {$status} {
    puts stderr "LOADER_MB_INSPECT_ERROR $message"
    exit 1
}
