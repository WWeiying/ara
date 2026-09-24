# Isolated catalog/configuration preflight. No existing project or hardware access.
namespace eval eth_preflight { variable report; variable stages }

proc eth_preflight::note {message} {
    variable report
    puts $report $message
    flush $report
}

proc eth_preflight::stage {name body {enabled 1}} {
    variable stages
    if {!$enabled} {
        puts $stages "$name\tSKIP"
        flush $stages
        return 0
    }
    note "BEGIN $name"
    if {[catch {uplevel 1 $body} message options]} {
        note "ERROR $name: $message"
        note [dict get $options -errorinfo]
        puts $stages "$name\tFAIL"
        flush $stages
        return 0
    }
    note "END $name"
    puts $stages "$name\tPASS"
    flush $stages
    return 1
}

proc eth_preflight::properties {object} {
    foreach property [lsort [list_property $object]] {
        if {![string match CONFIG.* $property] &&
            ![regexp -nocase {license|vlnv|ipdef|locked|supported_targets} $property]} { continue }
        if {[catch {get_property $property $object} value]} { set value "QUERY_ERROR: $value" }
        note "PROPERTY $object $property = $value"
        if {[string match CONFIG.* $property]} {
            if {![catch {list_property_value $property $object} values] && [llength $values]} {
                note "ALLOWED $property = $values"
            }
        }
    }
}

proc eth_preflight::same {actual expected} {
    if {[string equal -nocase $actual $expected]} { return 1 }
    if {$expected in {true false} && [string is boolean -strict $actual]} {
        return [expr {!!$actual == !!$expected}]
    }
    if {[string is double -strict $actual] && [string is double -strict $expected]} {
        return [expr {$actual == $expected}]
    }
    return 0
}

