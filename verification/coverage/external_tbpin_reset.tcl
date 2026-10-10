# Shared UCLI observer: only the external TB reset pin may be deposited.
proc etbr_path {path} {
    if {![regexp {^ara_tb(\.[A-Za-z_][A-Za-z0-9_]*(\[[0-9]+\])*)+$} $path]} {
        error "Invalid explicit HDL path: $path"
    }
    return $path
}
proc etbr_value {path} {
    set raw [string trim [get [etbr_path $path] -radix decimal]]
    if {[regexp {^([0-9]+)$} $raw -> number] ||
        [regexp {^[0-9]*'[dD]([0-9]+)$} $raw -> number]} {
        scan $number %d result
        return $result
    }
    error "Unknown/non-numeric HDL value: $path = $raw"
}
proc etbr_deposit {path value} {
    if {$path ne "ara_tb.rst_n" || ($value ne "0" && $value ne "1")} {
        error "External reset drive whitelist rejected: $path $value"
    }
    force ara_tb.rst_n $value -deposit
}
proc etbr_execute {route stage code valids} {
    if {![regexp {^[A-Za-z0-9_]+$} $route] ||
        ![string is integer -strict $code] || $code < 0 || [llength $valids] == 0} {
        error "Invalid route/code/valid contract"
    }
    etbr_path $stage
    set seen [list $stage]
    foreach path $valids {
        etbr_path $path
        if {[lsearch -exact $seen $path] >= 0} {error "Duplicate observer path"}
        lappend seen $path
    }
    set ara ara_tb.dut.i_ara_soc.i_system.i_ara
    set objects [concat [list ara_tb.clk ara_tb.rst_n ${ara}.axi_req_o ${ara}.axi_resp_i] $seen]
    set fid [dump -file focused-reset.vpd -type VPD]
    foreach path $objects {
        show -type $path
        set added [dump -add $path -fid $fid -depth 0 -aggregates]
        if {![string is integer -strict $added] || $added <= 0} {error "Missing dump object: $path"}
        puts "ETBR_OBJECT $path"
    }
    set condition "($stage == $code) && (ara_tb.rst_n == 1)"
    foreach path $valids {append condition " && ($path == 1)"}
    set ::etbr_hit 0
    stop -once -negedge ara_tb.clk -condition $condition -command {set ::etbr_hit 1}
    puts "ETBR_ARMED $route $stage $code"
    run
    if {!$::etbr_hit || [etbr_value $stage] != $code || [etbr_value ara_tb.rst_n] != 1} {
        error "Target stage not reached at the armed falling edge"
    }
    foreach path $valids {
        if {[etbr_value $path] != 1} {error "Target validity differs: $path"}
        puts "ETBR_VALID $path 1"
    }
    puts "ETBR_TARGET $route $stage $code"
    etbr_deposit ara_tb.rst_n 0
    puts "ETBR_ASSERT $route 0"
    for {set cycle 1} {$cycle <= 4} {incr cycle} {
        run -negedge ara_tb.clk
        if {[etbr_value ara_tb.rst_n] != 0} {error "Reset not held low for four cycles"}
        puts "ETBR_LOW_EDGE $route $cycle"
    }
    etbr_deposit ara_tb.rst_n 1
    puts "ETBR_RELEASE $route 1"
    puts "ETBR_RECOVERY $route"
    run
}
