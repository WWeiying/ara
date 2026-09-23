namespace eval fpga_run {}

proc fpga_run::nonempty {path} {
    if {![file isfile $path] || [file size $path] == 0} {
        error "Missing/empty file: $path"
    }
}

proc fpga_run::reusable {name expected checkpoint} {
    set run [get_runs -quiet $name]
    if {[llength $run] != 1} { error "Missing run: $name" }
    check_run $name $expected
    if {[get_property NEEDS_REFRESH $run]} { error "Run is out of date: $name" }
    nonempty [file join [get_property DIRECTORY $run] $checkpoint]
    return $run
}

proc fpga_run::check_ips {} {
    global profile_ips
    foreach name $profile_ips {
        set ip [get_ips -quiet $name]
        if {[llength $ip] != 1 || [get_property IS_LOCKED $ip]} {
            error "IP missing or locked: $name. No IP rebuild/upgrade was requested."
        }
        set run [reusable ${name}_synth_1 {*synth_design Complete*} ${name}.dcp]
        puts "REUSE IP: $name ([get_property DIRECTORY $run])"
    }
}

proc fpga_run::clone_run {base name parent} {
    set source [get_runs -quiet $base]
    if {[llength $source] != 1} { error "Missing template run: $base" }
    if {[llength [get_runs -quiet $name]]} { error "Run already exists: $name" }
    # Custom hooks can refer to the old run directory or mutate shared IP.
    foreach property [list_property $source] {
        if {[string match STEPS.*.TCL.* $property] && [get_property $property $source] ne ""} {
            error "Review custom hook before using isolated runs: $base/$property"
        }
    }
    set args [list -flow [get_property FLOW $source] -strategy [get_property STRATEGY $source] \
        -constrset [get_property CONSTRSET $source] -part [get_property PART $source]]
    if {$parent ne "-"} { lappend args -parent_run $parent }
    create_run $name {*}$args
    set target [get_runs $name]
    foreach property [list_property $source] {
        if {$property eq "SRCSET" || [string match STEPS.*.ARGS.* $property] ||
            [string match STEPS.*.IS_ENABLED $property]} {
            set_property $property [get_property $property $source] $target
        }
    }
    return $target
}

proc fpga_run::launch_error {dir} {
    foreach name {exception.log .vivado.error.rst} {
        set path [file join $dir $name]
        if {[file exists $path] && ($name ne "exception.log" || [file size $path] > 0)} {
            error "Run/launcher failed: inspect $path (old IP results were not reset)."
        }
    }
    foreach path [glob -nocomplain -directory $dir hs_err_pid*.log] {
        if {[file size $path] > 0} { error "Vivado crash report: $path" }
    }
    # A synthesis worker can crash without an error marker or a STATUS update.
    # Read only the log tail; quiet optimization alone is not a failure.
    set path [file join $dir runme.log]
    if {![file isfile $path]} { return }
    set handle [open $path rb]
    set code [catch {
        set offset [expr {max(0, [file size $path] - 65536)}]
        seek $handle $offset start
        set tail [read $handle 65536]
    } result options]
    set close_code [catch {close $handle} close_result close_options]
    if {$code} { return -options $options $result }
    if {$close_code} { return -options $close_options $close_result }
    if {$offset > 0} {
        set newline [string first "\n" $tail]
        if {$newline < 0} { return }
        set tail [string range $tail [expr {$newline + 1}] end]
    }
    if {[regexp -line -nocase {^[ \t]*(An unrecoverable error has occurred[^\r\n]*|TclStackFree: incorrect freePtr[^\r\n]*)} $tail diagnostic]} {
        error "Vivado crash in $path: [string trim $diagnostic]. Run STATUS may be stale; no run or IP was reset."
    }
}

