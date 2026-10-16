# Create an empty standalone Vitis application for linker review.
proc prepare_loader_app {workspace firmware} {
    if {![file isdirectory [file join $workspace loader_platform]] ||
        ![file isdirectory $firmware] ||
        [file exists [file join $workspace loader_app]]} {
        error "Missing platform/firmware or loader_app already exists"
    }
    setws $workspace
    platform active loader_platform
    domain active loader_domain
    app create -name loader_app -platform loader_platform -domain loader_domain -template {Empty Application}
    set source [file join $workspace loader_app src]
    foreach filename {
        eth_loader_core.c eth_loader_core.h
        eth_loader_stream.c eth_loader_stream.h
        eth_loader_raw.c eth_loader_raw.h
        eth_loader_ddr.c eth_loader_ddr.h
        eth_loader_platform.c eth_loader_platform.h
        eth_loader_main.c
    } {
        set input [file join $firmware $filename]
        if {![file isfile $input]} { error "Missing loader source: $input" }
        file copy $input [file join $source $filename]
    }
    set linker [file join $source lscript.ld]
    if {![file isfile $linker]} { error "Missing generated linker script" }
    set channel [open $linker r]
    set script [read $channel]
    close $channel
    set local_region mb_local_memory_ilmb_bram_if_cntlr_Mem_mb_local_memory_dlmb_bram_if_cntlr_Mem
    set ddr_region ddr_C0_DDR4_ADDRESS_BLOCK
    set old_memory "   $ddr_region : ORIGIN = 0x80000000, LENGTH = 0x80000000"
    set new_memory "   $ddr_region : ORIGIN = 0xFF000000, LENGTH = 0x01000000"
    set memory_at [string first $old_memory $script]
    if {$memory_at < 0 || [string first $old_memory $script [expr {$memory_at + 1}]] >= 0} {
        error "Unexpected generated DDR linker region"
    }
    set script [string map [list $old_memory $new_memory] $script]
    set bss_at [string first ".bss (NOLOAD) :" $script]
    set after_bss [string first "\n_SDA_BASE_" $script $bss_at]
    if {$bss_at < 0 || $after_bss < 0} { error "Unexpected generated BSS section" }
    set section [string range $script $bss_at [expr {$after_bss - 1}]]
    set old_target "\} > $local_region"
    set target_at [string first $old_target $section]
    if {$target_at < 0 || [string first $old_target $section [expr {$target_at + 1}]] >= 0} {
        error "Unexpected generated BSS target"
    }
    set section [string map [list $old_target "\} > $ddr_region"] $section]
    set script [string replace $script $bss_at [expr {$after_bss - 1}] $section]
    set channel [open $linker w]
    puts -nonewline $channel $script
    close $channel
    puts "LOADER_APP_PREPARED $source"
    puts "LOADER_BSS_RESERVED_DDR 0xFF000000..0xFFFFFFFF"
    puts "REVIEW_LINKER $linker"
    puts "NOT_LINKED_NOT_PROGRAMMED"
}

if {[llength $argv] != 2} {
    error "Usage: loader_app_prepare.tcl WORKSPACE FIRMWARE"
}
if {[catch {prepare_loader_app {*}$argv} message options]} {
    puts stderr [dict get $options -errorinfo]
    exit 1
}
exit 0
