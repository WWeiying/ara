# Pause the loader CPU to serialize MDIO access. Optional bounded AN restart.
if {$argv ni {{} --restart-sgmii}} { error "Usage: inspect_loader_mdio.tcl ?--restart-sgmii?" }
proc mdio_ready {} {
    for {set i 0} {$i < 100} {incr i} {
        if {([mrd -value 0x40c00504] & 0x80) != 0} { return }
        after 5
    }
    error "MDIO readiness timeout"
}
proc mdio_read {phy reg} {
    if {$phy < 0 || $phy > 31 || $reg ni {0 1 2 3 4 5 13 14 17 20}} {
        error "Unapproved MDIO read"
    }
    mdio_ready
    set command [expr {($phy << 24) | ($reg << 16) | 0x8800}]
    mwr 0x40c00504 $command
    mdio_ready
    set value [mrd -value 0x40c0050c]
    if {($value & 0x10000) == 0} { error "MDIO data invalid" }
    return [expr {$value & 0xffff}]
}
proc selector_write {reg value} {
    if {($reg != 13 && $reg != 14) || $value < 0 || $value > 65535} {
        error "Invalid MDIO selector"
    }
    mdio_ready
    mwr 0x40c00508 $value
    mwr 0x40c00504 [expr {(3 << 24) | ($reg << 16) | 0x4800}]
    mdio_ready
}
proc extended_inspect {} {
    set values [dict create]
    set control [mdio_read 3 13]
    selector_write 13 0x001f
    set address [mdio_read 3 14]
    set code [catch {
        foreach reg {0x31 0x37 0xd3} {
            selector_write 13 0x001f
            selector_write 14 $reg
            selector_write 13 0x401f
            set value [mdio_read 3 14]
            dict set values $reg $value
            puts [format "PHY_EXT REG=0x%04x VALUE=0x%04x" $reg $value]
        }
    } message]
    selector_write 13 0x001f
    selector_write 14 $address
    selector_write 13 $control
    if {$code} { error $message }
    return $values
}
connect -url tcp:localhost:3121
targets -set -filter {name == "MicroBlaze #0"} -index 0
set target_state [targets]
if {![string match "*MicroBlaze #0 (Running)*" $target_state]} {
    disconnect
    error "Expected running loader; no stop or MDIO access attempted"
}
set stopped 0
set code [catch {
    stop
    set stopped 1
    foreach phy {1 3} {
        foreach reg {0 1 1 2 3 4 5 17} {
            puts [format "MDIO PHY=%d REG=%d VALUE=0x%04x" $phy $reg [mdio_read $phy $reg]]
        }
    }
    set extended [extended_inspect]
    if {$argv eq "--restart-sgmii"} {
        set cfg [mdio_read 3 20]
        if {[mdio_read 3 2] != 0x2000 || [mdio_read 3 3] != 0xa231 ||
            [dict get $extended 0xd3] != 0x4000 ||
            [dict get $extended 0x37] != 0 || ($cfg & 0x80) == 0 ||
            ([mdio_read 3 1] & 0x24) != 0x24} {
            error "SGMII restart preconditions not met"
        }
        puts [format "RESTART_SGMII original_CFG2=0x%04x" $cfg]
        set restart_code [catch {
            mdio_ready
            mwr 0x40c00508 [expr {$cfg & ~0x80}]
            mwr 0x40c00504 0x03144800
            mdio_ready
            after 100
        } restart_error]
        # Restore the original configuration even if the first operation fails.
        mdio_ready
        mwr 0x40c00508 $cfg
        mwr 0x40c00504 0x03144800
        mdio_ready
        if {[mdio_read 3 20] != $cfg} { error "CFG2 restore verification failed" }
        if {$restart_code} { error $restart_error }
        after 2000
        extended_inspect
    }
    for {set phy 0} {$phy < 32} {incr phy} {
        set value [mdio_read $phy 1]
        if {$value != 0xffff} {
            puts [format "MDIO_SCAN PHY=%d BMSR=0x%04x" $phy $value]
        }
    }
} message]
if {$stopped} {
    if {[catch {con} resume_error]} {
        set code 1
        append message " RESUME_FAILED: $resume_error"
    } else { puts "LOADER_RESUMED" }
}
disconnect
if {$code} { puts stderr $message; exit 1 }
