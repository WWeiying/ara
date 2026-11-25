# Isolated DC power analysis for a mapped Ara netlist and one SAIF capture.
# Paths are passed through the environment so this script never depends on a
# synthesis run directory or on the legacy branch-specific saif.tcl.

if {![info exists env(POWER_DDC)] || ![file exists $env(POWER_DDC)]} {
    error "POWER_DDC is missing or does not exist"
}
if {![info exists env(POWER_SAIF)] || ![file exists $env(POWER_SAIF)]} {
    error "POWER_SAIF is missing or does not exist"
}
if {![info exists env(POWER_OUT)]} {
    error "POWER_OUT is missing"
}
if {![info exists env(POWER_DC_ENV)] || ![file exists $env(POWER_DC_ENV)]} {
    error "POWER_DC_ENV is missing or does not exist"
}

set out_dir $env(POWER_OUT)
file mkdir "$out_dir/reports"
set_app_var sh_output_log_file "$out_dir/reports/dc_power.out"

# Reuse the exact standard-cell and SRAM library set used by the timing run.
source -echo -verbose $env(POWER_DC_ENV)
set synthetic_library "/home/wangwy/software/synopsys/install/syn/syn/T-2022.03-SP2/libraries/syn/dw_foundation.sldb"
set power_target_library [list \
    $tcbn28hpcplusbwp12t40p140_180a \
    $tcbn28hpcplusbwp12t40p140cg_110c \
    $tcbn28hpcplusbwp12t40p140hvt_180a \
    $tcbn28hpcplusbwp12t40p140lvt_180a]
set power_memory_library [list \
    $ts1n28hpcpsvtb8192x128m4swbaso_180a \
    $ts1n28hpcpuhdsvtb8x128m1swbso_170a \
    $ts1n28hpcpuhdsvtb8x256m1swbso_170a \
    $ts1n28hpcpuhdsvtb16x64m1swbso_170a \
    $ts1n28hpcpuhdsvtb76x256m1swbso_170a \
    $ts1n28hpcpuhdsvtb96x256m1swbso_170a \
    $ts1n28hpcpuhdsvtb128x256m1swbso_170a \
    $ts1n28hpcpuhdsvtb64x128m4swbso_170a \
    $ts1n28hpcpuhdsvtb64x256m1swbso_170a \
    $ts1n28hpcpuhdsvtb64x48m4swbso_170a]
foreach lib [concat $power_target_library $power_memory_library [list $synthetic_library]] {
    if {![file exists $lib]} {
        error "power library does not exist: $lib"
    }
}

# Use application variables, rather than Tcl variables named target_library or
# link_library.  This also removes DC's default your_library.db entry.
set_app_var target_library $power_target_library
set_app_var link_library [concat [list *] $power_target_library \
    $power_memory_library [list $synthetic_library]]

read_ddc $env(POWER_DDC)
current_design ara_soc
if {![link]} {
    error "DC link failed"
}
update_timing

set instance_name "ara_tb/dut/i_ara_soc"
if {[info exists env(POWER_INSTANCE)] && $env(POWER_INSTANCE) ne ""} {
    set instance_name $env(POWER_INSTANCE)
}
saif_map -start
read_saif -input $env(POWER_SAIF) \
    -auto_map_names -instance_name $instance_name -verbose

report_saif -hierarchy -rtl_saif -missing \
    > "$out_dir/reports/saif_coverage.rpt"
report_power -groups "io_pad memory black_box clock_network register sequential combi" \
    > "$out_dir/reports/power_group.rpt"
report_power -hierarchy -verbose \
    > "$out_dir/reports/power_hierarchy.rpt"
report_power > "$out_dir/reports/power_total.rpt"
exit
