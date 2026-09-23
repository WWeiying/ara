# Read the saved reports, not the constraints we intended to apply. In particular,
# a positive setup slack can conceal a lost asynchronous datapath exception.
namespace eval fpga_checks {}

# In a saved checkpoint use the same hierarchy validation as the CDC script.
# Offline report checks use the explicitly selected profile (baseline by default).
proc fpga_checks::ddr_channels {} {
    if {[llength [info commands ::ara_cdc::ddr_channels]]} {
        return [::ara_cdc::ddr_channels]
    }
    set channels {i_dram_wrapper c0_ddr4_reset_n}
    if {[info exists ::fpga_profile] && $::fpga_profile eq "dual_ddr"} {
        lappend channels gen_ddr2.i_dram_wrapper_c2 c1_ddr4_reset_n
    }
    return $channels
}

proc fpga_checks::read_report {path} {
    set in [open $path r]
    set code [catch {read $in} result options]
    set close_code [catch {close $in} close_result close_options]
    if {$code} { return -options $options $result }
    if {$close_code} { return -options $close_options $close_result }
    return $result
}

proc fpga_checks::finite {value} {
    return [regexp {^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$} $value]
}

# Vivado 2020.1 report_timing/report_bus_skew path headers. Ignore the detailed
# path tables and summary tables; do not eval the Tcl queries printed in reports.
proc fpga_checks::path_headers {report} {
    set paths {}; set path {}
    foreach line [split $report \n] {
        set line [string trim $line]
        if {[regexp {^Id:\s+[0-9]+\s*$} $line]} {
            # A new skew constraint has its own Requirement before its Slack.
            if {[dict size $path]} { lappend paths $path }
            set path {}
        } elseif {[regexp {^Slack(?:\s+\([^)]*\))?\s*:\s*(\S+)} $line -> slack]} {
            if {[dict size $path]} { lappend paths $path }
            set path [dict create Slack [string trimright $slack ns]]
        } elseif {[dict size $path] && [regexp \
                {^(Source|Destination|Endpoint Source|Endpoint Destination|Requirement|Timing Exception|Path Type):\s*(.*)$} \
                $line -> key value]} {
            set key [string map {{Endpoint } {}} $key]
            if {$key in {Source Destination Requirement}} { set value [lindex [split $value] 0] }
            if {$key eq "Requirement"} { set value [string trimright $value ns] }
            dict set path $key $value
        }
    }
    if {[dict size $path]} { lappend paths $path }
    return $paths
}

proc fpga_checks::gray_groups {} {
    set groups {}
    foreach {wrapper pad} [ddr_channels] {
        foreach channel {aw w ar b r} {
            foreach half {src dst} {
                set side [expr {($channel in {aw w ar}) == ($half eq "src") ? "src" : "dst"}]
                lappend groups $wrapper/gen_cdc.i_axi_cdc_mig/i_axi_cdc_$side/i_cdc_fifo_gray_${half}_$channel
            }
        }
    }
    return $groups
}

proc fpga_checks::cdc_failures {report} {
    set expected {}; set failures {}; set seen {}; set data {}
    foreach group [gray_groups] {
        for {set bit 0} {$bit < 6} {incr bit} {
            dict set expected [format {%s/gen_sync[%d].i_sync/reg_q_reg[0]/D} $group $bit] 1
        }
    }
    foreach line [split $report \n] {
        if {![regexp {^\s*\d+\s+CDC-\d+\s+} $line]} { continue }
        set words [regexp -all -inline {\S+} $line]
        set dest [lindex $words end]
        set exception UNKNOWN
        regexp {\s{2,}(None|False Path|Max Delay Datapath Only|Partial Exceptions)\s{2,}\S+\s+\S+\s*$} \
            $line -> exception
        if {[dict exists $expected $dest]} {
            dict set seen $dest 1
            if {$exception ne "Max Delay Datapath Only"} {
                lappend failures "Gray pointer has no datapath-only bound: $dest ($exception)"
            }
        } elseif {[regexp {^(.*)/i_spill_register/} $dest -> fifo] && $fifo in [gray_groups]} {
            dict set data $fifo 1
            if {$exception ne "Max Delay Datapath Only"} {
                lappend failures "FIFO data has no datapath-only bound: $dest ($exception)"
            }
        } elseif {$dest eq {gen_status_sync[2].i_sync/reg_q_reg[0]/D}} {
            dict set seen status 1
            if {$exception ne "False Path"} { lappend failures "VIO first-stage exception missing" }
        }
    }
    dict for {pin unused} $expected {
        if {![dict exists $seen $pin]} { lappend failures "Gray pointer missing from CDC report: $pin" }
    }
    foreach group [gray_groups] {
        if {[string match */i_cdc_fifo_gray_dst_* $group] && ![dict exists $data $group]} {
            lappend failures "FIFO data missing from CDC report: $group"
        }
    }
    if {![dict exists $seen status]} { lappend failures "VIO ready crossing missing from CDC report" }
    return $failures
}

