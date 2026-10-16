# Single hardware breakpoint at main to distinguish startup from later stack damage.
if {[llength $argv] != 4} {
    error "Usage: loader_mb_main_sp.tcl ELF MAIN_ADDRESS STAGE_ADDRESS HW_SERVER_URL"
}
lassign $argv elf main_address stage_address server
if {![file isfile $elf] || ![regexp {^0x[0-9A-Fa-f]+$} $main_address] ||
    ![regexp {^0x[0-9A-Fa-f]+$} $stage_address]} {
    error "Missing ELF or invalid address"
}
set connected 0
set breakpoint {}
set status [catch {
    connect -url $server
    set connected 1
    targets -set -filter {name == "MicroBlaze #0"} -index 0
    rst -processor -stop
    dow -clear $elf
    puts "AFTER_DOW_STATE [targets]"
    puts "AFTER_DOW_PC [rrd pc]"
    puts "AFTER_DOW_SP [rrd r1]"
    puts "AFTER_DOW_STAGE [mrd -value $stage_address]"
    set breakpoint [bpadd -addr $main_address -type sw]
    puts "MAIN_BREAKPOINT $breakpoint [bplist]"
    con
    after 1000
    puts "MAIN_BREAK_STATE [targets]"
    puts "MAIN_BREAK_PC [rrd pc]"
    puts "MAIN_BREAK_SP [rrd r1]"
    puts "MAIN_BREAK_STAGE [mrd -value $stage_address]"
} message options]
if {$breakpoint ne {}} { catch {bpremove $breakpoint} }
if {$connected} {
    catch {con}
    catch {disconnect}
}
if {$status} {
    puts stderr "MAIN_SP_ERROR $message"
    exit 1
}
puts "MAIN_SP_PROBE_RESUMED"
