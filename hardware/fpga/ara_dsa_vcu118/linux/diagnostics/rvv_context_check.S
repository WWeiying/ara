# Linux userspace: rebuild vector state after each syscall (caller-clobbered).
.section .text
.globl _start
_start:
    # This freestanding ELF has no C runtime to initialize gp for relaxation.
    .option push
    .option norelax
    la gp, __global_pointer$
    .option pop
#ifdef INIT_PROBE
    li a0, 1
    la a1, start_message
    la a2, start_end
    sub a2, a2, a1
    li a7, 64
    ecall
#endif
    li s0, 128
    la s1, buffer
#ifdef MFPU_PROBE
    # 128 e64 elements produce 32 result words per lane, with a scalar oracle.
    mv t0, s1
    li t1, 128
    li t2, 0x5555555555555555
1:
    sd t2, 0(t0)
    addi t0, t0, 8
    addi t1, t1, -1
    bnez t1, 1b
    vsetvli t0, zero, e64, m8, ta, ma
    li t1, 128
    bne t0, t1, failed
    vid.v v0
    li t2, 3
    vmul.vx v8, v0, t2
    vse64.v v8, (s1)
    mv t0, s1
    li t1, 0
    li t2, 0
    li t3, 128
1:
    ld t4, 0(t0)
    bne t4, t2, failed
    addi t0, t0, 8
    addi t1, t1, 1
    addi t2, t2, 3
    bne t1, t3, 1b
    li a0, 1
    la a1, mfpu_message
    la a2, mfpu_end
    sub a2, a2, a1
    li a7, 64
    ecall
#endif
#ifdef FORK_PROBE
    # First vector use in a child, as in glibc's fork child branch.
    # First parent has no vector history; later parents have dirty VS.
    li s4, 16
fork_again:
    li a0, 17
    li a1, 0
    li a2, 0
    li a3, 0
    li a4, 0
    li a7, 220
    ecall
    bltz a0, failed
    beqz a0, fork_child
    la a1, fork_status
    li a2, 0
    li a3, 0
    li a7, 260
    ecall
    bltz a0, failed
    la t0, fork_status
    lw t1, 0(t0)
    bnez t1, failed
    vsetivli zero, 2, e64, m1, ta, ma
    vmv.v.i v1, -1
    addi s4, s4, -1
    bnez s4, fork_again
    li a0, 1
    la a1, fork_message
    la a2, fork_end
    sub a2, a2, a1
    li a7, 64
    ecall
    j fork_finished
fork_child:
    vsetivli zero, 2, e32, mf2, ta, ma
    vid.v v1
    vsetvli zero, zero, e64, m1, ta, ma
    vmv.v.i v2, 0
    vsetvli zero, zero, e32, mf2, ta, ma
    vrsub.vi v1, v1, 1
    la t0, fork_data
    vse32.v v1, (t0)
    lw t1, 0(t0)
    li t2, 1
    bne t1, t2, fork_bad
    lw t1, 4(t0)
    bnez t1, fork_bad
    li a0, 0
    j fork_exit
fork_bad:
    li a0, 1
fork_exit:
    li a7, 93
    ecall
    j fork_exit
fork_finished:
#endif
#ifdef FAULT_PROBE
    # Reproduce the loader's e64/m1 -> e8/mf2 change and a vector store to
    # a demand-paged mapping. PRETOUCH is the no-store-page-fault control.
    li a0, 0
    li a1, 4096
    li a2, 3
    li a3, 0x22
    li a4, -1
    li a5, 0
    li a7, 222
    ecall
    bltz a0, failed
    mv s3, a0
#ifdef PRETOUCH
    sd zero, 0(s3)
#endif
    sd zero, 0(s1)
    sd zero, 8(s1)
    vsetivli zero, 2, e64, m1, ta, ma
    li t0, 0x3535353535353535
    vmv.v.x v1, t0
    vse64.v v1, (s1)
    vsetivli zero, 8, e8, mf2, ta, ma
    vle8.v v1, (s1)
    vse8.v v1, (s3)
    ld t1, 0(s3)
    bne t1, t0, failed
    li a0, 1
    la a1, fault_message
    la a2, fault_end
    sub a2, a2, a1
    li a7, 64
    ecall
#endif
#ifdef READ_PROBE
    # Activate user vector state, then exercise kernel vector usercopy.
    vsetvli t0, zero, e8, m8, ta, ma
    vmv.v.i v0, 1
    li a0, -100
    la a1, self_path
    li a2, 0
    li a3, 0
    li a7, 56
    ecall
    bltz a0, failed
#ifdef MASK_PROBE
    # ld.so's two e64/m1 mask-generation/merge forms, before the read syscall.
    la t0, mask_data
    li t1, 11
    sd t1, 0(t0)
    li t1, 22
    sd t1, 8(t0)
    li t1, 33
    sd t1, 16(t0)
    li t1, 44
    sd t1, 24(t0)
    vsetivli zero, 2, e64, m1, ta, ma
    vid.v v1
    vadd.vi v2, v1, -1
    addi t2, t0, 32
    vse64.v v2, (t2)
    li a5, 3
    vmul.vx v1, v1, a5
    vmsleu.vi v0, v1, 1
    vle64.v v2, (t0)
    addi t2, t0, 16
    vle64.v v1, (t2)
    vmerge.vvm v1, v2, v1, v0
    addi t2, t0, 48
    vse64.v v1, (t2)
    vsetivli zero, 2, e64, m1, ta, ma
    vid.v v0
    vmul.vx v0, v0, a5
    vle64.v v2, (t0)
    addi t2, t0, 16
    vle64.v v1, (t2)
    vmsleu.vi v0, v0, 1
    vmerge.vvm v1, v2, v1, v0
    addi t2, t0, 64
    vse64.v v1, (t2)