proc fpga_run::wait_checked {name expected dir} {
    set last_status ""
    set last_print 0
    while {1} {
        update
        launch_error $dir
        set status [get_property STATUS [get_runs $name]]
        if {[string match $expected $status]} { return }
        if {[regexp -nocase {error|fail|cancel|abort} $status]} {
            error "$name: $status. Inspect [file join $dir runme.log]"
        }
        set now [clock seconds]
        if {$status ne $last_status || $now - $last_print >= 30} {
            puts "[clock format $now -format {%Y-%m-%d %H:%M:%S}] $name: $status"
            set last_print $now
            set last_status $status
            flush stdout
        }
        # No elapsed-time/CPU cutoff: quiet optimization phases can be valid.
        after 5000
    }
}

proc fpga_run::execute {stage session token parent} {
    global design_top max_threads package_root
    if {$stage ni {synth impl inspect} || ![regexp {^[0-9a-f]{12}$} $token]} {
        error "Invalid managed-run arguments"
    }
    if {![file isdirectory $session]} { error "Session directory missing: $session" }
    open_package_project
    set_param general.maxThreads $max_threads
    if {$stage eq "inspect"} {
        if {![regexp {^synth_[0-9a-f]{12}$} $parent]} { error "Missing synthesis to inspect" }
        # Stale sources are allowed only here: inspect the OLD netlist without
        # updating the accepted synthesis record or launching any runs.
        check_run $parent {*synth_design Complete*}
        nonempty [file join [get_property DIRECTORY [get_runs $parent]] ${design_top}.dcp]
        puts "INSPECT: $parent (existing netlist, current constraints; no synthesis)"
        set ::ara_cdc_inspect_legacy true
        # Use catch cleanup: the Windows Vivado 2020.1 Tcl has no try command.
        set code [catch {open_run $parent} result options]
        unset ::ara_cdc_inspect_legacy
        if {$code} { return -options $options $result }
        write_reports inspect_$token
        set handle [open [file join $session completed_run.txt] {WRONLY CREAT EXCL}]
        puts $handle inspect_$token
        close $handle
        close_project
        return
    }
    check_ips
    if {$stage eq "impl"} {
        if {![regexp {^synth_[0-9a-f]{12}$} $parent]} { error "Missing managed synthesis parent" }
        reusable $parent {*synth_design Complete*} ${design_top}.dcp
        open_run $parent
        require_no_multiple_drivers [file join $package_root reports preflight_$token]
        require_no_combinational_loops [file join $package_root reports preflight_$token]
        close_design
    } elseif {$parent ne "-"} { error "Synthesis must not have a parent" }
    if {$stage eq "synth"} {
        set hook [file join $package_root scripts synth_pre.tcl]
        nonempty $hook
    }
    set name ${stage}_$token
    set dir [file join $session $name]
    if {[file exists $dir]} { error "Refusing to reuse run directory: $dir" }
    set run [clone_run ${stage}_1 $name $parent]
    if {$stage eq "synth"} {
        set_property STEPS.SYNTH_DESIGN.TCL.PRE $hook $run
        current_run -synthesis $run
        set expected {*synth_design Complete*}
        set extra {}
    } else {
        current_run -implementation $run
        set expected {*route_design Complete*}
        set extra {-to_step route_design}
    }
    puts "NEW RUN: $name"
    puts "NEW LOG: [file join $dir runme.log]"
    launch_runs $name -jobs 1 -dir $session {*}$extra
    wait_checked $name $expected $dir
    check_run $name $expected
    open_run $name
    require_no_multiple_drivers [file join $package_root reports $name]
    write_reports $name [expr {$stage eq "impl"}]
    if {$stage eq "impl"} {
        set setup [get_timing_paths -quiet -delay_type max -max_paths 1]
        set hold [get_timing_paths -quiet -delay_type min -max_paths 1]
        if {![llength $setup] || ![llength $hold]} { error "No timing paths; inspect reports/$name" }
        if {[get_property SLACK $setup] < 0 || [get_property SLACK $hold] < 0} {
            error "Timing not met; inspect reports/$name. No bitstream was generated."
        }
        puts "Route complete. Review DRC/CDC/unconstrained paths before generating a bitstream."
    }
    set handle [open [file join $session completed_run.txt] {WRONLY CREAT EXCL}]
    puts $handle $name
    close $handle
    close_project
}
