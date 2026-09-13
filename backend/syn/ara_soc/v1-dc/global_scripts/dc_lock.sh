#!/usr/bin/env bash
# FD 9 stays open through recursive make, DC, and result collection.
dc_acquire_lock() {
    local lock_file
    lock_file=$(readlink -f -- "$1") || return 1
    if [[ ${ARA_DC_LOCK_FILE:-} != "$lock_file" ||
          ! /proc/$$/fd/9 -ef "$lock_file" ]]; then
        exec 9>>"$lock_file" || return 1
    fi
    flock -n 9 || {
        printf '%s\n' 'Another DC run owns this work directory.' >&2
        return 1
    }
    export ARA_DC_LOCK_FILE="$lock_file"
}

dc_require_lock() {
    local lock_file
    lock_file=$(readlink -f -- "$1") || return 1
    if [[ ${ARA_DC_LOCK_FILE:-} != "$lock_file" ||
          ! /proc/$$/fd/9 -ef "$lock_file" ]]; then
        printf '%s\n' 'Internal DC target requires the outer flow lock.' >&2
        return 1
    fi
    dc_acquire_lock "$lock_file"
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
    if [[ ${1:-} == --check && $# == 2 ]]; then
        dc_require_lock "$2"
        exit $?
    fi
    if (( $# < 2 )); then
        printf 'Usage: bash %s LOCK_FILE COMMAND [ARGS...]\n' "$0" >&2
        exit 2
    fi
    dc_acquire_lock "$1" || exit 1
    shift
    exec "$@"
fi
