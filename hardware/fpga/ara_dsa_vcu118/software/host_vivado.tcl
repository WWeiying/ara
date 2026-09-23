# SPDX-License-Identifier: Apache-2.0
# Private numeric request protocol. No remote Tcl evaluation and no board reset.
namespace eval host {
    variable cores
    variable cells
    variable device
    variable serial 0
}

proc host::select_one {objects name description} {
    if {$name ne "-"} {
        set matches {}
        foreach object $objects {
            if {[get_property NAME $object] eq $name} { lappend matches $object }
        }
        set objects $matches
    }
    if {[llength $objects] != 1} {
        error "Expected exactly one $description; specify its exact name (found $objects)"
    }
    return [lindex $objects 0]
}

proc host::core {bus} {
    variable cores
    variable cells
    variable device
    if {[info exists cores($bus)]} { return $cores($bus) }
    set matches {}
    foreach object [get_hw_axis -of_objects $device] {
        set cell [string map {. /} [get_property CELL_NAME $object]]
        set wanted [string map {. /} $cells($bus)]
        if {$cell eq $wanted || [string match "*/$wanted" $cell]} {
            lappend matches $object
        }
    }
    if {[llength $matches] != 1} {
        error "Expected one CELL_NAME suffix $cells($bus), found $matches"
    }
    set object [lindex $matches 0]
    set expected [expr {$bus eq "M" ? "AXI4_Full" : "AXI4_Lite"}]
    if {[get_property PROTOCOL $object] ne $expected} {
        error "Wrong AXI protocol for $cells($bus); expected $expected"
    }
    puts "HOST selected $bus: [get_property CELL_NAME $object] ($object)"
    set cores($bus) $object
    return $object
}

proc host::transaction {line} {
    variable serial
    variable cells
    if {[llength $line] != 5} { error "Malformed operation" }
    lassign $line bus kind address beats data
    if {$bus ni {M D} || $kind ni {READ WRITE} ||
        ![regexp {^[0-9a-fA-F]{16}$} $address] ||
        ![string is integer -strict $beats]} { error "Invalid operation" }
    set width [expr {$bus eq "M" ? 8 : 4}]
    set limit [expr {$bus eq "M" ? 256 : 1}]
    set addr [expr 0x$address]
    set bytes [expr {$width * $beats}]
    if {$beats < 1 || $beats > $limit || $addr % $width ||
        ($addr & 4095) + $bytes > 4096 ||
        ($bus eq "D" && $addr + $bytes > 0x100000000)} {
        error "Invalid AXI boundary/length/alignment"
    }
    if {$kind eq "WRITE"} {
        set clean_data [string map {_ ""} $data]
        if {![regexp {^[0-9a-fA-F]+$} $clean_data] ||
            [string length $clean_data] != $bytes * 2} {
            error "Invalid WRITE data length"
        }
        if {[string first _ $data] >= 0} {
            set words [split $data _]
            if {[llength $words] != $beats} { error "Invalid WRITE word separators" }
            foreach word $words {
                if {[string length $word] != $width * 2} {
                    error "Invalid WRITE word width"
                }
            }
        }
    } elseif {$data ne "-"} { error "Unexpected READ data" }
    set object [host::core $bus]
    set args [list -type $kind -address $address -len $beats]
    if {$bus eq "M"} { lappend args -burst INCR -cache 0 -id 0 }
    if {$kind eq "WRITE"} { lappend args -data $data }
    set txn [create_hw_axi_txn host_[incr serial] $object {*}$args]
    set code [catch {
        # Do not use -quiet (masks errors) or -queue (loses per-transaction status).
        # UG835 refresh_hw_axi documents these exact STATUS properties;
        # UG912 HW_AXI lists PROTOCOL, OKAY, and the boolean BUSY/DONE values.
        # https://docs.amd.com/r/2020.2-English/ug835-vivado-tcl-commands/refresh_hw_axi
        # https://docs.amd.com/r/2023.2-English/ug912-vivado-properties/HW_AXI
        if {[get_property CMD.SIZE $txn] != $width * 8} { error "Wrong IP data width" }
        if {[get_property CMD.LEN $txn] != $beats} { error "Vivado CMD.LEN differs from requested beats" }
        if {$bus eq "M" && [get_property CMD.BURST $txn] ne "INCR"} {
            error "Vivado CMD.BURST is not INCR"
        }
        if {$kind eq "WRITE"} {
            set accepted [string map {_ "" " " "" \n "" \r ""} [get_property DATA $txn]]
            regsub -nocase {^0x} $accepted "" accepted
            if {[string tolower $accepted] ne [string tolower $clean_data]} {
                error "Vivado DATA differs from requested WRITE data"
            }
        }
        if {$bus eq "M" && $beats == 2 && $addr == 0xffff0000} {
            puts "HOST AXI scratch $kind CMD.LEN=[get_property CMD.LEN $txn] DATA=[get_property DATA $txn]"
        }
        set trace_two_beat_read [expr {$bus eq "M" && $kind eq "READ" && $beats == 2 &&
            ($addr == 0x1401ff00 || $addr == 0xffff0000)}]
        run_hw_axi $txn
        if {$trace_two_beat_read && [catch {get_property DATA $txn} raw_before_refresh]} {
            set raw_before_refresh "unavailable:$raw_before_refresh"
        }
        refresh_hw_axi $object
        set prefix STATUS.AXI_${kind}
        if {[get_property ${prefix}_BUSY $object] != 0 ||
            [get_property ${prefix}_DONE $object] != 1} {
            error "$cells($bus) $kind did not complete"
        }
        set response [get_property [expr {$kind eq "READ" ? "STATUS.RRESP" : "STATUS.BRESP"}] $object]
        if {$response ne "OKAY"} { error "$bus $kind at $address returned $response" }
        if {$kind eq "READ"} {
            set raw_after_refresh [get_property DATA $txn]
            if {$trace_two_beat_read} {
                puts "HOST AXI two-beat READ address=[format 0x%08x $addr] before_refresh=$raw_before_refresh after_refresh=$raw_after_refresh"
            }
            set value [string map {_ "" " " "" \n "" \r ""} $raw_after_refresh]
            regsub -nocase {^0x} $value "" value
            if {![regexp {^[0-9a-fA-F]+$} $value] || [string length $value] != $bytes * 2} {
                error "Invalid Vivado DATA width"
            }
        } else {
            set value -
        }
        set value
    } value options]
    set cleanup_code [catch {delete_hw_axi_txn $txn} cleanup_value cleanup_options]
    if {$code} { return -options $options $value }
    if {$cleanup_code} { return -options $cleanup_options $cleanup_value }
    return $value
}

