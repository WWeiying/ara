# Bounded API introspection only; no exclusions or coverage qualification.
proc apply_reviewed_waivers {id} {
    global env
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) native-api.txt] w]
    puts $stream "Tcl: [info patchlevel]"
    puts $stream "Help commands: [info commands *help*]"
    puts $stream "List commands: [info commands *list*]"
    foreach query {{gui_list_get -help} {help gui_list_get} {gui_list_get_property -help}
                   {help gui_covdetail_query} {help gui_list_get_meta} {help gui_list_get_value}
                   {help gui_dump_common_list} {help gui_list_select_all}
                   {help gui_list_get_selected} {help gui_covdetail_select} {help gui_list_set_mode}} {
        puts $stream "QUERY [list $query]"
        set failed [catch {eval $query} result]
        puts $stream "STATUS $failed RESULT [list $result]"
    }
    close $stream
    puts "LZC_READ_ONLY_DISCOVERY_DONE 1"
}
