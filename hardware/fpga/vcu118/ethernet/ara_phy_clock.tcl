# VCU118 DP83867 six-wire clock preparation before the firmware's DMA/PCS reset.
# Caller has passed the integrated cold/zero-DDR guard and stopped MicroBlaze.
namespace eval ara_phy_clock {
    proc ready {} {
        for {set i 0} {$i < 100} {incr i} {
            if {([mrd -value 0x40c00504] & 0x80) != 0} { return }
            after 5
        }
        error "MDIO readiness timeout"
    }
    proc read_phy {reg} {
        if {$reg ni {2 3 13 14}} { error "Unapproved PHY read" }
        ready
        mwr 0x40c00504 [expr {0x03008800 | ($reg << 16)}]
        ready
        set value [mrd -value 0x40c0050c]
        if {($value & 0x10000) == 0} { error "Invalid MDIO response" }
        return [expr {$value & 0xffff}]
    }
    proc write_phy {reg value} {
        if {$reg ni {13 14} || $value < 0 || $value > 65535} {
            error "Unapproved PHY write"
        }
        ready
        mwr 0x40c00508 $value
        mwr 0x40c00504 [expr {0x03004800 | ($reg << 16)}]
        ready
    }
    proc prepare {} {
        set original_mc [mrd -value 0x40c00500]
        set failed [catch {
            # Reviewed integrated subsystem has a 100 MHz management clock.
            mwr 0x40c00500 0x58
            if {[mrd -value 0x40c00500] != 0x58} { error "MDIO clock mismatch" }
            if {[read_phy 2] != 0x2000 || [read_phy 3] != 0xa231} {
                error "Unexpected VCU118 PHY identity"
            }
            set selector [read_phy 13]
            write_phy 13 0x1f
            set original_address [read_phy 14]
            write_phy 14 0xd3
            write_phy 13 0x401f
            set before [read_phy 14]
            if {$before ni {0 16384}} { error "Unexpected SGMII clock mode" }
            write_phy 14 0x4000
            set value [read_phy 14]
            if {$value != 0x4000} { error "PHY clock readback mismatch" }
            after 100
            puts [format "ARA_PHY_CLOCK D3_BEFORE=0x%04x D3_AFTER=0x%04x" $before $value]
        } message options]
        # Restore the MDIO addressing state and divider, not the enabled PHY clock.
        set cleanup_failed [catch {
            if {[info exists original_address]} {
                write_phy 13 0x1f
                write_phy 14 $original_address
            }
            if {[info exists selector]} { write_phy 13 $selector }
        } cleanup_message]
        if {[catch {mwr 0x40c00500 $original_mc} clock_message]} {
            error "Failed to restore MDIO clock register: $clock_message"
        }
        if {$cleanup_failed} { error "Failed to restore MDIO selector: $cleanup_message" }
        if {$failed} { return -options $options $message }
    }
}