proc fpga_checks::skew_failures {report routed} {
    set failures {}; set seen {}
    foreach path [path_headers $report] {
        if {![dict exists $path Destination]} {
            lappend failures "Bus-skew path has no endpoint in report"
            continue
        }
        set dest [dict get $path Destination]
        foreach group [gray_groups] {
            if {![string match $group/gen_sync* $dest]} { continue }
            dict set seen $group 1
            if {![dict exists $path Requirement] ||
                ![finite [dict get $path Requirement]] ||
                abs([dict get $path Requirement] - 3.0) > 0.001} {
                lappend failures "Gray bus skew must be bounded to 3 ns: $group"
            }
        }
        # Include vendor IP bus-skew checks too. They are not in WNS/WHS.
        set slack [dict get $path Slack]
        if {![finite $slack] || ($routed && $slack < 0)} {
            lappend failures "Bus skew unconstrained or violated: $dest ($slack)"
        }
    }
    # Require complete physical skew coverage after routing. Before placement,
    # retain any available estimates without depending on path availability.
    if {$routed} {
        foreach group [gray_groups] {
            if {![dict exists $seen $group]} { lappend failures "Gray bus skew missing: $group" }
        }
    }
    return $failures
}

proc fpga_checks::pad_exception_failures {report port} {
    set paths [path_headers $report]
    if {[llength $paths] != 1} { return [list "$port: missing/ambiguous timing report"] }
    set path [lindex $paths 0]
    if {![dict exists $path {Timing Exception}] ||
        ![string match {MaxDelay Path *} [dict get $path {Timing Exception}]] ||
        ($port ne "uart_tx_o" &&
            ![string match {*-datapath_only*} [dict get $path {Timing Exception}]])} {
        return [list "$port: required max-delay exception missing (ordinary setup is not a pad budget)"]
    }
    return {}
}

proc write_constraint_checks {dir routed} {
    set failures [fpga_checks::cdc_failures [fpga_checks::read_report [file join $dir cdc.rpt]]]
    set failures [concat $failures [fpga_checks::skew_failures \
        [fpga_checks::read_report [file join $dir bus_skew.rpt]] $routed]]
    set ports {jtag_tck_i jtag_tms_i jtag_tdi_i uart_rx_i jtag_tdo_o uart_tx_o}
    foreach {wrapper pad} [fpga_checks::ddr_channels] { lappend ports $pad }
    foreach port $ports {
        set file [file join $dir pad_$port.rpt]
        if {![file exists $file]} {
            lappend failures "$port: pad timing report missing"
        } else {
            set failures [concat $failures [fpga_checks::pad_exception_failures \
                [fpga_checks::read_report $file] $port]]
        }
    }
    set out [open [file join $dir constraint_checks.rpt] w]
    set code [catch {
        set n [expr {[llength [fpga_checks::ddr_channels]] / 2}]
        puts $out "Expected: [expr {60*$n}] Gray first-stage paths, [expr {5*$n}] data crossings, [expr {10*$n}] Gray bus-skew groups, [llength $ports] pad exceptions, VIO ready first-stage exception"
        puts $out "ROUTED=$routed (complete bus-skew coverage and nonnegative slack required after routing)"
        puts $out "FAILURES=[llength $failures]"
        foreach failure $failures { puts $out $failure }
    } result options]
    set close_code [catch {close $out} close_result close_options]
    if {$code} { return -options $options $result }
    if {$close_code} { return -options $close_options $close_result }
    return $failures
}
