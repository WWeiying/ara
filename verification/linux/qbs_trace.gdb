set pagination off
set confirm off
set debuginfod enabled off
set auto-load off
set disable-randomization off
set $qbs_info_hits = 0
set $qbs_exec_hits = 0
break helper_qbs_info
commands
silent
set $qbs_info_hits = $qbs_info_hits + 1
continue
end
break helper_qbs_exec
commands
silent
set $qbs_exec_hits = $qbs_exec_hits + 1
printf "[QBS_HOST_TRACE] helper_qbs_exec entry=%d\n", $qbs_exec_hits
continue
end
run
printf "[QBS_HOST_TRACE] info_entries=%d exec_entries=%d\n", $qbs_info_hits, $qbs_exec_hits
