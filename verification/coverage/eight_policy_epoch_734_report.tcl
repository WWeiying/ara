# New entry only. All source files and generated library bytes are pinned.
source [file join $env(DVE_COVERAGE_OUTPUT) csv-row-library.tcl]
if {[llength [info commands csv_row]]!=1} {error "Missing fixed-eight CSV writer"}
puts EIGHT_CSV_WRITER_INSTALLED
source [file join $env(DVE_COVERAGE_OUTPUT) native-exclusion-multiset-v2.tcl]
source [file join $env(DVE_COVERAGE_OUTPUT) eight-session-v2.tcl]
