#!/usr/bin/env bash

# Run isolated DC power analysis in the Synopsys EDA container.
# Usage: run_dc_saif_power.sh <mapped.ddc> <capture.saif> <output-dir>

set -euo pipefail

if (($# != 3)); then
    echo "usage: $0 <mapped.ddc> <capture.saif> <output-dir>" >&2
    exit 2
fi

ddc=$(realpath "$1")
saif=$(realpath "$2")
out=$(realpath -m "$3")
repo_root=$(git -C "$(dirname "$0")/../.." rev-parse --show-toplevel)
dc_env="$repo_root/hardware/dc_runs/20260916_control_closure/backend/syn/ara_soc/v1-dc/global_scripts/synopsys_dc.setup.env"
dc_tcl="$repo_root/hardware/scripts/power/dc_saif_power.tcl"

[[ -f "$ddc" ]] || { echo "missing DDC: $ddc" >&2; exit 1; }
[[ -f "$saif" ]] || { echo "missing SAIF: $saif" >&2; exit 1; }
[[ -f "$dc_env" ]] || { echo "missing DC environment: $dc_env" >&2; exit 1; }
mkdir -p "$out/reports"

container=synopsys_workspace
docker exec \
    -u 1002:1001 \
    -e HOME=/home/wangwy \
    -e POWER_DDC="$ddc" \
    -e POWER_SAIF="$saif" \
    -e POWER_OUT="$out" \
    -e POWER_DC_ENV="$dc_env" \
    -w "$out" \
    "$container" \
    bash -lc "source /home/wangwy/.bashrc >/dev/null 2>&1; exec dc_shell -64bit -f '$dc_tcl'" \
    > "$out/reports/dc_power.console.log" 2>&1

echo "power reports: $out/reports"