proc host::serve {channel} {
    while {[gets $channel header] >= 0} {
        if {$header eq "QUIT"} { return }
        if {[llength $header] == 3 && [lindex $header 0] eq "RESET"} {
            lassign $header command seq bus
            if {![string is integer -strict $seq] || $bus ne "M"} { error "Invalid reset request" }
            set object [host::core M]
            if {[catch {reset_hw_axi $object} value]} {
                binary scan [encoding convertto utf-8 $value] H* error_hex
                puts $channel "ERR $seq 0 $error_hex"
            } else {
                puts "HOST reset memory AXI core: $object"
                puts $channel "OK $seq 0 -"
            }
            puts $channel "END $seq"
            flush $channel
            continue
        }
        if {[llength $header] != 3} { error "Malformed batch" }
        lassign $header command seq count
        if {$command ne "BATCH" || ![string is integer -strict $seq] ||
            ![string is integer -strict $count] || $count < 1 || $count > 256} {
            error "Invalid batch"
        }
        set operations {}
        for {set i 0} {$i < $count} {incr i} {
            if {[gets $channel line] < 0 || [string length $line] > 8192} {
                error "Truncated/oversized operation"
            }
            lappend operations $line
        }
        set i 0
        foreach operation $operations {
            if {[catch {host::transaction $operation} value]} {
                binary scan [encoding convertto utf-8 $value] H* error_hex
                puts $channel "ERR $seq $i $error_hex"
                break
            }
            puts $channel "OK $seq $i $value"
            incr i
        }
        puts $channel "END $seq"
        flush $channel
    }
}

proc host::main {arguments} {
    variable cells
    variable device
    if {[llength $arguments] != 8} { error "Expected port token server target device mem_cell debug_cell probes" }
    lassign $arguments port token server target_name device_name cells(M) cells(D) probes
    foreach cell [list $cells(M) $cells(D)] {
        if {![regexp {^[A-Za-z0-9_./]+$} $cell]} { error "Invalid CELL_NAME suffix" }
    }
    open_hw_manager
    connect_hw_server -url $server
    set target [host::select_one [get_hw_targets] $target_name target]
    open_hw_target $target
    set devices [get_hw_devices -of_objects $target -filter {PART =~ xcvu9p*}]
    set device [host::select_one $devices $device_name device]
    current_hw_device $device
    if {$probes ne "-"} {
        if {![file isfile $probes]} { error "Debug probes file not found: $probes" }
        set_property PROBES.FILE $probes $device
    }
    refresh_hw_device $device
    set axes [get_hw_axis -of_objects $device]
    puts "HOST JTAG AXI objects: [llength $axes]"
    foreach object $axes {
        puts "HOST AXI $object CELL_NAME=[get_property CELL_NAME $object] PROTOCOL=[get_property PROTOCOL $object]"
    }
    # Do not discover, reset or refresh the memory IP for a debug-only session.
    host::core D
    set channel [socket 127.0.0.1 $port]
    fconfigure $channel -encoding ascii -translation lf -buffering line
    puts $channel "READY $token"
    flush $channel
    set code [catch {
        host::serve $channel
    } value options]
    # Tcl 8.5-compatible cleanup; retain the first error and attempt every close.
    foreach cleanup [list [list close $channel] [list close_hw_target $target] \
                         [list disconnect_hw_server] [list close_hw_manager]] {
        set cleanup_code [catch {{*}$cleanup} cleanup_value cleanup_options]
        if {!$code && $cleanup_code} {
            set code $cleanup_code
            set value $cleanup_value
            set options $cleanup_options
        }
    }
    return -options $options $value
}

if {![info exists ::host_library_only]} {
    if {[catch {host::main $argv} message options]} {
        puts stderr "HOST ERROR: $message"
        puts stderr [dict get $options -errorinfo]
        exit 1
    }
    exit 0
}
