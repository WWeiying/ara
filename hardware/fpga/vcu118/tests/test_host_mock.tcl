# Mock Vivado APIs while running the real host_vivado.tcl socket/batch/response code.
set ::mode [lindex $argv 0]
set script [lindex $argv 1]
set argv [lrange $argv 2 end]
set ::host_library_only 1
source $script
# Exercise the real success/error/cleanup paths without Tcl 8.6-only helpers.
if {[llength [info commands try]]} { rename try {} }
rename binary original_binary
proc binary {subcommand args} {
    if {$subcommand in {encode decode}} { error "Tcl 8.6-only binary subcommand" }
    uplevel 1 [list original_binary $subcommand {*}$args]
}
array set ::memory {}
array set ::regs {0 0x41524442 4 1 8 3 12 50000000 20 7 24 0 28 0 32 0 36 0 40 0 44 0 48 0}
if {$::mode eq "bad_magic"} { set ::regs(0) 0 }
if {$::mode eq "ddr1_only"} { set ::regs(8) 1 }
if {$::mode eq "not_ready"} { set ::regs(20) 6 }
set ::regs(324) 0
set ::snapshot_changes 0

proc open_hw_manager {} {}
proc connect_hw_server {args} {}
proc get_hw_targets {} { return target0 }
proc open_hw_target {args} {}
proc get_hw_devices {args} { return device0 }
proc current_hw_device {args} {}
proc refresh_hw_device {args} {}
proc close_hw_target {args} {}
proc disconnect_hw_server {} {}
proc close_hw_manager {} {}
proc get_hw_axis {args} {
    if {$::mode eq "duplicate"} { return {debug_b mem_a debug_duplicate} }
    return {debug_b mem_a unrelated}
}
proc get_property {property object} {
    if {$property eq "NAME"} { return $object }
    if {$property eq "CELL_NAME"} {
        switch $object {
            mem_a { return top/gen_host/i_host_bridge/i_jtag_mem }
            debug_b - debug_duplicate { return top/gen_host.i_host_bridge/i_jtag_debug }
            default { return other/i_jtag_mem_unused }
        }
    }
    if {$property eq "PROTOCOL"} {
        return [expr {$object eq "mem_a" ? "AXI4_Full" : "AXI4_Lite"}]
    }
    if {$property eq "CMD.SIZE"} {
        if {$::mode eq "wrong_width" && $::txn($object,core) eq "mem_a"} { return 32 }
        return [expr {$::txn($object,core) eq "mem_a" ? 64 : 32}]
    }
    if {$property eq "CMD.LEN"} { return $::txn($object,-len) }
    if {$property eq "CMD.BURST"} { return $::txn($object,-burst) }
    if {$property eq "DATA"} {
        if {[info exists ::txn($object,result)]} { return $::txn($object,result) }
        if {[info exists ::txn($object,-data)]} { return $::txn($object,-data) }
        return ""
    }
    if {[string match STATUS.*_BUSY $property]} { return 0 }
    if {[string match STATUS.*_DONE $property]} {
        return [expr {$::mode ne "incomplete" || $object ne "mem_a"}]
    }
    if {$property in {STATUS.RRESP STATUS.BRESP}} {
        if {$::mode eq "response_error" && $object eq "mem_a"} { return SLVERR }
        return OKAY
    }
    error "Unmocked property $property on $object"
}
proc create_hw_axi_txn {name core args} {
    set ::txn($name,core) $core
    foreach {key value} $args { set ::txn($name,$key) $value }
    return $name
}
proc refresh_hw_axi {core} {}
proc reset_hw_axi {core} {
    if {$core ne "mem_a"} { error "Wrong AXI core reset" }
    if {$::mode eq "reset_error"} { error "Injected JTAG AXI reset failure" }
    puts "MOCK reset memory AXI core"
}
proc delete_hw_axi_txn {name} {
    foreach key [array names ::txn "$name,*"] { unset ::txn($key) }
}
proc reg_read {addr} {
    if {![info exists ::regs($addr)]} { return 0 }
    return $::regs($addr)
}
proc finish_program {} {
    set ::regs(256) 900
    set ::regs(264) 123
    set ::regs(272) 0x80000040
    set ::regs(32) 0
    set ::regs(48) 1
    set ::regs(448) 2
    set ::regs(456) 1
    if {$::mode eq "no_done"} { set ::regs(48) 0 }
    if {$::mode eq "no_retire"} { set ::regs(264) 0 }
    if {$::mode eq "stale"} { incr ::regs(36) }
    if {$::mode eq "software_error"} { set ::regs(32) 5 }
    if {$::mode eq "trap"} {
        set ::regs(288) 0x80000044
        set ::regs(296) 2
        set ::regs(312) 1
        set ::regs(32) 0x80000002
    }
    if {$::mode eq "bus_error"} {
        set ::regs(480) 1
        set ::regs(496) 0xab07
    }
    if {$::mode eq "watchdog"} {
        set ::regs(44) 1
        set ::regs(48) 0
        incr ::regs(24)
    }
}
proc run_hw_axi {name} {
    set core $::txn($name,core)
    set kind $::txn($name,-type)
    set addr [expr 0x$::txn($name,-address)]
    set beats $::txn($name,-len)
    if {$core eq "mem_a" && $::mode eq "debug_only"} { error "Main master must not be accessed" }
    if {$core eq "mem_a" && $::mode eq "hang_mem"} { after 60000 }
    set width [expr {$core eq "mem_a" ? 8 : 4}]
    set result ""
    for {set i 0} {$i < $beats} {incr i} {
        set a [expr {$addr + $width * $i}]
        if {$::mode eq "alias" && $core eq "mem_a" && $a >= 0x100000000} {
            set a [expr {$a - 0x80000000}]
        }
        if {$kind eq "WRITE"} {
            set end [expr {[string length $::txn($name,-data)] - $i * $width * 2 - 1}]
            if {$core eq "mem_a" && $::mode in {burst_left write_left}} {
                set end [expr {($i + 1) * $width * 2 - 1}]
            }
            set value [expr 0x[string range $::txn($name,-data) [expr {$end - $width * 2 + 1}] $end]]
            if {$core eq "mem_a"} {
                for {set b 0} {$b < 8} {incr b} {
                    set ::memory([expr {$a + $b}]) [expr {($value >> ($b * 8)) & 255}]
                }
                if {$a >= 0x80000000 && $::mode eq "loading_error"} { set ::regs(480) 1 }
                if {$a == 0x03000008 && ($value & 0xffffffff) == 2} { finish_program }
            } elseif {$a == 16} {
                if {$value & 1} {
                    set ::regs(44) 0
                    foreach base {256 384 512} {
                        for {set x 0} {$x < 120} {incr x 4} { set ::regs([expr {$base + $x}]) 0 }
                    }
                }
                if {$value & 2 && $::mode ne "snapshot_stuck"} { incr ::regs(24) }
            } else { set ::regs($a) $value }
        } else {
            set value 0
            if {$core eq "mem_a"} {
                for {set b 0} {$b < 8} {incr b} {
                    set byteaddr [expr {$a + $b}]
                    if {[info exists ::memory($byteaddr)]} { set byte $::memory($byteaddr) } else {
                        set byte [expr {$a >= 0x80000000 ? 0xa5 : 0}]
                    }
                    set value [expr {$value | ($byte << (8 * $b))}]
                }
                if {$::mode eq "corrupt" && $a >= 0x80000000 && [info exists ::memory($a)]} {
                    set value [expr {$value ^ 1}]
                }
            } else {
                if {$a == 256 && $::mode eq "sequence_race" && !$::snapshot_changes} {
                    incr ::regs(24)
                    incr ::snapshot_changes
                }
                set value [reg_read $a]
            }
            set word [format %0*x [expr {$width * 2}] $value]
            if {$core eq "mem_a" && $::mode in {burst_left read_left}} {
                append result $word
            } else { set result "$word$result" }
        }
    }
    set ::txn($name,result) $result
}

if {[catch {host::main $argv} message options]} {
    puts stderr [dict get $options -errorinfo]
    exit 1
}
