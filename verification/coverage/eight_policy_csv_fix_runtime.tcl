# Tcl8.4. The pinned CSV-only helper precedes all frozen eight initialization.
source [file join $env(DVE_COVERAGE_OUTPUT) csv-row-library.tcl]
if {[llength [info commands csv_row]]!=1} {error "Missing fixed-eight CSV writer"}
puts EIGHT_CSV_WRITER_INSTALLED
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/lzc_snapshot_eight_policy_runtime.tcl}
