# Read-only API help, no database or exclusion load.
puts "LZC_SUMMARY_COMMANDS [info commands *cov*]"
foreach command {gui_list_descend gui_list_ascend gui_list_get_meta gui_list_get_value gui_list_get_property gui_list_get_selected gui_covdetail_query gui_list_action gui_list_set_mode gui_exclusion gui_get_window_ids gui_covhier_list_init gui_cov_list_get_top_parent gui_covtable_setroot gui_covtable_show gui_covtable_query gui_cov_table_show gui_cov_show_value gui_reload_cov gui_show_covreport} {
    puts "LZC_HELP_BEGIN $command"
    set failed [catch {help $command} result]
    puts "LZC_HELP_END $command $failed [list $result]"
}
puts "LZC_SUMMARY_API_DONE"
gui_exit -noprompt
