# Exact qualified debug vectors only; never executes exclude-items or update.
proc obd_require {ok message} {if {!$ok} {error $message}}
proc obd_load {} {
    global dbg_library_only
    set dbg_library_only 1
    source /home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/capture_operand_debug.tcl
    foreach helper {dbg_select dbg_save dbg_require} {
        if {[info procs $helper] ne $helper} {error "Missing frozen helper: $helper"}
    }
}
proc obd_fullroot {} {
    gui_covtable_show -id CoverageTable.1 -show {Design Hierarchy} -cumulative 1
    gui_covtable_setroot -id CoverageTable.1 ara_tb
    gui_list_expand -id CoverageTable.1 -all {<root>}
    gui_process_events
}
proc obd_metadata {scope} {
    global dbg_keys
    gui_list_action -id CoverageTable.1 -column Branch $scope
    obd_require [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Branch"}] "Wrong detail type"
    gui_list_expand -id CovDetail.1 -all {<root>}
    array set found {}
    set parent [gui_list_get -id CovDetail.1 -firstChild]
    while {$parent ne "" && $parent ne "0"} {
        set parentpath [gui_list_get -id CovDetail.1 -path $parent]
        obd_require [regexp {^Item([0-9]+)$} $parentpath unused parentid] "Unknown branch parent"
        set item [gui_list_get -id CovDetail.1 -firstChild $parent]
        while {$item ne "" && $item ne "0"} {
            set meta [gui_list_get -id CovDetail.1 -meta $item]
            set path [gui_list_get -id CovDetail.1 -path $item]
            obd_require [regexp {^(Branch|MISSING_ELSE|MISSING_DEFAULT)([0-9]+)\.([0-9]+)$} $meta unused kind sid vid] "Unknown branch vector"
            obd_require [expr {$sid eq $parentid && $path eq "$parentpath.$meta" && [gui_list_get -id CovDetail.1 -childCount $item] == 0}] "Native vector identity differs"
            set key "$sid,$vid"
            obd_require [expr {![info exists found($key)]}] "Duplicate branch vector"
            set found($key) [list $meta $path]
            set item [gui_list_get -id CovDetail.1 -nextSibling $item]
        }
        set parent [gui_list_get -id CovDetail.1 -nextSibling $parent]
    }
    obd_require [expr {[lsort [array names found]] eq [lsort $dbg_keys($scope|branch)]}] "Full compiled/native inventory differs"
    return [array get found]
}
proc obd_audit {stage active} {
    global env dbg_scopes dbg_keys dbg_targets
    obd_fullroot
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) states_$stage.tsv] w]
    puts $stream "scope\tmetric\tcoordinate\tmeta\tpath\texcluded"
    set count 0
    set failed [catch {
        foreach scope $dbg_scopes {
            array unset metadata
            array set metadata [obd_metadata $scope]
            foreach key $dbg_keys($scope|branch) {
                set meta [lindex $metadata($key) 0]
                set path [lindex $metadata($key) 1]
                dbg_select branch $meta
                set actual [gui_exclusion -id CovDetail.1 -list branch -excluded -selected]
                set wanted [expr {$active && [lsearch -exact $dbg_targets($scope|branch) $key] >= 0}]
                obd_require [expr {($actual eq "0" || $actual eq "1") && $actual == $wanted}] "Exact target/protected state differs"
                puts $stream "$scope\tbranch\t$key\t$meta\t$path\t$actual"
                incr count
            }
        }
    } message]
    close $stream
    if {$failed} {error $message}
    obd_require [expr {$count == 3008}] "Wrong branch inventory count"
    puts "OBD_AUDIT $stage $count"
}
proc obd_csv {stream values} {
    set quoted {}
    foreach value $values {lappend quoted "\"[string map [list \" \"\"] $value]\""}
    puts $stream [join $quoted ,]
}
proc obd_values {item columns} {
    set values {}
    foreach column $columns {
        set value [string trim [gui_list_get -id CoverageTable.1 -text $column $item]]
        if {$value eq ""} {set value NA}
        lappend values $value
    }
    return $values
}
proc obd_rows {stream parent depth columns} {
    global obd_seen obd_names obd_count
    obd_require [expr {$depth <= 256 && $obd_count < 100000}] "Hierarchy bounds exceeded"
    if {$parent eq ""} {set item [gui_list_get -id CoverageTable.1 -firstChild]} else {
        set item [gui_list_get -id CoverageTable.1 -firstChild $parent]
    }
    while {$item ne "" && $item ne "0"} {
        obd_require [expr {![info exists obd_seen($item)]}] "Repeated hierarchy handle"
        set obd_seen($item) 1
        set name [gui_list_get -id CoverageTable.1 -text 0 $item]
        obd_require [expr {$name ne ""}] "Unnamed hierarchy row"
        set obd_names [lrange $obd_names 0 [expr {$depth-1}]]
        if {$depth == 0} {set obd_names {}}
        lappend obd_names $name
        set scope [join $obd_names .]
        obd_require [expr {![info exists obd_seen(scope:$scope)]}] "Duplicate reconstructed scope"
        set obd_seen(scope:$scope) 1
        set obd_seen(name:$scope) $name
        obd_csv $stream [concat [list $name $depth] [obd_values $item $columns]]
        incr obd_count
        obd_rows $stream $item [expr {$depth+1}] $columns
        set item [gui_list_get -id CoverageTable.1 -nextSibling $item]
    }
}
proc obd_token {raw} {
    obd_require [expr {[llength $raw] <= 1}] "Multiple selection groups"
    if {![llength $raw]} {return {}}
    set group [lindex $raw 0]
    obd_require [expr {[llength $group] <= 1}] "Multiple selection tokens"
    return $group
}
proc obd_select_scope {scope} {
    set old [obd_token [gui_list_get_selected -id CoverageTable.1 -flat]]
    if {[llength $old]} {gui_list_select -id CoverageTable.1 -unselect $old}
    gui_list_select -id CoverageTable.1 -select [list $scope]
    set actual [obd_token [gui_list_get_selected -id CoverageTable.1 -flat]]
    obd_require [expr {[llength $actual] == 1 && [lindex $actual 0] eq $scope}] "Actual full-scope token differs"
    return [lindex $actual 0]
}
proc obd_summary {stage} {
    global env obd_roots obd_seen obd_names obd_count
    obd_fullroot
    set columns {}
    set labels {}
    for {set col 5} {$col < 32} {incr col} {
        if {[catch {gui_list_get_property -id CoverageTable.1 -column $col} label]} {break}
        set label [string trim $label]
        if {$label eq ""} {continue}
        lappend columns $col
        lappend labels $label
    }
    obd_require [expr {[lsearch -exact $labels Branch] >= 0 && [lsearch -exact $labels Score] >= 0}] "Missing report columns"
    array unset obd_seen
    array set obd_seen {}
    set obd_names {}
    set obd_count 0
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) table_$stage.csv] w]
    obd_csv $stream [concat {Name Depth} $labels]
    set failed [catch {obd_rows $stream "" 0 $columns} message]
    close $stream
    if {$failed} {error $message}
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) roots_$stage.csv] w]
    obd_csv $stream [concat {Scope LocalPath LocalName Handle} $labels]
    set failed [catch {
        foreach scope $obd_roots {
            obd_require [expr {[info exists obd_seen(name:$scope)]}] "Missing reconstructed report scope"
            set savedname $obd_seen(name:$scope)
            obd_fullroot
            set token [obd_select_scope $scope]
            gui_covtable_setroot -id CoverageTable.1 $token
            gui_process_events
            gui_exclusion -id CoverageTable.1 -recalculate
            gui_process_events
            set item [gui_list_get -id CoverageTable.1 -firstChild]
            obd_require [expr {$item ne "" && $item ne "0"}] "Missing rooted row"
            set path [gui_list_get -id CoverageTable.1 -path $item]
            set name [gui_list_get -id CoverageTable.1 -text 0 $item]
            set sibling [gui_list_get -id CoverageTable.1 -nextSibling $item]
            set basename [lindex [split $scope .] end]
            obd_require [expr {$name eq $path && ($path eq $basename || $path eq $savedname) && ($sibling eq "" || $sibling eq "0")}] "Root row not bound to exact full scope"
            obd_csv $stream [concat [list $scope $path $name $item] [obd_values $item $columns]]
        }
    } message]
    close $stream
    if {$failed} {error $message}
    puts "OBD_SUMMARY $stage $obd_count"
}
proc obd_session {} {
    global env dbg_design dbg_test dbg_scopes dbg_keys dbg_targets dbg_python dbg_driver
    global obd_databases obd_tests obd_native obd_roots
    obd_load
    source $env(OBD_SELECTION)
    foreach command {gui_covtable_setroot gui_covtable_show gui_list_select gui_list_get_selected gui_exclusion} {puts [help $command]}
    set deadline [expr {[clock seconds]+60}]
    while {![file exists [file join $env(DVE_COVERAGE_OUTPUT) live-ready]]} {
        if {[clock seconds] >= $deadline} {error "Live identity timeout"}
        after 100
    }
    obd_require [expr {[llength $obd_tests] == [llength $obd_databases] && ([llength $obd_tests] == 1 || [llength $obd_tests] == 701)}] "Wrong test population"
    foreach name {obd_tests obd_databases} {
        set canonical {}
        foreach path [set $name] {
            obd_require [expr {[file pathtype $path] eq "absolute" && ![regexp {[\s{}]} $path]}] "Unsafe GUI input path"
            lappend canonical $path
        }
        set $name $canonical
    }
    gui_open_cov -hier $dbg_design -testdir $obd_databases -test $obd_tests -merge OperandDebugExact1832
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) DVEfiles dve_gui.log] r]
    set log [read $stream]
    close $stream
    obd_require [expr {![regexp {UCAPI-DLMA|DVCDT136|EK-CMD-|Load Failed|Failed to load tests|Error:|Fatal:} $log] && [string first "The design '$dbg_design' was loaded successfully." $log] >= 0}] "Coverage load failed"
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) selected_tests.txt] w]
    foreach test $obd_tests {puts $stream $test}
    close $stream
    obd_fullroot
    dbg_save initial-empty.el 1
    obd_audit raw 0
    obd_summary raw
    gui_exclusion_file -load -file [list $obd_native]
    gui_exclusion -id CoverageTable.1 -recalculate
    obd_require [expr {[gui_cov_excl_review -isEmpty] == 1}] "Native checksum review not empty"
    obd_audit applied 1
    obd_summary applied
    dbg_save applied.el
    obd_audit after 1
    dbg_save after-refresh.el
    gui_exclusion -reset
    obd_audit reset 0
    dbg_save reset-empty.el 1
    obd_summary reset
}
if {![info exists obd_library_only]} {
    set failed [catch {obd_session} message]
    if {$failed} {puts "OBD_FAILED $message\n$::errorInfo"}
    set cleanup {}
    foreach step {reset audit save} {
        set bad [catch {
            switch -- $step {
                reset {gui_exclusion -reset}
                audit {if {[info exists dbg_scopes]} {obd_audit final 0}}
                save {if {[info procs dbg_save] ne ""} {dbg_save final-empty.el 1}}
            }
        } detail]
        if {$bad} {lappend cleanup [list $step $detail]; puts "OBD_CLEANUP_ERROR $step $detail"}
    }
    if {!$failed && ![llength $cleanup]} {puts OBD_DONE_RESET}
    gui_exit -noprompt
}
