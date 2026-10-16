# XSCT/Vitis 2020.1 platform gate; generates no bootable image.
proc build_loader_bsp {output workspace thirdparty_repo os} {
    set xsa [file join $output loader_no_bitstream.xsa]
    if {![file isfile $xsa] || [file exists $workspace] ||
        ![file isdirectory [file join $thirdparty_repo bsp]]} {
        error "Missing XSA/ThirdParty BSP repository or workspace already exists"
    }
    if {$os ne "standalone"} { error "Loader BSP must be standalone" }
    setws $workspace
    puts "OS_BEFORE [repo -os]"
    repo -set $thirdparty_repo
    set operating_systems [repo -os]
    puts "OS_AFTER $operating_systems"
    if {[lsearch -exact $operating_systems $os] < 0} {
        error "Requested OS remains unavailable after repository scan: $os"
    }
    platform create -name loader_platform -hw $xsa -no-boot-bsp
    domain create -name loader_domain -os $os -proc mb
    domain active loader_domain
    bsp setlib -name lwip211
    # The vendor DMA adapter allocates two 9216-byte descriptor blocks here.
    bsp config mem_size 65536
    # The vendor RX setup consumes 64 pool buffers before starting DMA.
    bsp config pbuf_pool_size 80
    # One 4 KiB record should fit inside the advertised receive window.
    bsp config tcp_wnd 16384
    if {[bsp config mem_size] != 65536 ||
        [bsp config pbuf_pool_size] != 80 ||
        [bsp config tcp_wnd] != 16384} {
        error "Standalone lwIP memory profile was not applied"
    }
    platform generate
    puts "LOADER_BSP_GENERATED $workspace"
}

if {[llength $argv] != 4} {
    error "Usage: loader_bsp.tcl OUTPUT WORKSPACE THIRDPARTY_REPO OS"
}
if {[catch {build_loader_bsp {*}$argv} message options]} {
    puts stderr [dict get $options -errorinfo]
    exit 1
}
exit 0
