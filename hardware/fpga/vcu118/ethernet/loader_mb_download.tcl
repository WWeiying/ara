# Download the matching standalone loader ELF into the isolated MicroBlaze BRAM.
if {[llength $argv] != 2} {
    error "Usage: loader_mb_download.tcl ELF HW_SERVER_URL"
}
lassign $argv elf server
if {![file isfile $elf]} { error "Missing loader ELF: $elf" }
set connected 0
set status [catch {
    connect -url $server
    set connected 1
    targets -set -filter {name == "MicroBlaze #0"} -index 0
    puts "LOADER_MB_TARGET_SELECTED [targets]"
    rst -processor -stop
    dow -clear $elf
    puts "LOADER_ELF_DOWNLOADED $elf"
    con
    puts "LOADER_MB_RUNNING"
} message options]
if {$connected} { catch {disconnect} }
if {$status} {
    puts stderr "LOADER_MB_ERROR $message"
    puts stderr [dict get $options -errorinfo]
    exit 1
}
