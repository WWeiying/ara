#!/usr/bin/env bash
set -o pipefail

dc_shell-t -64bit -f ../global_scripts/dc.tcl | tee dc.log
