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
    la a1, kmsg
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

    # Activating VS makes Linux discard vector state at the following ecalls.
    .option push
    .option arch, +v
    vsetivli a0, 2, e64, m1, ta, ma
    .option pop
    li a0, 0
    li a7, 214
first_vector_ecall:
    ecall
    mv a0, s0
    la a1, after_brk
    la t0, after_brk_end
    sub a2, t0, a1
    li a7, 64
second_vector_ecall:
    ecall
    mv a0, s0
    la a1, after_write
    la t0, after_write_end
    sub a2, t0, a1
    li a7, 64
third_vector_ecall:
    ecall
1:
    j 1b
failed:
    li a0, 127
    li a7, 93
    ecall

.section .rodata
devtmpfs: .asciz "devtmpfs"
devdir: .asciz "/dev"
kmsg: .asciz "/dev/kmsg"
before: .ascii "<0>ARA_VEC_ECALL_BEFORE\n"
before_end:
after_brk: .ascii "<0>ARA_VEC_ECALL_AFTER_BRK\n"
after_brk_end:
after_write: .ascii "<0>ARA_VEC_ECALL_AFTER_WRITE\n"
after_write_end:
