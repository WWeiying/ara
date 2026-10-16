# Called only after integrated cold-board/zero-traffic checks by ara_init.py.
set ::ara_mb_clock_helper [file join [file dirname [info script]] ara_phy_clock.tcl]
proc ara_mb_download {elf server {prepare_phy_clock 0}} {
    if {![file isfile $elf]} { error "Missing firmware ELF" }
    connect -url $server
    set failed [catch {
        set matches [targets -target-properties -filter {name == "MicroBlaze #0"}]
        if {[llength $matches] != 1} { error "Expected exactly one MicroBlaze target: $matches" }
        # No fixed scan-chain index; XSCT -set itself also rejects ambiguity.
        targets -set -filter {name == "MicroBlaze #0"}
        puts "ARA_MB_TARGET $matches"
        rst -processor -stop
        if {$prepare_phy_clock} {
            source $::ara_mb_clock_helper
            ara_phy_clock::prepare
        }
        dow -clear $elf
        con
        puts "ARA_MB_FIRMWARE_STARTED"
    } message options]
    catch {disconnect}
    if {$failed} { return -options $options $message }
}
if {![info exists ::ara_mb_library_only]} {
    if {[llength $argv] ni {2 3} ||
        ([llength $argv] == 3 && [lindex $argv 2] ne "--prepare-phy-clock")} {
        error "Expected ELF HW_SERVER_URL ?--prepare-phy-clock?"
    }
    if {[catch {ara_mb_download {*}[lrange $argv 0 1] [expr {[llength $argv] == 3}]} message options]} {
        puts stderr [dict get $options -errorinfo]
        exit 1
    }
    exit 0
}
