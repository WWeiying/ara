# Link against the generated standalone BSP without relying on Vitis's stale
# Empty Application _sdk/bsp makefile path. No bitstream or board access.
proc build_loader_app {workspace} {
    if {![file isdirectory [file join $workspace loader_platform]] ||
        ![file isdirectory [file join $workspace loader_app]]} {
        error "Missing prepared loader workspace: $workspace"
    }
    set bsp [file join $workspace loader_platform mb loader_domain bsp mb]
    set include [file join $bsp include]
    set library [file join $bsp lib]
    set source [file join $workspace loader_app src]
    set linker [file join $source lscript.ld]
    foreach path [list [file join $include xparameters.h] [file join $library libxil.a] $linker] {
        if {![file isfile $path]} { error "Missing generated build input: $path" }
    }
    set build_dir [file join $workspace loader_app direct]
    file mkdir $build_dir
    set objects {}
    foreach name {
        eth_loader_core eth_loader_stream eth_loader_raw eth_loader_ddr
        eth_loader_platform eth_loader_main
    } {
        set object [file join $build_dir ${name}.o]
        set command [list mb-gcc -O2 -Wall -Wextra -std=c11 \
            -DETH_LOADER_PROFILE \
            -mcpu=v11.0 -mlittle-endian -mxl-soft-mul \
            -ffunction-sections -fdata-sections -I$include \
            -c [file join $source ${name}.c] -o $object]
        puts "COMPILE $name"
        set message [exec {*}$command 2>@1]
        if {$message ne ""} { puts $message }
        lappend objects $object
    }
    set elf [file join $build_dir loader_app.elf]
    set map [file join $build_dir loader_app.map]
    set command [concat [list mb-gcc -mcpu=v11.0 -mlittle-endian -mxl-soft-mul \
        -Wl,--no-relax -Wl,--gc-sections \
        -Wl,-defsym,_STACK_SIZE=0x4000 -Wl,-defsym,_HEAP_SIZE=0x4000 \
        -Wl,-T,$linker -Wl,-Map,$map \
        -L$library -o $elf] $objects \
        [list -Wl,--start-group -lxil -llwip4 -lgcc -lc -Wl,--end-group]]
    puts "LINK $elf"
    set message [exec {*}$command 2>@1]
    if {$message ne ""} { puts $message }
    if {![file isfile $elf]} { error "Loader ELF was not produced: $elf" }
    set scratch_symbols 0
    foreach line [split [exec mb-nm -S $elf] "\n"] {
        if {![regexp {^([0-9a-fA-F]+)[ \t]+([0-9a-fA-F]+)[ \t]+[A-Za-z][ \t]+scratch$} \
                      [string trim $line] -> address_hex size_hex]} { continue }
        incr scratch_symbols
        scan $address_hex %x scratch_address
        scan $size_hex %x scratch_size
    }
    if {$scratch_symbols != 1 || $scratch_address < 0x50 ||
        $scratch_address + $scratch_size > 0x80000 || $scratch_size != 32768} {
        error "Expected one 32 KiB scratch buffer wholly inside 512 KiB local BRAM"
    }
    puts [format "SCRATCH_BRAM 0x%08x SIZE %d" $scratch_address $scratch_size]
    puts "LOADER_ELF $elf"
    puts "LINK_MAP $map"
    puts [exec mb-size $elf]
    puts "NOT_PROGRAMMED_NOT_BOARD_VERIFIED"
}

if {[llength $argv] != 1} { error "Usage: loader_app_build.tcl WORKSPACE" }
if {[catch {build_loader_app [lindex $argv 0]} message options]} {
    puts stderr [dict get $options -errorinfo]
    exit 1
}
exit 0
