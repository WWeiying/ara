# Read-only routed source-to-ILA connectivity audit. Never programs hardware.
namespace eval scalar_connections {}
proc scalar_connections::one {objects label} {
    if {[llength $objects] != 1} { error "$label: expected one object, got [llength $objects]" }
    return [lindex $objects 0]
}
proc scalar_connections::connected {source sink} {
    set a [get_nets -quiet -segments -of_objects $source]
    set b [get_nets -quiet -segments -of_objects $sink]
    if {![llength $a] || ![llength $b]} { error "Disconnected pin: $source -> $sink" }
    set common {}
    foreach net $a { if {[lsearch -exact $b $net] >= 0} { lappend common $net } }
    if {![llength $common]} { error "No electrical net connection: $source -> $sink" }
    return [lsort -unique $common]
}
proc scalar_connections::source_pin {source cell name ref} {
    switch -- $source {
        pin { return [one [get_pins -quiet [list $cell/$name]] "source $cell/$name"] }
        register {
            set reg [one [get_cells -quiet [list $cell/$name]] "source register"]
            if {[get_property REF_NAME $reg] ne $ref} { error "Register primitive changed: $reg" }
            return [one [get_pins -quiet -of_objects $reg -filter {REF_PIN_NAME == Q}] "register Q"]
        }
        default { error "Unsupported source type: $source; requires explicit review" }
    }
}
proc scalar_connections::run {checkpoint table output width} {
    if {![string is integer -strict $width] || $width < 1 || $width > 1024} {
        error "Invalid probe width"
    }
    if {[file exists $output]} { error "Existing output; preserve prior evidence" }
    file mkdir $output
    open_checkpoint $checkpoint
    if {![report_route_status -boolean_check ROUTED_FULLY] ||
        [report_route_status -boolean_check ERRORS_IN_ROUTES]} { error "Incomplete/invalid routing" }
    set core [one [get_debug_cores -quiet i_stall_ila] "ILA"]
    if {[get_property C_INPUT_PIPE_STAGES $core] != 1 ||
        [get_property C_DATA_DEPTH $core] != 1024} { error "Sampling configuration changed" }
    set port [one [get_debug_ports -quiet i_stall_ila/probe0] "ILA probe"]
    if {[get_property PORT_WIDTH $port] != $width} { error "Probe width changed" }
    set f [open $table r]
    set report [open [file join $output connections.tsv] w]
    puts $report "source\tkind\tname\tbit\tsource_pin\tprobe_pin\tcommon_segments"
    if {[gets $f] ne "source\tkind\tname\tcell\tnet\trole\tprobe_bit\tregister_ref"} {
        error "Invalid table header"
    }
    set covered [dict create]
    set clocks 0
    while {[gets $f line] >= 0} {
        if {$line eq ""} { continue }
        set fields [split $line \t]
        if {[llength $fields] != 8} { error "Malformed source row" }
        lassign $fields source kind name cell expected role bit ref
        set pin [source_pin $source $cell $name $ref]
        if {$role eq "data"} {
            if {![string is integer -strict $bit] || $bit < 0 || $bit >= $width} {
                error "Invalid probe index"
            }
            set probe [one [get_pins -quiet [list [format {i_stall_ila/probe0[%d]} $bit]]] "ILA input $bit"]
            dict set covered $bit 1
        } elseif {$role eq "clock"} {
            set probe [one [get_pins -quiet [list i_stall_ila/clk]] "ILA clock"]
            set clock [one [get_clocks -quiet -of_objects $probe] "ILA clock domain"]
            if {$clock ne "clk_50_clkwiz" || abs([get_property PERIOD $clock]-20.0)>0.001} {
                error "Unexpected ILA clock"
            }
            incr clocks
        } else { error "Invalid source role" }
        puts $report [join [list $source $kind $name $bit $pin $probe [connected $pin $probe]] \t]
    }
    close $f
    close $report
    if {$clocks < 1 || [dict size $covered] != $width} { error "Incomplete probe coverage" }
    write_debug_probes [file join $output observation.ltx]
    set f [open [file join $output completed.txt] w]
    puts $f "routed_connectivity_pass width=$width hardware_validated=false"
    close $f
    close_design
}
if {![info exists ::scalar_connections_test]} {
    if {[catch {
        if {[llength $argv] != 4} { error "Expected routed-DCP source-table new-output width" }
        scalar_connections::run {*}$argv
    } message]} {
        puts stderr $::errorInfo
        exit 1
    }
    exit 0
}
