#!/bin/busybox sh
export PATH=/sbin:/bin:/usr/sbin:/usr/bin HOME=/root TERM=vt100
echo ARA_STAGE_SHELL_ENTERED
mount -t proc proc /proc 2>/dev/null || true
echo ARA_STAGE_PROC_DONE
mount -t sysfs sysfs /sys 2>/dev/null || true
echo ARA_STAGE_SYS_DONE
mount -t devtmpfs devtmpfs /dev 2>/dev/null || true
mkdir -p /dev/pts /dev/shm /run /tmp
mount -t devpts devpts /dev/pts 2>/dev/null || true
mount -t tmpfs tmpfs /run 2>/dev/null || true
mount -t tmpfs tmpfs /tmp 2>/dev/null || true
echo ARA_STAGE_MOUNTS_DONE
exec /bin/busybox setsid -c /bin/busybox sh </dev/console >/dev/console 2>&1
