set ::eth_board_library_only 1
source [file normalize [file join [file dirname [info script]] .. ethernet board_probe.tcl]]

set ::setup 0
set ::id1 0x2000
set ::id2 0xa231
set ::read_reg 0
set ::commands {}
proc create_hw_axi_txn {name axi args} {
    array set options $args
    set ::txn($name,kind) $options(-type)
    set ::txn($name,address) $options(-address)
    set ::txn($name,data) [expr {[info exists options(-data)] ? $options(-data) : "-"}]
    return $name
}
proc run_hw_axi {txn} {
    set address [scan $::txn($txn,address) %x]
    if {$::txn($txn,kind) eq "WRITE"} {
        set data [scan $::txn($txn,data) %x]
        lappend ::commands [list $address $data]
        if {$address == 0x500} { set ::setup $data }
        if {$address == 0x504} { set ::read_reg [expr {($data >> 16) & 31}] }
    } elseif {$address == 0x500} {
        set ::txn($txn,result) $::setup
    } elseif {$address == 0x504} {
        set ::txn($txn,result) 0x80
    } elseif {$address == 0x50c} {
        set value [switch -- $::read_reg {
            0 { expr {0x10000 | 0x1140} }
            1 { expr {0x10000 | 0x786d} }
            2 { expr {0x10000 | $::id1} }
            3 { expr {0x10000 | $::id2} }
        }]
        set ::txn($txn,result) $value
    }
}
proc refresh_hw_axi {axi} {}
proc get_property {property object} {
    if {$property eq "CMD.SIZE"} { return 32 }
    if {$property eq "CMD.LEN"} { return 1 }
    if {$property eq "DATA"} { return [format %08x $::txn($object,result)] }
    if {[string match STATUS.AXI_*_BUSY $property]} { return 0 }
    if {[string match STATUS.AXI_*_DONE $property]} { return 1 }
    if {$property in {STATUS.RRESP STATUS.BRESP}} { return OKAY }
    error "Unexpected property $property"
}
proc delete_hw_axi_txn {txn} {}

eth_board::identify_phy hw_axi_1
if {$::setup != 0} { error "MDIO setup was not restored" }
foreach command $::commands {
    lassign $command address data
    if {$address ni {1280 1284}} { error "Unexpected AXI write address $address" }
    if {$address == 1284 && ($data & 0xc800) != 0x8800} {
        error "Unexpected MDIO operation $data"
    }
}
set ::id1 0xffff
if {![catch {eth_board::identify_phy hw_axi_1} error] ||
    ![string match *not\ identified* $error]} {
    error "Wrong PHY ID was accepted: $error"
}
if {$::setup != 0} { error "MDIO setup was not restored after failure" }
if {![catch {eth_board::axi_word hw_axi_1 WRITE 0x508 0x1140}]} {
    error "PHY write register was accepted"
}
puts MOCK_MDIO_PASS
