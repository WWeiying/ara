# Read-only native condition metadata discovery; never excludes items.
proc lzc_dump_nodes {stream parent depth} {
    global lzc_rows
    if {$depth > 32 || $lzc_rows > 2000} {error "Unexpected condition tree size"}
    if {$parent eq ""} {
        set item [gui_list_get -id CovDetail.1 -firstChild]
    } else {
        set item [gui_list_get -id CovDetail.1 -firstChild $parent]
    }
    while {$item ne "" && $item ne "0"} {
        set path [gui_list_get -id CovDetail.1 -path $item]
        set meta ""
        catch {set meta [gui_list_get -id CovDetail.1 -meta $item]}
        set values [list $depth $path $meta]
        for {set column 0} {$column < 12} {incr column} {
            set value ""
            catch {set value [gui_list_get -id CovDetail.1 -text $column $item]}
            lappend values $value
        }
        csv_row $stream $values
        incr lzc_rows
        lzc_dump_nodes $stream $item [expr {$depth + 1}]
        set item [gui_list_get -id CovDetail.1 -nextSibling $item]
    }
}

proc apply_reviewed_waivers {id} {
    global env lzc_rows
    # The exporter callback name is reused only for a read-only inventory.
    gui_list_action -id $id -column Condition $env(LZC_DISCOVERY_SCOPE)
    if {[gui_covdetail_query -id CovDetail.1 -name type] ne "Condition"} {
        error "Not native Condition view"
    }
    gui_list_expand -id CovDetail.1 -all {<root>}
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) native-condition-tree.csv] w]
    fconfigure $stream -encoding utf-8 -translation lf
    set header {Depth Path Meta}
    for {set column 0} {$column < 12} {incr column} {lappend header "Column$column"}
    csv_row $stream $header
    set lzc_rows 0
    set failed [catch {lzc_dump_nodes $stream "" 0} message]
    close $stream
    if {$failed} {error $message}
    if {$lzc_rows == 0} {error "Empty native condition inventory"}
    puts "LZC_READ_ONLY_DISCOVERY_DONE $lzc_rows"
}
