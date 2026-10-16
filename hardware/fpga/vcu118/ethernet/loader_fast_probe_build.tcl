# Build the isolated raw-frame probe against an existing validated loader BSP.
proc build_fast_probe {workspace {mode frame}} {
    if {$mode ni {frame cdma ara_cdma}} { error "Expected frame, cdma or ara_cdma mode" }
    set use_cdma [expr {$mode ne "frame"}]
    set bsp [file join $workspace loader_platform mb loader_domain bsp mb]
    set include [file join $bsp include]
    set library [file join $bsp lib]
    set source [file join $workspace loader_app src]
    set linker [file join $source lscript.ld]
    foreach path [list [file join $include xparameters.h] \
                       [file join $library libxil.a] $linker] {
        if {![file isfile $path]} { error "Missing probe build input: $path" }
    }
    if {$use_cdma && ![file isfile [file join $include xaxicdma.h]]} {
        error "The CDMA BSP driver is missing"
    }
    set build_dir [file join $workspace loader_app fast_probe_$mode]
    file mkdir $build_dir
    set objects {}
    set names {eth_loader_platform eth_fast_probe_frame eth_fast_probe_main}
    if {$use_cdma} { lappend names eth_fast_load }
    foreach name $names {
        set input [file join $source ${name}.c]
        if {![file isfile $input]} { error "Missing probe source: $input" }
        set object [file join $build_dir ${name}.o]
        file delete -force $object
        puts "COMPILE $name"
        set command [list mb-gcc -O2 -Wall -Wextra -Werror -std=c11 \
            -mcpu=v11.0 -mlittle-endian -mxl-soft-mul \
            -ffunction-sections -fdata-sections -I$include \
            -c $input -o $object]
        if {$use_cdma} { set command [linsert $command 1 -DETH_PROBE_USE_CDMA=1] }
        if {$mode eq "ara_cdma"} { set command [linsert $command 1 -DETH_LOADER_ARA=1] }
        set message [exec {*}$command 2>@1]
        if {$message ne ""} { puts $message }
        if {![file isfile $object]} { error "Probe compile did not produce $object" }
        lappend objects $object
    }
    set elf [file join $build_dir fast_probe.elf]
    set map [file join $build_dir fast_probe.map]
    file delete -force $elf
    puts "LINK $elf"
    set command [concat [list mb-gcc -mcpu=v11.0 -mlittle-endian -mxl-soft-mul \
        -Wl,--no-relax -Wl,--gc-sections \
        -Wl,-defsym,_STACK_SIZE=0x4000 -Wl,-defsym,_HEAP_SIZE=0x4000 \
        -Wl,-T,$linker -Wl,-Map,$map -L$library -o $elf] \
        $objects [list -Wl,--start-group -lxil -llwip4 -lgcc -lc -Wl,--end-group]]
    set message [exec {*}$command 2>@1]
    if {$message ne ""} { puts $message }
    if {![file isfile $elf]} { error "Probe link did not produce $elf" }
    if {$use_cdma} {
        set symbols [exec mb-nm $elf]
        foreach name {cdma load_state} {
            if {![regexp -line [format {^([0-9a-fA-F]+) [dD] %s$} $name] $symbols -> address]} {
                error "Missing BRAM control object: $name"
            }
            scan $address %x location
            if {$location >= 0x80000} { error "Control object outside BRAM: $name=$address" }
            puts "BRAM_CONTROL $name 0x$address"
        }
    }
    puts "FAST_PROBE_ELF $elf"
    puts [exec mb-size $elf]
}

if {[llength $argv] < 1 || [llength $argv] > 2} {
    error "Usage: loader_fast_probe_build.tcl WORKSPACE ?frame|cdma|ara_cdma?"
}
if {[catch {build_fast_probe {*}$argv} message options]} {
    puts stderr [dict get $options -errorinfo]
    exit 1
}
exit 0
