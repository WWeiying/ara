# Resolve counters from the matching ELF; addresses change when layout changes.
if {[llength $argv] != 2} {
    error "Usage: loader_fast_profile.tcl ELF HW_SERVER_URL"
}
lassign $argv elf server
set symbols [exec mb-nm $elf]
set connected 0
set status [catch {
    connect -url $server
    set connected 1
    targets -set -filter {name == "MicroBlaze #0"} -index 0
    foreach name {eth_probe_stage eth_probe_cdma_ticks eth_probe_cdma_calls
                  eth_probe_input_ticks eth_probe_tx_ticks eth_probe_profile_frames
                  eth_probe_cdma_error eth_probe_cdma_timeouts eth_probe_tx_drops
                  eth_probe_bad_frames eth_probe_load_rejected eth_probe_ddr_bytes} {
        if {![regexp -line [format {^([0-9a-fA-F]+) [bBdD] %s$} $name] $symbols -> address]} {
            error "Missing counter: $name"
        }
        puts "COUNTER $name [mrd -value 0x$address]"
    }
    foreach address {0x80000000 0x800001c0 0x800012bc 0x8c000ff8 0x8c800ff8 0x8d000ff4} {
        puts "DDR $address [mrd -value $address]"
    }
} message options]
if {$connected} { catch {disconnect} }
if {$status} {
    puts stderr "PROFILE_ERROR $message"
    exit 1
}
puts "PROFILE_READ_COMPLETE"
