# Cold-board experiment only: enable PHY clock before the firmware resets DMA/PCS.
# The Python caller must first pass ara_init.fresh_guard. No DDR writes here.
if {$argv ne "--cold-board-confirmed"} { error "Expected --cold-board-confirmed" }
proc ready {} {
    for {set i 0} {$i < 100} {incr i} {
        if {([mrd -value 0x40c00504] & 0x80) != 0} { return }
        after 5
    }
    error "MDIO readiness timeout"
}
proc read_phy {reg} {
    ready
    mwr 0x40c00504 [expr {0x03008800 | ($reg << 16)}]
    ready
    set value [mrd -value 0x40c0050c]
    if {($value & 0x10000) == 0} { error "Invalid MDIO response" }
    return [expr {$value & 0xffff}]
}
proc write_phy {reg value} {
    if {$reg ni {13 14}} { error "Only extended-register selectors/data allowed" }
    ready
    mwr 0x40c00508 $value
    mwr 0x40c00504 [expr {0x03004800 | ($reg << 16)}]
    ready
}
connect -url tcp:localhost:3121
set code [catch {
    targets -set -filter {name == "MicroBlaze #0"}
    rst -processor -stop
    # 100 MHz management clock / (2 * (24+1)) = 2 MHz MDC.
    set original_mc [mrd -value 0x40c00500]
    mwr 0x40c00500 0x58
    if {[mrd -value 0x40c00500] != 0x58} { error "MDIO clock configuration mismatch" }
    if {[read_phy 2] != 0x2000 || [read_phy 3] != 0xa231} { error "Unexpected PHY identity" }
    set selector [read_phy 13]
    write_phy 13 0x1f
    set original_address [read_phy 14]
    set inner [catch {
        write_phy 14 0xd3
        write_phy 13 0x401f
        set before [read_phy 14]
        if {$before ni {0 16384}} { error "Unexpected SGMII clock mode" }
        write_phy 14 0x4000
        set after [read_phy 14]
        if {$after != 0x4000} { error "Clock mode verification failed" }
        puts [format "PRECLOCK_D3 before=0x%04x after=0x%04x" $before $after]
        after 100
    } reason]
    write_phy 13 0x1f
    write_phy 14 $original_address
    write_phy 13 $selector
    mwr 0x40c00500 $original_mc
    if {$inner} { error $reason }
    puts "PRECLOCK_READY MicroBlaze_stopped no_DDR_writes"
} message]
catch {disconnect}
if {$code} { puts stderr $message; exit 1 }