#endif
#ifdef PATH_PROBE
    # Captured ld.so path construction immediately before read: m8 VL=7,0,15.
    # Preserve actual page/beat offsets; scalar pretouch excludes page faults.
    la t0, path_source
    li t1, 4096
    li t2, 0x5a
1:
    sb t2, 0(t0)
    addi t0, t0, 1
    addi t1, t1, -1
    bnez t1, 1b
    la t0, path_destination
    sd zero, 0(t0)
    li a3, 7
    vsetvli a5, a3, e8, m8, ta, ma
    la a2, path_source + 0xfd0
    la a4, path_destination + 0x540
    vle8.v v8, (a2)
    add a2, a2, a5
    sub a3, a3, a5
    vse8.v v8, (a4)
#ifndef NO_ZERO
    vsetvli a5, a3, e8, m8, ta, ma
    la a1, path_source + 0xdb0
    la a2, path_destination + 0x547
    vle8.v v8, (a1)
    vse8.v v8, (a2)
#endif
    li a3, 15
    vsetvli a5, a3, e8, m8, ta, ma
    la a2, path_source + 0xf01
    la a4, path_destination + 0x547
    vle8.v v8, (a2)
    add a2, a2, a5
    sub a3, a3, a5
    vse8.v v8, (a4)
#endif
    la a1, read_buffer
    sd zero, 0(a1)
    # Match the dynamic loader's first observed read in the real Image trace.
    li a2, 832
    li a7, 63
    ecall
    li t0, 832
    bne a0, t0, failed
    la t0, read_buffer
    lw t1, 0(t0)
    li t2, 0x464c457f
    bne t1, t2, failed
#ifdef MASK_PROBE
    la t0, mask_data
    ld t1, 48(t0)
    li t2, 33
    bne t1, t2, failed
    ld t1, 64(t0)
    bne t1, t2, failed
    li t2, 22
    ld t1, 56(t0)
    bne t1, t2, failed
    ld t1, 72(t0)
    bne t1, t2, failed
#endif
#ifdef PATH_PROBE
    la t0, path_destination + 0x540
    li t1, 22
    li t2, 0x5a
1:
    lbu t3, 0(t0)
    bne t2, t3, failed
    addi t0, t0, 1
    addi t1, t1, -1
    bnez t1, 1b
#endif
    li a0, 1
    la a1, read_message
    la a2, read_end
    sub a2, a2, a1
    li a7, 64
    ecall
#endif
iteration:
    li a7, 172
    ecall
    blez a0, failed
    vsetvli t0, zero, e8, m8, ta, ma
    li t1, 1024
    bne t0, t1, failed
    vid.v v0
    li t0, 0x5a
    vxor.vx v8, v0, t0
    vadd.vi v16, v8, 1
    vmv.v.v v24, v16
    csrr t0, vl
    li t1, 1024
    bne t0, t1, failed
    csrr t0, vtype
    li t1, 0xc3
    bne t0, t1, failed
    vse8.v v24, (s1)
    mv t0, s1
    li t1, 0
    li t4, 1024
check_byte:
    lbu t2, 0(t0)
    xori t3, t1, 0x5a
    addi t3, t3, 1
    andi t3, t3, 255
    bne t2, t3, failed
    addi t0, t0, 1
    addi t1, t1, 1
    bne t1, t4, check_byte
    addi s0, s0, -1
    bnez s0, iteration
    la a1, pass_message
    la a2, pass_end
    sub a2, a2, a1
    li s2, 0
    j finish
failed:
    la a1, fail_message
    la a2, fail_end
    sub a2, a2, a1
    li s2, 1
finish:
    li a0, 1
    li a7, 64
    ecall
#ifdef INIT_PROBE
    # PID 1 must not exit; the console marker is the test result.
    j .
#endif
    mv a0, s2
    li a7, 93
    ecall
    j .
.section .rodata
#ifdef MFPU_PROBE
mfpu_message:
    .ascii "ARA_MFPU_QUEUE_OK elements=128\n"
mfpu_end:
#endif
#ifdef FORK_PROBE
fork_message:
    .ascii "ARA_RVV_FORK_OK children=16\n"
fork_end:
#endif
start_message:
    .ascii "ARA_RVV_CONTEXT_INIT_START\n"
start_end:
self_path:
    .asciz "/init"
read_message:
    .ascii "ARA_RVV_KERNEL_READ_OK\n"
read_end:
fault_message:
    .ascii "ARA_RVV_FAULT_STORE_OK\n"
fault_end:
pass_message:
    .ascii "ARA_RVV_CONTEXT_OK iterations=128 bytes_checked=131072\n"
pass_end:
fail_message:
    .ascii "ARA_RVV_CONTEXT_FAIL\n"
fail_end:
.section .bss
#ifdef FORK_PROBE
.balign 16
fork_status:
    .skip 16
fork_data:
    .skip 16
#endif
.balign 64
buffer:
    .skip 1024
#ifdef READ_PROBE
.balign 4096
read_buffer:
    .skip 4096
#endif
#ifdef PATH_PROBE
.balign 4096
path_source:
    .skip 4096
path_destination:
    .skip 4096
#endif
#ifdef MASK_PROBE
.balign 64
mask_data:
    .skip 128
#endif
