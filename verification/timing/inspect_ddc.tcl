# Read-only structural audit of an existing elaborated or mapped checkpoint.
# DDC_INPUT and DC_LIBRARY_ENV are absolute paths; reports go to the current dir.
# DC_DESIGNS can restrict the expensive per-design attribute audit.
source $env(DC_LIBRARY_ENV)
set_app_var target_library $STD_LIBRARY_LIST(BWP12T,tc)
set_app_var synthetic_library dw_foundation.sldb
set libs "* $target_library $synthetic_library"
foreach key [array names IP_LIBRARY_LIST *,tc] {
    append libs " $IP_LIBRARY_LIST($key)"
}
set_app_var link_library $libs
set_host_options -max_cores 2
read_ddc $env(DDC_INPUT)
if {![link]} {exit 1}
set top [get_object_name [current_design]]
set f [open design_cells.tsv w]
fconfigure $f -buffering line
puts $f "design\tdirect_cells\thierarchical_cells\tsequential_cells"
set h [open cell_types.tsv w]
fconfigure $h -buffering line
puts $h "design\treference\tcount"
set patterns {qbs_* akv_*}
if {[info exists env(DC_DESIGNS)]} {set patterns $env(DC_DESIGNS)}
set designs [get_designs -quiet $patterns]
foreach_in_collection d $designs {
    current_design $d
    set name [get_object_name $d]
    set cells [get_cells -quiet *]
    if {[sizeof_collection $cells] == 0} {
        puts $f "$name\t0\t0\t0"
        continue
    }
    set seq [filter_collection $cells {is_sequential == true}]
    set hier [filter_collection $cells {is_hierarchical == true}]
    puts $f "$name\t[sizeof_collection $cells]\t[sizeof_collection $hier]\t[sizeof_collection $seq]"
    array unset counts
    foreach ref [get_attribute $cells ref_name] {
        if {![info exists counts($ref)]} {set counts($ref) 0}
        incr counts($ref)
    }
    foreach ref [lsort [array names counts]] {
        puts $h "$name\t$ref\t$counts($ref)"
    }
}
close $f
close $h
current_design $top
redirect references.rpt {report_reference -hierarchy}
puts "DDC_AUDIT_COMPLETE"
exit
