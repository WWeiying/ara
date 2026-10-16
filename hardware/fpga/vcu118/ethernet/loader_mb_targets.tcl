# Read-only XSCT target inventory after programming the isolated loader.
if {[llength $argv] != 1} { error "Usage: loader_mb_targets.tcl HW_SERVER_URL" }
set connected 0
set status [catch {
    connect -url [lindex $argv 0]
    set connected 1
    puts "LOADER_XSCT_TARGETS_BEGIN"
    puts [targets]
    puts "LOADER_XSCT_TARGETS_END"
} message options]
if {$connected} { catch {disconnect} }
if {$status} {
    puts stderr "LOADER_XSCT_ERROR $message"
    exit 1
}
