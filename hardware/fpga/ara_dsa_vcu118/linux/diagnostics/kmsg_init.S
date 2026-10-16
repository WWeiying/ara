.section .text
.globl _start
_start:
    la a0, devtmpfs
    la a1, devdir
    la a2, devtmpfs
    li a3, 0
    li a4, 0
    li a7, 40
    ecall

    li a0, -100
    la a1, kmsg_path
    li a2, 1
    li a3, 0
    li a7, 56
    ecall
    bltz a0, failed
    mv s0, a0

    mv a0, s0
    la a1, before
    la t0, before_end
    sub a2, t0, a1
    li a7, 64
    ecall

    li a0, 1
    la a1, marker
    la t0, marker_end
    sub a2, t0, a1
    mv s1, a2
    li a7, 64
    ecall
    mv s2, a0

    bltz s2, write_error
    beq s2, s1, write_full
    la a1, write_partial_msg
    la t0, write_partial_end
    j log_write_result
write_error:
    la a1, write_error_msg
    la t0, write_error_end
    j log_write_result
write_full:
    la a1, write_full_msg
    la t0, write_full_end
log_write_result:
    mv a0, s0
    sub a2, t0, a1
    li a7, 64
    ecall

    li a0, -100
    la a1, tty_path
    li a2, 1
    li a3, 0
    li a7, 56
    ecall
    bltz a0, tty_open_error
    mv s3, a0
    la a1, marker
    mv a2, s1
    li a7, 64
    ecall
    bltz a0, tty_write_error
    beq a0, s1, tty_write_full
    la a1, tty_partial_msg
    la t0, tty_partial_end
    j log_tty_result
tty_open_error:
    la a1, tty_open_error_msg
    la t0, tty_open_error_end
    j log_tty_result
tty_write_error:
    la a1, tty_error_msg
    la t0, tty_error_end
    j log_tty_result
tty_write_full:
    la a1, tty_full_msg
    la t0, tty_full_end
log_tty_result:
    mv a0, s0
    sub a2, t0, a1
    li a7, 64
    ecall

    la a0, proc_name
    la a1, proc_dir
    la a2, proc_name
    li a3, 0
    li a4, 0
    li a7, 40
    ecall
    li a0, -100
    la a1, serial_path
    li a2, 0
    li a3, 0
    li a7, 56
    ecall
    bltz a0, skip_serial_stats
    mv s3, a0
    la a1, stats_buffer
    li a2, 1024
    li a7, 63
    ecall
    blez a0, skip_serial_stats
    mv a2, a0
    mv a0, s0
    la a1, stats_buffer
    li a7, 64
    ecall
skip_serial_stats:

    mv a0, s0
    la a1, after
    la t0, after_end
    sub a2, t0, a1
    li a7, 64
    ecall
1:
    j 1b

failed:
    neg a0, a0
    li a7, 93
    ecall

.section .rodata
devtmpfs:
    .asciz "devtmpfs"
devdir:
    .asciz "/dev"
kmsg_path:
    .asciz "/dev/kmsg"
tty_path:
    .asciz "/dev/ttyS0"
proc_name:
    .asciz "proc"
proc_dir:
    .asciz "/proc"
serial_path:
    .asciz "/proc/tty/driver/serial"
before:
    .ascii "<0>ARA_KMSG_BEFORE_STDOUT\n"
before_end:
marker:
    .ascii "Ara DSA VCU118 Linux init reached\n"
    .ascii "Linux console, DDR and RVV handoff are alive\n"
    .ascii "ARA_KMSG_INIT_STDOUT\n"
marker_end:
write_full_msg:
    .ascii "<0>ARA_STDOUT_WRITE_FULL\n"
write_full_end:
write_partial_msg:
    .ascii "<0>ARA_STDOUT_WRITE_PARTIAL\n"
write_partial_end:
write_error_msg:
    .ascii "<0>ARA_STDOUT_WRITE_ERROR\n"
write_error_end:
tty_full_msg:
    .ascii "<0>ARA_DIRECT_TTY_WRITE_FULL\n"
tty_full_end:
tty_partial_msg:
    .ascii "<0>ARA_DIRECT_TTY_WRITE_PARTIAL\n"
tty_partial_end:
tty_open_error_msg:
    .ascii "<0>ARA_DIRECT_TTY_OPEN_ERROR\n"
tty_open_error_end:
tty_error_msg:
    .ascii "<0>ARA_DIRECT_TTY_WRITE_ERROR\n"
tty_error_end:
after:
    .ascii "<0>ARA_KMSG_AFTER_STDOUT\n"
after_end:

.section .bss
.balign 8
stats_buffer:
    .skip 1024
