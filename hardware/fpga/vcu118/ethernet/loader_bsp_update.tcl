# Regenerate only the existing standalone BSP after a checked lwIP setting change.
if {[llength $argv] != 1} { error "Usage: loader_bsp_update.tcl WORKSPACE" }
set workspace [lindex $argv 0]
if {![file isdirectory [file join $workspace loader_platform]] ||
    ![file isfile [file join $workspace loader_app src lscript.ld]]} {
    error "Missing prepared loader workspace: $workspace"
}
setws $workspace
platform active loader_platform
domain active loader_domain
if {[bsp config mem_size] != 65536 || [bsp config pbuf_pool_size] != 80} {
    error "Refusing to update an unexpected BSP memory profile"
}
bsp config tcp_wnd 16384
if {[bsp config tcp_wnd] != 16384} { error "TCP receive window update failed" }
platform generate
puts "TCP_WND_VERIFIED [bsp config tcp_wnd]"
puts "LOADER_BSP_UPDATED $workspace"