proc eth_preflight::run {output board_repo} {
    variable report
    variable stages
    set output [file normalize $output]
    set report [open [file join $output preflight.rpt] {WRONLY CREAT EXCL}]
    set stages [open [file join $output stages.tsv] {WRONLY CREAT EXCL}]
    fconfigure $report -encoding utf-8
    fconfigure $stages -encoding utf-8
    set ok 1
    set opened 0
    set usable [stage version {
        set tool_version [version -short]
        note "VIVADO_VERSION $tool_version"
        if {$tool_version ne "2020.1"} { error "Expected Vivado 2020.1; refusing unreviewed IP version" }
    }]
    set usable [stage project {
        if {[llength [get_projects -quiet]]} { error "Run in a fresh batch process, not an existing project" }
        if {[file exists [file join $output project]]} { error "Project directory already exists" }
        note "BOARD_REPO_INPUT $board_repo"
        set board_repo [file normalize $board_repo]
        note "BOARD_REPO_NORMALIZED $board_repo"
        if {![file isdirectory $board_repo]} { error "Board repository directory does not exist: $board_repo" }
        foreach name {board.xml part0_pins.xml preset.xml} {
            set path [file join $board_repo vcu118 2.4 $name]
            note "BOARD_FILE $path EXISTS=[file isfile $path]"
            if {![file isfile $path]} { error "Bundled board file does not exist: $path" }
        }
        set_param board.repoPaths [list $board_repo]
        note "BOARD_REPO_PARAMETER [get_param board.repoPaths]"
        create_project eth_preflight [file join $output project] -part xcvu9p-flga2104-2L-e
        set opened 1
        set boards [get_board_parts -quiet xilinx.com:vcu118:part0:2.4]
        if {[llength $boards] != 1} {
            note "AVAILABLE_VCU118_BOARDS [get_board_parts -quiet *vcu118*]"
            error "Bundled VCU118 board definition not loaded: $boards"
        }
        set_property board_part [lindex $boards 0] [current_project]
        set_property target_language Verilog [current_project]
    } $usable]
    set usable [stage catalog {
        foreach name {axi_ethernet gig_ethernet_pcs_pma tri_mode_ethernet_mac} {
            set definitions [get_ipdefs -all -quiet xilinx.com:ip:${name}:*]
            note "CATALOG $name = $definitions"
            foreach definition $definitions { properties $definition }
        }
        # Use the 2020.1 catalog observed in uploaded evidence, not the version
        # printed on an older product guide. Do not silently choose the latest.
        set expected_axi xilinx.com:ip:axi_ethernet:7.2
        set selected [get_ipdefs -all -quiet $expected_axi]
        if {[llength $selected] != 1} { error "Expected one installed $expected_axi, found: $selected" }
        set selected_vlnv [get_property VLNV [lindex $selected 0]]
        if {$selected_vlnv ne $expected_axi} { error "Unexpected catalog VLNV: $selected_vlnv" }
        note "SELECTED_AXI_IP $selected_vlnv"
    } $usable]
    set created [stage create_ip {
        create_ip -vlnv $selected_vlnv -module_name eth_j10
        set ip [get_ips eth_j10]
        note "DEFAULT_CONFIG"
        properties $ip
    } $usable]
    set configured [stage configure {
        set channel [open [file join $output requested_config.tsv] r]
        set content [read $channel]
        close $channel
        set requested [dict create]
        foreach line [split [string trim $content] \n] {
            set fields [split [string trimright $line \r] \t]
            if {[llength $fields] != 2} { error "Malformed configuration row" }
            lassign $fields key value
            if {![regexp {^CONFIG\.[A-Za-z0-9_]+$} $key] || ![regexp {^[A-Za-z0-9_.]+$} $value]} {
                error "Unsafe configuration token"
            }
            if {[dict exists $requested $key]} { error "Duplicate configuration property $key" }
            dict set requested $key $value
        }
        if {![dict size $requested]} { error "Empty configuration" }
        set available [list_property $ip]
        dict for {key value} $requested {
            if {[lsearch -exact $available $key] < 0} { error "Unsupported property $key; no fallback attempted" }
        }
        set_property -dict $requested $ip
        note "REQUESTED_CONFIG $requested"
        note "EFFECTIVE_CONFIG"
        properties $ip
        dict for {key value} $requested {
            set actual [get_property $key $ip]
            if {![same $actual $value]} { error "Configuration not applied: $key requested=$value actual=$actual" }
        }
    } $created]
    if {![stage license_before {
        report_ip_status -license_status -file [file join $output ip_status_before.rpt]
    } $created]} { set ok 0 }
    set generated [stage generate {
        generate_target all $ip
    } $configured]
    if {![stage license_after {
        report_ip_status -license_status -file [file join $output ip_status_after.rpt]
    } $created]} { set ok 0 }
    set example [stage example {
        # Keep this in-process: the default opens a second Vivado GUI instance.
        open_example_project -in_process -dir [file join $output example] $ip
        note "EXAMPLE_PROJECT [get_property NAME [current_project]]"
    } $generated]
    if {![stage example_inventory {
        set file_count 0
        set xdc_count 0
        foreach path [lsort [get_files -all]] {
            note "EXAMPLE_FILE [get_property FILE_TYPE $path] $path"
            incr file_count
            if {[string equal -nocase [file extension $path] .xdc]} { incr xdc_count }
        }
        note "EXAMPLE_FILES=$file_count XDC_FILES=$xdc_count"
        if {$file_count == 0 || $xdc_count == 0} { error "Example file/constraint inventory is incomplete" }
        note "CONSTRAINTS_REQUIRE_MANUAL_PIN_CLOCK_RESET_REVIEW"
    } $example]} { set ok 0 }
    if {!$example} { set ok 0 }
    if {$opened} {
        if {[catch {close_project} message]} { note "CLOSE_ERROR $message"; set ok 0 }
    }
    note "HARDWARE_VERIFIED=false BITSTREAM_LICENSE_VERIFIED=false"
    note "PREFLIGHT_COMPLETE"
    close $report
    close $stages
    return $ok
}

if {![info exists ::eth_preflight_library_only]} {
    if {[llength $argv] != 2} { error "Usage: host_ethernet_preflight.tcl OUTPUT BOARD_REPO" }
    if {[catch {eth_preflight::run {*}$argv} result options]} {
        puts stderr [dict get $options -errorinfo]
        exit 1
    }
    exit [expr {!$result}]
}
