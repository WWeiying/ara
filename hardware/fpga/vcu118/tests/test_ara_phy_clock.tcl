source [file join [file dirname [info script]] .. ethernet ara_phy_clock.tcl]
proc after {args} {}
proc mrd {flag address} {
    switch -- [expr {$address}] {
        1086326016 { return $::mc }
        1086326020 { return [expr {$::timeout ? 0 : 128}] }
        1086326028 { return $::response }
        default { error "Unexpected read $address" }
    }
}
proc mwr {address value} {
    switch -- [expr {$address}] {
        1086326016 { set ::mc $value }
        1086326024 { set ::write_data $value }
        1086326020 {
            if {($value >> 24) != 3} { error "Wrong PHY" }
            set reg [expr {($value >> 16) & 31}]
            if {$value & 0x8000} {
                switch $reg {
                    2 { set v $::id }
                    3 { set v 0xa231 }
                    13 { set v $::selector }
                    14 { set v [expr {$::selector == 0x401f ? $::d3 : $::address}] }
                    default { error "Unexpected register" }
                }
                set ::response [expr {$v | 0x10000}]
            } else {
                switch $reg {
                    13 { set ::selector $::write_data }
                    14 {
                        if {$::selector == 0x401f} {
                            if {$::address != 0xd3} { error "Wrong extended register" }
                            if {!$::drop_write} { set ::d3 $::write_data }
                        } else { set ::address $::write_data }
                    }
                    default { error "Unapproved write" }
                }
            }
        }
        default { error "Unexpected write $address" }
    }
}
foreach case {cold enabled identity mode readback timeout} {
    set mc 0; set selector 31; set address 7; set d3 0
    set id 0x2000; set drop_write 0; set timeout 0
    switch $case {
        enabled { set d3 16384 }
        identity { set id 0 }
        mode { set d3 1 }
        readback { set drop_write 1 }
        timeout { set timeout 1 }
    }
    set failed [catch {ara_phy_clock::prepare} message]
    if {$failed != ($case ni {cold enabled})} { error "$case: $message" }
    if {$mc != 0 || $selector != 31 || $address != 7} { error "$case: cleanup failed" }
    if {!$failed && $d3 != 16384} { error "$case: clock not enabled" }
}
puts ARA_PHY_CLOCK_TEST_PASS
