# Runs inside the actual full-design synthesis worker, not just its launcher.
# A constant driver must not silently replace an intended register output.
foreach id {{Synth 8-6858} {Synth 8-6859}} {
    set_msg_config -id $id -new_severity ERROR
}
